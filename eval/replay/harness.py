"""Replay harness — record real Anthropic responses, then replay them
against the orchestrator without paying for API tokens.

Sits between unit tests (synthetic, fast) and live tests (real LLM, slow,
non-deterministic). Replay tests use real-shaped LLM responses but run
deterministically and for free, so the verifier and orchestrator wiring can
be regression-tested in CI without a Anthropic API key.

Cassettes are JSON, one per scenario, in eval/replay/cassettes/. Refresh
them with `python -m eval.replay.record`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anthropic.types import Message


CASSETTE_DIR = Path(__file__).parent / "cassettes"


# --- Cassette ---


@dataclass
class Cassette:
    scenario: str
    input: dict[str, str]  # {"patient_id": ..., "user_message": ...}
    model: str
    recorded_at: str
    calls: list[dict[str, Any]] = field(default_factory=list)
    expected: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, scenario: str) -> "Cassette":
        path = CASSETTE_DIR / f"{scenario}.json"
        if not path.is_file():
            raise FileNotFoundError(
                f"Cassette {scenario!r} not found at {path}.\n"
                f"Record it: python -m eval.replay.record {scenario}"
            )
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def save(self) -> Path:
        CASSETTE_DIR.mkdir(parents=True, exist_ok=True)
        path = CASSETTE_DIR / f"{self.scenario}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2, ensure_ascii=False)
        return path


# --- Replay (read-only stub) ---


class _ReplayMessages:
    """Stub for client.messages — returns recorded responses in order."""

    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self._calls = calls
        self._idx = 0

    async def create(self, **_kwargs: Any) -> Message:
        if self._idx >= len(self._calls):
            raise RuntimeError(
                f"Cassette exhausted: {self._idx} calls played, "
                f"{len(self._calls)} recorded. The orchestrator made an "
                f"unexpected extra LLM call — record a new cassette."
            )
        recorded = self._calls[self._idx]
        self._idx += 1
        return Message.model_validate(recorded["response"])


class ReplayAnthropicClient:
    """Drop-in replacement for anthropic.AsyncAnthropic that returns
    recorded responses instead of making real API calls.

    Pass an instance as the `client` arg to `agent.orchestrator.run_turn`
    — no monkeypatching needed."""

    def __init__(self, cassette: Cassette) -> None:
        self.messages = _ReplayMessages(cassette.calls)


# --- Recording (passthrough wrapper) ---


def _summarize_request(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Capture only the fields useful for cassette inspection. The full
    request body (system prompt + tool schemas + messages) is huge and
    redundant with the response — we don't need it for replay."""
    summary: dict[str, Any] = {
        "model": kwargs.get("model"),
        "max_tokens": kwargs.get("max_tokens"),
        "tool_choice": kwargs.get("tool_choice"),
        "tools": [t["name"] for t in (kwargs.get("tools") or [])],
        "messages_count": len(kwargs.get("messages") or []),
    }
    return {k: v for k, v in summary.items() if v is not None}


class _RecordingMessages:
    def __init__(self, real_messages: Any) -> None:
        self._real = real_messages
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Message:
        response = await self._real.create(**kwargs)
        self.calls.append(
            {
                "request_summary": _summarize_request(kwargs),
                "response": response.model_dump(mode="json"),
            }
        )
        return response


class RecordingAnthropicClient:
    """Wraps a real `anthropic.AsyncAnthropic`; captures every
    `messages.create()` call's response while otherwise passing through
    unchanged."""

    def __init__(self, real_client: Any) -> None:
        self.messages = _RecordingMessages(real_client.messages)


# --- Helpers ---


def derive_expectations(result: Any) -> dict[str, Any]:
    """Pin assertable expectations from a `TurnResult` so cassette tests
    catch regressions. We pin only properties that should be invariant
    under code changes — counts, booleans, tool ordering — never specific
    LLM phrasings."""
    verification = result.trace.verification
    return {
        "verified": result.verified,
        "no_unknown_ids": (
            verification is not None and not verification.unknown_ids
        ),
        "cited_ids_count": (
            len(verification.cited_ids) if verification else 0
        ),
        "retrieved_ids_count": len(result.trace.retrieved_source_ids),
        "plan_tool_calls": [
            tc["name"] for tc in result.trace.plan_tool_calls
        ],
        "refused": result.trace.refused,
        "response_nonempty": bool(result.response.strip()),
    }


def isoformat_now() -> str:
    return datetime.now(timezone.utc).isoformat()
