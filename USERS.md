# Users — Clinical Co-Pilot

This document defines the target user, the moment in their day when the Co-Pilot enters, and the specific use cases the agent will serve. Per the case study, every capability built in `ARCHITECTURE.md` must trace back to a use case here. Capabilities not justified by a use case are not built.

---

## Target User

**Dr. Maya Chen, MD — Primary Care Physician at a mid-sized outpatient clinic.**

- 8 years post-residency, internal medicine, 0.8 FTE clinical.
- Panel of ~1,400 patients; sees about 20 per clinic day.
- Patients skew older (median age 58), multi-comorbid, polypharmacy common.
- Uses OpenEMR daily. Comfortable with computers, not interested in tools that require special training.
- Has been burned by a previous "AI scribe" pilot that hallucinated a medication. Trust is the whole game for her.

Why this persona and not the others (ED resident, hospitalist):

- **PCPs see the same patients repeatedly.** "What changed since last visit" is a question that has a meaningful answer, and the agent's job is well-defined: surface the delta. For an ED resident seeing undifferentiated patients for the first time, the question is "what is this person?" — a fundamentally harder retrieval problem with a different evidence base.
- **The 90-second window is real and recurring.** A PCP hits this gap 20 times a day. A hospitalist hits it 12 times a morning. An ED resident hits a different problem (acute triage). The PCP's pain is the most directly addressable with structured data retrieval, which is what we have.
- **The data model favors us.** Outpatient continuity data — meds, labs, problem list, last visit — is exactly the data OpenEMR's FHIR API exposes well. Inpatient hospital course data is poorly modeled in OpenEMR; ED triage data isn't really represented.

This persona maximizes the alignment between the case study's "90 seconds between rooms" framing, the data we can actually retrieve cleanly, and the user's reason to trust a verified-grounded agent.

---

## A Day in Dr. Chen's Workflow

### 7:30 AM — Arrive

Coffee, check today's schedule. 22 patients, including 3 same-day add-ons, 1 new patient, and 18 returning. She has not seen 9 of these returning patients in over six months.

### 7:45–8:15 AM — Chart Prep ("Pre-Visit Planning")

Currently, she opens each chart, scans the last note, eyeballs the medication list, looks for any new labs or messages. She gets through about half the panel before the first patient arrives. The half she didn't pre-prep, she'll prep in the 90 seconds before the room.

**This is where the Co-Pilot earns its keep.**

### 8:15 AM — First Patient

She walks toward exam room 3, taps the patient's name in OpenEMR, and has 60–90 seconds before opening the door. Her question is rarely "tell me everything." It is one of:
- "Why are they here today?"
- "Anything important happen since I last saw them?"
- "Is there anything I'm going to forget to address?"

### Throughout the Day

Between every patient: a similar 60–90 second window. Every visit produces follow-ups (orders, refills, referrals). Documentation accrues. By 5 PM she has 8 unfinished notes; by 7 PM, "pajama time" — finishing notes from home.

### Pain Points the Co-Pilot Targets

| Pain | Frequency | Current workaround |
|---|---|---|
| Can't remember what changed since last visit | Every patient | Read the last note; hope she wrote it well |
| Lab trends require flipping screens | 5–10× per day | Open separate tab to flowsheet |
| Med list shows what's prescribed, not what's actually being taken | Every visit | Ask the patient |
| Overnight ED visits surface late or not at all | 2–3× per week | Catch-up at a later visit |
| Specialist letters buried in documents tab | Multiple per day | Skip unless something prompts her to look |

### Pain Points Explicitly Out of Scope

- Note documentation / scribe functionality. (Different agent, different verification model.)
- Order entry. Anything that writes back to the EMR is week 2/3.
- Generic medical reference ("what's the dose of metformin?"). UpToDate exists; we don't compete with it.
- Real-time clinical decision support during the visit. The Co-Pilot is for the moment _before_ the room, not for inside the room.

---

## Use Cases

Each use case below specifies (a) the trigger, (b) what the agent does, (c) why a conversational agent is the right shape — and not a dashboard, sorted list, or chart-view improvement.

### UC-1: Pre-Visit Briefing

**Trigger.** Dr. Chen clicks the patient on her schedule and types "brief me" or simply opens the Co-Pilot panel for that patient. Time budget: ~5 seconds to first useful content; ~15 seconds to complete answer.

**What the agent does.** Returns a 4–6 line briefing covering: reason for today's visit (from appointment), most recent encounter date and gist, problem list highlights (filtered by what's most likely relevant to today), any new labs since last visit, current med list with any changes since last visit, and any flags (overdue screening, missed appointment, ED visit).

**Why an agent and not a dashboard.** A dashboard requires Dr. Chen to know what to look for. The clinically-relevant signal differs per patient: for a diabetic with a new A1c, the A1c is the headline; for a CHF patient with weight changes, weight is the headline; for a stable hypertensive, "nothing changed" is the headline and is itself useful. A static dashboard treats every field as equally important and forces her to scan. The agent's job is the triage.

**Why this can't just be a "summary" generated server-side and shown statically.** Because she will follow up. ("What was that A1c again? Trend over the last year?") That follow-up is the agent's reason for being conversational.

**Tools required.** `get_patient_summary`, `get_problem_list`, `get_medication_list`, `get_recent_labs`, `get_recent_encounters`, `get_appointment_for_today`. Several are parallelizable.

**Verification requirements.** Every fact in the briefing must be source-attributed (patient record id + retrieval timestamp). The "any flags" section must distinguish between "data says X" and "data is silent on X."

### UC-2: What Changed Since Last Visit

**Trigger.** "What's new since I last saw her?" — typed or follow-up after UC-1.

**What the agent does.** Calls `get_recent_encounters` to anchor the previous visit's date and assessment, then walks `get_recent_labs` and `get_medication_list` for entries dated after that anchor. Surfaces only the changes: a new lab outside reference range, a new or stopped medication, a problem flagged at the prior assessment that now has a different status. Refills are not changes; dose adjustments are.

**Why an agent.** This requires reasoning over time and across data types. A "recent activity" feed dumps everything chronologically; the agent decides what counts as a meaningful change. The conversational shape matters because the user's natural follow-up ("just tell me what's new about the diabetes") narrows scope mid-conversation in a way a static dashboard can't.

**Tools required.** `get_recent_encounters` (anchors the date), `get_recent_labs`, `get_medication_list`, `get_problem_list`. Date math happens in the Reason node — the demo FHIR layer doesn't expose `_since` endpoints, mirroring the typical OpenEMR FHIR surface.

**Verification requirements.** The "since [date]" anchor is a citation: the encounter record's `source_id` must appear with the date. Any "change" claim must cite both the current record and reference the anchor encounter, so the verifier can confirm the comparison is grounded in two real retrievals rather than one real and one hallucinated baseline.

### UC-3: Lab Interpretation in Context

**Trigger.** "Is this A1c trend concerning?" or "What's been happening with her creatinine?"

**What the agent does.** Pulls the labs (`get_recent_labs`) and uses prior conversation turns (carried in `ChatRequest.history`) to know which lab the user means without the user having to repeat it. Shows the values with dates and reference ranges, applies the deterministic rule engine (e.g. `A1C_ABOVE_GOAL`, `CREATININE_ELEVATED`), and presents direction + magnitude. Correlates with `get_medication_list` and `get_problem_list` for context — a rising creatinine on metformin in a known-CKD patient is meaningfully different from the same trajectory in someone with no kidney history.

**Why an agent.** Interpretation requires correlating multiple data sources and applying domain rules — exactly what `agent/rules.py` was built for. A static graph shows the values; the agent shows the values plus the rule-based flag plus the cross-rule (e.g. `METFORMIN_RENAL_CONTRAINDICATION`) that turns "creatinine elevated" into "this patient should not be on metformin."

**Tools required.** `get_recent_labs`, `get_medication_list`, `get_problem_list`. Rule engine runs automatically as a graph node after retrieval — not a tool the LLM picks, but a deterministic input it always receives.

**Verification requirements.** Direction claims ("trending up") are verifiable from the data points (the verifier's value-tolerance check enforces accuracy on each cited number). Threshold claims must reference a `rule_findings` entry; inventing thresholds the rule engine didn't produce is forbidden by the Reason prompt and audit-able from the trace. The agent provides evidence and rule-based flags; clinical recommendations remain physician-owned.

### UC-4: Medication Reconciliation

**Trigger.** "What is she actually on?"

**What the agent does.** Synthesizes the active medication list from prescriptions, flags any disagreements with recently imported records (hospital discharge, specialist letters), and surfaces the date and prescriber for each medication. If a medication appears in one source but not another, that conflict is shown explicitly.

**Why an agent.** Medication reconciliation is fundamentally a reasoning-over-conflicting-sources problem. The current EMR shows the prescription list; it does not surface that the discharge summary lists a different dose. A list view treats every entry as authoritative; the agent reasons about provenance and conflict.

**Tools required.** `get_active_medications`, `get_recent_documents` (for discharge summaries), `get_medication_history`. RxNorm normalization is a stretch goal — without it, name-string matching is brittle.

**Verification requirements.** Every medication claim cites its source record and source date. Conflicts must be explicit, not silently resolved. If a medication can't be confirmed in a structured record, the agent says so.

### UC-5: Authorization Boundary (Refusal Test)

**Trigger.** A user (e.g., a medical assistant role with limited patient access) asks the agent about a patient outside their assigned panel, or asks about data they aren't permitted to see.

**What the agent does.** The FHIR API returns 403; the agent surfaces a refusal that explains _that_ access was denied without leaking _what_ would have been there. It does not retry, does not infer, does not synthesize from cached context.

**Why this is a use case, not just a test.** The case study explicitly calls out multi-user environments as the norm. Demonstrating that the auth boundary holds — visibly, in the product — is part of the trust model the user (and a hospital CTO) must see working. This use case has zero LLM cleverness; it is mostly a UX problem (how to refuse helpfully) and an architectural one (the agent never sees data it shouldn't).

**Tools required.** Any retrieval tool, all of which propagate the 403.

**Verification requirements.** The verification layer must catch any attempted response that includes information from a denied resource — even if cached from an earlier turn under a different identity. Session boundaries must be enforced.

### UC-6: Encounter Review

**Trigger.** "What did we discuss at the last visit?" or "Pull up the last encounter note." Often asked _during_ the room when the patient says "the doctor told me last time…" and Dr. Chen needs to verify the prior plan.

**What the agent does.** Calls `get_recent_encounters` and surfaces the most recent visit's date, type, chief complaint, and assessment summary verbatim — no synthesis. If the user follows up with "and the visit before that?", carries the conversation forward via the `history` field and surfaces the second-most-recent encounter using the same encounter records already retrieved.

**Why an agent.** A flowsheet view shows dates but not content. The note tab shows content but the most recent note may be 30 seconds away from open in a slow EMR. The agent answers in one breath, with the structured fields at hand and inline citations the clinician can click through to the note itself.

**Why this isn't UC-2.** UC-2 reasons across data types to compute a delta. UC-6 reads back what was already said — no comparison, no rule engine. Same `get_recent_encounters` tool, different question shape.

**Tools required.** `get_recent_encounters` (always), optionally `get_medication_list` if the user asks "and what did we change?" as a follow-up.

**Verification requirements.** Every quoted phrase from the assessment summary must cite the encounter's `source_id`. The agent does not paraphrase the assessment summary in a way that could change clinical meaning — direct quotes only when the user is asking for a recap. The verifier's source-id matching pass is the enforcement point.

### UC-7: Multi-Turn Trend Reasoning

**Trigger.** A two-or-three-turn exchange. Turn 1: "Brief me on Robert Mitchell." (UC-1.) Turn 2: "Wait, his creatinine — has that been trending up?" Turn 3: "Should the metformin be reconsidered?"

**What the agent does.** Each turn is a fresh retrieval bound to the current question, but the conversational `history` carries forward so turn 2 knows "his" refers to Robert Mitchell and turn 3 knows "the metformin" refers to the medication just surfaced. Turn 2 cites the lab time series + the rule engine's `CREATININE_ELEVATED` finding. Turn 3 cites the rule engine's `METFORMIN_RENAL_CONTRAINDICATION` cross-rule finding and provides the evidence — without making the prescribing recommendation itself, which stays physician-owned.

**Why an agent.** A single-turn summary cannot anticipate the follow-up. A static dashboard cannot resolve "his" or "the metformin" — those are pronouns the user expects the system to bind from context. This is the use case that most directly justifies the conversational shape.

**Why this isn't UC-3.** UC-3 is one turn. UC-7 is two-or-three turns where each turn re-retrieves and the cross-turn coherence is the user-visible value. The 8-turn server-side history cap (`MAX_HISTORY_TURNS`) was sized for this case.

**Tools required.** Spans the same toolset as UC-1+UC-3: `get_patient_summary`, `get_problem_list`, `get_medication_list`, `get_recent_labs`, `get_recent_encounters`. The rule engine runs on every turn's retrieval.

**Verification requirements.** The verifier runs on every turn independently — turn 2's response cannot cite a `source_id` from turn 1's retrieval bundle. The locked `patient_id` survives across turns; if the user pivots to a different patient, the UI flushes history (different conversation). The audit log records `history_len` per turn so a multi-turn session can be reconstructed end-to-end.

---

## Capability → Use Case Trace

| Capability | Implementation | Justifying use cases |
|---|---|---|
| Multi-turn conversation | `ChatRequest.history` → graph state → Plan + Reason | UC-1 → UC-2, UC-3, UC-6, **UC-7** |
| Conversation memory within session | UI keeps last 8 turns; server caps to MAX_HISTORY_TURNS=8 | UC-2, UC-3, UC-6, **UC-7** |
| Tool chaining (parallel) | `execute_tools_parallel` + Plan prompt nudges parallel calls | UC-1 (4-tool fan-out), UC-2 (encounters + labs + meds), UC-7 |
| Encounter retrieval | `get_recent_encounters` (5th tool) | UC-1, UC-2, **UC-6**, UC-7 |
| Source attribution | `verifier.py` source-id matching pass | All use cases |
| Numeric value-tolerance check | `verifier.py` value-tolerance pass | UC-3, UC-7 (any numeric trend claim) |
| Domain rule engine | `agent/rules.py` runs as a graph node every turn | UC-3, UC-4, UC-7 |
| Patient subject locking | `agent/tools.py` structural enforcement | All use cases (defense against UC-7 cross-patient pivot) |
| RBAC + assignment gate | `agent/rbac.py` + `/chat` upstream check | UC-5 (and pre-empts UC-1–7 for unassigned patients) |
| Refusal handling | `refuse_*` terminal nodes in `agent/graph.py` | UC-5; also UC-1–7 when data is missing or unverified |
| Audit trail | `agent/audit.py` append-only log + Langfuse trace per turn | All use cases (per `HIPAA_COMPLIANCE.md` §164.312(b)) |

If `ARCHITECTURE.md` proposes a capability not in this table, it gets cut.

---

## Authorization Model (v0)

The persona above (Dr. Maya Chen) is the target _clinical_ user. The
system also has a concrete _operational_ authorization model — three
roles, a role-to-tool whitelist, a per-user patient-assignment gate,
and a documented MFA carve-out for synthetic-data demo accounts.

### Roles and tool whitelist

Source of truth: [`agent/rbac.py`](./agent/rbac.py). The agent's Plan
node sees only the subset of tools allowed for the caller's role —
the LLM literally cannot invoke a tool its role isn't permitted to.

| Tool | Physician | Nurse | Resident |
|---|---|---|---|
| `get_patient_summary` | ✅ | ✅ | ✅ |
| `get_problem_list` | ✅ | ❌ | ✅ |
| `get_medication_list` | ✅ | ✅ | ✅ |
| `get_recent_labs` | ✅ | ✅ | ✅ |
| `get_recent_encounters` | ✅ | ✅ | ✅ |

Why nurse is excluded from `get_problem_list`: ICD-10 diagnostic
coding is physician-scope in the institutional pattern this
implementation models. Visit-summary access via
`get_recent_encounters` IS within nurse scope (intake, triage,
follow-up calls), which is why that tool is enabled for all three
roles. The resident role is physician-equivalent for tool access but
**every response is watermarked** "supervised review recommended" by
[`agent/main.py`](./agent/main.py) so downstream consumers know the
briefing came from a trainee.

### Patient assignment gate

`/chat` upstream of the orchestrator: if the caller is not assigned
to the requested patient, the request is **refused with 403
`CHAT_REFUSED_UNASSIGNED`** and the LLM never runs. Assignments live
in `patient_assignments` (composite PK on user_id, patient_id) and
are seeded by the bootstrap below. A physician with zero assignments
gets backfilled to all 5 demo patients on the next cold start to
preserve the demo flow; nurse and resident assignments are explicit
only.

### MFA model and the documented carve-out

Default: **MFA mandatory.** Every account goes through TOTP
enrollment on first login and a TOTP challenge on every subsequent
login before any `/chat` access. Secret stored per-user, never logged.

Carve-out: a single account flagged `bypass_mfa: true` in
`EXTRA_USERS_JSON` lands in the workspace with password only. Used
only on **synthetic-data demo deployments** for the operator's
daily-use account. Every bypass login emits a distinct
`LOGIN_MFA_BYPASSED` audit row so the carve-out is queryable from
the trail rather than silent. Documented in
[`HIPAA_COMPLIANCE.md` §164.312(d)](./HIPAA_COMPLIANCE.md) and
**must be removed before this deployment is allowed to process real
PHI**.

### Demo accounts on the live deployment

Three accounts ship via the `EXTRA_USERS_JSON` bootstrap. All three
exist purely to exercise the authorization model on the live URL —
the deployment holds **zero real PHI**.

| Account | Role | Patients | Auth mode | Purpose |
|---|---|---|---|---|
| `dr.pavan` | physician | all 5 | **password only** (`bypass_mfa: true`) | Operator's daily-use account; demonstrates UC-1 → UC-7 with no MFA friction |
| `grader.demo` | physician | all 5 | password + TOTP (pre-enrolled) | Hand-off account for graders / reviewers; pre-enrolled so the MFA challenge is a 6-digit code computed from a published TOTP secret, not a QR-scan ceremony |
| `nurse.adams` | nurse | demo-001 only | password + TOTP (pre-enrolled) | Exercises the RBAC refusal path: same UI, but `/chat` 403s for demo-002–005. Also has a smaller tool set (no problem list) so the agent's plan-node fan-out is observably different |

Passwords and TOTP secrets are published in [README.md](./README.md)
"Grader credentials" section because the data is synthetic; this
publication pattern is itself documented as a §164.312(d) carve-out.
End-to-end pinned by [`eval/test_published_grader_credentials.py`](./eval/test_published_grader_credentials.py)
and [`eval/test_bypass_mfa.py`](./eval/test_bypass_mfa.py) so a typo
in the README fails CI rather than reaching the deployment.

### What this enables for the use cases

- **UC-1 → UC-7** (Dr. Chen persona) run cleanly under `dr.pavan` for daily operator use, or under `grader.demo` for an external reviewer who follows the README's MFA flow.
- **UC-5 (Authorization Boundary)** is concretely demonstrable on the live URL by signing in as `nurse.adams` and trying to `/chat` about `demo-003` — the 403 + audit row is the visible artifact the case study calls for.

---

## Out of Scope (Capabilities Not Justified)

These are tempting but do not yet have a use case:

- **Multi-patient queries** ("show me all my diabetics with rising A1c"). Powerful but a different product surface; needs its own user research.
- **Long-term memory across sessions.** The agent is per-conversation. Cross-conversation memory introduces consent, retention, and stale-context risks not addressed in the data model.
- **Proactive notifications.** "Push" surface, different UX, different consent model.
- **Voice input.** Until measured, we don't know whether 90-second-window users prefer typing or talking. Default: typing, because typing is silent and the room is across the hall.

---

## Acceptance Criteria for Each Use Case

Each use case must, in evaluation:

1. Return a response in which every clinical claim is source-attributed.
2. Distinguish present / absent / conflicting data.
3. Refuse — visibly — when data is unavailable or access is denied.
4. Hit latency targets: first content < 5s for UC-1; full response < 15s for any use case.
5. Pass adversarial prompts that try to extract data outside the user's authorization scope.

These criteria become the eval suite specified in `ARCHITECTURE.md`.

---
