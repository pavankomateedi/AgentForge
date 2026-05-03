"""Tests for the EXTRA_USERS_JSON bootstrap path
(agent.main._bootstrap_extra_users).

This bootstrap exists so demo accounts (nurse, resident, second
physician) survive Railway's ephemeral filesystem — every cold start
re-seeds whatever the env var declares. The function must be:

  - idempotent (existing users left alone, assignments deduped)
  - tolerant of bad input (malformed JSON, unknown role, missing
    fields → log and skip the entry, never crash)
  - actually wire patient assignments (the demo's whole point)

We invoke `_bootstrap_extra_users` directly with a fabricated Config
rather than going through the FastAPI lifespan, so we can vary the
JSON per test without touching real env vars.
"""

from __future__ import annotations

from dataclasses import replace

from agent import auth, main as agent_main, rbac


# --- helpers ---


def _make_config(config, extra_users_json: str | None):
    """Return a copy of the test Config with extra_users_json set."""
    return replace(config, extra_users_json=extra_users_json)


# --- happy paths ---


def test_bootstrap_creates_user_with_role_and_patients(config):
    cfg = _make_config(
        config,
        '[{"username":"nurse.adams","email":"nurse.adams@example.com",'
        '"password":"NursePass123!","role":"nurse",'
        '"patients":["demo-001"]}]',
    )

    agent_main._bootstrap_extra_users(cfg)

    user = auth.get_user_by_username(cfg.database_url, "nurse.adams")
    assert user is not None
    assert user.role == "nurse"
    assert user.email == "nurse.adams@example.com"

    assigned = rbac.list_assigned_patients(cfg.database_url, user_id=user.id)
    assert assigned == ["demo-001"]


def test_bootstrap_creates_multiple_users(config):
    cfg = _make_config(
        config,
        '['
        '{"username":"nurse.adams","email":"n@e.com","password":"P@ssword1",'
        '"role":"nurse","patients":["demo-001"]},'
        '{"username":"resident.kim","email":"r@e.com","password":"P@ssword1",'
        '"role":"resident","patients":["demo-001","demo-002"]}'
        ']',
    )

    agent_main._bootstrap_extra_users(cfg)

    nurse = auth.get_user_by_username(cfg.database_url, "nurse.adams")
    resident = auth.get_user_by_username(cfg.database_url, "resident.kim")
    assert nurse is not None and nurse.role == "nurse"
    assert resident is not None and resident.role == "resident"

    assert rbac.list_assigned_patients(cfg.database_url, user_id=nurse.id) == ["demo-001"]
    assert sorted(
        rbac.list_assigned_patients(cfg.database_url, user_id=resident.id)
    ) == ["demo-001", "demo-002"]


def test_role_defaults_to_physician_when_omitted(config):
    cfg = _make_config(
        config,
        '[{"username":"dr.new","email":"dr.new@e.com","password":"P@ssword1"}]',
    )

    agent_main._bootstrap_extra_users(cfg)

    user = auth.get_user_by_username(cfg.database_url, "dr.new")
    assert user is not None
    assert user.role == "physician"


def test_no_patients_field_means_no_assignments(config):
    cfg = _make_config(
        config,
        '[{"username":"nurse.adams","email":"n@e.com","password":"P@ssword1",'
        '"role":"nurse"}]',
    )

    agent_main._bootstrap_extra_users(cfg)

    user = auth.get_user_by_username(cfg.database_url, "nurse.adams")
    assert user is not None
    assert rbac.list_assigned_patients(cfg.database_url, user_id=user.id) == []


# --- idempotency ---


def test_re_running_does_not_duplicate_user_or_error(config):
    payload = (
        '[{"username":"nurse.adams","email":"n@e.com","password":"P@ssword1",'
        '"role":"nurse","patients":["demo-001"]}]'
    )
    cfg = _make_config(config, payload)

    # First call creates.
    agent_main._bootstrap_extra_users(cfg)
    user = auth.get_user_by_username(cfg.database_url, "nurse.adams")
    assert user is not None
    first_id = user.id

    # Second call must be a no-op — same user, same id.
    agent_main._bootstrap_extra_users(cfg)
    user_again = auth.get_user_by_username(cfg.database_url, "nurse.adams")
    assert user_again is not None
    assert user_again.id == first_id


def test_re_running_reconciles_new_assignments(config):
    """If the operator widens a user's patients list and redeploys, the
    new assignments should land. Existing ones must remain (idempotent
    `INSERT OR IGNORE` in rbac.assign_patient)."""
    initial = (
        '[{"username":"nurse.adams","email":"n@e.com","password":"P@ssword1",'
        '"role":"nurse","patients":["demo-001"]}]'
    )
    expanded = (
        '[{"username":"nurse.adams","email":"n@e.com","password":"P@ssword1",'
        '"role":"nurse","patients":["demo-001","demo-002"]}]'
    )

    agent_main._bootstrap_extra_users(_make_config(config, initial))
    user = auth.get_user_by_username(config.database_url, "nurse.adams")
    assert user is not None

    agent_main._bootstrap_extra_users(_make_config(config, expanded))
    assert sorted(
        rbac.list_assigned_patients(config.database_url, user_id=user.id)
    ) == ["demo-001", "demo-002"]


# --- failure tolerance — never crash, log and skip ---


def test_no_env_var_is_a_noop(config):
    cfg = _make_config(config, None)
    # Should not raise and should not create users.
    agent_main._bootstrap_extra_users(cfg)
    assert auth.get_user_by_username(cfg.database_url, "nurse.adams") is None


def test_empty_string_is_a_noop(config):
    cfg = _make_config(config, "")
    agent_main._bootstrap_extra_users(cfg)
    assert auth.get_user_by_username(cfg.database_url, "nurse.adams") is None


def test_malformed_json_does_not_crash(config, caplog):
    cfg = _make_config(config, "this is not json {")
    with caplog.at_level("ERROR"):
        agent_main._bootstrap_extra_users(cfg)
    assert any("EXTRA_USERS_JSON is not valid JSON" in r.message for r in caplog.records)


def test_non_list_root_does_not_crash(config, caplog):
    cfg = _make_config(config, '{"username":"x"}')
    with caplog.at_level("ERROR"):
        agent_main._bootstrap_extra_users(cfg)
    assert any("must be a JSON list" in r.message for r in caplog.records)


def test_unknown_role_skipped_other_entries_succeed(config, caplog):
    cfg = _make_config(
        config,
        '['
        '{"username":"bad.role","email":"b@e.com","password":"P@ssword1",'
        '"role":"administrator"},'
        '{"username":"nurse.adams","email":"n@e.com","password":"P@ssword1",'
        '"role":"nurse"}'
        ']',
    )

    with caplog.at_level("WARNING"):
        agent_main._bootstrap_extra_users(cfg)

    # Bad entry skipped.
    assert auth.get_user_by_username(cfg.database_url, "bad.role") is None
    # Good entry still landed.
    assert auth.get_user_by_username(cfg.database_url, "nurse.adams") is not None
    assert any("unknown role" in r.message for r in caplog.records)


def test_missing_required_field_skipped(config, caplog):
    cfg = _make_config(
        config,
        '[{"username":"no.password","email":"n@e.com"}]',
    )
    with caplog.at_level("WARNING"):
        agent_main._bootstrap_extra_users(cfg)
    assert auth.get_user_by_username(cfg.database_url, "no.password") is None
    assert any("missing username/email/password" in r.message for r in caplog.records)


def test_non_object_entry_skipped(config, caplog):
    cfg = _make_config(config, '["not an object", 42]')
    with caplog.at_level("WARNING"):
        agent_main._bootstrap_extra_users(cfg)
    # Two warnings about non-object entries.
    msgs = [r.message for r in caplog.records if "not an object" in r.message]
    assert len(msgs) >= 2


def test_non_string_patient_id_skipped_other_assignments_proceed(config, caplog):
    cfg = _make_config(
        config,
        '[{"username":"nurse.adams","email":"n@e.com","password":"P@ssword1",'
        '"role":"nurse","patients":["demo-001",42]}]',
    )
    with caplog.at_level("WARNING"):
        agent_main._bootstrap_extra_users(cfg)
    user = auth.get_user_by_username(cfg.database_url, "nurse.adams")
    assert user is not None
    assert rbac.list_assigned_patients(cfg.database_url, user_id=user.id) == ["demo-001"]


# --- TOTP pre-enrollment ---


def test_totp_secret_pre_enrolls_user(config):
    """A valid base32 secret in the bootstrap entry should leave the
    user fully enrolled — login skips the enroll dance and goes
    straight to challenge."""
    import pyotp

    secret = pyotp.random_base32()
    cfg = _make_config(
        config,
        f'[{{"username":"grader.demo","email":"g@e.com","password":"P@ssword1",'
        f'"role":"physician","totp_secret":"{secret}"}}]',
    )

    agent_main._bootstrap_extra_users(cfg)

    user = auth.get_user_by_username(cfg.database_url, "grader.demo")
    assert user is not None
    assert user.totp_enrolled is True


def test_invalid_totp_secret_skips_pre_enroll_user_still_created(config, caplog):
    """A bad secret must not block account creation — the user lands,
    just un-enrolled, and falls back to normal in-app enrollment."""
    cfg = _make_config(
        config,
        '[{"username":"grader.demo","email":"g@e.com","password":"P@ssword1",'
        '"role":"physician","totp_secret":"!!!not-base32!!!"}]',
    )

    with caplog.at_level("WARNING"):
        agent_main._bootstrap_extra_users(cfg)

    user = auth.get_user_by_username(cfg.database_url, "grader.demo")
    assert user is not None
    assert user.totp_enrolled is False
    assert any(
        "totp_secret for 'grader.demo' is not valid base32" in r.message
        for r in caplog.records
    )


def test_omitted_totp_secret_leaves_user_unenrolled(config):
    cfg = _make_config(
        config,
        '[{"username":"nurse.adams","email":"n@e.com","password":"P@ssword1",'
        '"role":"nurse"}]',
    )

    agent_main._bootstrap_extra_users(cfg)

    user = auth.get_user_by_username(cfg.database_url, "nurse.adams")
    assert user is not None
    assert user.totp_enrolled is False


def test_pre_enrolled_user_can_complete_mfa_challenge(config, client):
    """End-to-end: a bootstrap-enrolled user logs in, gets sent to
    challenge (not enroll), and a TOTP code computed from the published
    secret completes the login."""
    import pyotp

    secret = pyotp.random_base32()
    cfg = _make_config(
        config,
        f'[{{"username":"grader.demo","email":"g@e.com",'
        f'"password":"GraderPass1!","role":"physician",'
        f'"patients":["demo-001"],"totp_secret":"{secret}"}}]',
    )
    agent_main._bootstrap_extra_users(cfg)

    # Step 1: password login → challenge (not enroll).
    res = client.post(
        "/auth/login",
        json={"username": "grader.demo", "password": "GraderPass1!"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["needs_mfa"] is True
    assert body["mfa_action"] == "challenge"

    # Step 2: TOTP code from the published secret completes the session.
    code = pyotp.TOTP(secret).now()
    res = client.post("/auth/mfa/challenge", json={"code": code})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user"]["username"] == "grader.demo"
    assert body["needs_mfa"] is False
