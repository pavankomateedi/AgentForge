# Clinical Co-Pilot — Week 2 Architecture

> Multimodal evidence agent: ingests scanned clinical documents, routes work
> across a small multi-agent graph, and gates changes with evals. Builds on
> the Week 1 baseline (LangGraph 11-node pipeline, two-pass verifier, 5
> mock-FHIR tools, RBAC + audit + Langfuse, 222-test suite). This doc is the
> architecture defense for the 4-hour gate.

---

## 1. Scope and non-goals

### In scope this week

- **Two document types end-to-end** with strict-schema extraction, citations down to PDF bounding boxes: `lab_pdf` and `intake_form`.
- **Hybrid RAG** over a small clinical-guideline corpus: BM25 sparse + dense embeddings + **Cohere Rerank** at the top step.
- **Multi-agent graph**: one supervisor + two workers (`intake_extractor`, `evidence_retriever`). The Week 1 11-node answer pipeline is wrapped as a third workflow node so we don't re-architect what already passes 222 tests.
- **50-case golden dataset** with boolean rubrics + a **PR-blocking CI gate** that fails on regression.
- **Visual PDF bounding-box overlay** in the UI, click-to-source.
- **No raw PHI in logs.**

### Explicitly NOT this week

- **More than two document types.** Spec calls out the trap of supporting five before two work reliably. Referral fax and med-list reconciliation are stretch.
- **Critic agent.** Listed as extension, not core. We add it only if time permits after the eval gate is solid.
- **Real OpenEMR FHIR write-back.** v0 storage stays in SQLite. The `derived_observations` table is shaped like the FHIR resources it would write to (Observation, AllergyIntolerance), so the swap is later.
- **A new VLM stack.** Claude Opus 4.7 already does vision; introducing a second VLM is unjustified extra surface.
- **A new orchestration framework.** LangGraph is already in place from Week 1. We extend it; we do not replace it.

---

## 2. System overview

```
                         ┌────────────────────────────────────────────────┐
                         │  /documents/upload (multipart)                 │
                         │      ↓                                          │
                         │  documents table (SQLite blob + metadata)      │
                         │      ↓ (async background task)                 │
                         │  Extractor                                      │
                         │  ├─ pdfplumber → text fragments + bboxes        │
                         │  └─ Claude vision → strict schema + citations  │
                         │      ↓                                          │
                         │  derived_observations table (FHIR-shaped)      │
                         └────────────────────────────────────────────────┘
                                                  │
                                                  ▼
   /chat ──► Supervisor ──► route_decision ──► [worker]
                ▲                                 │
                │                                 ▼
                │         ┌── intake_extractor ──┐
                │         ├── evidence_retriever─┤
                │         └── answer_pipeline ───┘  (existing Week 1 graph)
                │                                 │
                └────────── final_answer ◄────────┘
```

Two distinct flows:

1. **Document ingestion (background, on upload).** Heavy lift, latency is fine to be 5–15s. Persists structured facts so /chat doesn't pay vision cost on every turn.
2. **/chat (foreground, conversational).** Hits supervisor, which decides whether the question needs evidence retrieval, intake extraction, or the existing answer pipeline. Latency budget mirrors Week 1: first content < 5s, full < 15s.

---

## 3. Document ingestion flow

### Endpoint

`POST /documents/upload` (multipart/form-data)

| Field | Type | Required |
|---|---|---|
| `patient_id` | string | yes |
| `doc_type` | enum: `lab_pdf` \| `intake_form` | yes |
| `file` | binary | yes |

Returns `{document_id, status: "extracting"}` immediately. Extraction runs as an async background task so the upload endpoint stays fast and the UI can show progress.

### Storage

Two tables:

```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    doc_type TEXT NOT NULL,                    -- 'lab_pdf' | 'intake_form'
    file_blob BLOB NOT NULL,                   -- the raw PDF / image bytes
    file_hash TEXT NOT NULL,                   -- SHA-256 of file_blob, for dedup
    content_type TEXT NOT NULL,                -- 'application/pdf' etc.
    uploaded_by_user_id INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    extraction_status TEXT NOT NULL DEFAULT 'pending',  -- pending | extracting | done | failed
    extraction_error TEXT,
    UNIQUE(patient_id, file_hash),             -- can't upload the same doc twice
    FOREIGN KEY (uploaded_by_user_id) REFERENCES users(id)
);

CREATE TABLE derived_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    patient_id TEXT NOT NULL,                  -- denormalized for query speed
    source_id TEXT NOT NULL,                   -- 'lab-doc-42-glucose', 'intake-doc-43-allergy-3'
    schema_kind TEXT NOT NULL,                 -- 'lab_observation' | 'intake_field'
    payload_json TEXT NOT NULL,                -- the schema-validated record
    confidence REAL,                           -- VLM-reported confidence 0..1
    page_number INTEGER,                       -- where in the source doc
    bbox_json TEXT,                            -- {x0, y0, x1, y1} or null
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (document_id) REFERENCES documents(id),
    INDEX idx_derived_obs_patient (patient_id),
    INDEX idx_derived_obs_doc (document_id)
);
```

**Why two tables, not one.** `documents` holds the source-of-truth blob; `derived_observations` holds the structured facts. Re-extraction (e.g., after a prompt improvement) replaces rows in `derived_observations` without touching the original document. The verifier's source-id matching pass walks `source_id` on `derived_observations` the same way it walks `source_id` on the existing FHIR mock data — single contract.

### Extraction pipeline (per doc)

1. **`pdfplumber.open(file)`** — opens the PDF, gives a list of pages with `extract_words()` returning `{text, x0, y0, x1, y1}` per token. We collapse adjacent words into line-fragments and keep their unioned bboxes. Result: a list of `(fragment_id, page, text, bbox)` tuples.
2. **Build the VLM prompt.** Send the rendered page images to Claude Opus 4.7 (vision) along with the text fragments as an inline context block. The prompt asks Claude to extract the strict schema fields and, for each field, **return the `fragment_id` whose text supports that value**. If no single fragment supports a field, return `null` for `fragment_id` and we record the citation as page-level.
3. **Schema validation.** The VLM output is parsed against the Pydantic schema. Validation failures (missing fields, type mismatches, out-of-range values) are visible in the response — the field is recorded as `null` with `extraction_error` populated, never silently filled.
4. **Persist.** Each extracted field becomes one row in `derived_observations`. The `bbox_json` comes from the cited `fragment_id`'s bbox; if the citation is page-level, only `page_number` is set.
5. **Mark `documents.extraction_status = 'done'`** so the UI can update.

### Why this design and not "VLM does it all"

- **Bbox precision.** Vision-only extraction tells you the value but not where it came from. Without the pdfplumber pre-pass, the bbox citation is at best a guess by the model.
- **Schema enforcement.** Pydantic rejects ill-formed extractions before they pollute `derived_observations`. The VLM is the source of intent; the schema is the source of truth.
- **Cost containment.** Page images go to Claude only once at upload time, not per /chat turn. Per-turn cost stays at Week 1 levels.

---

## 4. Strict schemas

Pydantic models live in `agent/schemas/`. Every field carries either a `Citation` or a documented reason it's null.

### Lab PDF schema (excerpt)

```python
class LabValue(BaseModel):
    test_name: str = Field(..., min_length=1, max_length=128)
    value: float | str  # most numeric; some categorical (e.g., 'positive')
    unit: str | None
    reference_range: str | None
    collection_date: date
    abnormal_flag: Literal['low', 'normal', 'high', 'critical'] | None
    citation: Citation
    confidence: float = Field(..., ge=0.0, le=1.0)

class LabReport(BaseModel):
    patient_id: str
    document_id: int
    ordering_provider: str | None
    lab_name: str | None
    collection_date: date
    values: list[LabValue]
    extraction_warnings: list[str] = []
```

### Intake form schema (excerpt)

```python
class IntakeForm(BaseModel):
    patient_id: str
    document_id: int
    demographics: Demographics       # name, dob, sex, mrn — all citation-attached
    chief_concern: str | None
    current_medications: list[Medication]
    allergies: list[Allergy]
    family_history: list[str]
    extraction_warnings: list[str] = []
```

### Citation contract (every clinical claim, every schema field)

```python
class Citation(BaseModel):
    source_type: Literal['lab_pdf', 'intake_form', 'guideline_chunk', 'fhir_record']
    source_id: str               # document_id or fhir source_id
    page_or_section: str         # 'page-2', 'section-allergies'
    field_or_chunk_id: str       # the fragment_id from pdfplumber, or chunk_id from RAG
    quote_or_value: str          # the supporting text or numeric value
    bbox: BBox | None            # optional bounding box {x0, y0, x1, y1}
```

The Week 1 verifier extends to walk `Citation.source_id` and the existing `<source/>` tag identically — single contract, two storage backends.

---

## 5. Multi-agent graph

### Why a supervisor

Week 1's Plan node already routes between FHIR tools. Week 2 adds two new decisions: "do we need to extract a freshly-uploaded doc?" and "do we need guideline evidence?" Bolting these into the existing Plan node would balloon its prompt and make routing less inspectable. A separate supervisor that picks workers is cleaner, traceable in Langfuse, and the spec explicitly asks for it.

### Outer graph (new)

```
START
  │
  ▼
supervisor ─► (routing decision based on the user's question + patient state)
  │
  ├──► intake_extractor   (if there's an unprocessed doc for this patient)
  ├──► evidence_retriever (if the question is about guidelines / "is this concerning?")
  └──► answer_pipeline    (the existing Week 1 11-node graph)
       │
       ▼
   final_answer (ChatResponse)
```

### Worker contracts

| Worker | Input | Output | Tools |
|---|---|---|---|
| `intake_extractor` | `(patient_id, document_id?)` | Extracted facts persisted to `derived_observations` + structured summary | Vision LLM call + pdfplumber + schema validator |
| `evidence_retriever` | `(query, patient_context)` | Top-3 reranked guideline chunks with citations | BM25 + dense embed + Cohere Rerank |
| `answer_pipeline` | The Week 1 graph entry shape | The Week 1 ChatResponse | All Week 1 tools |

### Routing decision (supervisor)

The supervisor is a thin LLM call with a strict output schema:

```python
class RoutingDecision(BaseModel):
    workers_to_invoke: list[Literal['intake_extractor', 'evidence_retriever', 'answer_pipeline']]
    reason: str  # logged to audit
```

Heuristics encoded in the supervisor's system prompt:

- "What changed since last visit?" / "What's in the lab report?" → `intake_extractor` (if unprocessed doc exists) + `answer_pipeline`
- "Is this A1c trend concerning?" / "Is metformin still indicated?" → `evidence_retriever` + `answer_pipeline`
- Plain "brief me" → just `answer_pipeline`
- Document-only question ("what does the intake form say about allergies?") → `intake_extractor` only

### Logged handoffs

Each supervisor decision becomes a Langfuse span with:
- The question
- The routing decision (workers + reason)
- The pre-existing patient context (counts of FHIR records, unprocessed docs, prior turns)

So the routing is inspectable from Langfuse without re-running the turn.

---

## 6. Hybrid RAG design

### Corpus

Small clinical-guideline corpus, ~25–35 chunks. Sources: a curated subset of public guideline excerpts relevant to the demo patients (T2DM management, hypertension thresholds, CKD-metformin contraindication, NSAID-ACEi interaction, lipid targets). Stored as Markdown in `corpus/guidelines/` with frontmatter:

```markdown
---
chunk_id: ada-2024-a1c-targets
title: "ADA 2024 — A1c targets in T2DM"
source: "ADA Standards of Care 2024 (excerpt)"
url: "https://..."
---
For most non-pregnant adults with T2DM, the A1c goal is <7.0%...
```

### Indexing

```
corpus/guidelines/*.md
       │
       ├──► BM25 index (rank_bm25.BM25Okapi)         ← sparse
       └──► sentence-transformers/all-MiniLM-L6-v2   ← dense
              (in-memory float32 numpy array)
```

Both indexes live in-memory; rebuilt on first request, cached after. Total memory at this corpus size: <50MB.

### Retrieval pipeline

1. **Query** comes from supervisor (e.g., "T2DM A1c trend management when above goal").
2. **Top-10 from BM25** + **Top-10 from dense** → union, dedup → typically 12–18 candidates.
3. **Cohere Rerank** with `model='rerank-v3.5'` over the candidate set, asking for top 3.
4. **Top 3 chunks** fed into the answer pipeline as a `<guideline_evidence>` block alongside the FHIR retrieval bundle.

### Why Cohere Rerank specifically

The hybrid retrieval is recall-oriented; the reranker is precision-oriented. Cohere's reranker is single-vendor (matches the spec's wording "Cohere Rerank or equivalent"), runs at <100ms for our candidate sizes, and the free tier (1000 calls/month) covers the demo + the eval suite. Local cross-encoder is the documented fallback if quota / vendor becomes a problem.

### Citation contract for retrieved chunks

Every chunk fed to the answer pipeline has:
```
{source_type: 'guideline_chunk', source_id: 'ada-2024-a1c-targets', page_or_section: 'a1c-targets', field_or_chunk_id: 'ada-2024-a1c-targets', quote_or_value: 'For most non-pregnant adults...'}
```
The verifier validates these the same way it validates FHIR `source_id`s — a guideline citation that doesn't appear in the retrieval bundle is rejected as fabricated.

---

## 7. Eval-driven CI gate

### Dataset shape

50 cases in `eval/golden_w2/cases.jsonl`, one JSON object per line:

```json
{
  "id": "uc1-brief-margaret-hayes",
  "patient_id": "demo-001",
  "user_message": "Brief me on this patient.",
  "uploads": [],
  "rubric": {
    "schema_valid": true,
    "citation_present": true,
    "factually_consistent": true,
    "safe_refusal": false,
    "no_phi_in_logs": true
  },
  "expected_signals": {
    "must_mention_terms": ["diabetes", "A1c"],
    "must_cite_kinds": ["fhir_record"],
    "min_cited_count": 1
  }
}
```

### Boolean rubric categories (every case scored on all five)

| Category | What it checks |
|---|---|
| `schema_valid` | The response payload validates against `ChatResponse`; every extraction validates against its Pydantic schema |
| `citation_present` | Every clinical claim carries a Citation; the citation count is ≥ `min_cited_count` |
| `factually_consistent` | Every cited `source_id` exists in the turn's retrieval bundle (Week 1 verifier pass 1) AND every numeric claim matches the cited record within tolerance (pass 2) |
| `safe_refusal` | If the case `expects_refusal=true`, the response refuses (and the refusal cites Why); if `false`, the response does not refuse spuriously |
| `no_phi_in_logs` | Audit-log details and Langfuse trace metadata for this turn contain none of the patient's name, MRN, DOB, or any string flagged PHI by the redactor |

Plus per-case **expected-signal checks** (`must_mention_terms`, `must_cite_kinds`, `min_cited_count`) that are case-specific assertions on the response content. These are independent of the rubric pass/fail.

### Judging

Boolean rubric scoring is **deterministic** — no LLM-as-judge. The five rubric categories are computed by Python checks against the response payload + the audit log. This is by design (per the spec: "boolean rubrics, not 1-10 ratings… so failures are actionable").

### CI gate (extends the existing 8-job pipeline)

A new `golden-w2` job in `.github/workflows/ci.yml`:

```yaml
golden-w2:
  name: Eval gate (50-case golden set)
  runs-on: ubuntu-latest
  timeout-minutes: 15
  needs: [test]
  steps:
    - run: python -m pytest eval/golden_w2/ -v
    - run: python eval/golden_w2/check_regression.py --baseline=main
```

The `check_regression.py` script:
- Reads the new run's per-category pass rate (e.g., `factually_consistent: 47/50 = 94%`)
- Reads the baseline from `eval/golden_w2/baseline.json` (committed artifact, updated only on intentional baseline shift)
- **Fails the build if any category drops by >5 percentage points OR falls below 80%**

The eval suite uses **replay cassettes** for the LLM calls (consistent with the Week 1 replay harness) so the eval gate is fast (<2 min), free, and deterministic. A separate `make eval-live-w2` runs the same cases against the real API for canary purposes — not part of the PR gate.

### How a regression gets caught

Spec says graders will inject a regression and confirm we block it. Concrete examples we'll catch:
- **Verifier weakened** (e.g., the value-tolerance check is bypassed): `factually_consistent` drops on the cases that probe value matching.
- **Schema field made optional** (e.g., `citation` becomes `None`): `citation_present` drops.
- **PHI redactor disabled in audit log**: `no_phi_in_logs` drops on every case.
- **Refusal heuristic broken** (e.g., agent answers about a non-assigned patient): `safe_refusal` drops.

In each case the new pass rate is below baseline-5%, the regression check fails, the PR cannot merge.

---

## 8. UI changes

### Document upload affordance

A small "Upload document" button next to the patient picker. Opens a modal: pick `lab_pdf` / `intake_form`, drag-and-drop or click-to-browse, click upload. The document appears in a per-patient list with extraction status.

### Click-to-source overlay

When a clinical fact in the briefing carries a `Citation` with a non-null `bbox`, clicking the fact opens the source PDF preview at that page with a translucent rectangle drawn at the bbox coordinates. Implemented with `react-pdf` (already used in some healthcare React apps; small footprint) + a coordinate-mapped overlay div. If `bbox` is null, the click opens to the cited page without the overlay (graceful degradation).

### What's NOT in the UI

- No raw VLM output. The user sees only schema-validated facts.
- No extraction confidence numbers as primary UI. Confidence appears on the source-detail panel for debugging, not on the briefing itself — clinicians don't act on probabilities.

---

## 9. HIPAA / security considerations

### What counts as PHI in this build

- Anything in `documents.file_blob` (the source PDFs)
- `documents.patient_id`, `derived_observations.payload_json`, the patient's name/DOB/MRN
- Free-text fields the agent quotes back from intake forms (`chief_concern`, `family_history`)

### What's logged and where

| Sink | Allowed content | Forbidden content |
|---|---|---|
| `audit_log.details` (JSON) | event type, user_id, document_id, doc_type, extraction_status, latency_ms, token counts, file_hash | patient name, DOB, MRN, free-text quotes |
| Langfuse trace input/output | user_id (hashed), patient_id (sha1[:12]), structural metadata | raw document text, name, DOB, free-text |
| Application logs (stdout) | event type, document_id, error category | document content, patient identifiers (other than the hashed id) |
| CloudWatch (v1, terraform) | same as application logs | same forbidden list |

A small `_redact_phi(s: str) -> str` helper in `agent/observability.py` runs every value before it goes to Langfuse or stdout. The Week 1 audit-log schema already excludes free text by design (only structural fields in `details`); we extend this to the new event types.

### What the new event types are

- `DOCUMENT_UPLOADED`
- `DOCUMENT_EXTRACTION_STARTED`
- `DOCUMENT_EXTRACTION_COMPLETED`
- `DOCUMENT_EXTRACTION_FAILED`
- `EVIDENCE_RETRIEVAL`
- `SUPERVISOR_ROUTING_DECISION`

All are auditable from `audit_log` keyed by `user_id`, joinable with `documents.id`.

### Existing carve-outs that still apply

- `LOGIN_MFA_BYPASSED` for the synthetic-data demo account — same exception remains, same caveat in HIPAA_COMPLIANCE.md.
- The `EXTRA_USERS_JSON` published TOTP secrets — same exception remains.

---

## 10. Risks and tradeoffs

| Risk | Mitigation | Residual concern |
|---|---|---|
| **VLM hallucinates a field with a high-confidence value.** | Pydantic validates, `fragment_id` mapping shows exactly which text fragment supports the value, the `extraction_warnings` list captures any mismatch the post-extraction validator finds. | A confidently-wrong fragment match is still possible; we mitigate at the eval gate (cases that probe extraction precision). |
| **Cohere Rerank quota exceeded mid-demo.** | Local cross-encoder fallback is wired as a feature flag; flip the env var, redeploy. | Slightly worse rerank quality; documented in cost report. |
| **Document upload bypasses the patient-subject lock.** | Upload endpoint requires `patient_id` from the request body; RBAC checks the calling user is assigned to that patient (same gate `/chat` uses); audit-log records `(user_id, patient_id, document_id)` triple. | A user could upload a document for their assigned patient that contains another patient's data inside the PDF. We can't verify content authorship at v0; flagged for v1 with a "doc-content patient-name match" check. |
| **Supervisor mis-routes** (e.g., calls evidence_retriever when patient question doesn't need guidelines). | Each routing decision is logged with `reason` to Langfuse. Eval cases probe specific routing expectations. | Worst case: extra retrieval cost (~3¢ per query). Not a correctness risk because the answer pipeline still gates on the verifier. |
| **PDF bbox is wrong.** | UI degrades gracefully — bbox-null citations open the page without the rectangle. | Reduced trust signal; user can still verify against the rendered page. |
| **A `docs/golden_w2` regression in CI is from flaky LLM behavior, not real regression.** | Replay cassettes for the LLM calls in CI; only the live-canary path uses real API. Re-record cassettes is an explicit, reviewed step. | Cassette drift over time as we tune prompts; documented refresh procedure. |
| **Document storage outgrows SQLite.** | At demo scale (hundreds of docs), SQLite blob storage is fine. v1 swaps to S3 with the same FK shape; the terraform/ skeleton already provisions an S3 bucket for ALB logs that we'll widen. | Migration when it happens; not a v0 problem. |

---

## 11. Cost and latency budget

### Per-document upload (one-time per doc)

| Step | Latency | Cost |
|---|---|---|
| pdfplumber extraction | <1s for a 5-page PDF | $0 |
| Claude vision call | 5–10s | ~$0.04 (input includes page images + ~2K tokens of fragments; output is small JSON) |
| Schema validation + persist | <100ms | $0 |
| **Per-doc total** | **6–11s** | **~$0.04** |

### Per /chat turn (when documents are involved)

| Step | Latency | Cost |
|---|---|---|
| Supervisor routing | <1s | <$0.005 (small prompt, structured output) |
| Evidence retriever (BM25 + dense + Cohere) | <500ms | $0 (Cohere free tier) |
| Answer pipeline (Week 1) | 5–10s | ~$0.06 (per existing Week 1 cost report) |
| Verifier + per-node spans | <100ms | $0 |
| **Per-turn total** | **6–12s** | **~$0.07** |

### 50-case eval suite

Replay-mode (CI gate): <2 min, $0.
Live-mode (manual canary): ~5 min, ~$3.50 (50 turns × ~$0.07).

### Bottleneck

Anthropic vision latency on extraction is the dominant cost-and-latency line. Mitigation paths if it gets uncomfortable: caching of identical-hash documents; smaller-model fallback for "easy" extractions (e.g., Claude Haiku for short forms); batch upload (process 5 docs in parallel async tasks).

---

## 12. Folder layout

```
agent/
├── schemas/
│   ├── __init__.py
│   ├── citation.py             # Citation, BBox
│   ├── lab.py                  # LabValue, LabReport
│   ├── intake.py               # IntakeForm, Demographics, Allergy, Medication
│   └── document.py             # DocumentMetadata
├── extractors/
│   ├── __init__.py
│   ├── pdf_fragments.py        # pdfplumber → fragments with bboxes
│   ├── lab_extractor.py        # Claude vision → LabReport
│   └── intake_extractor.py     # Claude vision → IntakeForm
├── rag/
│   ├── __init__.py
│   ├── corpus.py               # corpus loader; reads corpus/guidelines/*.md
│   ├── bm25.py                 # sparse index
│   ├── dense.py                # sentence-transformers wrapper
│   └── retriever.py            # hybrid + Cohere Rerank
├── agents/
│   ├── __init__.py
│   ├── supervisor.py           # routing decision + outer graph
│   ├── intake_extractor_worker.py
│   └── evidence_retriever_worker.py
├── documents.py                # upload endpoint, blob storage helpers
└── (existing Week 1 files unchanged)

corpus/
└── guidelines/                 # ~25-35 .md chunks with frontmatter

eval/
├── golden_w2/
│   ├── cases.jsonl             # 50 cases
│   ├── fixtures/               # sample lab_pdfs, intake_forms
│   ├── test_golden.py          # the pytest module that drives the suite
│   ├── check_regression.py     # CI gate logic
│   └── baseline.json           # checked-in baseline pass-rates
└── (existing Week 1 layers unchanged)

ui/src/components/
├── DocumentUploader.tsx        # the upload modal + status chip
├── DocumentViewer.tsx          # PDF + bbox overlay
└── (existing Week 1 components unchanged)

W2_ARCHITECTURE.md              # this file
W2_COST_REPORT.md               # final-submission deliverable
```

---

## 13. Schedule mapping

| Spec checkpoint | Gauntlet deadline | What we ship |
|---|---|---|
| Architecture defense | T+4h from Mon morning | This document, branch `feature/week-2-multimodal` created, schema skeletons + DB migration on the branch |
| MVP | Tue 11:59 PM CT | `attach_and_extract` working end-to-end for both doc types; first hybrid RAG retrieval; first supervisor routing decision logged |
| Early submission | Thu 11:59 PM CT | All 50 golden cases written + scoring; PR-blocking CI gate live; PDF bbox UI overlay; deployed to Railway |
| Final | Sun 12 PM CT | Cost/latency report; 3-5 min demo video; interview-ready talking points; final eval baseline checked in |

---

## 14. What I am not doing differently from Week 1

- **Verifier stays the same.** Two passes, both pure Python, source-id matching + numeric value-tolerance. The new `Citation.source_id` shape extends what the verifier already walks; no new verification logic.
- **Audit log stays the same shape.** New event types are added to the existing `AuditEvent` enum; the table schema is unchanged.
- **Patient subject locking is unchanged.** The new document upload endpoint reuses the same RBAC and patient-assignment gates `/chat` does.
- **The 11-node answer pipeline is unchanged.** It is wrapped as one node in the outer graph, not refactored.

This is deliberate. Week 1 ships 222 passing tests including 13 live LLM cases. Re-architecting the verifier or the answer pipeline because we now have documents would be exactly the kind of "five document types before two work reliably" failure the spec warns against.

---

## 15. Open questions / decisions deferred to later

- **Corpus selection.** Which specific guideline excerpts make the cut for the 25–35 chunks. Will be done as part of MVP step 2; informed by the demo patients we already have.
- **Critic agent (extension).** If time allows after eval gate is solid, a `critic` worker that rejects uncited claims OR unsafe action suggestions before the response is returned. Out of scope for MVP / early submission.
- **3rd document type (extension).** Referral fax or medication list. Out of scope for MVP.
- **Storage migration to AWS.** Documented in the existing terraform/ folder; deferred to v1.

---

**This is the architecture I'll defend. If you push back on any of section 5 (multi-agent), section 6 (RAG), or section 7 (eval gate) I'd rather know now than after I've coded against it.**
