"""Plan → Retrieve → Reason → Verify pipeline.

Mirrors the LangGraph state machine spec'd in ARCHITECTURE.md §2.3 — kept as plain async
Python for the v0 slice. Lifting to LangGraph is a small follow-up: each function below
becomes a node, the dataclass becomes graph state, and Langfuse traces become per-node
spans rather than ad-hoc log lines."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic

from agent.prompts import PLAN_SYSTEM_PROMPT, REASON_SYSTEM_PROMPT
from agent.tools import TOOLS, execute_tools_parallel
from agent.verifier import VerificationResult, collect_source_ids, verify_response


log = logging.getLogger(__name__)


@dataclass
class TurnTrace:
    plan_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    retrieved_source_ids: list[str] = field(default_factory=list)
    reason_text: str = ""
    verification: VerificationResult | None = None
    refused: bool = False
    refusal_reason: str = ""
    plan_usage: dict[str, int] = field(default_factory=dict)
    reason_usage: dict[str, int] = field(default_factory=dict)


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
    trace = TurnTrace()

    plan_user_content = (
        f"Patient ID for this conversation (locked): {patient_id}\n\n"
        f"User question: {user_message}"
    )

    # ---- Plan node ----
    # Note: thinking is disabled here because the Anthropic API rejects
    # `thinking=adaptive` combined with `tool_choice` that forces tool use —
    # the two intents conflict. Plan is a simple "pick tools" call where
    # thinking adds little; clinical reasoning happens in the Reason node.
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
    trace.plan_usage = _usage_dict(plan_response.usage)

    tool_use_blocks = [b for b in plan_response.content if b.type == "tool_use"]
    if not tool_use_blocks:
        trace.refused = True
        trace.refusal_reason = "Plan node did not request any tools."
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
        "plan: %d tool call(s): %s",
        len(tool_use_blocks),
        [b.name for b in tool_use_blocks],
    )

    # ---- Retrieve node ----
    tool_results = await execute_tools_parallel(
        trace.plan_tool_calls,
        locked_patient_id=patient_id,
    )

    parsed_results: list[dict[str, Any]] = []
    for r in tool_results:
        try:
            parsed_results.append(json.loads(r["content"]))
        except (json.JSONDecodeError, TypeError):
            parsed_results.append({})

    retrieved_source_ids = collect_source_ids(parsed_results)
    trace.retrieved_source_ids = sorted(retrieved_source_ids)
    log.info("retrieve: %d source id(s) collected", len(retrieved_source_ids))

    if all(r.get("is_error") for r in tool_results):
        trace.refused = True
        trace.refusal_reason = "Every retrieval tool returned an error."
        return TurnResult(
            response=(
                "I couldn't retrieve the records I need to answer this. "
                "Please open the patient's chart directly."
            ),
            verified=False,
            trace=trace,
        )

    # ---- Reason node ----
    reason_response = await client.messages.create(
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
        messages=[
            {"role": "user", "content": plan_user_content},
            {"role": "assistant", "content": plan_response.content},
            {"role": "user", "content": tool_results},
        ],
    )
    trace.reason_usage = _usage_dict(reason_response.usage)

    reason_text = next(
        (b.text for b in reason_response.content if b.type == "text"),
        "",
    )
    trace.reason_text = reason_text

    # ---- Verify node ----
    verification = verify_response(reason_text, retrieved_source_ids)
    trace.verification = verification
    log.info(
        "verify: %s — %s",
        "PASS" if verification.passed else "FAIL",
        verification.note,
    )

    if not verification.passed:
        # v0: single-shot. ARCHITECTURE.md §2.5 specifies "regenerate once" — that's the
        # next iteration. For now, surface a structured fallback panel so the clinician
        # keeps a working tool instead of seeing an unverified narrative.
        return TurnResult(
            response=_fallback_panel(parsed_results, verification),
            verified=False,
            trace=trace,
        )

    return TurnResult(response=reason_text, verified=True, trace=trace)


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
