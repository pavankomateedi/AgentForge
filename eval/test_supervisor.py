"""Tests for the supervisor + heuristic router.

The LLM call surface is monkeypatched; what we pin is:
  - heuristic_route picks the right workers from natural-language
    questions for each demo scenario
  - LLM-mode supervisor delegates to heuristic on parse failure
  - RoutingDecision.normalize() always appends answer_pipeline last
    and dedups.
"""

from __future__ import annotations

from agent.agents.supervisor import (
    RoutingDecision,
    call_supervisor,
    heuristic_route,
)


# ---- RoutingDecision.normalize ----


def test_normalize_appends_answer_pipeline_last():
    d = RoutingDecision(
        workers_to_invoke=["evidence_retriever"], reason="x"
    ).normalize()
    assert d.workers_to_invoke == ["evidence_retriever", "answer_pipeline"]


def test_normalize_dedups_and_orders():
    d = RoutingDecision(
        workers_to_invoke=[
            "answer_pipeline",
            "intake_extractor",
            "evidence_retriever",
            "intake_extractor",
        ],
        reason="x",
    ).normalize()
    assert d.workers_to_invoke == [
        "intake_extractor",
        "evidence_retriever",
        "answer_pipeline",
    ]


def test_normalize_empty_input_still_includes_answer_pipeline():
    d = RoutingDecision(workers_to_invoke=[], reason="brief me only").normalize()
    assert d.workers_to_invoke == ["answer_pipeline"]


# ---- heuristic_route ----


def test_heuristic_brief_only_runs_answer_pipeline():
    d = heuristic_route(
        user_message="Brief me on this patient.",
        has_unprocessed_docs=False,
        has_extracted_docs=False,
    )
    assert d.workers_to_invoke == ["answer_pipeline"]


def test_heuristic_guideline_question_invokes_evidence():
    d = heuristic_route(
        user_message="Is this A1c trend concerning?",
        has_unprocessed_docs=False,
        has_extracted_docs=False,
    )
    assert "evidence_retriever" in d.workers_to_invoke
    assert d.workers_to_invoke[-1] == "answer_pipeline"


def test_heuristic_intake_question_with_docs_invokes_intake():
    d = heuristic_route(
        user_message="What does the intake form say about allergies?",
        has_unprocessed_docs=True,
        has_extracted_docs=False,
    )
    assert "intake_extractor" in d.workers_to_invoke


def test_heuristic_intake_question_without_docs_does_not_invoke_intake():
    """Calling intake_extractor when there's nothing to surface wastes
    a worker call. The supervisor should know this from patient
    context."""
    d = heuristic_route(
        user_message="What does the intake form say about allergies?",
        has_unprocessed_docs=False,
        has_extracted_docs=False,
    )
    assert "intake_extractor" not in d.workers_to_invoke


def test_heuristic_combined_question_invokes_both():
    d = heuristic_route(
        user_message=(
            "What does the lab report say, and is the trend concerning "
            "given the guideline target?"
        ),
        has_unprocessed_docs=False,
        has_extracted_docs=True,
    )
    assert "intake_extractor" in d.workers_to_invoke
    assert "evidence_retriever" in d.workers_to_invoke
    assert d.workers_to_invoke[-1] == "answer_pipeline"


# ---- call_supervisor (LLM-mode) ----


async def test_call_supervisor_falls_back_on_llm_failure(monkeypatch):
    """If the LLM raises or returns garbage, we MUST fall back to the
    heuristic router rather than break /chat."""

    class FailingClient:
        class messages:  # noqa: N801
            @staticmethod
            async def create(**kwargs):
                raise RuntimeError("network down")

    decision = await call_supervisor(
        client=FailingClient(),  # type: ignore[arg-type]
        model="claude-opus-4-7",
        user_message="Is metformin still indicated?",
        patient_context={"extracted_docs": 0, "unprocessed_docs": 0},
    )
    # Heuristic kicks in -> sees "indicated" keyword -> evidence_retriever.
    assert "evidence_retriever" in decision.workers_to_invoke
    assert decision.workers_to_invoke[-1] == "answer_pipeline"


async def test_call_supervisor_uses_llm_response(monkeypatch):
    """When the LLM returns valid JSON, that's what we use."""

    class OkClient:
        class messages:  # noqa: N801
            @staticmethod
            async def create(**kwargs):
                # Mimic Anthropic SDK response shape minimally.
                class Block:
                    type = "text"
                    text = (
                        '{"workers_to_invoke": ["evidence_retriever"], '
                        '"reason": "guideline-grounded question"}'
                    )

                class Resp:
                    content = [Block()]

                return Resp()

    decision = await call_supervisor(
        client=OkClient(),  # type: ignore[arg-type]
        model="claude-opus-4-7",
        user_message="Brief me",
        patient_context={"extracted_docs": 0, "unprocessed_docs": 0},
    )
    assert "evidence_retriever" in decision.workers_to_invoke


async def test_supervisor_mode_heuristic_skips_llm(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_MODE", "heuristic")
    called = {"n": 0}

    class CountingClient:
        class messages:  # noqa: N801
            @staticmethod
            async def create(**kwargs):
                called["n"] += 1
                raise RuntimeError("should not be called")

    await call_supervisor(
        client=CountingClient(),  # type: ignore[arg-type]
        model="claude-opus-4-7",
        user_message="brief me",
        patient_context={"extracted_docs": 0, "unprocessed_docs": 0},
    )
    assert called["n"] == 0
