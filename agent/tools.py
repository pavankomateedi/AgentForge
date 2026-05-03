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

    raise ToolNotFound(f"Unknown tool: {tool_name}")


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
