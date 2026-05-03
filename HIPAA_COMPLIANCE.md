# HIPAA compliance — current posture and v1 gap analysis

This document maps each requirement of the **HIPAA Security Rule
Technical Safeguards (45 CFR §164.312)** to the current implementation
of the Clinical Co-Pilot, and lists the gaps that must close before
the system can lawfully process **real ePHI**.

> ⚠️ **Status: NOT HIPAA-compliant.** The deployment at
> `web-production-6259a.up.railway.app` runs against synthetic demo
> data only. Loading real Protected Health Information is **prohibited**
> until every "Gap" row in the tables below has been resolved and a
> Business Associate Agreement (BAA) is in place with every vendor in
> the data path. This document exists to make those gaps explicit and
> to declare the v1 plan to close them.

---

## Scope

HIPAA's Security Rule has three families of safeguards:

| §164 | Family | This document covers |
|---|---|---|
| .308 | Administrative safeguards | Listed at the bottom; outside the scope of code |
| .310 | Physical safeguards | Inherited from the cloud provider (AWS) |
| **.312** | **Technical safeguards** | **The body of this document** |

Scope of "ePHI" in this system: anything returned by a FHIR call —
patient demographics, problem lists, medications, lab results, and
the LLM-generated briefing that combines them. The session cookie
itself is _not_ ePHI; the chat transcript persisted in audit logs and
Langfuse _is_.

---

## §164.312(a) Access Control

> "Implement technical policies and procedures for electronic
> information systems that maintain electronic protected health
> information to allow access only to those persons or software
> programs that have been granted access rights …"

### (a)(2)(i) Unique User Identification — **Required**

| | |
|---|---|
| **Requirement** | Each user gets a unique identifier; no shared accounts. |
| **Current impl** | `users` table: `id` PK + unique `username`. Sessions store `user_id`; every audit row carries `user_id`; every `/chat` call resolves the calling user via `auth.require_authenticated`. No public signup endpoint — accounts are admin-provisioned via `python -m agent.cli create-user`. |
| **Evidence** | `agent/auth.py` `create_user`, `require_authenticated`; `agent/db.py` schema; `eval/test_auth_login.py` |
| **Gap** | None for v0 stand-in. v1 replaces this with OpenEMR's identity (SMART-on-FHIR `sub` claim) — same property, different source of truth. |

### (a)(2)(ii) Emergency Access Procedure — **Required**

| | |
|---|---|
| **Requirement** | Documented "break-glass" path for an authorized clinician to read ePHI when the normal access mechanism is unavailable. |
| **Current impl** | None. The CLI can `unlock` a locked account but there is no audited break-glass path. |
| **Gap** | **Open.** v1: add an `EMERGENCY_ACCESS` audit event + a CLI command `python -m agent.cli emergency-access <user> --reason <text>` that grants a 30-minute elevated session and is reviewed daily by the Security Officer. Document the policy in an Incident Response Plan. |

### (a)(2)(iii) Automatic Logoff — **Addressable**

| | |
|---|---|
| **Requirement** | Sessions terminate after a period of inactivity. |
| **Current impl** | Two-layer timeout enforced in `agent/auth.py`: **5-minute idle timeout** (rolling) + **8-hour absolute timeout**. Both are computed server-side from session-stored timestamps; the cookie itself does not control expiry. |
| **Evidence** | `agent/auth.py` `_check_session_freshness`, `_set_session`; covered by `eval/test_auth_login.py`. |
| **Gap** | None. Clinic environments may want to lower the idle timeout to 2 minutes per local policy; this is a one-line config change. |

### (a)(2)(iv) Encryption and Decryption — **Addressable**

> Covered by §164.312(e)(2)(ii) for in-transit and below for at-rest.

| | |
|---|---|
| **Requirement** | ePHI at rest is encrypted with a vetted algorithm. |
| **Current impl (v0)** | SQLite file on Railway's ephemeral filesystem. **Not encrypted at rest.** Acceptable only because the file holds zero real ePHI (synthetic demo data only). |
| **Gap** | **Open.** v1 (per `terraform/`): RDS PostgreSQL with AWS KMS-managed encryption at rest (AES-256, FIPS 140-2 validated), automated daily backups also encrypted with KMS, snapshots in a separate KMS key for cross-account restore. |

---

## §164.312(b) Audit Controls — **Required**

> "Implement hardware, software, and/or procedural mechanisms that
> record and examine activity in information systems that contain or
> use electronic protected health information."

| | |
|---|---|
| **Requirement** | Tamper-evident, complete, queryable record of who-did-what-when. |
| **Current impl** | Append-only `audit_log` table; every login, MFA event, password reset, `/chat` call (success/refusal), patient assignment change, and budget breach is recorded with `(timestamp, user_id, event, ip_address, details_json)`. Every `/chat` request emits exactly one row. Refusals (unassigned patient, budget exceeded) emit dedicated event types. The 200K/day token budget gate emits `BUDGET_EXCEEDED` and returns 429. |
| **Evidence** | `agent/audit.py`; `eval/test_chat_protected.py` `test_chat_emits_audit_event`. |
| **Gaps to close for v1** | (1) Audit log lives in the same DB as the data it audits — needs a separate write-only sink (CloudWatch Logs or a dedicated DB role). (2) No immutability guarantee — needs append-only enforcement at the DB layer (RDS row-level triggers preventing UPDATE/DELETE on audit_log). (3) No alerting — needs a CloudWatch alarm on patterns like "5 LOGIN_FAILED in 60s for one user" or "any EMERGENCY_ACCESS event." (4) No retention policy — HIPAA recommends **6 years**; needs a documented retention rule + automated archival to S3 with Object Lock. |

---

## §164.312(c) Integrity

### (c)(1) Standard

> "Implement policies and procedures to protect electronic protected
> health information from improper alteration or destruction."

| | |
|---|---|
| **Current impl** | (a) Tools are **read-only** (`get_patient_summary`, `get_problem_list`, `get_medication_list`, `get_recent_labs`) — there is no write path to ePHI from the agent at all. (b) The verifier rejects any LLM-generated source-id that wasn't returned by an actual tool call, so the system cannot fabricate records into the response. (c) Numeric value-tolerance check rejects responses whose claimed values don't match the source. |
| **Evidence** | `agent/tools.py`; `agent/verifier.py`; `eval/test_verifier.py`. |
| **Gap** | None at the agent layer. Write paths (charting, prescribing) are explicitly out-of-scope per `ARCHITECTURE.md` §10. |

### (c)(2) Mechanism to Authenticate ePHI — **Addressable**

| | |
|---|---|
| **Requirement** | Detect unauthorized alteration of ePHI in storage and transit. |
| **Current impl** | TLS in transit (Railway terminates TLS 1.2/1.3 at its edge). At rest: not addressed in v0 (no real ePHI). |
| **Gap** | **Open.** v1: RDS storage uses checksummed pages; backups use SHA-256 manifests; CloudTrail logs every KMS key use; periodic restore-and-compare drill. |

---

## §164.312(d) Person or Entity Authentication — **Required**

> "Implement procedures to verify that a person or entity seeking
> access to electronic protected health information is the one
> claimed."

| | |
|---|---|
| **Current impl** | Two factors: (1) **password**, bcrypt-hashed with per-password salt (cost factor 12), 8-character minimum; (2) **TOTP** via `pyotp`, mandatory enrollment on first login, mandatory challenge on every subsequent login before any `/chat` access. **5 failed attempts in 15 minutes triggers a 15-minute lockout** with `LOGIN_FAILED_LOCKED` audit event. Reset tokens are SHA-256 hashed at rest, single-use, 1-hour expiry, and the response is **identical for unknown vs known emails** (no account enumeration). |
| **Evidence** | `agent/auth.py` `login`, `mfa_challenge`, `_record_failed_login`, `password_reset_*`; `eval/test_auth_login.py`, `eval/test_auth_mfa.py`, `eval/test_auth_password_reset.py`. |
| **Gap (v0 stand-in)** | The auth subsystem itself is a v0 stand-in. v1 delegates auth to OpenEMR's OAuth2 / SMART-on-FHIR + the clinic's existing identity provider (typically Okta or Azure AD with phishing-resistant MFA — WebAuthn / FIDO2). At that point the `users` table goes away and the agent only sees signed JWTs. |
| **Documented carve-out (v0 only)** | The `bypass_mfa: true` flag in `EXTRA_USERS_JSON` opts a single account out of the MFA challenge — password is enough. Used **only on synthetic-data demo deployments** for the operator's daily-use account; password-only would NOT satisfy §164.312(d) against real ePHI. Every bypass login emits a `LOGIN_MFA_BYPASSED` audit row distinct from `MFA_VERIFIED`, so the carve-out is queryable from the trail rather than silent. The flag is admin-set only (no HTTP path can flip it), can be reconciled off via the same env var on the next cold start, and the bypass only short-circuits MFA — password verification + the 5/15 lockout still apply. Tested by `eval/test_bypass_mfa.py` (11 cases). **Must be removed before this deployment is allowed to process real PHI.** |

---

## §164.312(e) Transmission Security

### (e)(1) Standard + (e)(2)(i) Integrity Controls + (e)(2)(ii) Encryption

> "Implement technical security measures to guard against unauthorized
> access to electronic protected health information that is being
> transmitted over an electronic communications network."

| | |
|---|---|
| **Current impl** | All public traffic is HTTPS — Railway terminates TLS 1.2+ at the edge. Session cookie is `HttpOnly`, signed (Starlette `SessionMiddleware` w/ `itsdangerous`), `SameSite=Lax`, and `Secure` when `SESSION_HTTPS_ONLY=true` (set in production). CORS is not enabled — same-origin only — so the static UI bundle served by FastAPI is the only legal client. |
| **Evidence** | `agent/main.py` `SessionMiddleware` config; `Procfile` + `railway.json`. |
| **Gaps to close for v1** | (1) **HSTS header** missing — add `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`. (2) **CSP header** missing — add a strict policy that only allows scripts from `'self'` and Langfuse domain. (3) **Anthropic API call** goes out over TLS but currently transits the public internet from Railway → api.anthropic.com — v1 uses AWS PrivateLink or VPC peering. (4) **Inter-service TLS** (RDS, between EC2 and Anthropic via NAT) all needs to be required, not optional. |

---

## Summary scorecard (v0 → v1)

| Safeguard | v0 status | v1 plan |
|---|---|---|
| (a)(2)(i) Unique user IDs | ✅ Met (in-app users table) | Replace with OpenEMR SMART-on-FHIR identity |
| (a)(2)(ii) Emergency access | ❌ Open | Add audited break-glass CLI + IRP |
| (a)(2)(iii) Automatic logoff | ✅ Met (5-min idle / 8-hr absolute) | No change |
| (a)(2)(iv) Encryption (at rest) | ❌ Synthetic data only | RDS + KMS (AES-256) |
| (b) Audit controls | ⚠️ Partial — no immutability, no alerting, no retention | Separate CloudWatch sink + S3 Object Lock + alarms |
| (c)(1) Integrity | ✅ Met (read-only tools + verifier) | No change |
| (c)(2) Authenticate ePHI | ❌ Synthetic data only | RDS checksums + CloudTrail + restore drills |
| (d) Person authentication | ✅ Met (bcrypt + TOTP MFA + lockout) | Delegate to clinic IdP via OAuth2 |
| (e) Transmission security | ⚠️ Partial — TLS only, no HSTS/CSP | Add headers + PrivateLink + WAF |

---

## What's NOT in scope for the technical work

The Security Rule has parallel administrative requirements (§164.308)
that are organizational, not code, and must be in place before code
can lawfully process ePHI:

| Item | Status | Notes |
|---|---|---|
| **Designated Security Officer** | ❌ TBD | Required by §164.308(a)(2). |
| **Designated Privacy Officer** | ❌ TBD | Required by §164.530(a)(1). |
| **BAA with Anthropic** | ❌ Required | Anthropic offers BAAs on the Enterprise tier; signing typically takes 2–6 weeks. **Cannot send real ePHI to the API until signed.** |
| **BAA with AWS** | ❌ Required | AWS BAA covers the HIPAA-eligible service list (RDS, EC2, KMS, etc.). |
| **BAA with Langfuse** | ❌ Required (or self-host) | Langfuse Cloud offers BAAs on enterprise plans; alternative is to self-host Langfuse in the same VPC. |
| **BAA with Resend** | ❌ Required (or stop using for ePHI-related emails) | Reset emails currently contain only a token + base URL — no ePHI — so this is borderline. v1: switch to AWS SES with BAA. |
| **Risk Assessment** | ❌ TBD | Required by §164.308(a)(1)(ii)(A). Typically $15K–$40K consulting engagement. |
| **SOC 2 Type II audit** | ❌ TBD | Not strictly required by HIPAA but expected by hospital procurement. 9–12 month engagement, $30K–$60K. |
| **Penetration test** | ❌ TBD | $15K–$30K. Should run annually after v1. |
| **Workforce training** | ❌ TBD | Required by §164.308(a)(5). Typically a 1-hour online course every 12 months. |
| **Patient consent flow** | ❌ TBD | Out of scope for an internal clinician tool, but relevant if any patient-facing surface is added. |
| **Breach Notification Plan** | ❌ TBD | Required by §164.404. Must define who notifies HHS within 60 days of discovery. |

---

## Why Railway is not the production target

Railway is excellent for v0 demonstrations but is **not HIPAA-eligible**:

1. Railway does not sign Business Associate Agreements (as of this writing).
2. Railway's storage layer does not offer customer-managed encryption keys.
3. Railway's network does not support PrivateLink to Anthropic / AWS services.
4. Railway's audit log retention is 30 days; HIPAA recommends 6 years.

The deployment plan in `terraform/` migrates the workload to AWS
HIPAA-eligible services (RDS, EC2, ALB, KMS, Secrets Manager,
CloudWatch, VPC, WAF) when the BAAs are in place. The Terraform
skeleton is `terraform plan`-able today with placeholder variables
and is intentionally **not yet applied**.

---

## How this document is maintained

- Every PR that touches `agent/auth.py`, `agent/audit.py`, or anything in `terraform/` must update the relevant row in this file.
- Reviewed quarterly by the (future) Security Officer.
- The "v0 status" column is the source of truth for what the running deployment can and cannot do; if you change this column you are also changing what the deployment is allowed to handle.
