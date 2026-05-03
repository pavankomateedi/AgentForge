# Terraform — AWS HIPAA-eligible deployment blueprint

This directory is a **`terraform plan`-able blueprint** for hosting
the Clinical Co-Pilot on AWS using only HIPAA-eligible services. It
is **not** applied — running it would provision real billable AWS
infrastructure and that step is gated on:

1. A signed **Business Associate Agreement** with AWS, Anthropic, and
   Langfuse (or a self-hosted Langfuse inside the same VPC).
2. A designated **Security Officer** and **Privacy Officer**.
3. Completion of the open items in [`../HIPAA_COMPLIANCE.md`](../HIPAA_COMPLIANCE.md).

Until those items are in place, the running deployment stays on
Railway with synthetic demo data only. See
[`../HIPAA_COMPLIANCE.md`](../HIPAA_COMPLIANCE.md) §"Why Railway is
not the production target" for the rationale.

---

## What this blueprint provisions

| Layer | Resource | HIPAA-eligible | Why |
|---|---|---|---|
| Network | VPC, 2× public + 2× private subnets across AZs, IGW, NAT GW | n/a | Private subnets isolate compute and data from the public internet |
| Edge | ALB + ACM cert + AWS WAFv2 (managed rule groups) | ✅ | TLS termination, OWASP Top-10 protection, rate-limiting |
| Compute | ECS Fargate service (no EC2 to patch) | ✅ | Auto-scaling, container immutability, no host SSH attack surface |
| Data | RDS PostgreSQL Multi-AZ (encrypted with customer-managed KMS key) | ✅ | Automated failover, encrypted backups, point-in-time recovery |
| Secrets | AWS Secrets Manager (rotation enabled for DB password) | ✅ | No secrets in env files, no secrets in container images |
| Observability | CloudWatch Logs (encrypted) + alarms on 5xx + auth-failure spikes | ✅ | Audit-trail tamper-evidence + alerting per §164.312(b) |
| Identity | IAM roles for ECS task + RDS rotation Lambda | n/a | Principle of least privilege |

Notably **NOT included** (these have separate code paths):

- **Anthropic API access** — outbound from ECS task to `api.anthropic.com` over a NAT gateway. v1.1 step is to use AWS PrivateLink (currently in private preview with Anthropic) or a self-hosted Bedrock proxy.
- **Langfuse** — currently SaaS. v1 step is either an enterprise BAA or self-hosting in the same VPC (`langfuse/langfuse` Helm chart, ~3 hour migration).
- **Email** — switch from Resend to AWS SES (BAA-eligible) once a sender domain is verified.

---

## Validating the blueprint (does NOT spend money)

```bash
cd terraform
terraform init
terraform validate
terraform plan -var-file=terraform.tfvars.example
```

`terraform plan` against the example tfvars should produce a clean
plan that creates ~30 resources. If it errors, the blueprint is
broken — please fix.

`terraform apply` is intentionally guarded: see "Before applying".

---

## Before applying (DO NOT skip)

1. **Sign the BAAs** listed at the top of this file.
2. **Replace placeholder values** in `terraform.tfvars`:
   - `aws_account_id` — your real 12-digit account
   - `aws_region` — typically `us-east-1` or `us-east-2`
   - `vpc_cidr` — pick a /16 that doesn't overlap existing networks
   - `domain_name` — DNS name for the public ALB (must exist in Route 53)
   - `anthropic_api_key_arn` — ARN of a Secrets Manager secret you've already created out-of-band
3. **Generate the ACM certificate** for `domain_name` and validate it via DNS — the blueprint references this cert by ARN; it does not create it (chicken-and-egg with DNS validation).
4. **Run a real plan** against your account: `terraform plan` (no `-var-file` so it reads `terraform.tfvars`).
5. **Have a second engineer review the plan output.**
6. Only then: `terraform apply`.

After apply, the post-deploy smoke test workflow
(`.github/workflows/smoke-prod.yml`) needs `SMOKE_BASE_URL` set to
the new ALB DNS name in the GitHub repo's `production` environment
secrets.

---

## File layout

| File | Purpose |
|---|---|
| `versions.tf` | Required Terraform + provider versions |
| `variables.tf` | All input variables |
| `network.tf` | VPC, subnets, IGW, NAT GW, route tables, security groups |
| `security.tf` | KMS keys, IAM roles, WAF rules |
| `database.tf` | RDS PostgreSQL Multi-AZ + parameter group + subnet group |
| `compute.tf` | ECR repo, ECS cluster + task def + service, ALB + listener + target group |
| `secrets.tf` | Secrets Manager entries with placeholder values |
| `observability.tf` | CloudWatch log groups + metric filters + alarms |
| `outputs.tf` | Public-facing values (ALB DNS, RDS endpoint, etc.) |
| `terraform.tfvars.example` | Example input file safe to commit |

---

## Cost estimate (us-east-1, on-demand pricing as of writing)

| Resource | Monthly |
|---|---|
| ALB | ~$22 |
| NAT Gateway (2 AZ for HA) | ~$67 |
| ECS Fargate (2× 0.5 vCPU / 1 GB, always-on) | ~$36 |
| RDS db.t4g.medium Multi-AZ + 50 GB gp3 | ~$130 |
| Secrets Manager (5 secrets) | ~$2 |
| CloudWatch Logs (10 GB ingest, 30-day retention) | ~$5 |
| KMS keys (3) | ~$3 |
| WAFv2 (1 web ACL + 4 managed rule groups) | ~$15 |
| Data transfer (50 GB egress) | ~$5 |
| **Subtotal** | **~$285/mo** |

This excludes Anthropic API spend
(see [`../COST_ANALYSIS.md`](../COST_ANALYSIS.md)).
