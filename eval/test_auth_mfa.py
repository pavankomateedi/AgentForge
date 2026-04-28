"""MFA enrollment + challenge integration tests (Phase 2 auth)."""

from __future__ import annotations

import pyotp
from fastapi.testclient import TestClient

from agent import auth
from agent.config import Config


def _password_login(client: TestClient, username: str, password: str) -> dict:
    res = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_mfa_setup_requires_pending_or_full_session(client: TestClient) -> None:
    res = client.post("/auth/mfa/setup", json={})
    assert res.status_code == 401


def test_mfa_setup_after_password_returns_secret_and_uri(
    client: TestClient, seed_user
) -> None:
    body = _password_login(client, "dr.chen", "TestPass123!")
    assert body["mfa_action"] == "enroll"
    res = client.post("/auth/mfa/setup", json={})
    assert res.status_code == 200
    payload = res.json()
    assert payload["secret"]
    assert payload["provisioning_uri"].startswith("otpauth://totp/")
    assert payload["account_name"] == "dr.chen@example.com"
    assert payload["issuer"] == "Clinical Co-Pilot"


def test_mfa_verify_setup_with_wrong_code_returns_400(
    client: TestClient, seed_user
) -> None:
    _password_login(client, "dr.chen", "TestPass123!")
    client.post("/auth/mfa/setup", json={})
    res = client.post("/auth/mfa/verify-setup", json={"code": "000000"})
    assert res.status_code == 400


def test_mfa_verify_setup_with_correct_code_completes_login(
    client: TestClient, seed_user, config: Config
) -> None:
    _password_login(client, "dr.chen", "TestPass123!")
    setup = client.post("/auth/mfa/setup", json={}).json()
    code = pyotp.TOTP(setup["secret"]).now()
    res = client.post("/auth/mfa/verify-setup", json={"code": code})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["needs_mfa"] is False
    assert body["user"]["username"] == "dr.chen"
    assert body["user"]["totp_enrolled"] is True

    # User is now in DB with totp_enrolled=true.
    refreshed = auth.get_user_by_username(config.database_url, "dr.chen")
    assert refreshed is not None and refreshed.totp_enrolled is True

    # Full session now: /auth/me returns the user.
    me = client.get("/auth/me")
    assert me.status_code == 200


def test_login_after_enrollment_routes_to_challenge(
    client: TestClient, seed_user_mfa
) -> None:
    body = _password_login(
        client, "dr.chen", seed_user_mfa["password"]
    )
    assert body["needs_mfa"] is True
    assert body["mfa_action"] == "challenge"


def test_mfa_challenge_with_wrong_code_returns_401(
    client: TestClient, seed_user_mfa
) -> None:
    _password_login(client, "dr.chen", seed_user_mfa["password"])
    res = client.post("/auth/mfa/challenge", json={"code": "000000"})
    assert res.status_code == 401


def test_mfa_challenge_with_correct_code_grants_full_session(
    client: TestClient, seed_user_mfa
) -> None:
    _password_login(client, "dr.chen", seed_user_mfa["password"])
    code = pyotp.TOTP(seed_user_mfa["secret"]).now()
    res = client.post("/auth/mfa/challenge", json={"code": code})
    assert res.status_code == 200
    body = res.json()
    assert body["needs_mfa"] is False
    assert body["user"]["totp_enrolled"] is True

    me = client.get("/auth/me")
    assert me.status_code == 200
