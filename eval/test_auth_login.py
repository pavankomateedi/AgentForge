"""Login + lockout integration tests (ARCHITECTURE.md §6, Phase 1 auth).

Uses a real FastAPI TestClient and a fresh SQLite DB. No LLM calls.
"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from agent import auth
from agent.config import Config


def test_login_with_no_user_returns_401(client: TestClient) -> None:
    res = client.post(
        "/auth/login", json={"username": "ghost", "password": "whatever"}
    )
    assert res.status_code == 401
    body = res.json()
    assert "Invalid username or password" in body["detail"]


def test_login_with_correct_password_returns_needs_mfa_enroll(
    client: TestClient, seed_user
) -> None:
    res = client.post(
        "/auth/login",
        json={"username": "dr.chen", "password": "TestPass123!"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["needs_mfa"] is True
    assert body["mfa_action"] == "enroll"
    assert body["user"] is None
    # Verify a session cookie was set (even if it's only the pending-MFA state).
    assert any(c.startswith("session=") for c in client.cookies.keys()) or len(
        client.cookies
    ) > 0


def test_login_with_bad_password_returns_401_and_increments_attempts(
    client: TestClient, seed_user, config: Config
) -> None:
    res = client.post(
        "/auth/login",
        json={"username": "dr.chen", "password": "wrong"},
    )
    assert res.status_code == 401
    refreshed = auth.get_user_by_username(config.database_url, "dr.chen")
    assert refreshed is not None
    assert refreshed.failed_login_attempts == 1


def test_login_locks_account_after_five_failed_attempts(
    client: TestClient, seed_user, config: Config
) -> None:
    for i in range(4):
        res = client.post(
            "/auth/login",
            json={"username": "dr.chen", "password": "wrong"},
        )
        assert res.status_code == 401, f"attempt {i + 1}"
    # 5th attempt — server locks during this call and returns 423.
    res = client.post(
        "/auth/login",
        json={"username": "dr.chen", "password": "wrong"},
    )
    assert res.status_code == 423
    assert "locked" in res.json()["detail"].lower()

    # Even with the correct password the account is locked now.
    res = client.post(
        "/auth/login",
        json={"username": "dr.chen", "password": "TestPass123!"},
    )
    assert res.status_code == 423


def test_login_inactive_user_returns_403(
    client: TestClient, seed_user, config: Config
) -> None:
    with sqlite3.connect(config.database_url[len("sqlite:///") :]) as conn:
        conn.execute(
            "UPDATE users SET is_active = 0 WHERE id = ?", (seed_user.id,)
        )
        conn.commit()
    res = client.post(
        "/auth/login",
        json={"username": "dr.chen", "password": "TestPass123!"},
    )
    assert res.status_code == 403


def test_me_without_session_returns_401(client: TestClient) -> None:
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_logout_clears_session(
    client: TestClient, authed_client: TestClient
) -> None:
    """authed_client has a fresh full session; /me works, then logout, then /me 401."""
    res = client.get("/auth/me")
    assert res.status_code == 200
    res = client.post("/auth/logout")
    assert res.status_code == 200
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_audit_log_records_login_failures_and_successes(
    client: TestClient, seed_user_mfa, config: Config
) -> None:
    # One bad attempt + one full successful login (via authed flow helpers).
    client.post(
        "/auth/login",
        json={"username": "dr.chen", "password": "wrong"},
    )
    # Successful login + MFA challenge.
    from eval.conftest import _login_with_mfa  # noqa: PLC0415

    _login_with_mfa(
        client,
        username="dr.chen",
        password=seed_user_mfa["password"],
        secret=seed_user_mfa["secret"],
    )

    db_path = config.database_url[len("sqlite:///") :]
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT event_type FROM audit_log ORDER BY id"
        ).fetchall()
    events = [r["event_type"] for r in rows]
    assert "login_failed_bad_password" in events
    assert "login_success" in events
    assert "mfa_verified" in events
