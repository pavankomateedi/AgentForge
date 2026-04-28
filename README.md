# Clinical Co-Pilot — Setup & Deployment

> AgentForge Week 1 submission. AI agent integrated into a fork of [OpenEMR](https://github.com/openemr/openemr) to support primary care physicians in pre-visit chart prep.

**Deployed:** _(replace with your live URL)_
**Demo video:** _(replace with link)_
**Documents:** [`AUDIT.md`](./AUDIT.md) · [`USERS.md`](./USERS.md) · [`ARCHITECTURE.md`](./ARCHITECTURE.md)

---

## Architecture at a Glance

| Layer | Tech |
|---|---|
| EHR host | OpenEMR 7.x (PHP / MariaDB), Dockerized |
| Chat UI | React + Vite, served as an OpenEMR custom module |
| Agent service | Python 3.12 + FastAPI |
| Orchestration | LangGraph (explicit state machine) |
| LLM | Claude Sonnet 4.5 via Anthropic API |
| Observability | Langfuse, self-hosted |
| Reverse proxy / TLS | Caddy |
| Deployment | Oracle Cloud Always-Free ARM VM (Docker Compose) |

Full architecture and rationale: [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## Local Setup

### Prerequisites

- Docker Desktop (macOS / Windows) or Docker Engine + Compose plugin (Linux)
- 8 GB RAM available to Docker
- An Anthropic API key (`ANTHROPIC_API_KEY`)
- `git`, `make`

### Steps

```bash
# 1. Clone
git clone https://github.com/<you>/openemr-copilot.git
cd openemr-copilot

# 2. Configure
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY, OPENEMR_ADMIN_PASS (rotate from default!)

# 3. Bring up the stack
docker compose up -d

# 4. Wait for OpenEMR setup wizard to complete
# Check: docker compose logs -f openemr
# Expect "OpenEMR is now installed and ready to use" before proceeding

# 5. Load demo patient data
make seed-demo-data

# 6. Verify
open https://localhost     # OpenEMR
open https://localhost:3000 # Langfuse
curl http://localhost:8000/health  # Agent service
```

### First login

- URL: `https://localhost`
- User: `admin`
- Password: the value you set in `.env`
- Navigate to: **Modules → Clinical Co-Pilot** to access the agent.

### Demo patients

The `make seed-demo-data` step loads 5 synthetic patients with realistic histories chosen to exercise UC-1 through UC-5 (see [`USERS.md`](./USERS.md)). All data is synthetic; no real PHI is included anywhere in this repo.

---

## Public Deployment (Oracle Cloud Always-Free)

### One-time setup

1. Create an Oracle Cloud Free Tier account → request an Always-Free **ARM (Ampere) VM**: 4 OCPUs, 24 GB RAM, Ubuntu 22.04.
2. Open ports 80, 443 in the VCN security list.
3. Point a domain (or a Cloudflare-proxied subdomain) at the VM's public IP.
4. SSH in:
   ```bash
   ssh ubuntu@<vm-ip>
   sudo apt update && sudo apt install -y docker.io docker-compose-plugin make git
   sudo usermod -aG docker ubuntu
   # log out / log back in
   ```

### Deploy

```bash
git clone https://github.com/<you>/openemr-copilot.git
cd openemr-copilot
cp .env.example .env
# Edit .env — production values, strong admin password, real domain in CADDY_DOMAIN
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Caddy will provision a Let's Encrypt cert automatically on first request.

### Tuesday-MVP fallback: local + Cloudflare Tunnel

If Oracle account approval is pending, expose your local stack temporarily:

```bash
# Install cloudflared per https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
cloudflared tunnel --url https://localhost
```

Submit the resulting `*.trycloudflare.com` URL. Move to Oracle for the Thursday/Sunday submissions.

---

## Repository Layout

```
.
├── AUDIT.md                  # OpenEMR audit findings
├── USERS.md                  # Target user, workflow, use cases
├── ARCHITECTURE.md           # AI integration plan + cost analysis
├── README.md                 # This file
├── docker-compose.yml        # Local stack
├── docker-compose.prod.yml   # Production overrides (Caddy, prod DB volumes)
├── .env.example
├── Makefile                  # seed-demo-data, eval, deploy, clean
│
├── openemr/                  # Forked OpenEMR (submodule or vendored)
│   └── interface/modules/custom_modules/clinical-copilot/
│       └── (React UI lives here; built into OpenEMR module page)
│
├── agent/                    # Python/FastAPI agent service
│   ├── main.py
│   ├── graph/                # LangGraph nodes
│   ├── tools/                # FHIR tools
│   ├── verifier/             # Deterministic verification layer
│   ├── audit/                # Append-only audit log
│   ├── prompts/
│   └── tests/
│
├── ui/                       # React chat UI source
│   ├── src/
│   ├── vite.config.ts
│   └── package.json          # builds into openemr/.../clinical-copilot/dist
│
└── eval/                     # Eval framework
    ├── golden/               # Per-use-case golden cases
    ├── adversarial/          # Prompt injection / leakage probes
    ├── property/             # Latency, attribution, cost properties
    └── runner.py
```

---

## Operating the Agent

### Running the eval suite

```bash
make eval
# or
docker compose exec agent pytest eval/
```

Results are written as Langfuse scores so you can track regressions over time. Eval gates CI: see [`ARCHITECTURE.md` §5](./ARCHITECTURE.md).

### Inspecting a conversation

1. Open Langfuse at `https://<your-domain>:3000` (local: `http://localhost:3000`).
2. Filter traces by user_id or use_case.
3. Each trace shows the full plan → retrieve → reason → verify → respond chain with timing and token cost.

### Inspecting the audit log

```bash
docker compose exec audit-db mariadb -u root -p audit_log \
  -e "SELECT timestamp, user_id, request_id, verification_status FROM agent_audit ORDER BY timestamp DESC LIMIT 50;"
```

The audit log is independent of Langfuse and never fails open.

---

## Security & Compliance Notes

- **No real PHI.** This repo and all deployments use synthetic demo data only. Do not load real patient records.
- **BAA assumption.** Per the case study, we operate as if a Business Associate Agreement is in place with Anthropic. For a real production deployment, that BAA must be signed and verified.
- **PHI traces stay inside the trust boundary.** Self-hosted Langfuse keeps prompts/completions out of any SaaS observability provider. See [`ARCHITECTURE.md` §2.7](./ARCHITECTURE.md).
- **Default credentials.** OpenEMR's setup wizard ships with a default admin password. The setup script in this repo forces a rotation on first run; verify before exposing publicly.
- **Audit findings.** Known limitations and verification items are tracked in [`AUDIT.md` Appendix A](./AUDIT.md#appendix-a--verification-checklist-for-local-deployment).

---

## Submission Artifacts (for graders)

| Requirement | Location |
|---|---|
| Forked repo | This repository |
| Setup guide | This README |
| Audit document | [`AUDIT.md`](./AUDIT.md) |
| User doc | [`USERS.md`](./USERS.md) |
| Architecture doc | [`ARCHITECTURE.md`](./ARCHITECTURE.md) |
| Cost analysis | [`ARCHITECTURE.md` §8](./ARCHITECTURE.md) |
| Deployed app | _link at top of this README_ |
| Demo video | _link at top of this README_ |
| Eval dataset | `eval/` directory |

---

## License

OpenEMR is licensed under GPL v3. This fork preserves that license. Code added in `agent/`, `ui/`, and `eval/` is also released under GPL v3 to remain license-compatible.

---
