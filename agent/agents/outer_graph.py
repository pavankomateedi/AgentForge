"""LangGraph outer graph wrapping the Week 1 answer pipeline.

Topology:

    START -> supervisor -> dispatch (intake + evidence in parallel)
                        -> answer_pipeline -> END

The Week 1 11-node graph is invoked unchanged inside `answer_node` via
`agent.orchestrator.run_turn`. We don't modify it; we only enrich the
user_message with prep-worker output before calling it.

Each node writes a Langfuse-friendly log line so routing is inspectable
without re-running the turn (per the architecture doc's §5 commitment).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, TypedDict

import anthropic
from langgraph.graph import END, START, StateGraph

from agent import audit
from agent.agents.evidence_retriever_worker import (
    render_evidence_block,
    run_evidence_retriever_worker,
)
from agent.agents.intake_extractor_worker import (
    count_derived_for_patient,
    count_unprocessed_docs,
    run_intake_extractor_worker,
)
from agent.agents.supervisor import RoutingDecision, call_supervisor
from agent.orchestrator import TurnResult, run_turn
from agent.rag.retriever import RetrievalHit

log = logging.getLogger(__name__)


class OuterState(TypedDict, total=False):
    # ---- inputs ----
    patient_id: str
    user_message: str
    user_id: str
    user_role: str
    available_tools: list[dict[str, Any]]
    history: list[dict[str, str]]

    # ---- supervisor + workers ----
    routing: RoutingDecision
    extraction_summary: str
    evidence_hits: list[RetrievalHit]
    timings_ms: dict[str, int]

    # ---- output ----
    final_result: TurnResult


def _patient_context(database_url: str, patient_id: str) -> dict:
    return {
        "patient_id_hash": patient_id[-4:],
        "extracted_docs": count_derived_for_patient(database_url, patient_id),
        "unprocessed_docs": count_unprocessed_docs(database_url, patient_id),
    }


def build_outer_graph(
    *,
    client: anthropic.AsyncAnthropic,
    model: str,
    database_url: str,
):
    """Compile the outer graph. Captures `client/model/database_url` in
    closures so the graph nodes have everything they need without
    threading every dependency through state."""

    async def supervisor_node(state: OuterState) -> dict:
        t0 = time.perf_counter()
        ctx = _patient_context(database_url, state["patient_id"])
        decision = await call_supervisor(
            client=client,
            model=model,
            user_message=state["user_message"],
            patient_context=ctx,
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        audit.record(
            database_url,
            audit.AuditEvent.SUPERVISOR_ROUTING_DECISION,
            user_id=int(state["user_id"]) if state["user_id"].isdigit() else None,
            details={
                "patient_id": state["patient_id"],
                "workers_to_invoke": decision.workers_to_invoke,
                "reason": decision.reason[:256],
                "patient_context": ctx,
                "latency_ms": elapsed,
            },
        )
        return {"routing": decision, "timings_ms": {"supervisor_ms": elapsed}}

    async def dispatch_node(state: OuterState) -> dict:
        """Run the prep workers. intake_extractor + evidence_retriever
        are independent; gather them concurrently so prep latency is
        max(intake, evidence) rather than the sum."""
        decision = state["routing"]
        run_intake = "intake_extractor" in decision.workers_to_invoke
        run_evidence = "evidence_retriever" in decision.workers_to_invoke

        timings: dict[str, int] = dict(state.get("timings_ms", {}))
        out: dict[str, Any] = {}

        async def _intake():
            t0 = time.perf_counter()
            text = await run_intake_extractor_worker(
                database_url=database_url, patient_id=state["patient_id"]
            )
            return text, int((time.perf_counter() - t0) * 1000)

        async def _evidence():
            t0 = time.perf_counter()
            hits = await run_evidence_retriever_worker(
                query=state["user_message"], top_k=3
            )
            audit.record(
                database_url,
                audit.AuditEvent.EVIDENCE_RETRIEVAL,
                user_id=(
                    int(state["user_id"]) if state["user_id"].isdigit() else None
                ),
                details={
                    "patient_id": state["patient_id"],
                    "query_len": len(state["user_message"]),
                    "n_hits": len(hits),
                    "top_chunk_ids": [h.chunk.chunk_id for h in hits],
                },
            )
            return hits, int((time.perf_counter() - t0) * 1000)

        tasks: list = []
        if run_intake:
            tasks.append(_intake())
        if run_evidence:
            tasks.append(_evidence())

        if not tasks:
            return {"timings_ms": timings}

        results = await asyncio.gather(*tasks, return_exceptions=True)
        i = 0
        if run_intake:
            r = results[i]
            i += 1
            if isinstance(r, Exception):
                log.warning("dispatch: intake_extractor failed: %s", r)
                out["extraction_summary"] = ""
            else:
                text, ms = r
                out["extraction_summary"] = text
                timings["intake_extractor_ms"] = ms
        if run_evidence:
            r = results[i]
            i += 1
            if isinstance(r, Exception):
                log.warning("dispatch: evidence_retriever failed: %s", r)
                out["evidence_hits"] = []
            else:
                hits, ms = r
                out["evidence_hits"] = hits
                timings["evidence_retriever_ms"] = ms

        out["timings_ms"] = timings
        return out

    async def answer_node(state: OuterState) -> dict:
        """Wrap the existing Week 1 pipeline. The user_message is
        enriched with extraction_summary + evidence_hits as inline
        context blocks; the verifier still validates citations against
        the (extended) source set."""
        enriched = state["user_message"]
        ext = state.get("extraction_summary", "")
        hits = state.get("evidence_hits", [])
        suffixes: list[str] = []
        if ext:
            suffixes.append(ext)
        if hits:
            suffixes.append(render_evidence_block(hits))
        if suffixes:
            enriched = state["user_message"] + "\n\n" + "\n\n".join(suffixes)

        t0 = time.perf_counter()
        result = await run_turn(
            client=client,
            model=model,
            patient_id=state["patient_id"],
            user_message=enriched,
            user_id=state["user_id"],
            user_role=state["user_role"],
            available_tools=state["available_tools"],
            history=state.get("history", []),
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        timings = dict(state.get("timings_ms", {}))
        timings["answer_pipeline_ms"] = elapsed
        return {"final_result": result, "timings_ms": timings}

    builder = StateGraph(OuterState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("dispatch", dispatch_node)
    builder.add_node("answer_pipeline", answer_node)

    builder.add_edge(START, "supervisor")
    builder.add_edge("supervisor", "dispatch")
    builder.add_edge("dispatch", "answer_pipeline")
    builder.add_edge("answer_pipeline", END)

    return builder.compile()


async def run_multi_agent_turn(
    *,
    client: anthropic.AsyncAnthropic,
    model: str,
    database_url: str,
    patient_id: str,
    user_message: str,
    user_id: str,
    user_role: str,
    available_tools: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
) -> tuple[TurnResult, RoutingDecision, dict[str, int]]:
    """Top-level entry from /chat. Returns the final TurnResult plus
    the routing decision and per-step timings so the response trace
    can include the supervisor's reasoning."""
    graph = build_outer_graph(
        client=client, model=model, database_url=database_url
    )
    initial: OuterState = {
        "patient_id": patient_id,
        "user_message": user_message,
        "user_id": user_id,
        "user_role": user_role,
        "available_tools": available_tools,
        "history": history or [],
    }
    final_state = await graph.ainvoke(initial)
    return (
        final_state["final_result"],
        final_state["routing"],
        final_state.get("timings_ms", {}),
    )
