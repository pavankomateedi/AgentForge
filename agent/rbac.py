"""Role-based access control + patient assignment
(case-study doc "Authorization & Access Control"; ARCHITECTURE.md §6).

Three roles modeled in v0:

  - physician — full clinical decision support; sees all four FHIR
    tools (summary, problems, meds, labs).
  - nurse — medication/labs/summary view; no diagnostic problem list,
    matching the institutional pattern where diagnostic reasoning is
    physician-scope.
  - resident — physician-equivalent tool access, but every response is
    watermarked "supervised review recommended" so downstream consumers
    know the response is from a trainee.

Patient assignment is enforced separately: /chat checks
`user_assigned_to_patient(user_id, patient_id)` before invoking the
agent. An unassigned access attempt is refused with 403 and audited.

In the OpenEMR target architecture (§6), this module is replaced by
OpenEMR's `acl_check()` upstream of every FHIR read. Here it stands in
so the full request flow can be tested end-to-end.
"""

from __future__ import annotations

from typing import Any

from agent.db import connect


# --- Role constants ---

ROLE_PHYSICIAN = "physician"
ROLE_NURSE = "nurse"
ROLE_RESIDENT = "resident"

ALL_ROLES: tuple[str, ...] = (ROLE_PHYSICIAN, ROLE_NURSE, ROLE_RESIDENT)


def is_valid_role(role: str | None) -> bool:
    return role in ALL_ROLES


# --- Tool whitelist per role ---
# Centralized so tests + admin CLI + orchestrator agree on what each
# role can call. Tool names match agent/tools.py — keep these in sync.

_TOOLS_FOR_ROLE: dict[str, frozenset[str]] = {
    ROLE_PHYSICIAN: frozenset(
        {
            "get_patient_summary",
            "get_problem_list",
            "get_medication_list",
            "get_recent_labs",
        }
    ),
    ROLE_NURSE: frozenset(
        {
            "get_patient_summary",
            "get_medication_list",
            "get_recent_labs",
            # Note: no get_problem_list — diagnostic codes are physician-
            # scope in this model. The agent's plan node sees a smaller
            # tool set and adapts.
        }
    ),
    ROLE_RESIDENT: frozenset(
        {
            "get_patient_summary",
            "get_problem_list",
            "get_medication_list",
            "get_recent_labs",
        }
    ),
}


def allowed_tool_names(role: str) -> frozenset[str]:
    return _TOOLS_FOR_ROLE.get(role, frozenset())


def filter_tools_for_role(
    role: str, all_tools: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return the subset of `all_tools` whose `name` is allowed for the
    role. Preserves order so the LLM sees a stable schema."""
    allowed = allowed_tool_names(role)
    return [t for t in all_tools if t.get("name") in allowed]


def is_resident(role: str | None) -> bool:
    return role == ROLE_RESIDENT


# --- Patient assignment ---


def assign_patient(
    database_url: str, *, user_id: int, patient_id: str
) -> None:
    """Idempotent: re-assigning is a no-op."""
    with connect(database_url) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO patient_assignments (user_id, patient_id) "
            "VALUES (?, ?)",
            (user_id, patient_id),
        )
        conn.commit()


def revoke_assignment(
    database_url: str, *, user_id: int, patient_id: str
) -> None:
    with connect(database_url) as conn:
        conn.execute(
            "DELETE FROM patient_assignments "
            "WHERE user_id = ? AND patient_id = ?",
            (user_id, patient_id),
        )
        conn.commit()


def is_assigned(
    database_url: str, *, user_id: int, patient_id: str
) -> bool:
    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT 1 FROM patient_assignments "
            "WHERE user_id = ? AND patient_id = ? LIMIT 1",
            (user_id, patient_id),
        ).fetchone()
    return row is not None


def list_assigned_patients(database_url: str, *, user_id: int) -> list[str]:
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT patient_id FROM patient_assignments "
            "WHERE user_id = ? ORDER BY assigned_at",
            (user_id,),
        ).fetchall()
    return [r["patient_id"] for r in rows]
