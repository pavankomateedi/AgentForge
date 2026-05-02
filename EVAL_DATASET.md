# Eval Dataset — Clinical Co-Pilot

This document describes the test suite that gates every change. It maps each test layer to the property it guarantees and lists the case counts at the time of submission.

> Source code: [`eval/`](./eval/) · Run all: `pytest` · Run live-API only: `pytest -m live`

## Layers and what each one guarantees

| Layer | Files | What it tests | Speed | Cost |
|---|---|---|---|---|
| **Unit** | `test_verifier.py`, `test_tools.py`, `test_rules.py`, `test_budget.py` | Pure-Python tests of the deterministic verifier (source-id + value-tolerance), tool dispatcher (incl. patient subject locking), clinical rule engine (thresholds, dosage, interactions, cross-rules), and the per-user daily token budget module. | < 1 s | $0 |
| **Integration** | `test_auth_login.py`, `test_auth_mfa.py`, `test_auth_password_reset.py`, `test_chat_protected.py`, `test_rbac.py` | FastAPI `TestClient` against a fresh SQLite DB. Covers login + lockout, MFA enroll + challenge, password reset (request, confirm, expiry, single-use), `/chat` auth gating + audit emission, role-based tool whitelisting, patient-assignment refusal, resident watermark. Orchestrator stubbed — no LLM calls. | ~5 s | $0 |
| **Golden** | `test_golden_cases.py` | 16 hand-curated synthetic (bundle, response_text) pairs across UC-1 through UC-5 with pinned expected verifier outcomes (verified / unknown_ids / value_mismatch ids) and rule findings. Deterministic; no LLM. | < 1 s | $0 |
| **Adversarial** | `test_adversarial.py` | 17 cases. 12 patient-injection variants (instruction override, role impersonation, SQL/path payloads, case/whitespace tricks, zero-width-space, URL/numeric attempts) — each must raise `PatientSubjectMismatch` in the dispatcher BEFORE FHIR is touched. Plus mixed-batch tool dispatch, role whitelist immutability, unknown-role zero-tools fallback. | < 1 s | $0 |
| **Tampering** | `test_synthetic_tampering.py` | 10 cases. Post-generation bundle mutation (caught), LLM-side hallucination of values (caught), value swaps (first caught; second caught when prose windows don't overlap — documented limit), upstream-tampering boundary (out of scope; documented). | < 1 s | $0 |
| **Replay** | `replay/test_replay.py` + `replay/cassettes/*.json` | Replay pre-recorded LLM responses through the orchestrator; assert the verifier + trace properties match what was captured. Catches verifier / orchestrator / audit regressions on real-shaped LLM outputs without paying for API tokens. Cassettes refresh via `python -m eval.replay.record`. | < 1 s | $0 |
| **Live** | `live/test_agent_property.py`, `live/test_agent_adversarial.py`, `live/test_agent_golden.py` | Hits the real Anthropic API. Property-based assertions, adversarial probes, golden expected-fact cases. | ~30-90 s | ~$0.05/run |

## Counts at submission

| File | Tests |
|---|---|
| `test_verifier.py` | 17 |
| `test_tools.py` | 9 |
| `test_rules.py` | 33 |
| `test_budget.py` | 10 |
| `test_auth_login.py` | 8 |
| `test_auth_mfa.py` | 7 |
| `test_auth_password_reset.py` | 7 |
| `test_chat_protected.py` | 5 |
| `test_rbac.py` | 13 |
| `test_golden_cases.py` | 16 |
| `test_adversarial.py` | 17 |
| `test_synthetic_tampering.py` | 10 |
| `replay/test_replay.py` | 4 (deselected by default; replay-only) |
| `live/*` | varies (deselected by default; `pytest -m live`) |
| **Total (default run)** | **156** |
| **Total including replay** | **160** |

## Per-UC golden case coverage

| UC | Description | Cases |
|---|---|---|
| UC-1 | Pre-visit briefing | 3 |
| UC-2 | Changes since last visit (subset retrieval) | 1 |
| UC-3 | Lab interpretation in context | 4 |
| UC-4 | Medication reconciliation | 2 |
| UC-5 | Authorization-boundary refusal | 1 |
| Failure-mode (cross-UC) | Fabrication / value mismatch detection | 5 |

The architecture spec target is 10/UC = 50 hand-curated cases. The current count (16) sits below that ceiling on purpose: the file's coverage gate (`test_golden_case_count_per_uc_meets_minimum`) enforces "every UC has ≥ 1 case + total ≥ 15", which we ratchet upward as UCs come into focus rather than padding with aspirational cases.

## What each layer catches

**Verifier unit tests:**
- Source-id matching catches fabricated citations.
- Numeric value-tolerance catches "real ID, wrong number" cases.
- Patient subject locking rejects any tool call against a different patient_id.
- Mock FHIR returns the expected shape with `source_id` on every record.

**Rule engine unit tests:**
- Lab thresholds fire at correct boundaries (A1c >9 critical, 7-9 warning; LDL ≥190 critical, 100-189 warning; Cr >1.5 critical, 1.2-1.5 warning).
- Dosage ranges fire above-typical (warning) and above-max (critical) for metformin / lisinopril / atorvastatin / furosemide.
- Drug interactions fire when both drugs present (lisinopril × NSAIDs, metformin × IV contrast, atorvastatin × clarithromycin).
- Cross-rule (metformin + creatinine) fires when both signals present.
- Rule engine output is deterministic (`test_evaluate_is_deterministic`).

**Integration auth + RBAC:**
- Login: bad password → 401, no user → 401, inactive → 403, 5 failed → 423 lock.
- MFA: pre-auth `/mfa/setup` → 401, post-password it returns a valid TOTP secret + URI, wrong code → 400, right code → full session.
- Password reset: unknown email returns 200 (no enumeration), valid token rotates password and clears lockout, expired/used/invalid token → 400.
- `/chat`: 401 without a session, 401 with a pending-MFA-only session, 200 with a full session, emits `chat_request` audit event.
- RBAC: physician sees 4 tools, nurse sees 3 (no problem list), resident sees 4 + watermark, unknown-role sees 0.
- Patient assignment: unassigned user returns 403 + `chat_refused_unassigned` audit event.
- Token budget: at-or-above threshold returns 429 + `budget_exceeded` audit event; under threshold proceeds.

**Adversarial:**
- 12 prompt-injection variants → patient-subject locking holds without exception.
- Mixed-batch dispatch refuses only the mismatched call; siblings succeed.
- Role whitelists are immutable frozensets at runtime.

**Synthetic tampering:**
- Post-generation bundle mutation between Reason and Verify is caught.
- LLM-side hallucination of values (real ID, fabricated number) is caught.
- Value swaps with isolated citations: both caught.
- Value swaps with adjacent citations: at least one caught (enough to fail verification overall).
- Upstream FHIR tampering before retrieval: out of scope; documented threat boundary.

**Replay:**
- For each recorded scenario, the orchestrator runs against the cassette's recorded LLM responses and the verifier + trace properties match what was captured at record time.
- Pinned: `verified` flag, presence/absence of unknown ids, cited-id count, retrieved-id count, plan-node tool selection, refused flag, response non-emptiness.
- Catches: verifier bugs, orchestrator wiring drift, audit emission regressions, citation-extraction drift — all on real-shaped LLM outputs.
- Doesn't catch: actual LLM behavior changes (those are the live layer's job).

**Live:**
- Every response passes the deterministic verifier with zero unknown source ids.
- Sparse-data briefings do not fabricate (cited subset of retrieved bundle).
- Plan node never emits a tool call with a different patient_id, even under prompt injection.
- No leakage of one patient's data when the user asks about a different one.
- Golden expected-fact cases for UC-1, UC-3 (medications), UC-4 (active conditions), and the sparse-data briefing.

## Adding new cases

- **Unit (verifier / rules / budget):** pure functions — add new test functions in the appropriate `test_*.py`.
- **Integration:** use `client` (no session), `seed_user` (dr.chen, no MFA), `seed_user_mfa` (dr.chen, MFA enrolled with secret), or `authed_client` (full session post-MFA).
- **Golden:** append a `GoldenCase(...)` to `GOLDEN_CASES` in `eval/test_golden_cases.py`. The parametrized test picks it up automatically.
- **Adversarial:** add a tuple to `INJECTION_TOOL_CALLS` for new injection variants, or write a focused test for a new structural defense.
- **Tampering:** add a focused test exercising a specific corruption pattern.
- **Replay:** add an entry to `SCENARIOS` in `replay/record.py`, run `python -m eval.replay.record <new_scenario>`, commit the cassette JSON. The parametrized test in `replay/test_replay.py` picks it up automatically.
- **Live:** add a `@pytest.mark.live` test. Keep latency-sensitive assertions generous; tighten as you collect data.

## CI gate

Every PR runs the default test suite (156 tests, `pytest`) on Python 3.12 via [`.github/workflows/ci.yml`](./.github/workflows/ci.yml). A red CI blocks merge. Pre-commit hooks (`.pre-commit-config.yaml`) run a faster local subset on every commit.

Live tests are not in the merge gate — they run manually post-merge against the deployed app to catch model-behavior regressions over time.
