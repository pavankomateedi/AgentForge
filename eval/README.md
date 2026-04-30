# Eval suite

Four layers, mapping to ARCHITECTURE.md §5:

| Layer | Files | What | Speed | Cost |
|---|---|---|---|---|
| **Unit** | `test_verifier.py`, `test_tools.py` | Pure-Python tests of the deterministic verifier and tool dispatcher (incl. patient subject locking). | <1s | $0 |
| **Integration** | `test_auth_login.py`, `test_auth_mfa.py`, `test_auth_password_reset.py`, `test_chat_protected.py` | FastAPI `TestClient` against a fresh SQLite DB. Covers login + lockout, MFA enroll + challenge, password reset (request, confirm, expiry, single-use), `/chat` auth gating + audit emission. Orchestrator stubbed — no LLM calls. | ~5s | $0 |
| **Replay** | `replay/test_replay.py` + `replay/cassettes/*.json` | Replay pre-recorded LLM responses through the orchestrator. Catches verifier / orchestrator regressions on real-shaped LLM outputs without paying for API tokens. Cassettes refresh via `python -m eval.replay.record`. | <1s | $0 |
| **Live** | `live/test_agent_property.py`, `live/test_agent_adversarial.py`, `live/test_agent_golden.py` | Hit the real Anthropic API. Property-based assertions, adversarial probes, golden expected-fact cases. | ~30-90s | A few cents per run |

## Run

Default run — unit + integration + replay, fast and free:

```bash
pytest
```

Live LLM tests, only when ANTHROPIC_API_KEY is set to a real `sk-ant-...`:

```bash
pytest -m live
```

(Re-)record replay cassettes against the live API:

```bash
python -m eval.replay.record                   # all scenarios
python -m eval.replay.record uc1_brief_demo_001  # one scenario
python -m eval.replay.record --list             # list available
```

Cost: ~$0.02-$0.04 per scenario. Refresh when scenarios are added or when a
replay test starts failing because the LLM output legitimately changed
(e.g. you tuned a system prompt).

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

**Replay (`replay/test_replay.py`)**
- For each recorded scenario, the orchestrator runs against the cassette's recorded LLM responses and the verifier + trace properties match what was captured at record time.
- Pinned: `verified` flag, presence/absence of unknown ids, cited-id count, retrieved-id count, plan-node tool selection, refused flag, response non-emptiness.
- Catches: verifier bugs, orchestrator wiring drift, audit emission regressions, citation-extraction drift — all on real-shaped LLM outputs.
- Doesn't catch: actual LLM behavior changes (those are the live layer's job).

**Live (`live/test_agent_*`)**
- Every response passes the deterministic verifier with zero unknown source ids.
- Sparse-data briefings do not fabricate (cited subset of retrieved bundle).
- Plan node never emits a tool call with a different patient_id, even under prompt injection.
- No leakage of one patient's data when the user asks about a different one.
- Golden expected-fact cases for UC-1, UC-3 (medications), UC-4 (active conditions), and the sparse-data briefing.

## Adding new cases

- **Unit**: pure functions — add new test functions in the appropriate `test_*.py`.
- **Integration**: use `client` (no session), `seed_user` (dr.chen, no MFA), `seed_user_mfa` (dr.chen, MFA enrolled with secret), or `authed_client` (full session post-MFA).
- **Replay**: add an entry to `SCENARIOS` in `replay/record.py`, run `python -m eval.replay.record <new_scenario>`, commit the cassette JSON. The parametrized test in `replay/test_replay.py` picks it up automatically.
- **Live**: add a `@pytest.mark.live` test. Keep latency-sensitive assertions generous; tighten as you collect data.
