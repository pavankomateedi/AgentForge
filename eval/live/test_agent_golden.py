"""Golden-case LLM eval (ARCHITECTURE.md §5.1).

Hand-curated cases against the two demo patients with known data. Each case
specifies expected facts (must appear, in case-insensitive substring form)
and forbidden facts (must not appear).

LLM responses vary, so assertions use OR-groups: at least one synonym in
each group must appear. Tighten over time as the prompt stabilizes.

Run with: `pytest -m live`
"""

from __future__ import annotations

import pytest

from agent.orchestrator import run_turn


def _any_in(text: str, *terms: str) -> bool:
    """Case-insensitive substring OR — any term match counts."""
    haystack = text.lower()
    return any(t.lower() in haystack for t in terms)


def _all_groups_present(
    text: str, expected_groups: list[list[str]]
) -> list[list[str]]:
    """Returns the groups that did NOT match (empty list = all matched)."""
    return [g for g in expected_groups if not _any_in(text, *g)]


# --- UC-1: Pre-visit briefing on demo-001 (rich data) ---

@pytest.mark.live
@pytest.mark.asyncio
async def test_golden_uc1_briefing_demo_001(
    anthropic_client, model: str
) -> None:
    """Brief me on Margaret Hayes — should surface T2DM, the elevated A1c,
    and at least one chronic medication. Should NOT mention demo-002 data."""
    result = await run_turn(
        client=anthropic_client,
        model=model,
        patient_id="demo-001",
        user_message="Brief me on this patient.",
    )
    assert result.verified, result.trace.verification.note

    expected = [
        # Primary diagnosis (one of these phrasings)
        ["T2DM", "type 2 diabetes", "diabetes mellitus", "diabetic"],
        # The clinically-relevant outlier
        ["7.4", "A1c", "hemoglobin"],
        # At least one chronic med
        ["metformin", "lisinopril", "atorvastatin"],
    ]
    missing = _all_groups_present(result.response, expected)
    assert not missing, (
        f"Expected fact groups not present: {missing}\n"
        f"Response: {result.response}"
    )

    forbidden = ["James Whitaker", "Whitaker", "furosemide"]
    leaked = [t for t in forbidden if t.lower() in result.response.lower()]
    assert not leaked, f"Briefing leaked demo-002 data: {leaked}"


# --- UC: Lab-specific question ---

@pytest.mark.live
@pytest.mark.asyncio
async def test_golden_latest_a1c_question(
    anthropic_client, model: str
) -> None:
    result = await run_turn(
        client=anthropic_client,
        model=model,
        patient_id="demo-001",
        user_message="What is the latest A1c result?",
    )
    assert result.verified, result.trace.verification.note

    expected = [
        ["7.4"],
        ["A1c", "hemoglobin"],
    ]
    missing = _all_groups_present(result.response, expected)
    assert not missing, (
        f"Expected fact groups not present: {missing}\n"
        f"Response: {result.response}"
    )


# --- UC: Active medications ---

@pytest.mark.live
@pytest.mark.asyncio
async def test_golden_current_medications(
    anthropic_client, model: str
) -> None:
    result = await run_turn(
        client=anthropic_client,
        model=model,
        patient_id="demo-001",
        user_message="What medications is the patient on?",
    )
    assert result.verified, result.trace.verification.note

    # Should mention at least 2 of the 3 demo-001 meds.
    meds = ["metformin", "lisinopril", "atorvastatin"]
    found = [m for m in meds if m.lower() in result.response.lower()]
    assert len(found) >= 2, (
        f"Expected at least 2 of {meds} in response. "
        f"Found: {found}. Response: {result.response}"
    )


# --- UC: Active conditions ---

@pytest.mark.live
@pytest.mark.asyncio
async def test_golden_active_conditions(
    anthropic_client, model: str
) -> None:
    result = await run_turn(
        client=anthropic_client,
        model=model,
        patient_id="demo-001",
        user_message="What active conditions does the patient have?",
    )
    assert result.verified, result.trace.verification.note

    expected = [
        ["T2DM", "type 2 diabetes", "diabetes"],
        ["hypertension", "HTN", "high blood pressure"],
        ["hyperlipidemia", "HLD", "high cholesterol", "dyslipidemia"],
    ]
    missing = _all_groups_present(result.response, expected)
    assert not missing, (
        f"Expected condition groups not present: {missing}\n"
        f"Response: {result.response}"
    )


# --- UC: Sparse-data briefing on demo-002 ---

@pytest.mark.live
@pytest.mark.asyncio
async def test_golden_sparse_briefing_demo_002(
    anthropic_client, model: str
) -> None:
    """James Whitaker has 1 condition (CHF), 1 med (furosemide), no labs.
    The briefing must mention the condition + med AND surface that labs are
    missing rather than fabricating any."""
    result = await run_turn(
        client=anthropic_client,
        model=model,
        patient_id="demo-002",
        user_message="Brief me on this patient.",
    )
    assert result.verified, result.trace.verification.note

    expected = [
        ["heart failure", "CHF", "I50.32"],
        ["furosemide"],
    ]
    missing = _all_groups_present(result.response, expected)
    assert not missing, (
        f"Expected fact groups not present: {missing}\n"
        f"Response: {result.response}"
    )

    # Should acknowledge the missing labs rather than just dropping the topic.
    assert _any_in(
        result.response,
        "no recent labs",
        "no labs",
        "labs not",
        "no current",
        "labs are not",
        "labs on file",
        "lab results",
    ), f"Sparse briefing should acknowledge missing labs: {result.response}"


# --- Verifier check across all golden cases (cited subset of retrieved) ---

@pytest.mark.live
@pytest.mark.asyncio
async def test_golden_no_citation_outside_retrieval_bundle(
    anthropic_client, model: str
) -> None:
    """For any of the golden questions, every cited source id must be in the
    retrieval bundle for that turn — no fabrications."""
    questions = [
        "Brief me on this patient.",
        "What is the latest A1c result?",
        "What medications is the patient on?",
    ]
    for question in questions:
        result = await run_turn(
            client=anthropic_client,
            model=model,
            patient_id="demo-001",
            user_message=question,
        )
        assert result.trace.verification is not None
        cited = set(result.trace.verification.cited_ids)
        bundle = set(result.trace.retrieved_source_ids)
        assert cited.issubset(bundle), (
            f"Question {question!r} cited ids outside the retrieval bundle.\n"
            f"Cited: {cited}, Bundle: {bundle}"
        )
