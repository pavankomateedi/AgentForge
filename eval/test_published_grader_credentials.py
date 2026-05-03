"""End-to-end verification that the EXACT credentials published in
README.md for `grader.demo` and `nurse.adams` will work on the live
deployment.

If this test passes locally, the only thing standing between a grader
typing those credentials at the Railway URL and landing in the
workspace is:

  1. The PR being merged
  2. Railway redeploying with the new bundle
  3. The EXTRA_USERS_JSON env var being set to the literal string below

This test exists specifically to prevent a "doesn't work in production"
regression — by pinning the exact strings the README publishes."""

from __future__ import annotations

from dataclasses import replace

import pyotp

from agent import auth, main as agent_main


# --- Source of truth: the literal strings that ship in README.md ---

GRADER_TOTP_SECRET = "6AV66JNIZTTPEBNBIUQWE2M7GVPNKDBD"
NURSE_TOTP_SECRET = "LMLIHJIU6JGPW2KCFYDVLGETQX54QUFG"

# This is the EXACT EXTRA_USERS_JSON string the operator pastes into
# Railway. If you change anything in README.md, change it here too.
EXTRA_USERS_JSON = (
    '['
    '{"username":"grader.demo","email":"grader@example.com",'
    '"password":"GraderDemo!2026","role":"physician",'
    '"patients":["demo-001","demo-002","demo-003","demo-004","demo-005"],'
    f'"totp_secret":"{GRADER_TOTP_SECRET}"' + '},'
    '{"username":"nurse.adams","email":"nurse@example.com",'
    '"password":"NurseDemo!2026","role":"nurse",'
    '"patients":["demo-001"],'
    f'"totp_secret":"{NURSE_TOTP_SECRET}"' + '}'
    ']'
)


def _make_config(config):
    return replace(config, extra_users_json=EXTRA_USERS_JSON)


def test_grader_demo_lands_in_workspace_with_published_credentials(
    config, client
):
    """The exact happy path a grader will run on the live URL."""
    cfg = _make_config(config)
    agent_main._bootstrap_extra_users(cfg)

    # 1. Password login → MFA challenge (NOT enrollment).
    res = client.post(
        "/auth/login",
        json={"username": "grader.demo", "password": "GraderDemo!2026"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["needs_mfa"] is True
    assert body["mfa_action"] == "challenge", (
        "If this is 'enroll' instead of 'challenge', the totp_secret "
        "didn't pre-enroll. Check the EXTRA_USERS_JSON parser."
    )

    # 2. Compute the current 6-digit code from the published secret.
    code = pyotp.TOTP(GRADER_TOTP_SECRET).now()
    res = client.post("/auth/mfa/challenge", json={"code": code})
    assert res.status_code == 200, res.text
    assert res.json()["user"]["username"] == "grader.demo"
    assert res.json()["user"]["role"] == "physician"


def test_nurse_adams_lands_in_workspace_with_published_credentials(
    config, client
):
    cfg = _make_config(config)
    agent_main._bootstrap_extra_users(cfg)

    res = client.post(
        "/auth/login",
        json={"username": "nurse.adams", "password": "NurseDemo!2026"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["needs_mfa"] is True
    assert body["mfa_action"] == "challenge"

    code = pyotp.TOTP(NURSE_TOTP_SECRET).now()
    res = client.post("/auth/mfa/challenge", json={"code": code})
    assert res.status_code == 200, res.text
    assert res.json()["user"]["role"] == "nurse"


def test_grader_demo_can_chat_about_all_five_patients(
    config, client, stub_run_turn
):
    """The patient list in EXTRA_USERS_JSON must actually grant access
    to all 5 demo patients — not just the ones that happen to exist
    in some other table."""
    cfg = _make_config(config)
    agent_main._bootstrap_extra_users(cfg)

    # Sign in.
    client.post(
        "/auth/login",
        json={"username": "grader.demo", "password": "GraderDemo!2026"},
    )
    code = pyotp.TOTP(GRADER_TOTP_SECRET).now()
    client.post("/auth/mfa/challenge", json={"code": code})

    # Each patient should return 200 (assignment exists). With the stub
    # in place, run_turn returns the canned response and we just want
    # to confirm the RBAC gate doesn't 403.
    for pid in ("demo-001", "demo-002", "demo-003", "demo-004", "demo-005"):
        res = client.post("/chat", json={"patient_id": pid, "message": "x"})
        assert res.status_code == 200, (
            f"grader.demo should be assigned to {pid} but got "
            f"{res.status_code}: {res.text}"
        )


def test_nurse_adams_can_only_chat_about_demo_001(
    config, client, stub_run_turn
):
    """Inverse: nurse.adams must be REFUSED on every patient except
    demo-001, so the RBAC demo on the live URL actually shows
    something."""
    cfg = _make_config(config)
    agent_main._bootstrap_extra_users(cfg)

    client.post(
        "/auth/login",
        json={"username": "nurse.adams", "password": "NurseDemo!2026"},
    )
    code = pyotp.TOTP(NURSE_TOTP_SECRET).now()
    client.post("/auth/mfa/challenge", json={"code": code})

    # Allowed.
    res = client.post(
        "/chat", json={"patient_id": "demo-001", "message": "x"}
    )
    assert res.status_code == 200, res.text

    # Refused.
    for pid in ("demo-002", "demo-003", "demo-004", "demo-005"):
        res = client.post("/chat", json={"patient_id": pid, "message": "x"})
        assert res.status_code == 403, (
            f"nurse.adams should be refused on {pid} (RBAC demo) "
            f"but got {res.status_code}"
        )


def test_bootstrap_is_idempotent_with_published_json(config):
    """Railway re-runs the bootstrap on every cold start. Running it
    twice with the published JSON must NOT create duplicates or
    corrupt the existing accounts."""
    cfg = _make_config(config)

    agent_main._bootstrap_extra_users(cfg)
    agent_main._bootstrap_extra_users(cfg)

    grader = auth.get_user_by_username(cfg.database_url, "grader.demo")
    nurse = auth.get_user_by_username(cfg.database_url, "nurse.adams")
    assert grader is not None
    assert nurse is not None
    assert grader.totp_enrolled is True
    assert nurse.totp_enrolled is True


def test_published_totp_secrets_are_valid_base32():
    """A typo'd secret silently degrades to 'no MFA enrolled' which
    is exactly the failure mode the grader will hit. Lock in the
    format check at the source-of-truth string."""
    # If either of these constructs raises, the README is broken.
    code1 = pyotp.TOTP(GRADER_TOTP_SECRET).now()
    code2 = pyotp.TOTP(NURSE_TOTP_SECRET).now()
    assert len(code1) == 6 and code1.isdigit()
    assert len(code2) == 6 and code2.isdigit()
