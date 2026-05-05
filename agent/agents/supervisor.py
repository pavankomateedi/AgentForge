"""Supervisor: LLM-driven routing decision.

Picks which prep workers to invoke before the answer pipeline runs.
Output is a strict-schema `RoutingDecision`; failures fall back to a
safe default of `[answer_pipeline]` so a misbehaving supervisor never
blocks the user.

The supervisor is a thin call by design:
  - tiny system prompt describing the 3 workers + when each fires
  - the user's question
  - a structural patient context summary (counts, not PHI text)
  - asks for JSON: {workers_to_invoke: [...], reason: "..."}

Heuristic fallback (`heuristic_route`) is used when the LLM call is
disabled (`SUPERVISOR_MODE=heuristic`) or as the last-resort default.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from agent.extractors._vision import _strip_to_json

log = logging.getLogger(__name__)


WorkerName = Literal["intake_extractor", "evidence_retriever", "answer_pipeline"]

_GUIDELINE_KEYWORDS = (
    "guideline", "guidance", "recommend", "indicat", "concern",
    "appropriate", "should", "target", "threshold", "interaction",
    "interact", "contraindicat", "safe", "risk", "criteria",
)
_INTAKE_KEYWORDS = (
    "intake", "form", "document", "uploaded", "lab report", "scan",
    "pdf", "what does the form", "say in the document",
)


class RoutingDecision(BaseModel):
    """Strict supervisor output. `answer_pipeline` is implicitly always
    invoked after the prep workers; the supervisor only decides which
    prep workers run alongside it. We still keep `answer_pipeline` as
    a valid value so the LLM can express 'just the existing pipeline,
    no prep' explicitly."""

    workers_to_invoke: list[WorkerName] = Field(default_factory=list)
    reason: str = Field(..., min_length=1, max_length=512)

    def normalize(self) -> "RoutingDecision":
        """answer_pipeline always runs last; dedup workers; keep stable
        order: intake_extractor, evidence_retriever, answer_pipeline."""
        ordered = []
        if "intake_extractor" in self.workers_to_invoke:
            ordered.append("intake_extractor")
        if "evidence_retriever" in self.workers_to_invoke:
            ordered.append("evidence_retriever")
        ordered.append("answer_pipeline")
        return RoutingDecision(workers_to_invoke=ordered, reason=self.reason)


def heuristic_route(
    *,
    user_message: str,
    has_unprocessed_docs: bool,
    has_extracted_docs: bool,
) -> RoutingDecision:
    """Cheap deterministic router used by tests + the eval gate. Mirrors
    the routing examples in W2_ARCHITECTURE.md §5."""
    text = user_message.lower()
    workers: list[WorkerName] = []
    reasons: list[str] = []

    if any(k in text for k in _INTAKE_KEYWORDS) and (
        has_unprocessed_docs or has_extracted_docs
    ):
        workers.append("intake_extractor")
        reasons.append("question references intake/document content")

    if any(k in text for k in _GUIDELINE_KEYWORDS):
        workers.append("evidence_retriever")
        reasons.append("question references guideline/recommendation")

    workers.append("answer_pipeline")
    if not reasons:
        reasons.append("default — answer pipeline only")

    return RoutingDecision(
        workers_to_invoke=workers, reason="; ".join(reasons)
    ).normalize()


_SYSTEM_PROMPT = """You are a routing supervisor for a clinical co-pilot.

Three workers are available:
  - intake_extractor: surfaces structured facts from previously-uploaded
    clinical documents (lab PDFs, intake forms) for this patient.
    Invoke when the question is about document content or recently-
    uploaded data.
  - evidence_retriever: retrieves clinical guideline excerpts (A1c
    targets, drug interactions, BP thresholds, GDMT, etc.). Invoke
    when the question requires guideline grounding ("is this trend
    concerning?", "is metformin still indicated?", "should we add a
    statin?").
  - answer_pipeline: the standard FHIR-data answer pipeline. ALWAYS
    invoked last; the prep workers add context for it.

Output STRICT JSON (no prose, no markdown fences):
  {"workers_to_invoke": [...], "reason": "<brief>"}

Use empty list for workers_to_invoke when neither prep worker is
needed; answer_pipeline runs unconditionally."""


async def call_supervisor(
    *,
    client: anthropic.AsyncAnthropic,
    model: str,
    user_message: str,
    patient_context: dict,
) -> RoutingDecision:
    """Run the supervisor LLM call. Returns a RoutingDecision.

    Falls back to `heuristic_route` on any failure (network, parse,
    schema mismatch). The supervisor is fail-safe — a routing failure
    must not break the user's request, and the answer pipeline can
    almost always answer correctly without prep workers.
    """
    if os.environ.get("SUPERVISOR_MODE", "").lower() == "heuristic":
        return heuristic_route(
            user_message=user_message,
            has_unprocessed_docs=bool(patient_context.get("unprocessed_docs", 0)),
            has_extracted_docs=bool(patient_context.get("extracted_docs", 0)),
        )

    user_prompt = (
        f"Patient context (counts only): {json.dumps(patient_context)}\n"
        f"User message: {user_message}\n\n"
        "Return the routing decision JSON."
    )
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text_blocks = [
            b.text for b in response.content if getattr(b, "type", None) == "text"
        ]
        if not text_blocks:
            raise ValueError("supervisor response had no text blocks")
        raw = json.loads(_strip_to_json("".join(text_blocks)))
        decision = RoutingDecision.model_validate(raw).normalize()
        log.info(
            "supervisor: workers=%s reason=%r",
            decision.workers_to_invoke, decision.reason[:80],
        )
        return decision
    except (json.JSONDecodeError, ValidationError, ValueError, Exception) as e:
        log.warning(
            "supervisor: LLM routing failed (%s) — falling back to heuristic",
            type(e).__name__,
        )
        return heuristic_route(
            user_message=user_message,
            has_unprocessed_docs=bool(patient_context.get("unprocessed_docs", 0)),
            has_extracted_docs=bool(patient_context.get("extracted_docs", 0)),
        )
