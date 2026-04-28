"""/chat is auth-gated. These tests don't hit the LLM — orchestrator.run_turn
is stubbed so we can exercise the auth dependency and the audit-log emission."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from agent.config import Config


def _audit_events(database_url: str) -> list[str]:
    with sqlite3.connect(database_url[len("sqlite:///") :]) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT event_type FROM audit_log ORDER BY id"
        ).fetchall()
    return [r["event_type"] for r in rows]


def test_chat_without_session_returns_401(client: TestClient) -> None:
    res = client.post(
        "/chat",
        json={"patient_id": "demo-001", "message": "brief me"},
    )
    assert res.status_code == 401


def test_chat_with_full_session_returns_200(
    authed_client: TestClient, stub_run_turn
) -> None:
    res = authed_client.post(
        "/chat",
        json={"patient_id": "demo-001", "message": "brief me"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["response"] == "Stubbed briefing."
    assert body["verified"] is True
    # Stub captured the call.
    assert len(stub_run_turn["calls"]) == 1
    assert stub_run_turn["calls"][0]["patient_id"] == "demo-001"


def test_chat_emits_chat_request_audit_event(
    authed_client: TestClient, stub_run_turn, config: Config
) -> None:
    authed_client.post(
        "/chat",
        json={"patient_id": "demo-001", "message": "brief me"},
    )
    events = _audit_events(config.database_url)
    assert "chat_request" in events


def test_chat_with_pending_mfa_session_returns_401(
    client: TestClient, seed_user
) -> None:
    """Password verified but MFA not completed = pending state, NOT a full
    session. /chat should still 401."""
    res = client.post(
        "/auth/login",
        json={"username": "dr.chen", "password": "TestPass123!"},
    )
    assert res.status_code == 200
    assert res.json()["mfa_action"] == "enroll"
    res = client.post(
        "/chat",
        json={"patient_id": "demo-001", "message": "brief me"},
    )
    assert res.status_code == 401


def test_health_endpoint_is_public(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
