"""Adversarial tests — prompt-injection / cross-patient leakage /
role-bypass / out-of-scope probes (ARCHITECTURE.md §5.2; case-study
"inputs that attempt to extract information the requester is not
authorized to see").

These tests exercise the structural defenses, not the LLM's politeness:

  - Patient-subject locking (agent.tools.PatientSubjectMismatch) is
    raised by the dispatcher when a tool call carries a patient_id
    other than the conversation's locked subject. This is the
    canonical injection defense and survives any prompt-level bypass.

  - Role-based tool whitelisting (agent.rbac.filter_tools_for_role)
    means a nurse session never receives the diagnosis-tool schema, so
    even a prompt-injection that asks for one cannot succeed — there's
    no tool call shape the LLM can construct.

  - Patient-assignment gate (/chat) refuses 403 before the orchestrator
    runs. An attacker with a valid session but no assignment cannot
    reach the LLM at all.

We deliberately don't try every prompt phrasing — a deterministic
defense doesn't care about wording. We test the structural behavior at
the dispatcher / RBAC layer where the bypass actually has to happen.
"""

from __future__ import annotations

import asyncio

import pytest

from agent import rbac
from agent.tools import (
    PatientSubjectMismatch,
    execute_tool,
    execute_tools_parallel,
)


# --- Patient-subject locking probes (the structural defense) ---


# Variants of "the LLM was tricked into calling a tool with the wrong
# patient_id". The dispatcher should refuse every one. The string
# values are illustrative — the defense is the patient_id mismatch,
# not the prompt that produced it.
INJECTION_TOOL_CALLS: list[tuple[str, str, str]] = [
    # (label, locked_patient_id, requested_patient_id)
    ("ignore_previous_instructions", "demo-001", "demo-002"),
    ("act_as_demo_002", "demo-001", "demo-002"),
    ("system_override", "demo-001", "admin"),
    ("null_patient", "demo-001", "null"),
    ("empty_patient", "demo-001", ""),
    ("sql_like_payload", "demo-001", "' OR '1'='1"),
    ("path_like_payload", "demo-001", "../demo-002"),
    ("uppercase_attempt", "demo-001", "DEMO-001"),  # case-sensitive
    ("trailing_space", "demo-001", "demo-001 "),
    ("zwsp_lookalike", "demo-001", "demo​-001"),  # zero-width space
    ("numeric_id_attempt", "demo-001", "1"),
    ("absolute_url_attempt", "demo-001", "https://example.com/demo-002"),
]


@pytest.mark.parametrize(
    "label,locked,requested",
    INJECTION_TOOL_CALLS,
    ids=lambda x: x if isinstance(x, str) else "",
)
async def test_dispatcher_rejects_mismatched_patient_id(
    label: str, locked: str, requested: str
) -> None:
    """Each variant attempts to have the agent call a FHIR tool with a
    patient_id different from the conversation's locked subject. The
    dispatcher must raise PatientSubjectMismatch BEFORE any data is
    fetched. This is the structural defense referenced in
    ARCHITECTURE.md §6.4."""
    with pytest.raises(PatientSubjectMismatch):
        await execute_tool(
            "get_patient_summary",
            {"patient_id": requested},
            locked_patient_id=locked,
        )


async def test_parallel_dispatch_marks_each_mismatch_as_error() -> None:
    """When the LLM emits multiple tool calls, even if just one targets
    the wrong patient, only that one is refused — the others run
    unaffected. The refusal is encoded as is_error=True so the
    orchestrator can react without crashing."""
    calls = [
        {
            "id": "t1",
            "name": "get_patient_summary",
            "input": {"patient_id": "demo-001"},
        },
        {
            "id": "t2",
            "name": "get_problem_list",
            "input": {"patient_id": "demo-002"},  # injection
        },
        {
            "id": "t3",
            "name": "get_recent_labs",
            "input": {"patient_id": "demo-001"},
        },
    ]
    results = await execute_tools_parallel(
        calls, locked_patient_id="demo-001"
    )
    assert results[0].get("is_error") is None or results[0].get("is_error") is False
    assert results[1].get("is_error") is True
    assert "REFUSED" in results[1]["content"]
    assert results[2].get("is_error") is None or results[2].get("is_error") is False


async def test_all_tools_mismatched_all_refused() -> None:
    """Worst-case prompt-injection where every tool call targets a
    different patient. Every tool returns is_error=True; orchestrator
    treats this as the "all retrieval errored" path and returns the
    refusal panel."""
    calls = [
        {
            "id": f"t{i}",
            "name": tool,
            "input": {"patient_id": "demo-002"},
        }
        for i, tool in enumerate(
            [
                "get_patient_summary",
                "get_problem_list",
                "get_medication_list",
                "get_recent_labs",
            ]
        )
    ]
    results = await execute_tools_parallel(
        calls, locked_patient_id="demo-001"
    )
    assert all(r.get("is_error") for r in results)


# --- Role-based tool whitelist (the second structural layer) ---


def test_nurse_role_excludes_diagnostic_tool_schema() -> None:
    """A nurse session never receives the get_problem_list tool, so a
    prompt-injection that asks the LLM to use it cannot succeed — there
    is no schema in the API call to invoke."""
    all_tools = [
        {"name": "get_patient_summary"},
        {"name": "get_problem_list"},
        {"name": "get_medication_list"},
        {"name": "get_recent_labs"},
    ]
    nurse_tools = rbac.filter_tools_for_role("nurse", all_tools)
    nurse_tool_names = {t["name"] for t in nurse_tools}
    assert "get_problem_list" not in nurse_tool_names


def test_unknown_role_gets_no_tools() -> None:
    """Defensive: if a session arrives with a role we don't recognize
    (corrupted cookie, future role added without whitelist update), the
    agent gets zero tools and cannot retrieve any patient data."""
    nurse_tools = rbac.filter_tools_for_role(
        "custodian", [{"name": "get_patient_summary"}]
    )
    assert nurse_tools == []


# --- Out-of-scope / prompt-coercion probes (deterministic asserts) ---


def test_role_constants_are_immutable() -> None:
    """The role whitelists are frozen sets — sanity that an attacker
    can't smuggle in a 'configure' call that adds a tool to the nurse
    whitelist at runtime."""
    nurse_set = rbac.allowed_tool_names("nurse")
    assert isinstance(nurse_set, frozenset)
    with pytest.raises((AttributeError, TypeError)):
        nurse_set.add("get_problem_list")  # type: ignore[attr-defined]
