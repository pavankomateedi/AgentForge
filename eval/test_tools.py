"""Tool dispatcher tests — patient subject locking + mock FHIR shape
(ARCHITECTURE.md §2.4, §6.4).

These are async because the dispatcher is async; pytest-asyncio runs them
under the auto-mode set in pyproject.toml.
"""

from __future__ import annotations

import json

import pytest

from agent.tools import (
    PatientSubjectMismatch,
    ToolNotFound,
    execute_tool,
    execute_tools_parallel,
)


# --- Happy paths ---

async def test_get_patient_summary_returns_demo_001_demographics() -> None:
    result = await execute_tool(
        "get_patient_summary",
        {"patient_id": "demo-001"},
        locked_patient_id="demo-001",
    )
    assert result["patient"]["id"] == "demo-001"
    assert result["patient"]["name"] == "Margaret Hayes"
    assert result["patient"]["source_id"] == "patient-demo-001"


async def test_problem_list_includes_source_ids() -> None:
    result = await execute_tool(
        "get_problem_list",
        {"patient_id": "demo-001"},
        locked_patient_id="demo-001",
    )
    ids = {p["source_id"] for p in result["problems"]}
    assert "cond-001-1" in ids


async def test_recent_labs_for_sparse_patient_is_empty() -> None:
    result = await execute_tool(
        "get_recent_labs",
        {"patient_id": "demo-002"},
        locked_patient_id="demo-002",
    )
    assert result["labs"] == []


# --- Patient subject locking — the structural defense ---

async def test_locking_blocks_call_to_different_patient_id() -> None:
    with pytest.raises(PatientSubjectMismatch):
        await execute_tool(
            "get_patient_summary",
            {"patient_id": "demo-002"},
            locked_patient_id="demo-001",
        )


async def test_locking_blocks_when_patient_id_missing() -> None:
    with pytest.raises(PatientSubjectMismatch):
        await execute_tool(
            "get_patient_summary",
            {},
            locked_patient_id="demo-001",
        )


# --- Unknown tool name ---

async def test_unknown_tool_raises() -> None:
    with pytest.raises(ToolNotFound):
        await execute_tool(
            "get_secret_data",
            {"patient_id": "demo-001"},
            locked_patient_id="demo-001",
        )


# --- Unknown patient_id ---

async def test_unknown_patient_id_returns_error_record_not_mismatch() -> None:
    """A locked-but-unknown patient_id is a 'no record' case, not a structural
    failure (since the LLM stayed inside the locked subject)."""
    result = await execute_tool(
        "get_patient_summary",
        {"patient_id": "demo-999"},
        locked_patient_id="demo-999",
    )
    assert "error" in result


# --- Parallel dispatch ---

async def test_execute_tools_parallel_dispatches_in_order() -> None:
    calls = [
        {
            "id": "toolu_1",
            "name": "get_patient_summary",
            "input": {"patient_id": "demo-001"},
        },
        {
            "id": "toolu_2",
            "name": "get_problem_list",
            "input": {"patient_id": "demo-001"},
        },
    ]
    results = await execute_tools_parallel(
        calls, locked_patient_id="demo-001"
    )
    assert [r["tool_use_id"] for r in results] == ["toolu_1", "toolu_2"]
    body0 = json.loads(results[0]["content"])
    assert "patient" in body0


async def test_execute_tools_parallel_marks_subject_mismatch_as_error() -> None:
    calls = [
        {
            "id": "toolu_attack",
            "name": "get_patient_summary",
            "input": {"patient_id": "demo-002"},
        },
    ]
    results = await execute_tools_parallel(
        calls, locked_patient_id="demo-001"
    )
    assert results[0].get("is_error") is True
    assert "REFUSED" in results[0]["content"]
