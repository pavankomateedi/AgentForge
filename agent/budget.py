"""Per-user daily token budget (ARCHITECTURE.md §8.4).

Bounds the cost a single misuse can incur in one day. Tokens accrue
across both LLM calls in a turn (Plan + Reason, plus the regenerate-
once retry when it fires). When a user crosses the configured
threshold, /chat returns 429 with a friendly message and audits the
event; usage continues to accrue (so the audit log shows whether the
user kept retrying past the cap).

Day boundary: UTC midnight. Choosing UTC keeps the cap easy to reason
about across timezones — a multi-region rollout doesn't need per-
region rollover logic. Reset is automatic: the next day's row is a
fresh insert.

Why a hard cap and not a soft warning: the case-study doc names cost
control as a real constraint. A misbehaving client (or a malicious
prompt that drives token-bloated responses) should be containable
without a manual revert. Surfacing the cap in the response is the
soft signal; the cap itself is the hard one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from agent.db import connect


log = logging.getLogger(__name__)


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_today_usage(database_url: str, *, user_id: int) -> int:
    """Tokens consumed by this user today (UTC). Returns 0 when there
    is no row yet."""
    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT tokens_used FROM daily_token_usage "
            "WHERE user_id = ? AND usage_date = ?",
            (user_id, _today_utc()),
        ).fetchone()
    return int(row["tokens_used"]) if row else 0


def is_over_budget(
    database_url: str, *, user_id: int, budget: int
) -> bool:
    """True if today's usage already meets or exceeds the cap. The
    pre-/chat check uses this so we refuse the request before incurring
    additional tokens."""
    if budget <= 0:
        return False  # 0 disables the guard
    return get_today_usage(database_url, user_id=user_id) >= budget


def record_usage(
    database_url: str, *, user_id: int, tokens: int
) -> int:
    """Increment today's counter atomically. Returns the new total.
    Idempotent under duplicate calls only if the caller dedupes —
    we always increment by `tokens`."""
    if tokens <= 0:
        return get_today_usage(database_url, user_id=user_id)

    today = _today_utc()
    with connect(database_url) as conn:
        # SQLite upsert: insert if missing, otherwise add to existing.
        conn.execute(
            "INSERT INTO daily_token_usage (user_id, usage_date, tokens_used) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, usage_date) DO UPDATE SET "
            "tokens_used = tokens_used + excluded.tokens_used",
            (user_id, today, tokens),
        )
        conn.commit()
        row = conn.execute(
            "SELECT tokens_used FROM daily_token_usage "
            "WHERE user_id = ? AND usage_date = ?",
            (user_id, today),
        ).fetchone()
    return int(row["tokens_used"])


def total_tokens_in_turn(plan_usage: dict, reason_usage: dict) -> int:
    """Sum input + output tokens across both LLM calls. Cache reads
    are excluded from the budget on the principle that cache hits are
    a cost optimization the user shouldn't be charged for, but cache
    creations are billed and ARE included via input_tokens."""
    return (
        int(plan_usage.get("input_tokens", 0))
        + int(plan_usage.get("output_tokens", 0))
        + int(reason_usage.get("input_tokens", 0))
        + int(reason_usage.get("output_tokens", 0))
    )
