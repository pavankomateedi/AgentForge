"""Replay tests — re-run the orchestrator against pre-recorded LLM
responses and assert that the verifier + trace properties match what was
captured at record time.

These tests are FREE (no Anthropic API call) and DETERMINISTIC. They catch
regressions in the verifier, the orchestrator wiring, and the audit
emission against real-shaped LLM outputs — the gap between unit tests
(synthetic inputs) and live tests (paid + non-deterministic).

Cassettes live in eval/replay/cassettes/. Refresh them with:
    python -m eval.replay.record
"""

from __future__ import annotations

import pytest

from agent.orchestrator import run_turn
from eval.replay.harness import CASSETTE_DIR, Cassette, ReplayAnthropicClient


def _scenarios() -> list[str]:
    if not CASSETTE_DIR.is_dir():
        return []
    return sorted(p.stem for p in CASSETTE_DIR.glob("*.json"))


SCENARIOS = _scenarios()


@pytest.mark.parametrize("scenario", SCENARIOS or ["__no_cassettes__"])
async def test_replay_scenario(scenario: str) -> None:
    if scenario == "__no_cassettes__":
        pytest.skip(
            "No cassettes recorded yet. "
            "Run: python -m eval.replay.record"
        )

    cassette = Cassette.load(scenario)
    client = ReplayAnthropicClient(cassette)
    result = await run_turn(
        client=client,
        model=cassette.model,
        patient_id=cassette.input["patient_id"],
        user_message=cassette.input["user_message"],
    )

    expected = cassette.expected
    verification = result.trace.verification

    # Verifier outcome must match what was captured.
    assert result.verified == expected["verified"], (
        f"{scenario}: verified drift "
        f"(got {result.verified}, expected {expected['verified']})"
    )

    if expected.get("no_unknown_ids"):
        assert verification is not None and not verification.unknown_ids, (
            f"{scenario}: verifier surfaced unknown ids "
            f"{verification.unknown_ids if verification else None}"
        )

    # Citation + retrieval counts pin the deterministic post-processing.
    assert (
        len(verification.cited_ids) if verification else 0
    ) == expected["cited_ids_count"], (
        f"{scenario}: cited-ids count drift "
        f"(got {len(verification.cited_ids) if verification else 0}, "
        f"expected {expected['cited_ids_count']})"
    )
    assert (
        len(result.trace.retrieved_source_ids)
        == expected["retrieved_ids_count"]
    ), (
        f"{scenario}: retrieval count drift "
        f"(got {len(result.trace.retrieved_source_ids)}, "
        f"expected {expected['retrieved_ids_count']})"
    )

    # Plan-node tool selection is part of the recorded LLM output, so it
    # should round-trip exactly.
    assert (
        [tc["name"] for tc in result.trace.plan_tool_calls]
        == expected["plan_tool_calls"]
    ), f"{scenario}: plan tool calls drifted from cassette"

    assert result.trace.refused == expected["refused"], (
        f"{scenario}: refused flag drift"
    )

    if expected["response_nonempty"]:
        assert result.response.strip() != "", (
            f"{scenario}: cassette expected nonempty response, got empty"
        )
