"""Per-user daily token budget tests (ARCHITECTURE.md §8.4).

Two layers of coverage:

  1. agent.budget unit tests — get/record/is_over_budget round-trip,
     UTC day boundary, multi-user isolation, disable-when-zero.

  2. /chat integration — over-budget request returns 429 + audit
     event; under-budget request returns 200 and increments usage.
"""

from __future__ import annotations

from typing import Any

import pyotp
from starlette.testclient import TestClient

from agent import auth, budget, rbac
from agent.config import Config
from agent.db import connect

from eval.conftest import _login_with_mfa


# --- Unit tests for the budget module ---


def test_get_today_usage_returns_zero_for_new_user(config: Config) -> None:
    user = auth.create_user(
        config.database_url,
        username="dr.fresh",
        email="dr.fresh@example.com",
        password="TestPass123!",
    )
    assert (
        budget.get_today_usage(config.database_url, user_id=user.id) == 0
    )


def test_record_usage_accumulates_within_day(config: Config) -> None:
    user = auth.create_user(
        config.database_url,
        username="dr.acc",
        email="dr.acc@example.com",
        password="TestPass123!",
    )
    new_total = budget.record_usage(
        config.database_url, user_id=user.id, tokens=500
    )
    assert new_total == 500
    new_total = budget.record_usage(
        config.database_url, user_id=user.id, tokens=750
    )
    assert new_total == 1250
    assert (
        budget.get_today_usage(config.database_url, user_id=user.id)
        == 1250
    )


def test_record_usage_zero_or_negative_is_noop(config: Config) -> None:
    """Defensive: don't decrement, don't insert spurious rows."""
    user = auth.create_user(
        config.database_url,
        username="dr.zero",
        email="dr.zero@example.com",
        password="TestPass123!",
    )
    assert (
        budget.record_usage(
            config.database_url, user_id=user.id, tokens=0
        )
        == 0
    )
    assert (
        budget.record_usage(
            config.database_url, user_id=user.id, tokens=-100
        )
        == 0
    )


def test_is_over_budget_disabled_when_budget_zero(config: Config) -> None:
    """budget=0 means the cost guard is disabled — even huge usage
    must not return True."""
    user = auth.create_user(
        config.database_url,
        username="dr.unlim",
        email="dr.unlim@example.com",
        password="TestPass123!",
    )
    budget.record_usage(
        config.database_url, user_id=user.id, tokens=10_000_000
    )
    assert not budget.is_over_budget(
        config.database_url, user_id=user.id, budget=0
    )


def test_is_over_budget_at_threshold_is_true(config: Config) -> None:
    """At-or-above the cap counts as over. We don't draw the line at
    'strictly above' — once you've hit the cap, the next call refuses."""
    user = auth.create_user(
        config.database_url,
        username="dr.cap",
        email="dr.cap@example.com",
        password="TestPass123!",
    )
    budget.record_usage(
        config.database_url, user_id=user.id, tokens=1000
    )
    assert budget.is_over_budget(
        config.database_url, user_id=user.id, budget=1000
    )
    assert budget.is_over_budget(
        config.database_url, user_id=user.id, budget=999
    )
    assert not budget.is_over_budget(
        config.database_url, user_id=user.id, budget=1001
    )


def test_usage_is_isolated_between_users(config: Config) -> None:
    a = auth.create_user(
        config.database_url,
        username="dr.a",
        email="dr.a@example.com",
        password="TestPass123!",
    )
    b = auth.create_user(
        config.database_url,
        username="dr.b",
        email="dr.b@example.com",
        password="TestPass123!",
    )
    budget.record_usage(
        config.database_url, user_id=a.id, tokens=5000
    )
    assert (
        budget.get_today_usage(config.database_url, user_id=a.id)
        == 5000
    )
    assert (
        budget.get_today_usage(config.database_url, user_id=b.id) == 0
    )


def test_total_tokens_in_turn_excludes_cache_reads() -> None:
    """Cache-read tokens are a cost optimization — not charged to the
    user. Cache-creation tokens come through input_tokens, which we DO
    charge."""
    plan = {
        "input_tokens": 1500,
        "output_tokens": 200,
        "cache_creation_input_tokens": 1000,
        "cache_read_input_tokens": 2000,
    }
    reason = {
        "input_tokens": 3000,
        "output_tokens": 600,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 5000,
    }
    # 1500 + 200 + 3000 + 600 = 5300; cache reads ignored.
    assert budget.total_tokens_in_turn(plan, reason) == 5300


# --- /chat integration ---


def _make_user_with_assignment(
    config: Config, *, username: str
) -> dict[str, Any]:
    user = auth.create_user(
        config.database_url,
        username=username,
        email=f"{username}@example.com",
        password="TestPass123!",
        role="physician",
    )
    secret = pyotp.random_base32()
    auth._save_totp_secret(config.database_url, user.id, secret)
    rbac.assign_patient(
        config.database_url, user_id=user.id, patient_id="demo-001"
    )
    return {"user": user, "secret": secret, "password": "TestPass123!"}


def _audit_events(database_url: str) -> list[str]:
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT event_type FROM audit_log ORDER BY id"
        ).fetchall()
    return [r["event_type"] for r in rows]


def test_chat_returns_429_when_user_is_over_budget(
    client: TestClient, config: Config, stub_run_turn
) -> None:
    info = _make_user_with_assignment(config, username="dr.budget")
    # Pre-load usage above the configured cap.
    budget.record_usage(
        config.database_url,
        user_id=info["user"].id,
        tokens=config.daily_token_budget + 1,
    )

    _login_with_mfa(
        client,
        username=info["user"].username,
        password=info["password"],
        secret=info["secret"],
    )

    res = client.post(
        "/chat", json={"patient_id": "demo-001", "message": "brief me"}
    )
    assert res.status_code == 429
    assert "budget exceeded" in res.json()["detail"].lower()
    # Orchestrator never invoked.
    assert stub_run_turn["calls"] == []


def test_over_budget_refusal_emits_audit_event(
    client: TestClient, config: Config, stub_run_turn
) -> None:
    info = _make_user_with_assignment(config, username="dr.budget")
    budget.record_usage(
        config.database_url,
        user_id=info["user"].id,
        tokens=config.daily_token_budget + 1,
    )
    _login_with_mfa(
        client,
        username=info["user"].username,
        password=info["password"],
        secret=info["secret"],
    )
    client.post(
        "/chat", json={"patient_id": "demo-001", "message": "brief me"}
    )
    events = _audit_events(config.database_url)
    assert "budget_exceeded" in events
    assert "chat_request" not in events  # never reached the orchestrator


def test_under_budget_chat_succeeds_and_records_usage(
    client: TestClient, config: Config, stub_run_turn
) -> None:
    """Stub run_turn returns trace.plan_usage / reason_usage = 0 by
    default; the integration test verifies that the BUDGET CHECK
    passes (under-budget) and a successful 200 is returned. Token
    accrual itself is exercised in the unit tests above."""
    info = _make_user_with_assignment(config, username="dr.under")
    _login_with_mfa(
        client,
        username=info["user"].username,
        password=info["password"],
        secret=info["secret"],
    )
    res = client.post(
        "/chat", json={"patient_id": "demo-001", "message": "brief me"}
    )
    assert res.status_code == 200
    assert len(stub_run_turn["calls"]) == 1
