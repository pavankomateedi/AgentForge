"""Run the golden suite: load cases, synthesize responses, score, aggregate.

Stage 4 ships this with a `synthesize_response` function that builds
realistic, citation-rich ChatResponse payloads for each case template.
The Week 1 verifier is invoked on the synthesized response so a bug
in the verifier reduces the `factually_consistent` pass rate — that's
the regression-detection mechanism.

A future tier (cassette-replay) would swap `synthesize_response` for
a real-LLM call captured under `eval/replay/cassettes/`; the rubric +
runner shape stays unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.demo_data import DEMO_PATIENTS
from agent.verifier import build_record_index, verify_response
from eval.golden_w2.rubric import CaseScore, score_case

CASES_PATH = Path(__file__).parent / "cases.jsonl"
BASELINE_PATH = Path(__file__).parent / "baseline.json"


def load_cases() -> list[dict]:
    cases = []
    for line in CASES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        cases.append(json.loads(line))
    return cases


# ---- Response synthesis (one shape per template) ----


def _patient_record(patient_id: str) -> dict:
    """Pick one real source_id from the demo_data so the verifier can
    walk it. Tries labs -> meds -> problems -> encounters in order."""
    record = DEMO_PATIENTS.get(patient_id)
    if not record:
        return {"source_id": f"summary-{patient_id}", "value": None}
    labs = record.get("recent_labs") or []
    if labs:
        lab = labs[0]
        return {
            "source_id": lab["source_id"],
            "test_name": lab.get("name") or lab.get("test_name"),
            "value": lab["value"],
            "unit": lab.get("unit"),
        }
    for cat in ("medications", "problem_list", "recent_encounters"):
        items = record.get(cat) or []
        if items and "source_id" in items[0]:
            return {"source_id": items[0]["source_id"], "value": None}
    return {"source_id": f"summary-{patient_id}", "value": None}


def _build_verification(
    response_text: str, retrieved_records: list[dict]
) -> dict:
    """Run the Week 1 verifier on the synthetic response. Returns the
    serialized verification block for trace.verification."""
    record_index = build_record_index(retrieved_records)
    retrieved_ids = {r["source_id"] for r in retrieved_records}
    v = verify_response(
        response_text=response_text,
        retrieved_source_ids=retrieved_ids,
        record_index=record_index,
    )
    return {
        "passed": v.passed,
        "note": v.note,
        "cited_ids": list(v.cited_ids),
        "unknown_ids": list(v.unknown_ids),
        "value_mismatches": [
            {
                "source_id": mm.source_id,
                "cited_value": mm.cited_value,
                "record_value": mm.record_value,
            }
            for mm in v.value_mismatches
        ],
    }


def _ok_trace(
    *, retrieved_source_ids: list[str], verification: dict
) -> dict:
    return {
        "trace_id": "synthetic-trace-id",
        "trace_url": None,
        "plan_tool_calls": [],
        "retrieved_source_ids": retrieved_source_ids,
        "verification": verification,
        "rule_findings": [],
        "regenerated": False,
        "refused": False,
        "refusal_reason": "",
        "timings_ms": {"first_byte_ms": 100, "total_ms": 1500},
        "usage": {
            "plan": {"input_tokens": 100, "output_tokens": 50,
                     "cache_creation_input_tokens": 0,
                     "cache_read_input_tokens": 0},
            "reason": {"input_tokens": 200, "output_tokens": 150,
                       "cache_creation_input_tokens": 0,
                       "cache_read_input_tokens": 0},
        },
        "multi_agent": None,
    }


def _refusal_trace(reason: str) -> dict:
    return {
        "trace_id": "synthetic-trace-id",
        "trace_url": None,
        "plan_tool_calls": [],
        "retrieved_source_ids": [],
        "verification": None,
        "rule_findings": [],
        "regenerated": False,
        "refused": True,
        "refusal_reason": reason,
        "timings_ms": {"first_byte_ms": 80, "total_ms": 200},
        "usage": {
            "plan": {"input_tokens": 50, "output_tokens": 20,
                     "cache_creation_input_tokens": 0,
                     "cache_read_input_tokens": 0},
            "reason": {"input_tokens": 0, "output_tokens": 0,
                       "cache_creation_input_tokens": 0,
                       "cache_read_input_tokens": 0},
        },
        "multi_agent": None,
    }


def synthesize_response(case: dict) -> dict:
    """Build a realistic ChatResponse for the case template. Citations
    point at REAL FHIR/guideline source_ids so the Week 1 verifier
    runs on real data."""
    template = case["response_template"]

    if template.startswith("refusal_"):
        reason = "off-topic" if "offtopic" in template else "unassigned"
        text = (
            f"I can't help with that — this assistant is scoped to clinical "
            f"questions for patients you're assigned to. ({reason})"
        )
        return {
            "response": text,
            "verified": True,
            "trace": _refusal_trace(reason),
        }

    p = case["patient_id"]
    rec = _patient_record(p)
    sid = rec["source_id"]

    if template == "good_briefing":
        text = (
            f"Patient overview based on chart data. "
            f"<source id='{sid}'/> Recent labs and conditions on file are "
            f"consistent with the active problem list. "
            f"See the chart for full history."
        )
        verification = _build_verification(text, [{"source_id": sid}])
        return {
            "response": text, "verified": verification["passed"],
            "trace": _ok_trace(
                retrieved_source_ids=[sid], verification=verification
            ),
        }

    if template == "good_lab_answer":
        if rec.get("test_name") and rec.get("value") is not None:
            text = (
                f"Latest {rec['test_name']}: {rec['value']}"
                f"{(' ' + rec['unit']) if rec.get('unit') else ''}. "
                f"<source id='{sid}'/>"
            )
        else:
            text = (
                f"No structured lab result available — refer to the chart. "
                f"<source id='{sid}'/>"
            )
        verification = _build_verification(text, [{"source_id": sid}])
        return {
            "response": text, "verified": verification["passed"],
            "trace": _ok_trace(
                retrieved_source_ids=[sid], verification=verification
            ),
        }

    if template == "good_med_answer":
        record = DEMO_PATIENTS.get(p, {})
        meds = record.get("medications") or []
        med_sid = (meds[0]["source_id"] if meds and "source_id" in meds[0] else sid)
        text = (
            f"Medication list per chart. "
            f"<source id='{med_sid}'/>"
        )
        verification = _build_verification(text, [{"source_id": med_sid}])
        return {
            "response": text, "verified": verification["passed"],
            "trace": _ok_trace(
                retrieved_source_ids=[med_sid], verification=verification
            ),
        }

    if template == "good_guideline":
        # Cite a real guideline chunk_id from the corpus.
        guideline_id = "ada-2024-a1c-targets"
        text = (
            f"Per current guidance, the recommended approach for this "
            f"patient supports the documented plan. "
            f"<source id='{sid}'/> "
            f"<source id='{guideline_id}'/>"
        )
        verification = _build_verification(
            text, [{"source_id": sid}, {"source_id": guideline_id}]
        )
        return {
            "response": text, "verified": verification["passed"],
            "trace": _ok_trace(
                retrieved_source_ids=[sid, guideline_id],
                verification=verification,
            ),
        }

    raise ValueError(f"unknown template: {template!r}")


# ---- Runner entrypoint ----


def run(*, mutate: dict[str, Any] | None = None) -> list[CaseScore]:
    """Run all cases. `mutate` lets tests inject a regression — e.g.,
    {"strip_citations": True} to test that citation_present catches it.
    """
    cases = load_cases()
    scores: list[CaseScore] = []
    for case in cases:
        response = synthesize_response(case)
        if mutate:
            response = _apply_mutation(response, mutate)

        # The "audit details" we'd grep for PHI: build from what the
        # /chat endpoint logs in real life. We emulate by including
        # only structural keys.
        audit_details = [
            {
                "patient_id": case["patient_id"],
                "message_len": len(case["user_message"]),
                "trace_id": response["trace"]["trace_id"],
                "verified": response["verified"],
                "refused": response["trace"]["refused"],
            }
        ]

        score = score_case(
            case_id=case["id"],
            response_payload=response,
            audit_details=audit_details,
            expected_rubric=case["expected_rubric"],
            expects_refusal=case["expects_refusal"],
            min_cited_count=case["expected_signals"].get("min_cited_count", 0),
            phi_markers=case["phi_markers"],
            expected_signals=case["expected_signals"],
        )
        scores.append(score)
    return scores


def _apply_mutation(response: dict, mutate: dict[str, Any]) -> dict:
    """Synthetic regressions for testing the gate's catch-rate."""
    if mutate.get("strip_citations"):
        import re

        response["response"] = re.sub(
            r"<source\b[^>]*/?>", "", response["response"]
        )
    if mutate.get("break_verifier"):
        if response["trace"].get("verification"):
            response["trace"]["verification"]["passed"] = False
            response["trace"]["verification"]["note"] = "synthetic regression"
    if mutate.get("leak_phi_marker"):
        # Inject a known PHI string into the audit-emulation path —
        # the runner builds audit_details from response, so we'd need
        # to mutate audit_details directly. Easier: stash in trace.
        response["trace"]["__leaked_phi"] = mutate["leak_phi_marker"]
    if mutate.get("flip_refusal"):
        response["trace"]["refused"] = not response["trace"]["refused"]
    return response
