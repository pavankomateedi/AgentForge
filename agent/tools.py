"""Tool definitions and mock FHIR execution.

Tools never return free text — they return structured records with a `source_id` field
that the verifier later uses to confirm every clinical claim is grounded in real retrieval.

The real FHIR client (against OpenEMR) is a follow-up; this module's interface stays the
same when we swap in the real implementation."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from agent.demo_data import DEMO_PATIENTS


# Map between informal test names the LLM might pass and the
# `lab_history` keys we store. Keep tight — substring matching against
# either the key OR the canonical full name handles the rest.
_LAB_HISTORY_ALIASES: dict[str, str] = {
    "a1c": "a1c",
    "hba1c": "a1c",
    "hemoglobin a1c": "a1c",
    "ldl": "ldl",
    "ldl-c": "ldl",
    "ldl cholesterol": "ldl",
    "creatinine": "creatinine",
    "cr": "creatinine",
    "scr": "creatinine",
    "serum creatinine": "creatinine",
}


def _resolve_lab_history_key(test_name: str) -> str | None:
    """Normalize an LLM-supplied test name to a lab_history dict key.
    Case-insensitive; falls back to substring search across the alias
    keys so 'A1C trend' or 'creatinine level' still resolve."""
    lowered = test_name.lower().strip()
    if lowered in _LAB_HISTORY_ALIASES:
        return _LAB_HISTORY_ALIASES[lowered]
    for alias, key in _LAB_HISTORY_ALIASES.items():
        if alias in lowered:
            return key
    return None


TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_patient_summary",
        "description": (
            "Retrieve patient demographics: name, date of birth, sex, MRN. "
            "Use this for the basic 'who is this patient' fact set. Returns a single record."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient identifier locked to this conversation.",
                },
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_problem_list",
        "description": (
            "Retrieve the patient's active problem list (chronic conditions). "
            "Each entry has an ICD-10 code, description, onset date, and status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_medication_list",
        "description": (
            "Retrieve the patient's active medication list. Each entry has name, dose, "
            "frequency, start date, and prescriber."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_recent_labs",
        "description": (
            "Retrieve recent lab results. Each entry has name, numeric value, unit, "
            "reference range, date, and a flag (normal/high/low)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_recent_encounters",
        "description": (
            "Retrieve the patient's recent encounter history (most recent first). "
            "Each entry has date, encounter type (office visit, telehealth, ER, "
            "hospitalization), provider, chief complaint, and a brief assessment "
            "summary. Use this for follow-up questions like 'what changed since "
            "the last visit?', to find the date of the previous encounter, or "
            "to summarize what was addressed at prior visits."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_lab_history",
        "description": (
            "Retrieve the FULL historical timeline for one specific lab "
            "(or all labs if test_name is omitted). Returns each "
            "measurement as a separate citable record (newest first), "
            "so the agent can reason about and cite individual data "
            "points in a trend. Use this when the user asks about "
            "trajectory, rate of change, or 'is this concerning over "
            "time?'. test_name accepts common aliases — 'A1c', 'HbA1c', "
            "'creatinine', 'LDL', etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "test_name": {
                    "type": "string",
                    "description": (
                        "Lab test name. Optional. Omit to receive every "
                        "available test history."
                    ),
                },
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_changes_since",
        "description": (
            "Return clinical activity for this patient that occurred on "
            "or after `since_date` (ISO YYYY-MM-DD). Surfaces new "
            "problems (by onset_date), new medications (by started "
            "date), new lab measurements (by date), new encounters, and "
            "new uploaded documents — all as separately citable records. "
            "Use this for 'what's changed since their last visit?' or "
            "'what's new since [date]?' style questions instead of "
            "asking the user to scan everything."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "since_date": {
                    "type": "string",
                    "description": (
                        "ISO date YYYY-MM-DD. Records with onset/started/"
                        "date/uploaded_at on or after this date are "
                        "returned."
                    ),
                },
            },
            "required": ["patient_id", "since_date"],
        },
    },
    {
        "name": "get_recent_documents",
        "description": (
            "List uploaded clinical documents for this patient (lab "
            "PDFs, intake forms) with extraction status. Use when the "
            "user asks 'what documents do we have on file?' or wants "
            "to confirm that an uploaded form has been processed. Each "
            "entry has document_id, doc_type, uploaded_at, "
            "extraction_status, and a citable source_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "limit": {
                    "type": "integer",
                    "description": "Max documents to return (default 10).",
                },
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "check_clinical_thresholds",
        "description": (
            "Evaluate the patient's currently retrieved clinical state "
            "against the rule engine — lab thresholds (A1c, LDL, "
            "creatinine), dose ranges (metformin, lisinopril, "
            "atorvastatin, furosemide), and drug interactions. Returns "
            "a list of rule findings with severity, message, and the "
            "evidence_source_ids that triggered each rule. Use this "
            "when the user asks 'are there any safety concerns?' or "
            "'what guidelines does this patient violate?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
            },
            "required": ["patient_id"],
        },
    },
]


class PatientSubjectMismatch(Exception):
    """Raised when a tool is called with a patient_id that doesn't match the conversation's
    locked patient. Structural defense against prompt-injection that tries to redirect the
    agent to a different patient mid-conversation (ARCHITECTURE.md §6.4)."""


class ToolNotFound(Exception):
    """LLM asked for a tool we don't expose."""


async def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    locked_patient_id: str,
) -> dict[str, Any]:
    requested = tool_input.get("patient_id")
    if requested != locked_patient_id:
        raise PatientSubjectMismatch(
            f"Tool {tool_name} called with patient_id={requested!r}, "
            f"conversation is locked to {locked_patient_id!r}."
        )

    record = DEMO_PATIENTS.get(locked_patient_id)
    if record is None:
        return {"error": f"No record found for patient_id {locked_patient_id}"}

    if tool_name == "get_patient_summary":
        return {"patient": record["patient"]}
    if tool_name == "get_problem_list":
        return {"problems": record["problem_list"]}
    if tool_name == "get_medication_list":
        return {"medications": record["medications"]}
    if tool_name == "get_recent_labs":
        return {"labs": record["recent_labs"]}
    if tool_name == "get_recent_encounters":
        # Demo data ships encounters newest-first; the dispatcher
        # preserves that order for the LLM.
        return {"encounters": record.get("recent_encounters", [])}
    if tool_name == "get_lab_history":
        return _execute_get_lab_history(record, tool_input)
    if tool_name == "get_changes_since":
        return _execute_get_changes_since(record, tool_input)
    if tool_name == "get_recent_documents":
        return await _execute_get_recent_documents(
            locked_patient_id, tool_input
        )
    if tool_name == "check_clinical_thresholds":
        return _execute_check_clinical_thresholds(record)

    raise ToolNotFound(f"Unknown tool: {tool_name}")


def _execute_get_lab_history(
    record: dict[str, Any], tool_input: dict[str, Any]
) -> dict[str, Any]:
    history: dict[str, list[dict]] = record.get("lab_history") or {}
    requested = tool_input.get("test_name")
    if requested:
        key = _resolve_lab_history_key(requested)
        if key is None:
            return {
                "test_name": requested,
                "history": [],
                "note": (
                    f"No history available for {requested!r}. Available "
                    f"tests: {sorted(history.keys()) or '[]'}"
                ),
            }
        return {
            "test_name": requested,
            "resolved_test_key": key,
            "history": history.get(key, []),
        }
    # No test_name: return every history we have, keyed by canonical
    # name. Empty dict for sparse patients (e.g. demo-002) is a valid
    # signal that there's no historical data on file.
    return {"all_histories": history}


def _execute_get_changes_since(
    record: dict[str, Any], tool_input: dict[str, Any]
) -> dict[str, Any]:
    from datetime import date

    since_date = tool_input.get("since_date") or ""
    if not isinstance(since_date, str) or len(since_date) < 10:
        return {
            "error": (
                "since_date must be an ISO date string YYYY-MM-DD; "
                f"got {since_date!r}"
            )
        }
    cutoff = since_date[:10]
    try:
        date.fromisoformat(cutoff)
    except ValueError:
        return {
            "error": (
                f"since_date {cutoff!r} is not a valid ISO date "
                "(expected YYYY-MM-DD)"
            )
        }

    def _on_or_after(item: dict, *fields: str) -> bool:
        for f in fields:
            v = item.get(f)
            if isinstance(v, str) and v[:10] >= cutoff:
                return True
        return False

    new_problems = [
        p for p in record.get("problem_list", [])
        if _on_or_after(p, "onset_date")
    ]
    new_medications = [
        m for m in record.get("medications", [])
        if _on_or_after(m, "started")
    ]
    new_labs = [
        lab for lab in record.get("recent_labs", [])
        if _on_or_after(lab, "date")
    ]
    # Also walk lab_history so the agent doesn't miss historical
    # measurements on or after the cutoff that aren't in recent_labs.
    for series in (record.get("lab_history") or {}).values():
        for lab in series:
            if _on_or_after(lab, "date") and lab not in new_labs:
                new_labs.append(lab)
    new_encounters = [
        e for e in record.get("recent_encounters", [])
        if _on_or_after(e, "date")
    ]
    return {
        "since_date": cutoff,
        "new_problems": new_problems,
        "new_medications": new_medications,
        "new_labs": new_labs,
        "new_encounters": new_encounters,
        # new_documents added by the async dispatcher path so we can
        # query the documents table; this purely-FHIR view is the
        # baseline. Documents merge in the wrapper.
    }


async def _execute_get_recent_documents(
    patient_id: str, tool_input: dict[str, Any]
) -> dict[str, Any]:
    """Wraps documents.list_for_patient into a tool-result shape with
    a citable `source_id` per row (`doc-<id>`)."""
    from agent import documents as doc_storage
    from agent.config import get_config

    limit = tool_input.get("limit") or 10
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 10
    config = get_config()
    docs = doc_storage.list_for_patient(config.database_url, patient_id)
    return {
        "documents": [
            {
                "source_id": f"doc-{d.id}",
                "document_id": d.id,
                "doc_type": d.doc_type,
                "uploaded_at": d.uploaded_at.isoformat(),
                "extraction_status": d.extraction_status,
                "extraction_error": d.extraction_error,
                "content_type": d.content_type,
            }
            for d in docs[:limit]
        ],
        "total_count": len(docs),
    }


def _execute_check_clinical_thresholds(record: dict[str, Any]) -> dict[str, Any]:
    """Run the rule engine over the patient's currently-known FHIR data
    and return findings as a serializable list. The engine itself is
    pure; this wrapper just shapes the result for tool_result content."""
    from agent.rules import evaluate_clinical_rules

    # Bundle the patient's records the same way the orchestrator does
    # at retrieval time. The rule engine accepts a "parsed_tool_results"
    # shape — give it one synthesized bundle.
    bundle = [
        {"problems": record.get("problem_list", [])},
        {"medications": record.get("medications", [])},
        {"labs": record.get("recent_labs", [])},
    ]
    findings = evaluate_clinical_rules(bundle)
    return {
        "findings": [
            {
                "rule_id": f.rule_id,
                "category": f.category,
                "severity": f.severity,
                "message": f.message,
                "evidence_source_ids": list(f.evidence_source_ids),
            }
            for f in findings
        ],
        "n_findings": len(findings),
    }


async def execute_tools_parallel(
    tool_calls: list[dict[str, Any]],
    *,
    locked_patient_id: str,
) -> list[dict[str, Any]]:
    """Run all tool_use blocks in parallel; return tool_result content blocks in input order."""

    async def _one(call: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await execute_tool(
                call["name"],
                call["input"],
                locked_patient_id=locked_patient_id,
            )
            return {
                "type": "tool_result",
                "tool_use_id": call["id"],
                "content": json.dumps(result),
            }
        except PatientSubjectMismatch as exc:
            return {
                "type": "tool_result",
                "tool_use_id": call["id"],
                "content": f"REFUSED: {exc}",
                "is_error": True,
            }
        except ToolNotFound as exc:
            return {
                "type": "tool_result",
                "tool_use_id": call["id"],
                "content": str(exc),
                "is_error": True,
            }

    return await asyncio.gather(*(_one(call) for call in tool_calls))
