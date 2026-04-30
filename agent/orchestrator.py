"""Plan → Retrieve → Reason → Verify pipeline.

Mirrors the LangGraph state machine spec'd in ARCHITECTURE.md §2.3 — kept as plain async
Python for the v0 slice. Lifting to LangGraph is a small follow-up: each function below
becomes a node, the dataclass becomes graph state, and Langfuse traces become per-node
spans rather than ad-hoc log lines.

What this module guarantees:
  - Plan → tool calls (subject locked)
  - Retrieve → parallel tool execution, structured records w/ provenance
  - Reason → LLM-generated narrative with <source/> tags
  - Verify → deterministic pass over tags (source-id matching + numeric
    value-tolerance, see agent/verifier.py)
  - Regenerate-once on first verify fail; second fail → structured panel
  - Per-node timing + per-request trace_id surfaced in TurnTrace for the
    audit log and the UI's trace pane
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import anthropic

from agent.prompts import PLAN_SYSTEM_PROMPT, REASON_SYSTEM_PROMPT
from agent.tools import TOOLS, execute_tools_parallel
from agent.verifier import (
    VerificationResult,
    build_record_index,
    collect_source_ids,
    verify_response,
)


log = logging.getLogger(__name__)


@dataclass
class TurnTrace:
    trace_id: str = ""
    plan_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    retrieved_source_ids: list[str] = field(default_factory=list)
    reason_text: str = ""
    verification: VerificationResult | None = None
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
) -> TurnResult:
    trace = TurnTrace(trace_id=uuid.uuid4().hex[:12])
    log.info(
        "turn[%s] start patient=%s msg_len=%d",
        trace.trace_id,
        patient_id,
        len(user_message),
    )

    plan_user_content = (
        f"Patient ID for this conversation (locked): {patient_id}\n\n"
        f"User question: {user_message}"
    )

    # ---- Plan node ----
    # Note: thinking is disabled here because the Anthropic API rejects
    # `thinking=adaptive` combined with `tool_choice` that forces tool use —
    # the two intents conflict. Plan is a simple "pick tools" call where
    # thinking adds little; clinical reasoning happens in the Reason node.
    t0 = time.perf_counter()
    plan_response = await client.messages.create(
        model=model,
        max_tokens=16000,
        system=[
            {
                "type": "text",
                "text": PLAN_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=TOOLS,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": plan_user_content}],
    )
    trace.timings_ms["plan"] = _elapsed_ms(t0)
    trace.plan_usage = _usage_dict(plan_response.usage)

    tool_use_blocks = [b for b in plan_response.content if b.type == "tool_use"]
    if not tool_use_blocks:
        trace.refused = True
        trace.refusal_reason = "Plan node did not request any tools."
        log.info(
            "turn[%s] refused at plan: no tool calls",
            trace.trace_id,
        )
        return TurnResult(
            response=(
                "I couldn't plan a retrieval for that question. "
                "Please rephrase or open the patient's record directly."
            ),
            verified=False,
            trace=trace,
        )

    trace.plan_tool_calls = [
        {"id": b.id, "name": b.name, "input": dict(b.input)} for b in tool_use_blocks
    ]
    log.info(
        "turn[%s] plan: %dms, %d tool call(s): %s",
        trace.trace_id,
        trace.timings_ms["plan"],
        len(tool_use_blocks),
        [b.name for b in tool_use_blocks],
    )

    # ---- Retrieve node ----
    t0 = time.perf_counter()
    tool_results = await execute_tools_parallel(
        trace.plan_tool_calls,
        locked_patient_id=patient_id,
    )
    trace.timings_ms["retrieve"] = _elapsed_ms(t0)

    parsed_results: list[dict[str, Any]] = []
    for r in tool_results:
        try:
            parsed_results.append(json.loads(r["content"]))
        except (json.JSONDecodeError, TypeError):
            parsed_results.append({})

    retrieved_source_ids = collect_source_ids(parsed_results)
    record_index = build_record_index(parsed_results)
    trace.retrieved_source_ids = sorted(retrieved_source_ids)
    log.info(
        "turn[%s] retrieve: %dms, %d source id(s)",
        trace.trace_id,
        trace.timings_ms["retrieve"],
        len(retrieved_source_ids),
    )

    if all(r.get("is_error") for r in tool_results):
        trace.refused = True
        trace.refusal_reason = "Every retrieval tool returned an error."
        log.info(
            "turn[%s] refused at retrieve: all tools errored",
            trace.trace_id,
        )
        return TurnResult(
            response=(
                "I couldn't retrieve the records I need to answer this. "
                "Please open the patient's chart directly."
            ),
            verified=False,
            trace=trace,
        )

    # ---- Reason node (first pass) ----
    base_messages: list[dict[str, Any]] = [
        {"role": "user", "content": plan_user_content},
        {"role": "assistant", "content": plan_response.content},
        {"role": "user", "content": tool_results},
    ]

    t0 = time.perf_counter()
    reason_text, reason_usage = await _reason_call(client, model, base_messages)
    trace.timings_ms["reason"] = _elapsed_ms(t0)
    trace.reason_text = reason_text
    trace.reason_usage = reason_usage

    # ---- Verify node ----
    t0 = time.perf_counter()
    verification = verify_response(
        reason_text, retrieved_source_ids, record_index
    )
    trace.timings_ms["verify"] = _elapsed_ms(t0)
    trace.verification = verification
    log.info(
        "turn[%s] verify: %dms %s — %s",
        trace.trace_id,
        trace.timings_ms["verify"],
        "PASS" if verification.passed else "FAIL",
        verification.note,
    )

    if verification.passed:
        return TurnResult(response=reason_text, verified=True, trace=trace)

    # ---- Regenerate once (ARCHITECTURE.md §2.5) ----
    # Hand the failure back to the model verbatim so it can correct
    # itself instead of just retrying with the same context. This is
    # the cheap escape hatch before we fall back to the structured panel.
    log.info(
        "turn[%s] verify failed first pass — regenerating once",
        trace.trace_id,
    )
    trace.regenerated = True
    retry_messages = base_messages + [
        {"role": "assistant", "content": reason_text},
        {
            "role": "user",
            "content": _retry_feedback(verification),
        },
    ]

    t0 = time.perf_counter()
    retry_text, retry_usage = await _reason_call(
        client, model, retry_messages
    )
    trace.timings_ms["reason_retry"] = _elapsed_ms(t0)
    trace.reason_text = retry_text  # the user-facing text is the retry
    # Sum usage so cost accounting reflects both calls.
    for k, v in retry_usage.items():
        trace.reason_usage[k] = trace.reason_usage.get(k, 0) + v

    t0 = time.perf_counter()
    retry_verification = verify_response(
        retry_text, retrieved_source_ids, record_index
    )
    trace.timings_ms["verify_retry"] = _elapsed_ms(t0)
    trace.verification = retry_verification
    log.info(
        "turn[%s] verify retry: %s — %s",
        trace.trace_id,
        "PASS" if retry_verification.passed else "FAIL",
        retry_verification.note,
    )

    if retry_verification.passed:
        return TurnResult(response=retry_text, verified=True, trace=trace)

    # Two failures — fall back to a structured panel so the clinician
    # keeps a working tool instead of seeing an unverified narrative.
    return TurnResult(
        response=_fallback_panel(parsed_results, retry_verification),
        verified=False,
        trace=trace,
    )


async def _reason_call(
    client: anthropic.AsyncAnthropic,
    model: str,
    messages: list[dict[str, Any]],
) -> tuple[str, dict[str, int]]:
    response = await client.messages.create(
        model=model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": REASON_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )
    text = next(
        (b.text for b in response.content if b.type == "text"),
        "",
    )
    return text, _usage_dict(response.usage)


def _retry_feedback(v: VerificationResult) -> str:
    """Compose the user-turn message we send back to the LLM after a
    failed verification. The goal is to be specific so the model can
    correct itself, not just retry."""
    parts = [
        "Your previous response failed verification. Re-read the tool "
        "results above and produce a corrected briefing that addresses "
        "the failures below. Cite only source ids that appear in the "
        "tool results, and quote numeric values exactly as they appear "
        "in the cited record.",
        "",
        f"Failure: {v.note}",
    ]
    if v.unknown_ids:
        parts.append(
            f"Unknown source ids cited: {v.unknown_ids}. Remove these "
            f"or replace them with ids that are present in the bundle."
        )
    if v.value_mismatches:
        parts.append("Numeric value mismatches:")
        for mm in v.value_mismatches:
            parts.append(
                f"  - {mm.source_id}: prose said {mm.cited_value}, "
                f"record has {mm.record_value}. Use the record value."
            )
    return "\n".join(parts)


def _elapsed_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _usage_dict(usage: object) -> dict[str, int]:
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )
    return {f: getattr(usage, f, 0) or 0 for f in fields}


def _fallback_panel(parsed_results: list[dict[str, Any]], v: VerificationResult) -> str:
    lines = [
        "I retrieved the following records but could not produce a verified narrative.",
        f"({v.note})",
        "",
    ]
    for result in parsed_results:
        if not isinstance(result, dict):
            continue
        for key, value in result.items():
            lines.append(f"- {key}: {value}")
    return "\n".join(lines)
