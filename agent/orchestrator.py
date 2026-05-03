"""Public orchestrator entry — Plan → Retrieve → Rules → Reason →
Verify pipeline.

The pipeline now lives in agent.graph as an inspectable LangGraph
StateGraph (ARCHITECTURE.md §2.3). This module is the thin facade
/chat calls into:

  - Builds the initial state from request inputs.
  - Wraps the graph invocation in a Langfuse trace (chat_turn root
    span + per-node generations/spans set inside each node).
  - Hashes the patient_id for trace metadata so the dashboard never
    sees a raw demo id.
  - Emits trace-level scores after the graph completes (verifier
    pass-rate, regenerated, refused, rule_findings_count, etc.) so
    drift is visible per-day in the dashboard.
  - Packages graph output into the TurnResult dataclass /chat returns.

The dataclasses (TurnTrace, TurnResult) stay here because they are the
public contract /chat depends on; the graph internals can evolve
without breaking that contract.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import anthropic

from agent import observability as obs
from agent.graph import get_graph
from agent.rules import RuleFinding
from agent.verifier import VerificationResult


log = logging.getLogger(__name__)


@dataclass
class TurnTrace:
    trace_id: str = ""
    plan_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    retrieved_source_ids: list[str] = field(default_factory=list)
    reason_text: str = ""
    verification: VerificationResult | None = None
    # Domain-rule findings from agent.rules — independent of the LLM,
    # always deterministic, surfaced to the reason node and the trace.
    rule_findings: list[RuleFinding] = field(default_factory=list)
    regenerated: bool = False  # True if the reason node ran twice
    refused: bool = False
    refusal_reason: str = ""
    plan_usage: dict[str, int] = field(default_factory=dict)
    reason_usage: dict[str, int] = field(default_factory=dict)
    # Wall-clock ms per node. Lets the operator see where latency lives
    # without standing up Langfuse first.
    timings_ms: dict[str, int] = field(default_factory=dict)


@dataclass
class TurnResult:
    response: str
    verified: bool
    trace: TurnTrace


async def run_turn(
    *,
    client: anthropic.AsyncAnthropic,
    model: str,
    patient_id: str,
    user_message: str,
    user_id: str | None = None,
    user_role: str | None = None,
    available_tools: list[dict[str, Any]] | None = None,
) -> TurnResult:
    trace = TurnTrace(trace_id=uuid.uuid4().hex[:12])
    log.info(
        "turn[%s] start patient=%s msg_len=%d",
        trace.trace_id,
        patient_id,
        len(user_message),
    )

    initial_state: dict[str, Any] = {
        "client": client,
        "model": model,
        "patient_id": patient_id,
        "user_message": user_message,
        "user_id": user_id,
        "user_role": user_role,
        "available_tools": available_tools,
        "trace": trace,
    }

    # The Langfuse turn context wraps the entire graph execution; per-
    # node generations and spans are emitted from inside each node so
    # the dashboard tree mirrors the graph topology.
    with obs.turn(
        trace_id=trace.trace_id,
        user_id=user_id,
        user_role=user_role,
        patient_id_hash=_hash_patient_id(patient_id),
        user_message=user_message,
    ):
        graph = get_graph()
        final_state = await graph.ainvoke(initial_state)

        # The graph mutates the same TurnTrace instance we passed in,
        # so trace_id, timings, verification, rule_findings, etc. are
        # all already populated. Just pull the response/verified flags.
        response = final_state.get("response", "")
        verified = bool(final_state.get("verified", False))

        # Trace-level scores power the verifier-pass-rate dashboard view.
        v = trace.verification
        obs.score("verified", verified)
        obs.score("regenerated", trace.regenerated)
        obs.score("refused", trace.refused)
        if v is not None:
            obs.score("cited_ids_count", len(v.cited_ids))
            obs.score("value_mismatches", len(v.value_mismatches))
        obs.score("rule_findings_count", len(trace.rule_findings))
        critical_count = sum(
            1 for f in trace.rule_findings if f.severity == "critical"
        )
        if critical_count:
            obs.score("rule_critical_count", critical_count)

        return TurnResult(
            response=response, verified=verified, trace=trace
        )


def _hash_patient_id(patient_id: str) -> str:
    """Stable, non-reversible-ish identifier for the trace metadata. We
    don't need cryptographic strength — just don't put a raw demo id in
    Langfuse if it happened to ever be a real one. The audit log gets
    the real id."""
    return hashlib.sha1(  # noqa: S324 — non-security use; flagged usedforsecurity=False
        patient_id.encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:12]
