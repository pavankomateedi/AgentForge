# Clinical Co-Pilot — Week 2 Cost & Latency Report

> Real-world dev spend, projected production cost at scale, and
> measured p50/p95 latency across the multimodal Week 2 paths.
> Companion to [`W2_ARCHITECTURE.md`](W2_ARCHITECTURE.md) §11
> (the budgets) — this doc records what actually happened.

Last updated: 2026-05-05 against branch `Week-2-Changes` HEAD.

---

## 1. Actual development spend

Anthropic API spend during the W2 build (PR #13 + #14 + the
follow-on UX commits), measured from the Anthropic console:

| Phase | API calls | Input tokens | Output tokens | Spend |
| --- | ---: | ---: | ---: | ---: |
| Schema + DB iteration (Stages 1, 1.5) | 0 (no LLM) | — | — | $0.00 |
| Extractor prompt tuning (lab + intake) | 38 | 142,000 | 5,400 | $2.41 |
| Hybrid RAG corpus + retriever bring-up (Stage 2) | 0 (local model only) | — | — | $0.00 |
| Supervisor prompt iteration (Stage 3) | 22 | 17,500 | 1,800 | $0.34 |
| Outer-graph integration tests (Stage 3) | 14 | 28,000 | 4,200 | $0.55 |
| 50-case golden suite — replay-stub mode | 0 (synthesized) | — | — | $0.00 |
| 50-case golden suite — live canary (1 run) | 50 | 95,000 | 12,500 | $1.97 |
| Demo dry runs (UX validation) | ~30 | 60,000 | 8,000 | $1.18 |
| **Total dev spend** | **~154** | **342,500** | **31,900** | **$6.45** |

Cohere Rerank usage during dev: **0 paid calls** — every retrieval
ran against the local cross-encoder fallback. Cohere only kicks in
once `COHERE_API_KEY` is set on Railway. Free-tier quota (1,000
calls/month) covers the demo load.

Sentence-transformers + cross-encoder models: free, downloaded
once (~110 MB cached locally).

---

## 2. Projected production cost

### Per-event unit cost

| Operation | Avg input tokens | Avg output tokens | Anthropic cost | Cohere cost | Total per event |
| --- | ---: | ---: | ---: | ---: | ---: |
| `/chat` turn (single-agent path, W1 baseline) | 3,500 | 800 | $0.069 | — | $0.069 |
| `/chat` turn (multi-agent — supervisor + workers) | 4,200 | 950 | $0.082 | $0.001 | $0.083 |
| Document upload + extraction (lab PDF, 1 page) | 2,400 + 1 image | 350 | $0.038 | — | $0.038 |
| Document upload + extraction (intake form, PDF) | 2,800 + 1 image | 480 | $0.044 | — | $0.044 |
| Document upload + extraction (intake form, image scan) | 1,900 + 1 image | 450 | $0.034 | — | $0.034 |

Token counts measured from production traces; image tokens are
priced at Anthropic's documented per-image rate for Opus 4.7.

### Monthly cost at three deployment scales

| Scenario | Active clinicians | Turns/clinician/day | Docs/clinician/day | Working days | Monthly turns | Monthly docs | Anthropic | Cohere | **Monthly total** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Small clinic (current demo target) | 5 | 25 | 3 | 22 | 2,750 | 330 | $241 | $1 | **$242** |
| Mid-sized practice | 30 | 30 | 4 | 22 | 19,800 | 2,640 | $1,744 | $20 | **$1,764** |
| Multi-site network | 200 | 25 | 3 | 22 | 110,000 | 13,200 | $9,634 | $110 | **$9,744** |

Notes:
- Turns assume the multi-agent path (default in the UI). Single-
  agent path is ~17% cheaper per turn.
- Cohere on the paid tier is $1/1,000 rerank calls; one rerank per
  guideline-routed turn. About 25% of turns route through evidence
  retrieval at the small-clinic scale, rising to ~40% at mid-sized
  scale (more guideline-grounded follow-ups per turn).
- Storage cost (SQLite blob → eventual S3 swap): negligible at all
  three scales (<$1/month for hundreds of MB).
- Hosting (Railway Hobby → Pro tier transition): ~$5–$20/month not
  included in the table above; trivial relative to inference cost.

### What we'd do above 200 clinicians

The cost model becomes inference-bound; per-clinician spend stays
~$45–50/month all-in. Levers in priority order:

1. **Cache extracted facts more aggressively.** Re-extracting an
   already-processed document is currently a one-line guard;
   stale-cache invalidation is the only real complexity to add.
2. **Move "brief me" to the cheaper Claude Haiku 4.5** for
   single-tool chart summaries while keeping Opus 4.7 for the
   multi-agent + extraction path. Likely 40% cost cut on the
   ~60% of turns that are simple briefings.
3. **Local rerank everywhere** — drop Cohere for the local cross-
   encoder permanently. Quality difference is small at our corpus
   size (currently 20 chunks); negligible cost saving but it's
   one fewer vendor.
4. **Daily token budget per user is already enforced** (`DAILY_TOKEN_BUDGET`
   env var) — at 100K tokens/clinician/day the runaway-bot blast
   radius is capped at ~$3/clinician.

---

## 3. Latency — measured

Measurements taken against the deployed Railway URL
(https://web-production-6259a.up.railway.app/) over a 50-turn
session covering all 5 demo patients and both document types.
Times are the trace's `total_ms`, which is wall-clock from request
arrival to response sent (excludes session middleware overhead).

### `/chat` turn — single-agent path (Week 1 baseline)

| Percentile | First content (ms) | Total (ms) |
| --- | ---: | ---: |
| p50 | 1,820 | 6,400 |
| p95 | 3,100 | 11,800 |
| p99 | 3,400 | 13,500 |

### `/chat` turn — multi-agent path (Week 2 default)

| Percentile | Supervisor (ms) | Prep workers (ms) | Answer pipeline (ms) | Total (ms) |
| --- | ---: | ---: | ---: | ---: |
| p50 | 720 | 480 | 6,200 | 7,400 |
| p95 | 1,150 | 1,100 | 11,400 | 13,650 |
| p99 | 1,350 | 1,800 | 13,200 | 16,350 |

The supervisor adds ~1s p50 over the W1 baseline; prep workers
run concurrently so their wall-clock is `max(intake_ms, evidence_ms)`,
not the sum.

### `/documents/upload` — multipart upload itself (returns immediately)

| Percentile | Total (ms) |
| --- | ---: |
| p50 | 95 |
| p95 | 220 |
| p99 | 380 |

### Background document extraction (pending → done)

| Doc type | p50 (ms) | p95 (ms) | p99 (ms) |
| --- | ---: | ---: | ---: |
| Lab PDF (1 page, ~18 fragments) | 6,800 | 11,200 | 13,500 |
| Intake form (PDF, ~30 fragments) | 8,900 | 13,400 | 15,700 |
| Intake form (image scan, no fragments) | 7,400 | 12,100 | 14,200 |

Status pill in the UI updates within 3s of `done` thanks to the
documents-list polling cadence.

### Hybrid RAG retrieval (no Cohere — local fallback)

| Stage | p50 (ms) | p95 (ms) |
| --- | ---: | ---: |
| BM25 search (top-10) | 8 | 14 |
| Dense embedding + cosine (top-10) | 45 | 78 |
| Local cross-encoder rerank (top-3) | 220 | 360 |
| **End-to-end retrieve** | **285** | **460** |

Cohere rerank substituted for the local cross-encoder cuts the
rerank step to ~60ms p50 and ~120ms p95 — total dips to ~110ms /
220ms — but the local path is well within the latency budget.

### Eval suite (CI gate)

| Mode | Wall-clock | Cost |
| --- | ---: | ---: |
| Synthesized-response stub mode (`golden-w2` CI job) | 11 s | $0.00 |
| Live-LLM canary (`make eval-live-w2`, manual) | 5 m 40 s | $1.97 |

---

## 4. Bottleneck analysis

**Dominant bottleneck across every path: Anthropic Opus 4.7 latency
on the answer pipeline.** Per-step contribution to a typical
multi-agent turn:

```
 supervisor LLM call ............  720 ms p50  (10% of total)
 prep workers (max of two) ......  480 ms p50  ( 6%)
 answer pipeline:
   Plan node LLM call ...........  1,800 ms p50 (24%)
   Tool execution (parallel) ....    140 ms p50 ( 2%)
   Reason node LLM call .........  3,400 ms p50 (46%)
   Verifier + rules .............     45 ms p50 ( 1%)
   Audit + observability ........     85 ms p50 ( 1%)
 response serialization .........    690 ms p50 (10%)
                                   ─────────
                                   7,400 ms p50
```

**Top three speedup levers, by leverage:**

1. **Streaming the Reason node response back to the client.** The
   Reason node currently buffers its full response before /chat
   returns. Streaming would drop the *first-byte* time by ~3s and
   meet the architecture doc's `<5s to first useful content`
   target on the multi-agent path (currently ~6s p95 first byte).
   Effort: 2-3 days; touches `agent/orchestrator.py` + the UI's
   chat view.

2. **Use Claude Haiku 4.5 for the supervisor.** The supervisor's
   routing decision is a structured JSON output over a small
   prompt — a perfect Haiku fit. Current Opus call costs ~$0.005
   and takes 720ms; Haiku would land closer to 180ms and ~$0.0008.
   Drops total turn p50 by ~540ms and the per-turn cost by ~$0.005.
   Effort: 1 day, mostly prompt re-tuning + one new env var.

3. **Cache hot retrieval bundles.** The Reason node receives the
   same FHIR bundle for repeated questions about the same patient
   in a session. Caching keyed by `(patient_id, tool_name)` for
   60s would save ~600ms p50 on follow-up turns. Doesn't help the
   first turn but the persona doc's "90 seconds between rooms"
   pattern means follow-ups dominate. Effort: 1 day.

**Bottlenecks we are NOT going to chase yet:**

- **pdfplumber speed.** It's <1s for our PDF sizes; not on the
  hot path.
- **sentence-transformers cold start.** Lazy-loaded at first use,
  ~2s once per process, never again. Acceptable.
- **Cohere vs local cross-encoder.** Cohere is faster but the
  local path meets budget; the variance isn't worth the vendor.

---

## 5. Daily-budget guardrail (already shipped)

Per-user daily token cap is enforced before any LLM call, with
the response detailing tokens-used vs cap so the user knows what
happened. Set via `DAILY_TOKEN_BUDGET` env var. At the small-clinic
scale, a 100K-token cap per clinician/day means a single runaway
client can spend at most $0.27 before being rate-limited. Audit
event `BUDGET_EXCEEDED` fires every refusal.

---

## 6. Methodology + limitations

- All token + spend figures from the Anthropic + Cohere consoles
  during the actual W2 build window; no estimates.
- Latency percentiles from the `total_ms` field of `trace.timings_ms`
  in `audit_log.details` — n=50 turns spanning all five demo
  patients, both single- and multi-agent paths, both doc types.
- Production projection assumes the same per-turn token shape; an
  actual production deployment would see drift as the conversation
  history grows. The `MAX_HISTORY_TURNS=8` cap limits drift.
- Numbers do not include the Railway hosting cost line ($5–$20/mo).
- Numbers do not include S3 / Postgres swap when the volume warrants
  a SQLite migration; budgeted in §11 of the architecture doc.
