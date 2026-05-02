"""RBAC tests — role × query matrix + patient assignment gate.

Two layers of access control covered here:

  1. Patient assignment — /chat refuses (403) when the authenticated
     user is not assigned to the requested patient. Refusal is audited
     as `chat_refused_unassigned`. The orchestrator never runs.

  2. Role-based tool whitelist — the agent invokes `run_turn` with a
     subset of tools determined by the user's role:
       physician → all four FHIR tools
       nurse     → all except get_problem_list (no diagnostic codes)
       resident  → all four, response watermarked

These tests stub `run_turn` (no LLM cost) and assert the dispatch
contract: which tools the orchestrator received, what status code the
client got, what audit events fired.
"""

from __future__ import annotations

from typing import Any

import pyotp
from starlette.testclient import TestClient

from agent import auth, rbac
from agent.config import Config
from agent.db import connect

# Reuse the MFA-aware login helper from conftest so we mirror the real
# user flow rather than reinventing a partial sign-in.
from eval.conftest import _login_with_mfa


# --- helpers ---


def _audit_events(database_url: str) -> list[dict[str, Any]]:
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT event_type, details FROM audit_log ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def _make_user_with_role(
    config: Config,
    role: str,
    *,
    username: str,
    assign_demo_001: bool = True,
) -> dict[str, Any]:
    """Create a user, enroll TOTP, optionally assign to demo-001.
    Returns a dict with user, secret, password — same shape
    seed_user_mfa returns — so tests can drive the MFA login helper."""
    user = auth.create_user(
        config.database_url,
        username=username,
        email=f"{username}@example.com",
        password="TestPass123!",
        role=role,
    )
    secret = pyotp.random_base32()
    auth._save_totp_secret(config.database_url, user.id, secret)
    if assign_demo_001:
        rbac.assign_patient(
            config.database_url, user_id=user.id, patient_id="demo-001"
        )
    return {"user": user, "secret": secret, "password": "TestPass123!"}


def _sign_in(
    client: TestClient, info: dict[str, Any]
) -> None:
    _login_with_mfa(
        client,
        username=info["user"].username,
        password=info["password"],
        secret=info["secret"],
    )


# --- Patient assignment gate ---


def test_chat_refuses_when_user_not_assigned_to_patient(
    client: TestClient, config: Config, stub_run_turn
) -> None:
    """A physician with no assignment to demo-002 hits the gate."""
    info = _make_user_with_role(
        config, "physician", username="dr.solo", assign_demo_001=True
    )
    _sign_in(client, info)
    res = client.post(
        "/chat", json={"patient_id": "demo-002", "message": "brief me"}
    )
    assert res.status_code == 403
    assert "not assigned" in res.json()["detail"].lower()
    # The orchestrator must never have been invoked.
    assert stub_run_turn["calls"] == []


def test_chat_refusal_emits_audit_event(
    client: TestClient, config: Config, stub_run_turn
) -> None:
    info = _make_user_with_role(
        config, "physician", username="dr.solo", assign_demo_001=False
    )
    _sign_in(client, info)
    res = client.post(
        "/chat", json={"patient_id": "demo-001", "message": "brief me"}
    )
    assert res.status_code == 403
    events = [e["event_type"] for e in _audit_events(config.database_url)]
    assert "chat_refused_unassigned" in events
    # The successful chat audit event must NOT fire.
    assert "chat_request" not in events


def test_chat_succeeds_when_user_is_assigned(
    client: TestClient, config: Config, stub_run_turn
) -> None:
    info = _make_user_with_role(
        config, "physician", username="dr.assigned"
    )
    _sign_in(client, info)
    res = client.post(
        "/chat", json={"patient_id": "demo-001", "message": "brief me"}
    )
    assert res.status_code == 200
    assert len(stub_run_turn["calls"]) == 1


# --- Role-based tool whitelist ---


def test_physician_sees_all_four_tools(
    client: TestClient, config: Config, stub_run_turn
) -> None:
    info = _make_user_with_role(config, "physician", username="dr.full")
    _sign_in(client, info)
    client.post(
        "/chat", json={"patient_id": "demo-001", "message": "brief me"}
    )
    call = stub_run_turn["calls"][0]
    tool_names = [t["name"] for t in call["available_tools"]]
    assert set(tool_names) == {
        "get_patient_summary",
        "get_problem_list",
        "get_medication_list",
        "get_recent_labs",
    }


def test_nurse_does_not_see_problem_list_tool(
    client: TestClient, config: Config, stub_run_turn
) -> None:
    info = _make_user_with_role(config, "nurse", username="rn.smith")
    _sign_in(client, info)
    client.post(
        "/chat", json={"patient_id": "demo-001", "message": "brief me"}
    )
    call = stub_run_turn["calls"][0]
    tool_names = {t["name"] for t in call["available_tools"]}
    assert "get_problem_list" not in tool_names
    assert tool_names == {
        "get_patient_summary",
        "get_medication_list",
        "get_recent_labs",
    }
    assert call["user_role"] == "nurse"


def test_resident_sees_all_tools_like_physician(
    client: TestClient, config: Config, stub_run_turn
) -> None:
    info = _make_user_with_role(config, "resident", username="dr.junior")
    _sign_in(client, info)
    client.post(
        "/chat", json={"patient_id": "demo-001", "message": "brief me"}
    )
    call = stub_run_turn["calls"][0]
    tool_names = {t["name"] for t in call["available_tools"]}
    assert tool_names == {
        "get_patient_summary",
        "get_problem_list",
        "get_medication_list",
        "get_recent_labs",
    }


def test_resident_response_is_watermarked(
    client: TestClient, config: Config, stub_run_turn
) -> None:
    info = _make_user_with_role(config, "resident", username="dr.junior")
    _sign_in(client, info)
    res = client.post(
        "/chat", json={"patient_id": "demo-001", "message": "brief me"}
    )
    body = res.json()
    assert "supervised review recommended" in body["response"].lower()
    assert "resident" in body["response"].lower()


def test_physician_response_is_not_watermarked(
    client: TestClient, config: Config, stub_run_turn
) -> None:
    info = _make_user_with_role(config, "physician", username="dr.attending")
    _sign_in(client, info)
    res = client.post(
        "/chat", json={"patient_id": "demo-001", "message": "brief me"}
    )
    body = res.json()
    assert "supervised" not in body["response"].lower()


# --- rbac module unit tests ---


def test_filter_tools_for_role_preserves_order() -> None:
    all_tools = [
        {"name": "get_patient_summary"},
        {"name": "get_problem_list"},
        {"name": "get_medication_list"},
        {"name": "get_recent_labs"},
    ]
    nurse_tools = rbac.filter_tools_for_role("nurse", all_tools)
    assert [t["name"] for t in nurse_tools] == [
        "get_patient_summary",
        "get_medication_list",
        "get_recent_labs",
    ]


def test_filter_tools_unknown_role_returns_empty() -> None:
    """Defensive: an unknown role gets zero tools so the agent fails
    safely. Caller is responsible for validating the role at the auth
    layer; this is the second line of defense."""
    assert rbac.filter_tools_for_role("custodian", [{"name": "x"}]) == []


def test_assign_and_revoke_patient_roundtrip(config: Config) -> None:
    info = _make_user_with_role(
        config, "physician", username="dr.test", assign_demo_001=False
    )
    user_id = info["user"].id
    assert (
        rbac.is_assigned(
            config.database_url,
            user_id=user_id,
            patient_id="demo-001",
        )
        is False
    )

    rbac.assign_patient(
        config.database_url, user_id=user_id, patient_id="demo-001"
    )
    assert (
        rbac.is_assigned(
            config.database_url,
            user_id=user_id,
            patient_id="demo-001",
        )
        is True
    )
    # Idempotent — repeated assign is a no-op, no IntegrityError.
    rbac.assign_patient(
        config.database_url, user_id=user_id, patient_id="demo-001"
    )

    rbac.revoke_assignment(
        config.database_url, user_id=user_id, patient_id="demo-001"
    )
    assert (
        rbac.is_assigned(
            config.database_url,
            user_id=user_id,
            patient_id="demo-001",
        )
        is False
    )


def test_list_assigned_patients(config: Config) -> None:
    info = _make_user_with_role(
        config, "physician", username="dr.multi", assign_demo_001=False
    )
    user_id = info["user"].id
    rbac.assign_patient(
        config.database_url, user_id=user_id, patient_id="demo-001"
    )
    rbac.assign_patient(
        config.database_url, user_id=user_id, patient_id="demo-002"
    )
    patients = rbac.list_assigned_patients(
        config.database_url, user_id=user_id
    )
    assert set(patients) == {"demo-001", "demo-002"}


def test_role_constants_match_db_default() -> None:
    """Sanity: the rbac role constants match what the schema defaults
    to so create_user without an explicit role lands in a known
    bucket."""
    assert rbac.ROLE_PHYSICIAN == "physician"
    assert rbac.is_valid_role("physician")
    assert rbac.is_valid_role("nurse")
    assert rbac.is_valid_role("resident")
    assert not rbac.is_valid_role("custodian")
