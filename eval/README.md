# Eval suite

Three layers, mapping to ARCHITECTURE.md §5:

| Layer | Files | What | Speed | Cost |
|---|---|---|---|---|
| **Unit** | `test_verifier.py`, `test_tools.py` | Pure-Python tests of the deterministic verifier and tool dispatcher (incl. patient subject locking). | <1s | $0 |
| **Integration** | `test_auth_login.py`, `test_auth_mfa.py`, `test_auth_password_reset.py`, `test_chat_protected.py` | FastAPI `TestClient` against a fresh SQLite DB. Covers login + lockout, MFA enroll + challenge, password reset (request, confirm, expiry, single-use), `/chat` auth gating + audit emission. Orchestrator stubbed — no LLM calls. | ~5s | $0 |
| **Live** | `live/test_agent_property.py`, `live/test_agent_adversarial.py` | Hit the real Anthropic API. Property-based assertions (every response cites sources, no unknown ids, latency budget) and adversarial probes (cross-patient prompt injection, unknown patient_id, leakage). | ~30-60s | A few cents per run |

## Run

Default run — unit + integration only, fast and free:

```bash
pytest
```

Live LLM tests, only when ANTHROPIC_API_KEY is set to a real `sk-ant-...`:

```bash
pytest -m live
```

Both:

```bash
pytest -m "not live or live"   # equivalent to no marker filter
```

## What each layer guarantees

**Unit (`test_verifier.py`, `test_tools.py`)**
- Source-id matching catches fabricated citations.
- Patient subject locking rejects any tool call against a different patient_id (structural defense per ARCHITECTURE.md §6.4).
- Mock FHIR returns the expected shape with `source_id` on every record.

**Integration auth (`test_auth_*`)**
- Login: bad password → 401, no user → 401, inactive → 403, 5 failed → 423 lock.
- MFA: pre-auth `/mfa/setup` → 401, post-password it returns a valid TOTP secret + URI, wrong code → 400, right code → full session.
- Password reset: unknown email returns 200 (no enumeration), valid token rotates password and clears lockout, expired/used/invalid token → 400.
- `/chat`: 401 without a session, 401 with a pending-MFA-only session, 200 with a full session, emits `chat_request` audit event.

**Live (`live/test_agent_*`)**
- Every response passes the deterministic verifier with zero unknown source ids.
- Sparse-data briefings do not fabricate (cited subset of retrieved bundle).
- Plan node never emits a tool call with a different patient_id, even under prompt injection.
- No leakage of one patient's data when the user asks about a different one.

## Adding new cases

- **Unit**: pure functions — add new test functions in the appropriate `test_*.py`.
- **Integration**: use `client` (no session), `seed_user` (dr.chen, no MFA), `seed_user_mfa` (dr.chen, MFA enrolled with secret), or `authed_client` (full session post-MFA).
- **Live**: add a `@pytest.mark.live` test. Keep latency-sensitive assertions generous; tighten as you collect data.
