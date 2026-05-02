# Contributing

This project is small enough that any reader should be able to land a change in a day. The notes below describe the development loop and the quality gates so the bar stays consistent.

## Development loop — Red / Green / Refactor

We follow **test-first** development. The standard cycle:

1. **Red.** Write a failing test for the behavior you want. Run `pytest <path-to-test>` and confirm it fails for the right reason — not an import error or a syntax bug. The failure message is the spec for the change.
2. **Green.** Write the minimum code to make the test pass. Resist the urge to add the next feature; resist the urge to clean up unrelated code. The point is one test green, no others red.
3. **Refactor.** With the suite green, simplify and rename. Delete dead code. Extract helpers. Run the full suite (`pytest`) at the end and confirm it stays green.

The eval suite is the unit of progress — a failing test IS the bug report; a passing test IS the spec. Drift in scores triggers investigation, not auto-revert.

### When to skip test-first

Only when:

- The change is a typo / cosmetic doc edit with no behavioral impact.
- You're spiking exploratory code that you'll throw away. (If you keep any of it, write the tests then.)

Otherwise, write the test first. The hour you save by skipping the test you spend twice in debugging.

## Quality gates

Three layers, listed in order of cost-to-run:

| Layer | Where | What | Speed |
|---|---|---|---|
| Pre-commit hook | local, every `git commit` | ruff lint + format, fast unit subset | < 5 s |
| GitHub Actions CI | every PR + push to `main` | ruff + full unit/integration/replay suite | ~30 s |
| Live-API tests | manual (`pytest -m live`) | hits real Anthropic API | ~30-90 s, costs $0.05/run |

A PR cannot merge unless CI is green. Live tests are not in the merge gate — they run against the deployed app post-merge to catch model-behavior regressions.

### Setting up the local hooks

```bash
python -m pip install pre-commit
pre-commit install
```

After that, every commit runs the fast subset. To run on all files (e.g. before opening a PR):

```bash
pre-commit run --all-files
```

To skip the hook for a one-off commit (rare; usually the right answer is to fix what it complains about):

```bash
git commit --no-verify
```

## Test conventions

- **Unit tests** (`eval/test_*.py`) — pure Python, no LLM, no DB writes outside the truncate-between-tests fixture. Should run in < 1 s each.
- **Integration tests** (`eval/test_chat_protected.py`, `test_rbac.py`, `test_budget.py`) — exercise FastAPI via `TestClient` against a fresh SQLite DB. Should run in < 1 s each. Use the existing fixtures (`client`, `seed_user`, `seed_user_mfa`, `authed_client`, `stub_run_turn`).
- **Replay tests** (`eval/replay/test_replay.py`) — re-run the orchestrator against pre-recorded LLM responses. Refresh cassettes via `python -m eval.replay.record`.
- **Live tests** (`eval/live/test_*.py`) — `@pytest.mark.live`. Skipped by default. Run manually with `pytest -m live` when you want to validate against the real model.

When adding a new test:

- Pick the cheapest layer that exercises the behavior. Prefer unit > integration > replay > live.
- Synthetic fixtures over real LLM responses where possible. The verifier and rule engine are deterministic; the LLM is not.
- One assertion per concept. Multi-assert tests are fine when the assertions are different facets of the same property.

## Commit messages

- Subject line < 70 chars, present tense ("Add rule engine", not "Added rule engine").
- Body explains the **why**, not the **what** — the diff is the what.
- One commit per logical change. Refactors and feature additions in separate commits.

## Branching

- Never push directly to `main`. Open a PR from a feature branch.
- Branch names: `feature/<name>`, `fix/<name>`, `docs/<name>`. Hyphens, lowercase.
- The `main` branch is the deployed-to-Railway head. Treat it as production.

## What goes where

| Concern | File |
|---|---|
| Plan/Reason LLM calls + node functions | `agent/graph.py` |
| Public orchestrator entry (`run_turn`) | `agent/orchestrator.py` |
| Verification (source-id matching + value tolerance) | `agent/verifier.py` |
| Domain rules (lab thresholds, dosage, interactions) | `agent/rules.py` |
| Tools (mock FHIR clients, patient-subject locking) | `agent/tools.py` |
| Auth (login, MFA, sessions, password reset) | `agent/auth.py` |
| Role-based access + patient assignment | `agent/rbac.py` |
| Per-user daily token budget | `agent/budget.py` |
| Audit log writer + event types | `agent/audit.py` |
| FastAPI app + `/chat` middleware stack | `agent/main.py` |
| Langfuse wrapper (init, scores, generations, spans) | `agent/observability.py` |

## Getting help

- Open an issue for bugs or feature requests.
- For architectural questions, `ARCHITECTURE.md` is the source of truth.
- For known gaps and v1 work, see `ARCHITECTURE.md` §9 ("Risks and Open Questions").
