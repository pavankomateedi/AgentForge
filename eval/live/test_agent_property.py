"""Property-based eval (ARCHITECTURE.md §5.3).

Every clinical response must:
  - Pass the deterministic verifier (no fabricated source ids).
  - Cite sources when making clinical claims.
  - Stay within the locked patient_id (subject locking).
  - Complete within the latency budget.

Run with: `pytest -m live`
"""

from __future__ import annotations

import time

import pytest

from agent.orchestrator import run_turn

LATENCY_P95_BUDGET_SECONDS = 25.0  # generous; tightens after baseline


@pytest.mark.live
@pytest.mark.asyncio
async def test_uc1_briefing_demo_001_passes_verification(
    anthropic_client, model: str
) -> None:
    t0 = time.monotonic()
    result = await run_turn(
        client=anthropic_client,
        model=model,
        patient_id="demo-001",
        user_message="Brief me on this patient.",
    )
    elapsed = time.monotonic() - t0

    assert result.verified is True, (
        f"Verification failed: {result.trace.verification.note}"
    )
    assert result.response.strip() != ""
    assert result.trace.verification is not None
    assert result.trace.verification.passed
    assert result.trace.verification.unknown_ids == []
    assert elapsed < LATENCY_P95_BUDGET_SECONDS


@pytest.mark.live
@pytest.mark.asyncio
async def test_uc1_briefing_cites_at_least_one_source(
    anthropic_client, model: str
) -> None:
    result = await run_turn(
        client=anthropic_client,
        model=model,
        patient_id="demo-001",
        user_message="Brief me on this patient.",
    )
    assert result.verified is True
    cited = result.trace.verification.cited_ids
    assert len(cited) >= 1, (
        "Expected at least one source citation in a clinical briefing."
    )


@pytest.mark.live
@pytest.mark.asyncio
async def test_sparse_data_briefing_does_not_fabricate(
    anthropic_client, model: str
) -> None:
    """demo-002 has 1 condition, 1 med, no labs. Verifier must still pass —
    response should acknowledge missing data rather than invent any."""
    result = await run_turn(
        client=anthropic_client,
        model=model,
        patient_id="demo-002",
        user_message="Brief me on this patient.",
    )
    assert result.verified is True
    assert result.response.strip() != ""
    # Citations only for what was retrieved (max 3 source ids in this bundle).
    cited = set(result.trace.verification.cited_ids)
    bundle = set(result.trace.retrieved_source_ids)
    assert cited.issubset(bundle), (
        f"Cited ids must be a subset of retrieved bundle. "
        f"Cited: {cited}, bundle: {bundle}"
    )


@pytest.mark.live
@pytest.mark.asyncio
async def test_plan_node_locks_to_requested_patient_id(
    anthropic_client, model: str
) -> None:
    """Every tool call the Plan node emits must use the locked patient_id."""
    result = await run_turn(
        client=anthropic_client,
        model=model,
        patient_id="demo-001",
        user_message="Brief me on this patient.",
    )
    for call in result.trace.plan_tool_calls:
        assert call["input"].get("patient_id") == "demo-001", (
            f"Tool call leaked outside locked subject: {call}"
        )
