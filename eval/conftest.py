"""Eval / test fixtures.

This file MUST set required env vars before any `agent.*` import — `agent.main`
calls `get_config()` at module load to install SessionMiddleware, and
`get_config()` raises if `ANTHROPIC_API_KEY` or (transitively) `SESSION_SECRET`
are missing.

The DB lives in a temp file that's wiped between tests. The Anthropic client
on the app is replaced with a stub (`run_turn` is monkey-patched per test) so
no real API calls happen unless a test explicitly opts in via the `live` mark.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

# --- Env setup BEFORE any agent.* import ---

_TEST_DB = Path(tempfile.gettempdir()) / "agentforge_test.db"

os.environ.setdefault("ANTHROPIC_API_KEY", "test-not-a-real-key")
os.environ.setdefault("ANTHROPIC_MODEL", "claude-opus-4-7")
os.environ.setdefault(
    "SESSION_SECRET", "test-secret-must-be-at-least-16-characters"
)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ.setdefault("APP_BASE_URL", "http://testserver")
os.environ.setdefault("RESEND_API_KEY", "")
os.environ.setdefault("RESEND_FROM", "")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("SESSION_HTTPS_ONLY", "false")

# These bootstraps must NOT auto-seed during tests — we provision via fixtures.
os.environ.setdefault("DEFAULT_USER_USERNAME", "")
os.environ.setdefault("DEFAULT_USER_EMAIL", "")
os.environ.setdefault("DEFAULT_USER_PASSWORD", "")

# --- Now safe to import agent code ---

import pyotp
import pytest
from fastapi.testclient import TestClient

from agent import auth, db, main as agent_main
from agent.config import get_config
from agent.orchestrator import TurnResult, TurnTrace


# --- Fixtures ---

@pytest.fixture(autouse=True)
def _wipe_db_each_test() -> Iterator[None]:
    """Each test starts with empty tables. We truncate rather than unlinking the
    file because Windows holds SQLite file locks longer than POSIX would, so
    file-deletion between tests intermittently fails with PermissionError."""
    database_url = f"sqlite:///{_TEST_DB.as_posix()}"
    db.init_db(database_url)
    with db.connect(database_url) as conn:
        # Order matters: child tables before users (FK target).
        # derived_observations FK -> documents FK -> users.
        for table in (
            "derived_observations",
            "documents",
            "daily_token_usage",
            "patient_assignments",
            "password_reset_tokens",
            "audit_log",
            "users",
        ):
            conn.execute(f"DELETE FROM {table}")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN "
            "('users','audit_log','password_reset_tokens',"
            "'patient_assignments','daily_token_usage',"
            "'documents','derived_observations')"
        )
        conn.commit()
    yield


@pytest.fixture(autouse=True)
def _no_op_extraction_scheduler(monkeypatch):
    """Default behavior in tests: don't kick off a background extraction
    when /documents/upload returns. The lifespan already wired _client
    to a fake-key Anthropic client, and an actual call would hit the
    real API and fail (or time out, blocking CI). Tests of the
    extraction pipeline opt back in by calling
    `agent.extractors.extraction.run_extraction` directly with a
    stubbed `call_vision_pdf`."""

    def _noop(stored):  # noqa: ARG001 — signature-compatible stub
        return None

    monkeypatch.setattr(agent_main, "_schedule_extraction", _noop)


@pytest.fixture
def config():
    get_config.cache_clear()
    return get_config()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient with no session cookie."""
    with TestClient(agent_main.app) as c:
        yield c


def _assign_demo_patients(database_url: str, user_id: int) -> None:
    """Seed both demo-patient assignments so /chat tests pass the RBAC
    gate. Tests that specifically need to exercise the unassigned
    refusal path can revoke afterward."""
    from agent import rbac

    for pid in ("demo-001", "demo-002"):
        rbac.assign_patient(database_url, user_id=user_id, patient_id=pid)


@pytest.fixture
def seed_user(config) -> auth.User:
    """Provision dr.chen with password TestPass123! + demo assignments."""
    user = auth.create_user(
        config.database_url,
        username="dr.chen",
        email="dr.chen@example.com",
        password="TestPass123!",
        role="physician",
    )
    _assign_demo_patients(config.database_url, user.id)
    return user


@pytest.fixture
def seed_user_mfa(config) -> dict[str, Any]:
    """Provision dr.chen, enroll TOTP up front, and seed demo
    assignments; returns user + secret."""
    user = auth.create_user(
        config.database_url,
        username="dr.chen",
        email="dr.chen@example.com",
        password="TestPass123!",
    )
    secret = pyotp.random_base32()
    # Persist the secret directly (bypassing the API enrollment dance).
    auth._save_totp_secret(config.database_url, user.id, secret)
    _assign_demo_patients(config.database_url, user.id)
    return {"user": user, "secret": secret, "password": "TestPass123!"}


def _login_with_mfa(
    client: TestClient,
    *,
    username: str,
    password: str,
    secret: str,
) -> dict[str, Any]:
    """Helper: log a TOTP-enrolled user all the way through to a full session."""
    res = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["needs_mfa"] is True
    assert body["mfa_action"] == "challenge"
    code = pyotp.TOTP(secret).now()
    res = client.post("/auth/mfa/challenge", json={"code": code})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture
def authed_client(
    client: TestClient, seed_user_mfa: dict[str, Any]
) -> TestClient:
    """A TestClient already past login + MFA challenge — full session in cookies."""
    _login_with_mfa(
        client,
        username=seed_user_mfa["user"].username,
        password=seed_user_mfa["password"],
        secret=seed_user_mfa["secret"],
    )
    return client


@pytest.fixture
def stub_run_turn(monkeypatch) -> dict[str, Any]:
    """Replace orchestrator.run_turn with a fast stub. Tests can mutate the
    returned dict to control what the stub returns next."""
    state: dict[str, Any] = {
        "response": "Stubbed briefing.",
        "verified": True,
        "calls": [],
    }

    async def fake_run_turn(
        *,
        client,
        model,
        patient_id,
        user_message,
        user_id=None,
        user_role=None,
        available_tools=None,
        history=None,
        extra_retrieved_records=None,
    ) -> TurnResult:
        state["calls"].append(
            {
                "patient_id": patient_id,
                "user_message": user_message,
                "model": model,
                "user_id": user_id,
                "user_role": user_role,
                "available_tools": available_tools,
                "history": history,
                "extra_retrieved_records": extra_retrieved_records,
            }
        )
        trace = TurnTrace()
        return TurnResult(
            response=state["response"],
            verified=state["verified"],
            trace=trace,
        )

    monkeypatch.setattr(agent_main, "run_turn", fake_run_turn)
    # The outer (multi-agent) graph also imports run_turn into its own
    # namespace; patching only `agent.main` would leave that path live.
    from agent.agents import outer_graph as outer_graph_mod

    monkeypatch.setattr(outer_graph_mod, "run_turn", fake_run_turn)
    return state


def totp_now(secret: str) -> str:
    return pyotp.TOTP(secret).now()
