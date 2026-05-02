# Cost Analysis — Clinical Co-Pilot

This document covers actual development spend during week 1 and projects production cost at 100 / 1K / 10K / 100K users. The submission requirement explicitly notes: "this is not simply cost-per-token × n users." We treat the projection as a function of **caching, model tiering, and infrastructure amortization**, not a multiplication.

> Detailed methodology mirrors `ARCHITECTURE.md` §8. This document is the standalone artifact for the submission deliverable.

---

## 1. Per-query token profile (UC-1, the heaviest use case)

| Component | Tokens | Cost @ Opus 4.7 |
|---|---:|---:|
| System prompt (cached after first call) | ~1.5K | $0.00045 cached read |
| Tools schema (cached) | ~1.0K | $0.00030 cached read |
| Retrieved patient context (per-turn, fresh) | ~1.5K | $0.0045 |
| Plan + Reason call shape (fresh user message) | ~0.2K | $0.0006 |
| Output text | ~0.4K | $0.006 |
| **Total per query (warm cache)** | | **~$0.012** |
| **Total per query (cold cache)** | ~4.0K fresh in | **~$0.020** |

The cost guard caps usage per user at 200,000 tokens/day by default (configurable via `DAILY_TOKEN_BUDGET`); at the warm-cache profile that's roughly 30-50 turns per user per day before the agent refuses with `429 Budget exceeded`.

---

## 2. Actual dev spend (week 1)

| Category | Actual | Notes |
|---|---:|---|
| Eval cassette recording | ~$0.10 | 4 scenarios at Opus 4.7, all four committed |
| Live API smoke tests during integration (Langfuse, rules, LangGraph cutover) | ~$1.00 | ~50 turns across the build |
| Manual testing during demo prep | ~$0.50 | ~20 turns |
| Demo video record | ~$0.20 | one full take |
| **Total dev spend, week 1** | **~$1.80** | |

Significantly under the architecture-spec estimate (~$155) because:
1. The 200-case eval suite spec was scoped down to 16 deterministic golden cases that exercise the verifier without LLM cost — see `EVAL_DATASET.md`.
2. Replay cassettes mean every regression test re-uses prior recorded responses instead of re-paying. The cassette-record action costs ~$0.10 once per scenario, then the test runs free forever.
3. Prompt caching on the static system prompt + tools schema cut cold-call cost by ~40% on every subsequent turn within the 5-minute cache window.

---

## 3. Production projections

Assumptions: PCP averages 25 queries/clinical day, 220 clinical days/year, ~5,500 queries/year/user. Plus a 20% buffer for retries, exploration, and supporting roles.

| Users | Queries/year | LLM cost/year | Infra | **Total/yr** | Architectural changes required |
|---:|---:|---:|---:|---:|---|
| 100 | 660K | ~$8K | ~$3K | **~$11K** | Move from Railway free to a HIPAA-eligible AWS or GCP tier. Add nightly DB backups + a non-prod staging env. |
| 1K | 6.6M | ~$80K | ~$25K | **~$105K** | Dedicated VPC. RDS Postgres Multi-AZ (replaces SQLite). Autoscaling for the agent service. Self-hosted Langfuse moves from a single VM to a dedicated Postgres + worker pool. |
| 10K | 66M | ~$300K (with aggressive caching) instead of ~$800K naive | ~$120K | **~$420K** | Tiered model strategy: Haiku for plan + classify, Opus for reason. Per-tenant retrieval cache layer (Redis) keyed by `(patient_id, tool_call_hash)`. Dedicated Langfuse cluster; Langfuse v3 instead of Cloud. Per-region deployment (USE-EAST + USE-WEST) for latency. |
| 100K | 660M | ~$1.2M (with self-hosted small models for non-reasoning) instead of ~$3M naive | ~$1M | **~$2.5M** | Self-hosted Llama or Mistral at the Plan/Classify nodes (CPU-only inference is viable for the 8-shot tool-picking task; Opus stays on the Reason node). Sharded agent service per region. Read-replica clinical knowledge store separate from OpenEMR — OpenEMR is no longer the hot read path. Dedicated SRE function. SOC 2 Type II. BAA chain documented end-to-end (Anthropic, AWS, RDS, Langfuse, et al.). |

### Why the 10K → 100K step is 6× cost, not 10×

Three economies kick in at scale:

1. **Cache hit rate climbs.** With 100K users, the same patient gets briefed multiple times in a day across consults. The retrieval cache (`(patient_id, tool_call_hash)` → bundle) returns hits often enough to materially reduce both LLM and FHIR cost.
2. **Model tiering becomes worth the build cost.** Plan and classify nodes don't need Opus-level reasoning — the task is "pick from 4 tools given a prompt", which an open-source 7B-parameter model handles for ~1/100th the cost. The build cost (eval + rollout + monitoring) only amortizes at this scale.
3. **Infrastructure amortizes.** A multi-region SOC 2-audited stack costs roughly the same to run for 10K users as for 100K — most of the cost is the audit + the headcount, not the compute.

### What it understates

The naive token-cost-times-N model also dramatically **understates** costs at scale. The 100K column hides:

- Compliance overhead: SOC 2 audit (~$50K/year), HIPAA audits, BAA chain documentation.
- SRE headcount: at least 1 FTE owning the agent service, probably 2-3 across regions.
- Customer success: clinicians escalating "the agent said something wrong" need triage; that's a person.
- Legal: drug-interaction tables and clinical rule updates require physician review.

These costs don't appear in API bills but are load-bearing for any actual hospital deployment.

---

## 4. Cost controls built in from day 1

These ship in the v0 codebase, not in a "later" backlog:

| Control | Implementation | What it bounds |
|---|---|---|
| Prompt caching | `cache_control: {"type": "ephemeral"}` on system prompt + tools schema in both Plan and Reason calls. | Per-turn input cost; saves ~40% per turn within the 5-minute cache window. |
| Structured retrieval bundles capped | Mock FHIR returns small structured records with `source_id` only — no free text bloat. | Per-turn fresh input tokens. |
| Verifier failure → one regeneration max | `agent/graph.py` verify → reason_retry → verify_retry → refuse. Never an unbounded loop. | Worst-case per-turn cost (≤ 2× a normal turn). |
| Per-user daily token budget | `agent/budget.py` + `/chat` middleware. Default 200K tokens/user/day, configurable. Returns 429 with `BUDGET_EXCEEDED` audit event when crossed. | Per-user, per-day blast radius. |
| Token spend tracked in Langfuse | `obs.log_generation` records `usage_details` on every LLM call; Langfuse computes cost. | Per-request, per-user, per-use-case attribution surfaceable in the dashboard. |
| Replay cassettes for regression tests | `eval/replay/cassettes/*.json`. New regressions test against recorded responses instead of paying per-run. | CI cost (effectively $0). |

---

## 5. What this analysis does NOT cover

- **Long-term context cost.** Multi-turn conversations across a day would inflate input tokens. Today's scope is single-turn per request; the architecture document flags multi-turn memory as a v1 design with its own verification story.
- **Streaming vs. non-streaming.** Current implementation is non-streaming. Streaming (SSE) is in the v1 spec; cost is identical, perceived latency drops.
- **Real OpenEMR FHIR latency.** Mock FHIR returns in <10ms; real FHIR will dominate the latency budget. Cost-wise, this changes nothing — FHIR calls don't bill — but it changes the cache strategy: the retrieval cache becomes a latency optimization, not just a cost one.

---

## Sources

- Anthropic public pricing for Claude Opus 4.7 (2026 rate sheet).
- Self-measured per-turn token usage from Langfuse traces during development.
- AWS pricing calculator for the 100/1K/10K/100K infra columns (2026 USE-EAST rates).
- Industry benchmarks for clinician query volume from public health-IT studies.
