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


# --- get_recent_encounters (5th tool) ---


async def test_recent_encounters_returns_records_newest_first() -> None:
    """Demo data ships encounters newest-first. The dispatcher must
    preserve that order so the LLM doesn't have to re-sort."""
    result = await execute_tool(
        "get_recent_encounters",
        {"patient_id": "demo-001"},
        locked_patient_id="demo-001",
    )
    assert "encounters" in result
    encounters = result["encounters"]
    assert len(encounters) >= 2
    dates = [e["date"] for e in encounters]
    assert dates == sorted(dates, reverse=True)


async def test_recent_encounters_record_shape() -> None:
    result = await execute_tool(
        "get_recent_encounters",
        {"patient_id": "demo-001"},
        locked_patient_id="demo-001",
    )
    enc = result["encounters"][0]
    # Every field the briefing might cite is present.
    for key in (
        "source_id",
        "date",
        "type",
        "provider",
        "chief_complaint",
        "assessment_summary",
    ):
        assert key in enc, f"missing {key} in encounter record"
    assert enc["source_id"].startswith("enc-001-")


async def test_recent_encounters_locked_to_subject() -> None:
    """The 5th tool must respect patient subject locking like the
    others. Cross-patient call → mismatch raised."""
    with pytest.raises(PatientSubjectMismatch):
        await execute_tool(
            "get_recent_encounters",
            {"patient_id": "demo-002"},
            locked_patient_id="demo-001",
        )


async def test_recent_encounters_for_sparse_patient_returns_what_exists() -> None:
    """demo-002 has only one stale encounter — must return it, not
    fabricate recency by returning empty."""
    result = await execute_tool(
        "get_recent_encounters",
        {"patient_id": "demo-002"},
        locked_patient_id="demo-002",
    )
    assert len(result["encounters"]) == 1
    assert result["encounters"][0]["date"] == "2024-08-22"


async def test_demo_003_encounter_trajectory_is_sequential() -> None:
    """Sanity: the trend-supporting encounters for demo-003 cover the
    A1c progression. The agent uses these dates to compute deltas in
    a UC-6 follow-up."""
    result = await execute_tool(
        "get_recent_encounters",
        {"patient_id": "demo-003"},
        locked_patient_id="demo-003",
    )
    encounters = result["encounters"]
    assert len(encounters) == 3
    assert encounters[0]["date"] == "2026-04-12"  # newest
    assert encounters[-1]["date"] == "2025-04-18"  # oldest of the three


def test_get_recent_encounters_is_in_tools_schema() -> None:
    from agent.tools import TOOLS

    names = {t["name"] for t in TOOLS}
    assert "get_recent_encounters" in names
    schema = next(t for t in TOOLS if t["name"] == "get_recent_encounters")
    # Same input contract as the other 4: patient_id is the only required field.
    assert schema["input_schema"]["required"] == ["patient_id"]


def test_role_whitelist_includes_encounters_for_all_roles() -> None:
    """Encounters / visit summaries are within nurse + resident scope
    (per agent/rbac.py docstring); diagnostic ICD-10 codes remain
    physician-only."""
    from agent.rbac import ROLE_NURSE, ROLE_PHYSICIAN, ROLE_RESIDENT, allowed_tool_names

    for role in (ROLE_PHYSICIAN, ROLE_NURSE, ROLE_RESIDENT):
        assert "get_recent_encounters" in allowed_tool_names(role), (
            f"role {role} should see encounters"
        )
