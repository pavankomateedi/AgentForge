"""Tests for the synthetic-data MFA bypass.

The bypass exists for the operator's own daily-use account on demo
deployments where typing a TOTP code 20 times a day adds friction
without a corresponding security gain (zero real PHI). This file
locks in the exact behavior so the bypass:

  - actually skips MFA for flagged accounts (the daily-use case)
  - LEAVES THE NORMAL FLOW UNCHANGED for every other account
    (the regression risk we're paying down with these tests)
  - emits LOGIN_MFA_BYPASSED in the audit log so the carve-out is
    observable from the trail, not silent
  - can be reconciled at a later cold start by flipping the flag
    back to False in EXTRA_USERS_JSON
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pyotp

from agent import audit, auth, main as agent_main
from agent.config import Config
from agent.db import connect


# --- helpers ---


def _make_config(config: Config, extra_users_json: str | None) -> Config:
    return replace(config, extra_users_json=extra_users_json)


def _audit_events(database_url: str) -> list[dict[str, Any]]:
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT event_type, user_id, details FROM audit_log "
            "ORDER BY id"
        ).fetchall()
    return [
        {
            "event_type": r["event_type"],
            "user_id": r["user_id"],
            "details": r["details"],
        }
        for r in rows
    ]


# --- bypass happy path ---


def test_bypass_flag_lands_user_in_session_with_password_only(config, client):
    cfg = _make_config(
        config,
        '[{"username":"dr.pavan","email":"dr.pavan@example.com",'
        '"password":"PavanDaily!2026","role":"physician",'
        '"patients":["demo-001","demo-002","demo-003","demo-004","demo-005"],'
        '"bypass_mfa":true}]',
    )
    agent_main._bootstrap_extra_users(cfg)

    # Single POST → full session, no MFA challenge.
    res = client.post(
        "/auth/login",
        json={"username": "dr.pavan", "password": "PavanDaily!2026"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["needs_mfa"] is False, (
        "Bypass account must land directly in the workspace; got "
        f"needs_mfa={body['needs_mfa']}"
    )
    assert body["user"]["username"] == "dr.pavan"
    assert body["mfa_action"] is None


def test_bypass_user_can_chat_immediately_after_login(
    config, client, stub_run_turn
):
    """End-to-end: password login + a /chat call works in two HTTP
    round trips, no MFA in between."""
    cfg = _make_config(
        config,
        '[{"username":"dr.pavan","email":"dr.pavan@example.com",'
        '"password":"PavanDaily!2026","role":"physician",'
        '"patients":["demo-001"],"bypass_mfa":true}]',
    )
    agent_main._bootstrap_extra_users(cfg)

    res = client.post(
        "/auth/login",
        json={"username": "dr.pavan", "password": "PavanDaily!2026"},
    )
    assert res.status_code == 200

    res = client.post(
        "/chat", json={"patient_id": "demo-001", "message": "brief me"}
    )
    assert res.status_code == 200, res.text


def test_bypass_login_emits_LOGIN_MFA_BYPASSED_audit_event(config, client):
    cfg = _make_config(
        config,
        '[{"username":"dr.pavan","email":"d@e.com","password":"PavanDaily!2026",'
        '"role":"physician","bypass_mfa":true}]',
    )
    agent_main._bootstrap_extra_users(cfg)

    client.post(
        "/auth/login",
        json={"username": "dr.pavan", "password": "PavanDaily!2026"},
    )

    events = _audit_events(cfg.database_url)
    types = [e["event_type"] for e in events]
    # The bypass event AND the login_success event must both appear
    # (login_success keeps existing dashboards working; bypass event
    # makes the carve-out queryable).
    assert audit.AuditEvent.LOGIN_MFA_BYPASSED in types
    assert audit.AuditEvent.LOGIN_SUCCESS in types


def test_bypass_can_coexist_with_pre_enrolled_totp(config, client):
    """If both bypass_mfa AND totp_secret are set, bypass wins. Useful
    for an operator who might want to flip MFA back on without
    re-enrolling."""
    cfg = _make_config(
        config,
        '[{"username":"dr.pavan","email":"d@e.com","password":"PavanDaily!2026",'
        '"role":"physician","bypass_mfa":true,'
        '"totp_secret":"6AV66JNIZTTPEBNBIUQWE2M7GVPNKDBD"}]',
    )
    agent_main._bootstrap_extra_users(cfg)

    user = auth.get_user_by_username(cfg.database_url, "dr.pavan")
    assert user is not None
    assert user.bypass_mfa is True
    assert user.totp_enrolled is True  # secret was still pre-loaded

    res = client.post(
        "/auth/login",
        json={"username": "dr.pavan", "password": "PavanDaily!2026"},
    )
    assert res.status_code == 200
    assert res.json()["needs_mfa"] is False


def test_bypass_can_be_reconciled_off(config, client):
    """Flipping bypass_mfa from true → false in EXTRA_USERS_JSON and
    re-running the bootstrap restores the normal MFA flow on the next
    login."""
    on = (
        '[{"username":"dr.pavan","email":"d@e.com","password":"PavanDaily!2026",'
        '"role":"physician","bypass_mfa":true,'
        '"totp_secret":"6AV66JNIZTTPEBNBIUQWE2M7GVPNKDBD"}]'
    )
    off = (
        '[{"username":"dr.pavan","email":"d@e.com","password":"PavanDaily!2026",'
        '"role":"physician","bypass_mfa":false,'
        '"totp_secret":"6AV66JNIZTTPEBNBIUQWE2M7GVPNKDBD"}]'
    )

    agent_main._bootstrap_extra_users(_make_config(config, on))
    agent_main._bootstrap_extra_users(_make_config(config, off))

    user = auth.get_user_by_username(config.database_url, "dr.pavan")
    assert user is not None
    assert user.bypass_mfa is False

    res = client.post(
        "/auth/login",
        json={"username": "dr.pavan", "password": "PavanDaily!2026"},
    )
    body = res.json()
    assert body["needs_mfa"] is True
    assert body["mfa_action"] == "challenge"


# --- regression: normal MFA flow MUST be unchanged for non-bypass accounts ---


def test_mfa_still_mandatory_for_flag_omitted_account(config, client):
    """A user without bypass_mfa goes through the normal MFA flow.
    This is the load-bearing regression check — if this fails, the
    bypass leaked into accounts that didn't ask for it."""
    cfg = _make_config(
        config,
        '[{"username":"dr.normal","email":"d@e.com","password":"NormalPass1!",'
        '"role":"physician","totp_secret":"6AV66JNIZTTPEBNBIUQWE2M7GVPNKDBD"}]',
    )
    agent_main._bootstrap_extra_users(cfg)

    user = auth.get_user_by_username(cfg.database_url, "dr.normal")
    assert user is not None
    assert user.bypass_mfa is False  # default

    res = client.post(
        "/auth/login",
        json={"username": "dr.normal", "password": "NormalPass1!"},
    )
    body = res.json()
    assert body["needs_mfa"] is True
    assert body["mfa_action"] == "challenge"


def test_mfa_still_mandatory_for_flag_explicitly_false(config, client):
    cfg = _make_config(
        config,
        '[{"username":"dr.normal","email":"d@e.com","password":"NormalPass1!",'
        '"role":"physician","totp_secret":"6AV66JNIZTTPEBNBIUQWE2M7GVPNKDBD",'
        '"bypass_mfa":false}]',
    )
    agent_main._bootstrap_extra_users(cfg)

    res = client.post(
        "/auth/login",
        json={"username": "dr.normal", "password": "NormalPass1!"},
    )
    body = res.json()
    assert body["needs_mfa"] is True


def test_existing_users_get_bypass_mfa_default_false_after_migration(config):
    """The schema migration must add the column with default 0 so
    accounts created before the bypass feature retain mandatory MFA."""
    user = auth.create_user(
        config.database_url,
        username="legacy.user",
        email="legacy@example.com",
        password="LegacyPass1!",
        role="physician",
    )
    assert user.bypass_mfa is False


# --- bad password / locked account / inactive — bypass does NOT short-circuit those ---


def test_bypass_does_not_skip_password_check(config, client):
    cfg = _make_config(
        config,
        '[{"username":"dr.pavan","email":"d@e.com","password":"PavanDaily!2026",'
        '"role":"physician","bypass_mfa":true}]',
    )
    agent_main._bootstrap_extra_users(cfg)

    res = client.post(
        "/auth/login",
        json={"username": "dr.pavan", "password": "WrongPassword!"},
    )
    # Bypass only skips MFA, not password verification. A wrong password
    # is still 401 + counts toward lockout.
    assert res.status_code == 401


def test_bypass_does_not_skip_account_lockout(config, client):
    cfg = _make_config(
        config,
        '[{"username":"dr.pavan","email":"d@e.com","password":"PavanDaily!2026",'
        '"role":"physician","bypass_mfa":true}]',
    )
    agent_main._bootstrap_extra_users(cfg)

    # 5 failed attempts triggers the 15-min lockout, same as any account.
    for _ in range(5):
        client.post(
            "/auth/login",
            json={"username": "dr.pavan", "password": "WrongPassword!"},
        )

    # Even with the right password, account is locked for 15 min.
    res = client.post(
        "/auth/login",
        json={"username": "dr.pavan", "password": "PavanDaily!2026"},
    )
    assert res.status_code == 423


# --- one assertion against the literal published config ---


def test_published_dr_pavan_config_actually_works(config, client):
    """Pin the literal published EXTRA_USERS_JSON entry so a typo in
    the README won't survive CI."""
    cfg = _make_config(
        config,
        '['
        '{"username":"dr.pavan","email":"dr.pavan@example.com",'
        '"password":"PavanDaily!2026","role":"physician",'
        '"patients":["demo-001","demo-002","demo-003","demo-004","demo-005"],'
        '"bypass_mfa":true}'
        ']',
    )
    agent_main._bootstrap_extra_users(cfg)

    # Full happy path with the published string.
    res = client.post(
        "/auth/login",
        json={"username": "dr.pavan", "password": "PavanDaily!2026"},
    )
    assert res.status_code == 200
    assert res.json()["needs_mfa"] is False

    # Confirm patient access (the daily-use case).
    res = client.get("/auth/me")
    assert res.status_code == 200
    assert res.json()["username"] == "dr.pavan"


# --- pyotp is imported above; explicit reference so unused-import lint stays quiet ---
assert pyotp.random_base32  # sanity touch
