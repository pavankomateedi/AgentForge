# Clinical Co-Pilot — AgentForge Week 1

> AI agent for primary care physicians. The Co-Pilot fits in the 60-90 second
> gap between exam rooms: clinician opens a patient, asks **"brief me"** or a
> follow-up, the agent retrieves structured records, verifies every claim
> against a real source, and returns a concise grounded briefing.
>
> **Architectural target** (`ARCHITECTURE.md`): integrated into a fork of
> [OpenEMR](https://github.com/openemr/openemr), using OpenEMR's OAuth2/SMART-on-FHIR
> for auth and FHIR R4 as the only data path.
>
> **What's actually deployed in this v0**: standalone FastAPI agent service
> + React UI, mock FHIR with two synthetic patients, in-app auth (bcrypt +
> sessions + TOTP MFA + audit + password reset) standing in for OpenEMR
> OAuth2 until OpenEMR is wired up. The architecture document continues to
> specify OpenEMR OAuth2 as the production target; the in-app auth is a
> labeled v0 stand-in.

**Deployed:** _(your Railway public URL)_
**Demo video:** _(link)_
**Documents:** [AUDIT.md](./AUDIT.md) · [USERS.md](./USERS.md) · [ARCHITECTURE.md](./ARCHITECTURE.md)

---

## Stack

| Layer | What's actually running |
|---|---|
| Agent service | Python 3.11+ · FastAPI · uvicorn |
| Orchestration | Plain async Python pipeline shaped as LangGraph nodes (Plan → Retrieve → Reason → Verify → Respond). Lifts to LangGraph as a follow-up. |
| LLM | **Claude Opus 4.7** via Anthropic SDK, with adaptive thinking + prompt caching on system prompt + tools schema |
| Verifier | Pure Python — deterministic source-id matching against the per-turn retrieval bundle |
| Tools | 4 read-only FHIR tools: patient summary, problem list, medication list, recent labs. Mock FHIR client returns synthetic data for two demo patients. |
| Auth (v0 stand-in) | bcrypt password hashing · signed cookie sessions (Starlette `SessionMiddleware`) · 5-min idle / 8-hr absolute timeout · 5-fail / 15-min lockout · TOTP MFA (`pyotp`) · password reset via Resend (with dev fallback) · append-only audit log |
| Data | SQLite (users, audit_log, password_reset_tokens) |
| UI | React 19 + Vite + TypeScript, served as a static bundle from FastAPI |
| Email | Resend (optional — falls back to logging the reset link to console) |
| Deploy | Railway (Nixpacks builder, `Procfile` + `railway.json`) |

The architecture diagram and full design rationale are in [ARCHITECTURE.md](./ARCHITECTURE.md).

---

## Quick start (local)

### Prerequisites

- **Python 3.11+** (tested on 3.12 and 3.14)
- **Node 18+** (only needed if you'll modify the UI; the production bundle is checked into `agent/static/`)
- An **Anthropic API key** (`sk-ant-...`)
- `git`. `make` is optional — every Make target is a one-line command you can run directly.

### Steps

```bash
# 1. Clone
git clone https://github.com/pavankomateedi/AgentForge.git
cd AgentForge

# 2. (Optional) virtual env
python -m venv .venv
source .venv/Scripts/activate    # Git Bash on Windows
# source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\Activate.ps1     # PowerShell

# 3. Install Python deps
pip install -e ".[dev]"
# Or: pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY and SESSION_SECRET.
# Generate SESSION_SECRET with:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"

# 5. Seed a demo user (one-time)
python -m agent.cli create-user dr.chen dr.chen@example.com
# Prompts for password (8+ chars). Alternatively, set DEFAULT_USER_*
# env vars so the app self-bootstraps on first start.

# 6. Run the server
python -m uvicorn agent.main:app --host 127.0.0.1 --port 8000
# Or: make dev

# 7. Open in browser
open http://127.0.0.1:8000     # or visit manually
```

### What you'll see on first login

1. **Sign in** screen — username `dr.chen`, the password you just set.
2. **MFA enrollment** — a QR code appears. Scan it with **Google Authenticator** / **1Password** / **Authy**, then enter the 6-digit code to complete enrollment. (Subsequent logins skip enrollment and show only the 6-digit challenge.)
3. **Main chat UI** — pick a patient (Margaret Hayes / James Whitaker), click **Brief me**, see a verified briefing with a green ✓ badge.

### Required environment variables

`.env.example` has the full list with comments. Critical ones:

| Variable | Purpose | Required? |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API access | ✅ |
| `SESSION_SECRET` | Signs the session cookie. Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Must be ≥16 chars. | ✅ |
| `ANTHROPIC_MODEL` | Defaults to `claude-opus-4-7` | — |
| `DATABASE_URL` | Defaults to `sqlite:///./agentforge.db` | — |
| `SESSION_HTTPS_ONLY` | `true` in prod, `false` for local http | — |
| `DEFAULT_USER_USERNAME`, `_EMAIL`, `_PASSWORD` | If all three are set AND DB is empty, a user is bootstrapped on startup. Useful for Railway's ephemeral filesystem. | — |
| `RESEND_API_KEY`, `RESEND_FROM` | Real password-reset email delivery. Without them, the reset link is logged to the server console (dev fallback). | — |
| `APP_BASE_URL` | Used in password-reset link emails. Defaults to `http://127.0.0.1:8000`. Set to your public URL in prod. | — |

---

## Admin CLI

The agent ships with an admin CLI for user provisioning. Invoke via `python -m agent.cli <command>`:

```bash
# Create / list / deactivate users
python -m agent.cli create-user dr.chen dr.chen@example.com
python -m agent.cli list-users
python -m agent.cli deactivate dr.chen

# Reset password (interactive prompt for new value)
python -m agent.cli reset-password dr.chen

# Clear MFA enrollment (forces re-enroll on next login)
python -m agent.cli reset-mfa dr.chen

# Clear failed-attempt lockout
python -m agent.cli unlock dr.chen

# Send a test email (verifies your Resend setup)
python -m agent.cli send-test-email someone@example.com
```

There is no public signup endpoint — accounts are admin-provisioned. This is by design (per [ARCHITECTURE.md §10](./ARCHITECTURE.md): "open signup for a 'physician' persona without credential verification undercuts the HIPAA premise").

---

## Repository layout

```
.
├── README.md                — this file
├── AUDIT.md                 — OpenEMR audit findings (drives architectural choices)
├── USERS.md                 — target user, workflow, 5 enumerated use cases
├── ARCHITECTURE.md          — AI integration design, trust boundaries, cost projections
├── pyproject.toml           — Python package config + pytest config
├── requirements.txt         — runtime + dev deps (mirror of pyproject)
├── Makefile                 — dev, test, eval, smoke targets
├── Procfile, railway.json   — Railway deploy config
├── .env.example             — env var template (copy to .env)
│
├── agent/                   — FastAPI agent service
│   ├── main.py              — app, routes, SessionMiddleware, static UI mount
│   ├── orchestrator.py      — Plan → Retrieve → Reason → Verify → Respond pipeline
│   ├── auth.py              — login, MFA, password reset, sessions, lockout
│   ├── audit.py             — append-only audit log
│   ├── tools.py             — 4 mock FHIR tools + patient subject locking
│   ├── verifier.py          — deterministic source-id matcher
│   ├── prompts.py           — Plan / Reason system prompts
│   ├── demo_data.py         — synthetic patients (NO real PHI)
│   ├── email.py             — Resend integration with dev fallback
│   ├── config.py            — env-var loading
│   ├── db.py                — SQLite init / connection helpers
│   ├── cli.py               — admin commands
│   └── static/              — built React bundle (committed; rebuilt by `cd ui && npm run build`)
│
├── ui/                      — React + Vite + TypeScript source
│   ├── src/
│   │   ├── App.tsx          — auth state machine, routes between Login / MFA / Reset / main
│   │   ├── components/      — Login, Header, ChatForm, ResponsePanel, MfaSetup, MfaChallenge,
│   │   │                       PasswordResetRequest, PasswordResetConfirm, SourceText
│   │   ├── api.ts           — typed fetch helpers; cookie auth via credentials: 'include'
│   │   └── types.ts         — schema mirroring agent/main.py
│   └── vite.config.ts       — outDir: ../agent/static; dev proxy /chat /health -> :8000
│
└── eval/                    — Eval suite (44 tests)
    ├── README.md            — what each layer guarantees
    ├── conftest.py          — fixtures (test DB, TestClient, seed_user, authed_client, stubs)
    ├── test_verifier.py     — verifier unit tests
    ├── test_tools.py        — tool dispatch + patient subject locking
    ├── test_auth_login.py   — login + lockout
    ├── test_auth_mfa.py     — TOTP enroll + challenge
    ├── test_auth_password_reset.py — reset request, confirm, expiry, single-use
    ├── test_chat_protected.py — /chat auth gating + audit emission
    └── live/                — LLM-calling tests (skip-by-default, run with `pytest -m live`)
        ├── test_agent_property.py   — every response verified, no fabricated ids, latency
        ├── test_agent_adversarial.py— prompt injection, cross-patient leakage, fabrication
        └── test_agent_golden.py     — UC-1 / UC-3 / UC-4 expected-fact assertions
```

---

## Eval suite

Three layers. Default `pytest` runs unit + integration only — fast, free, deterministic. Live LLM tests run on demand.

```bash
make eval                    # unit + integration (~25s, $0)
make eval-live               # adds LLM probes (~30-60s, a few cents)
```

| Layer | What |
|---|---|
| Unit | Verifier source-id matching · tool dispatcher · patient subject locking |
| Integration | Login + lockout · MFA enroll/challenge · password reset (request, confirm, expiry, single-use, no enumeration) · `/chat` auth gating · audit emission |
| Live (LLM) | Property-based (every response verified, no fabricated ids, plan node stays locked) · adversarial (prompt injection, cross-patient leakage) · golden cases (UC-1 mentions T2DM/A1c, UC-3 lists meds, UC-4 lists conditions, sparse data acknowledges missing) |

Full layer descriptions in [`eval/README.md`](./eval/README.md).

---

## Architecture trace

Every architectural claim has a regression test. The most load-bearing ones:

| Claim | Where it lives | What proves it |
|---|---|---|
| Verifier rejects fabricated source ids | `agent/verifier.py` | `eval/test_verifier.py` |
| Patient subject locking is structural (not LLM-mediated) | `agent/tools.py` `execute_tool` | `eval/test_tools.py` + `eval/live/test_agent_adversarial.py` |
| 5 failed login attempts → 15-min account lockout | `agent/auth.py` `_record_failed_login` | `eval/test_auth_login.py` |
| MFA is mandatory before any access to `/chat` | `agent/auth.py` `login` + `mfa_*` | `eval/test_auth_mfa.py` + `eval/test_chat_protected.py` |
| Password-reset tokens are single-use, expire in 1 hour, leak nothing about whether an account exists | `agent/auth.py` `password_reset_*` | `eval/test_auth_password_reset.py` |
| Every authenticated request is audit-logged with user_id | `agent/audit.py` | `eval/test_auth_login.py`, `eval/test_chat_protected.py` |

---

## Railway deployment

```bash
# 1. Push to GitHub
git push origin main

# 2. In Railway dashboard:
#    - "New Project" -> "Deploy from GitHub repo" -> pick this repo
#    - The build uses Nixpacks (no Dockerfile needed)
#    - railway.json + Procfile already wire the start command and /health check

# 3. Set env vars in the service's Variables tab:
#    ANTHROPIC_API_KEY, SESSION_SECRET, SESSION_HTTPS_ONLY=true,
#    DEFAULT_USER_USERNAME, _EMAIL, _PASSWORD (so the user gets re-seeded
#    after each redeploy — Railway's filesystem is ephemeral),
#    APP_BASE_URL (the Railway public URL, used in reset email links),
#    RESEND_API_KEY, RESEND_FROM (optional — for real reset emails)

# 4. Settings -> Networking -> "Generate Domain" gives you the public URL
```

For a full step-by-step including the Variables tab and healthcheck verification, see the chat history of this project — the deploy walkthrough is captured there.

### Resend setup (real password-reset emails)

Optional, for production. Without `RESEND_API_KEY` set, password-reset still works but the reset link only appears in the server logs (visible to the operator, not actually emailed).

1. Sign up at [resend.com](https://resend.com) — free tier: **3,000 emails/month, 100/day**, no credit card required.
2. **API Keys** → Create API Key → copy the `re_...` value.
3. Set in Railway (and `.env` locally):
   - `RESEND_API_KEY` = the key from above
   - `RESEND_FROM` = `onboarding@resend.dev` for testing, or an address at a domain you've verified in Resend
4. Verify it works:
   ```bash
   python -m agent.cli send-test-email your-email@example.com
   ```

---

## Security notes

- **No real PHI.** All demo data is synthetic. Don't load real patient data into this v0.
- **BAA assumption** for Anthropic. Treat as if a Business Associate Agreement is in place — production deployment requires it in writing.
- **The auth subsystem here is a v0 stand-in** for OpenEMR's OAuth2/SMART-on-FHIR. Real HIPAA still needs SOC 2 Type II, MFA-channel verification, audit dashboard, breach-notification workflows, etc., as documented in [ARCHITECTURE.md §10](./ARCHITECTURE.md).
- **`.env` is gitignored.** `.env.example` is checked in — keep it free of real secrets.
- **Session cookie** is HTTP-only, signed, `SameSite=Lax`, and `Secure` when `SESSION_HTTPS_ONLY=true`.
- **Password storage** uses bcrypt with per-password salt.
- **Reset tokens** are stored hashed (SHA-256), one-time-use, 1-hour expiry. The plaintext only exists in transit (the email link).

---

## Submission artifacts (graders)

| Requirement | Where |
|---|---|
| Forked repo | This repository |
| Setup guide | This README |
| Audit document | [AUDIT.md](./AUDIT.md) |
| User doc | [USERS.md](./USERS.md) |
| Architecture doc | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| Cost analysis | [ARCHITECTURE.md §8](./ARCHITECTURE.md) |
| Deployed app | Railway public URL at top of this README |
| Demo video | _(link at top)_ |
| Eval dataset | [`eval/`](./eval/) directory; run `make eval` (or `make eval-live` for the LLM tests) |

---

## License

Code added in `agent/`, `ui/`, and `eval/` is released under **GPL v3** to remain compatible with the architectural target of a fork of OpenEMR (which is GPL v3). The repo currently does not vendor OpenEMR; this license remains forward-compatible with that integration.
