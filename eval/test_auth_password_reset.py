"""Password reset integration tests (Phase 3).

Resend is not configured in tests; the dev fallback logs the reset URL but
doesn't deliver email. We pull the plaintext token from the request response
chain via the URL captured in the log — but easier and more deterministic is
to compute the reset URL ourselves from the most-recent token row by mocking
secrets.token_urlsafe so we know the value.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from agent.auth import _hash_token
from agent.config import Config


def _db(database_url: str) -> sqlite3.Connection:
    conn = sqlite3.connect(database_url[len("sqlite:///") :])
    conn.row_factory = sqlite3.Row
    return conn


def test_request_for_unknown_email_returns_200_no_enumeration(
    client: TestClient,
) -> None:
    res = client.post(
        "/auth/password-reset/request",
        json={"email": "nobody@example.com"},
    )
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_request_for_known_user_returns_200_and_creates_token(
    client: TestClient, seed_user, config: Config
) -> None:
    res = client.post(
        "/auth/password-reset/request",
        json={"email": "dr.chen@example.com"},
    )
    assert res.status_code == 200
    with _db(config.database_url) as conn:
        rows = conn.execute(
            "SELECT user_id, used_at FROM password_reset_tokens"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["user_id"] == seed_user.id
    assert rows[0]["used_at"] is None


def _create_reset_token(
    config: Config, user_id: int, *, expires_in_seconds: int = 3600,
    plaintext: str = "dev-reset-token-very-long-string-1234567890ABCD"
) -> str:
    """Insert a reset token row directly so we know the plaintext."""
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=expires_in_seconds
    )
    with _db(config.database_url) as conn:
        conn.execute(
            """INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
               VALUES (?, ?, ?)""",
            (user_id, _hash_token(plaintext), expires_at.isoformat()),
        )
        conn.commit()
    return plaintext


def test_confirm_with_invalid_token_returns_400(client: TestClient) -> None:
    res = client.post(
        "/auth/password-reset/confirm",
        json={
            "token": "definitely-not-a-real-token-xxxxxxxxxxx",
            "new_password": "NewPass123!",
        },
    )
    assert res.status_code == 400


def test_confirm_with_valid_token_resets_password(
    client: TestClient, seed_user, config: Config
) -> None:
    token = _create_reset_token(config, seed_user.id)
    res = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "NewSecurePass456!"},
    )
    assert res.status_code == 200

    # Old password no longer works.
    res = client.post(
        "/auth/login",
        json={"username": "dr.chen", "password": "TestPass123!"},
    )
    assert res.status_code == 401

    # New password works (proceeds to MFA enrollment since not enrolled).
    res = client.post(
        "/auth/login",
        json={"username": "dr.chen", "password": "NewSecurePass456!"},
    )
    assert res.status_code == 200
    assert res.json()["mfa_action"] == "enroll"


def test_confirm_with_used_token_returns_400(
    client: TestClient, seed_user, config: Config
) -> None:
    token = _create_reset_token(config, seed_user.id)
    res = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "NewSecurePass456!"},
    )
    assert res.status_code == 200
    # Same token again.
    res = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "AnotherPass789!"},
    )
    assert res.status_code == 400
    assert "already been used" in res.json()["detail"]


def test_confirm_with_expired_token_returns_400(
    client: TestClient, seed_user, config: Config
) -> None:
    token = _create_reset_token(
        config, seed_user.id, expires_in_seconds=-3600
    )
    res = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "NewSecurePass456!"},
    )
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower()


def test_password_reset_clears_failed_attempts_and_lockout(
    client: TestClient, seed_user, config: Config
) -> None:
    # Force a partial lockout.
    for _ in range(3):
        client.post(
            "/auth/login",
            json={"username": "dr.chen", "password": "wrong"},
        )
    token = _create_reset_token(config, seed_user.id)
    client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "NewSecurePass456!"},
    )
    # Failed-attempts counter should be reset.
    with _db(config.database_url) as conn:
        row = conn.execute(
            "SELECT failed_login_attempts, locked_until FROM users WHERE id = ?",
            (seed_user.id,),
        ).fetchone()
    assert row["failed_login_attempts"] == 0
    assert row["locked_until"] is None
