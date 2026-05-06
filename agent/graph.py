"""LangGraph state machine for the Plan→Retrieve→Rules→Reason→Verify
pipeline (ARCHITECTURE.md §2.3).

Each pipeline step is a node; transitions are explicit edges. Verify
uses conditional edges to route to either Respond (pass), Reason-retry
(first fail), or the structured fallback panel (second fail). The graph
is the inspectable artifact reviewers can point at and say "this is
where verification happens" — exactly the property §2.3 calls out as the
reason LangGraph was chosen over a free-form ReAct loop.

Node ↔ orchestrator mapping:
  plan           — Plan LLM call; picks which FHIR tools to invoke
  retrieve       — Parallel tool execution against mock FHIR
  rules          — Deterministic clinical-rule engine over retrieval
  reason         — Reason LLM call; produces briefing with <source/>
                   tags, conditioned on rule findings
  verify         — Deterministic verifier (source-id + value-tolerance)
  reason_retry   — Reason LLM call again with the verifier's failure
                   reason in context (regenerate-once per §2.5)
  verify_retry   — Verifier rerun on the regenerated text
  respond        — Terminal: surfaces verified narrative
  refuse_no_plan — Terminal: Plan node returned no tool calls
  refuse_no_data — Terminal: every retrieval tool errored
  refuse_unverified — Terminal: two verifier failures → fallback panel

Per-node Langfuse spans/generations are emitted from inside each node
via agent.observability so trace structure stays the same as the
pre-LangGraph orchestrator. Adding the LangChain callback handler is a
v1 swap-out; for now the manual instrumentation gives us the custom
metadata (cited_ids, value_mismatches, severity counts) that the
generic callback wouldn't capture.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, TypedDict

import anthropic
from langgraph.graph import END, START, StateGraph

from agent import observability as obs
from agent.prompts import PLAN_SYSTEM_PROMPT, REASON_SYSTEM_PROMPT
from agent.rules import RuleFinding, evaluate_clinical_rules
from agent.tools import TOOLS, execute_tools_parallel
from agent.verifier import (
    VerificationResult,
    build_record_index,
    collect_source_ids,
    verify_response,
)


log = logging.getLogger(__name__)


# --- Shared state shape ---


class TurnState(TypedDict, total=False):
    """State threaded through every node in the graph.

    `total=False` because nodes populate fields incrementally — Plan
    sets plan_response_content, Retrieve sets parsed_results, etc.
    Inputs come in pre-set; outputs (response, verified) come out at
    the terminal nodes."""

    # ---- Inputs (set by run_turn before invoke) ----
    client: anthropic.AsyncAnthropic
    model: str
    patient_id: str
    user_message: str
    user_id: str | None
    user_role: str | None
    available_tools: list[dict[str, Any]] | None
    # Prior turns for follow-up coherence. Empty list = single-turn
    # behavior. Capped server-side in /chat before reaching here.
    history: list[dict[str, str]]

    # ---- Mutated by nodes ----
    trace: Any  # TurnTrace, kept Any to avoid circular import
    plan_user_content: str
    plan_response_content: list[Any]  # anthropic content blocks
    parsed_results: list[dict[str, Any]]
    retrieved_source_ids: set[str]
    record_index: dict[str, dict[str, Any]]
    base_messages: list[dict[str, Any]]
    rule_findings: list[RuleFinding]
    verification: VerificationResult | None

    # ---- Outputs ----
    response: str
    verified: bool


# --- Node functions ---


async def plan_node(state: TurnState) -> dict[str, Any]:
    client = state["client"]
    model = state["model"]
    patient_id = state["patient_id"]
    user_message = state["user_message"]
    plan_tools = state.get("available_tools") or TOOLS

    plan_user_content = (
        f"Patient ID for this conversation (locked): {patient_id}\n\n"
        f"User question: {user_message}"
    )

    # Prior turns (if any) are inserted BEFORE the locked-patient
    # prompt. Order matters: the locked-patient instruction is the
    # last user-role message the model sees, so any prior reference
    # to a different patient cannot override the current scope.
    history = state.get("history") or []
    plan_messages: list[dict[str, Any]] = [
        *history,
        {"role": "user", "content": plan_user_content},
    ]

    # Note: thinking is disabled here because the Anthropic API rejects
    # `thinking=adaptive` combined with `tool_choice` that forces tool
    # use — the two intents conflict. Plan is a simple "pick tools"
    # call; clinical reasoning happens in Reason.
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
        tools=plan_tools,
        tool_choice={"type": "any"},
        messages=plan_messages,
    )
    elapsed = _elapsed_ms(t0)

    trace = state["trace"]
    trace.timings_ms["plan"] = elapsed
    trace.plan_usage = _usage_dict(plan_response.usage)

    tool_use_blocks = [
        b for b in plan_response.content if b.type == "tool_use"
    ]

    obs.log_generation(
        name="plan",
        model=model,
        input_messages=[{"role": "user", "content": plan_user_content}],
        output=str([b.name for b in tool_use_blocks]),
        usage=trace.plan_usage,
        duration_ms=elapsed,
        metadata={"tool_calls": [b.name for b in tool_use_blocks]},
    )

    if not tool_use_blocks:
        trace.refused = True
        trace.refusal_reason = "Plan node did not request any tools."
        log.info(
            "turn[%s] refused at plan: no tool calls",
            trace.trace_id,
        )
        return {
            "plan_user_content": plan_user_content,
            "trace": trace,
        }

    trace.plan_tool_calls = [
        {"id": b.id, "name": b.name, "input": dict(b.input)}
        for b in tool_use_blocks
    ]
    log.info(
        "turn[%s] plan: %dms, %d tool call(s): %s",
        trace.trace_id,
        elapsed,
        len(tool_use_blocks),
        [b.name for b in tool_use_blocks],
    )
    return {
        "plan_user_content": plan_user_content,
        "plan_response_content": plan_response.content,
        "trace": trace,
    }


async def retrieve_node(state: TurnState) -> dict[str, Any]:
    trace = state["trace"]
    patient_id = state["patient_id"]
    plan_tool_calls = trace.plan_tool_calls

    t0 = time.perf_counter()
    tool_results = await execute_tools_parallel(
        plan_tool_calls,
        locked_patient_id=patient_id,
    )
    elapsed = _elapsed_ms(t0)
    trace.timings_ms["retrieve"] = elapsed

    parsed_results: list[dict[str, Any]] = []
    for r in tool_results:
        try:
            parsed_results.append(json.loads(r["content"]))
        except (json.JSONDecodeError, TypeError):
            parsed_results.append({})

    # Fold any caller-provided extras (intake_extractor derived rows,
    # evidence_retriever guideline chunks) into the source-id pool so
    # the verifier doesn't reject citations the supervisor injected
    # via the user_message text. Extras are NOT re-injected into the
    # Reason node's message list — that already happened upstream
    # via the user_message's <extracted_documents> / <guideline_evidence>
    # blocks. We just need them in the verifier's "what was retrieved
    # this turn" set.
    extras: list[dict[str, Any]] = state.get("extra_retrieved_records") or []
    pool = parsed_results + extras

    retrieved_source_ids = collect_source_ids(pool)
    record_index = build_record_index(pool)
    trace.retrieved_source_ids = sorted(retrieved_source_ids)

    tool_errors = [r for r in tool_results if r.get("is_error")]
    obs.log_span(
        name="retrieve",
        duration_ms=elapsed,
        metadata={
            "tools": [tc["name"] for tc in plan_tool_calls],
            "source_id_count": len(retrieved_source_ids),
            "error_count": len(tool_errors),
        },
        output={"source_ids": trace.retrieved_source_ids},
        error=(
            f"{len(tool_errors)}/{len(tool_results)} tool calls errored"
            if tool_errors
            else None
        ),
    )
    log.info(
        "turn[%s] retrieve: %dms, %d source id(s)",
        trace.trace_id,
        elapsed,
        len(retrieved_source_ids),
    )

    if all(r.get("is_error") for r in tool_results):
        trace.refused = True
        trace.refusal_reason = "Every retrieval tool returned an error."
        log.info(
            "turn[%s] refused at retrieve: all tools errored",
            trace.trace_id,
        )

    # Stash the raw tool_results for the reason node (it builds the
    # message list off them). History is prepended so Reason has the
    # same conversational context Plan saw, then the tool-call /
    # tool-result chain for THIS turn.
    history = state.get("history") or []
    base_messages: list[dict[str, Any]] = [
        *history,
        {
            "role": "user",
            "content": state["plan_user_content"],
        },
        {
            "role": "assistant",
            "content": state["plan_response_content"],
        },
        {"role": "user", "content": tool_results},
    ]

    return {
        "parsed_results": parsed_results,
        "retrieved_source_ids": retrieved_source_ids,
        "record_index": record_index,
        "base_messages": base_messages,
        "trace": trace,
    }


async def rules_node(state: TurnState) -> dict[str, Any]:
    trace = state["trace"]
    parsed_results = state["parsed_results"]

    t0 = time.perf_counter()
    rule_findings = evaluate_clinical_rules(parsed_results)
    elapsed = _elapsed_ms(t0)
    trace.timings_ms["rules"] = elapsed
    trace.rule_findings = rule_findings

    log.info(
        "turn[%s] rules: %dms, %d finding(s) — %s",
        trace.trace_id,
        elapsed,
        len(rule_findings),
        [f.rule_id for f in rule_findings],
    )

    obs.log_span(
        name="rules",
        duration_ms=elapsed,
        metadata={
            "finding_count": len(rule_findings),
            "rule_ids": [f.rule_id for f in rule_findings],
            "severities": [f.severity for f in rule_findings],
        },
        output={
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "category": f.category,
                    "severity": f.severity,
                    "message": f.message,
                    "evidence_source_ids": list(f.evidence_source_ids),
                }
                for f in rule_findings
            ]
        },
    )

    base_messages = state["base_messages"]
    if rule_findings:
        base_messages = base_messages + [
            {
                "role": "user",
                "content": _format_rule_findings_for_llm(rule_findings),
            }
        ]

    return {
        "rule_findings": rule_findings,
        "base_messages": base_messages,
        "trace": trace,
    }


async def reason_node(state: TurnState) -> dict[str, Any]:
    trace = state["trace"]
    client = state["client"]
    model = state["model"]
    base_messages = state["base_messages"]

    t0 = time.perf_counter()
    reason_text, reason_usage = await _reason_call(
        client, model, base_messages
    )
    elapsed = _elapsed_ms(t0)
    trace.timings_ms["reason"] = elapsed
    trace.reason_text = reason_text
    trace.reason_usage = reason_usage

    obs.log_generation(
        name="reason",
        model=model,
        input_messages="<plan + tool results + rule findings>",
        output=reason_text,
        usage=reason_usage,
        duration_ms=elapsed,
    )

    return {"trace": trace}


async def verify_node(state: TurnState) -> dict[str, Any]:
    trace = state["trace"]

    t0 = time.perf_counter()
    verification = verify_response(
        trace.reason_text,
        state["retrieved_source_ids"],
        state["record_index"],
    )
    elapsed = _elapsed_ms(t0)
    trace.timings_ms["verify"] = elapsed
    trace.verification = verification

    log.info(
        "turn[%s] verify: %dms %s — %s",
        trace.trace_id,
        elapsed,
        "PASS" if verification.passed else "FAIL",
        verification.note,
    )
    obs.log_span(
        name="verify",
        duration_ms=elapsed,
        metadata={
            "passed": verification.passed,
            "cited_ids": verification.cited_ids,
            "unknown_ids": verification.unknown_ids,
            "value_mismatches": [
                {
                    "source_id": mm.source_id,
                    "cited_value": mm.cited_value,
                    "record_value": mm.record_value,
                }
                for mm in verification.value_mismatches
            ],
        },
        output={"note": verification.note},
        error=None if verification.passed else verification.note,
    )

    return {"verification": verification, "trace": trace}


async def reason_retry_node(state: TurnState) -> dict[str, Any]:
    """Regenerate-once on first verify fail (ARCHITECTURE.md §2.5).
    Hands the failure note back to the LLM as a user-turn message so
    the model can correct itself rather than retry blind."""
    trace = state["trace"]
    client = state["client"]
    model = state["model"]
    base_messages = state["base_messages"]
    verification = state["verification"]

    log.info(
        "turn[%s] verify failed first pass — regenerating once",
        trace.trace_id,
    )
    trace.regenerated = True

    retry_messages = base_messages + [
        {"role": "assistant", "content": trace.reason_text},
        {"role": "user", "content": _retry_feedback(verification)},
    ]

    t0 = time.perf_counter()
    retry_text, retry_usage = await _reason_call(
        client, model, retry_messages
    )
    elapsed = _elapsed_ms(t0)
    trace.timings_ms["reason_retry"] = elapsed
    trace.reason_text = retry_text  # user-facing text is the retry

    # Sum usage so cost accounting reflects both calls.
    for k, v in retry_usage.items():
        trace.reason_usage[k] = trace.reason_usage.get(k, 0) + v

    obs.log_generation(
        name="reason_retry",
        model=model,
        input_messages="<retry feedback>",
        output=retry_text,
        usage=retry_usage,
        duration_ms=elapsed,
        metadata={"retry_reason": verification.note},
    )

    return {"trace": trace}


async def verify_retry_node(state: TurnState) -> dict[str, Any]:
    trace = state["trace"]

    t0 = time.perf_counter()
    retry_verification = verify_response(
        trace.reason_text,
        state["retrieved_source_ids"],
        state["record_index"],
    )
    elapsed = _elapsed_ms(t0)
    trace.timings_ms["verify_retry"] = elapsed
    trace.verification = retry_verification

    log.info(
        "turn[%s] verify retry: %s — %s",
        trace.trace_id,
        "PASS" if retry_verification.passed else "FAIL",
        retry_verification.note,
    )
    obs.log_span(
        name="verify_retry",
        duration_ms=elapsed,
        metadata={"passed": retry_verification.passed},
        error=None if retry_verification.passed else retry_verification.note,
    )

    return {"verification": retry_verification, "trace": trace}


async def respond_node(state: TurnState) -> dict[str, Any]:
    """Terminal: surface the verified briefing as the user-facing
    response."""
    return {
        "response": state["trace"].reason_text,
        "verified": True,
    }


async def refuse_no_plan_node(state: TurnState) -> dict[str, Any]:
    return {
        "response": (
            "I couldn't plan a retrieval for that question. "
            "Please rephrase or open the patient's record directly."
        ),
        "verified": False,
    }


async def refuse_no_data_node(state: TurnState) -> dict[str, Any]:
    return {
        "response": (
            "I couldn't retrieve the records I need to answer this. "
            "Please open the patient's chart directly."
        ),
        "verified": False,
    }


async def refuse_unverified_node(state: TurnState) -> dict[str, Any]:
    """Terminal: two verifier failures → structured fallback panel.
    The clinician keeps a working tool instead of an unverified
    narrative (§4 graceful-degradation principle)."""
    return {
        "response": _fallback_panel(
            state["parsed_results"], state["verification"]
        ),
        "verified": False,
    }


# --- Routers ---


def _route_after_plan(state: TurnState) -> str:
    if state["trace"].refused:
        return "refuse_no_plan"
    return "retrieve"


def _route_after_retrieve(state: TurnState) -> str:
    if state["trace"].refused:
        return "refuse_no_data"
    return "rules"


def _route_after_verify(state: TurnState) -> str:
    if state["verification"].passed:
        return "respond"
    return "reason_retry"


def _route_after_verify_retry(state: TurnState) -> str:
    if state["verification"].passed:
        return "respond"
    return "refuse_unverified"


# --- Graph construction ---


def build_graph(*, checkpointer: Any | None = None):
    """Build and compile the StateGraph. `checkpointer` is optional;
    when provided (e.g. a SQLite saver), state is persisted between
    node executions and the run is resumable. The runtime instance is
    cached at module level via get_graph() so we don't pay
    re-compilation cost per request."""
    g: StateGraph = StateGraph(TurnState)

    g.add_node("plan", plan_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("rules", rules_node)
    g.add_node("reason", reason_node)
    g.add_node("verify", verify_node)
    g.add_node("reason_retry", reason_retry_node)
    g.add_node("verify_retry", verify_retry_node)
    g.add_node("respond", respond_node)
    g.add_node("refuse_no_plan", refuse_no_plan_node)
    g.add_node("refuse_no_data", refuse_no_data_node)
    g.add_node("refuse_unverified", refuse_unverified_node)

    g.add_edge(START, "plan")

    g.add_conditional_edges(
        "plan",
        _route_after_plan,
        {"retrieve": "retrieve", "refuse_no_plan": "refuse_no_plan"},
    )
    g.add_conditional_edges(
        "retrieve",
        _route_after_retrieve,
        {"rules": "rules", "refuse_no_data": "refuse_no_data"},
    )
    g.add_edge("rules", "reason")
    g.add_edge("reason", "verify")
    g.add_conditional_edges(
        "verify",
        _route_after_verify,
        {"respond": "respond", "reason_retry": "reason_retry"},
    )
    g.add_edge("reason_retry", "verify_retry")
    g.add_conditional_edges(
        "verify_retry",
        _route_after_verify_retry,
        {
            "respond": "respond",
            "refuse_unverified": "refuse_unverified",
        },
    )

    g.add_edge("respond", END)
    g.add_edge("refuse_no_plan", END)
    g.add_edge("refuse_no_data", END)
    g.add_edge("refuse_unverified", END)

    return g.compile(checkpointer=checkpointer)


_compiled = None


def get_graph():
    """Module-level cache so we compile once and reuse."""
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


# --- Helpers (private) ---


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


def _format_rule_findings_for_llm(findings: list[RuleFinding]) -> str:
    lines = [
        "Clinical rules engine — deterministic findings on the retrieved "
        "records. Surface every CRITICAL finding in your briefing using "
        "its exact wording, and cite the listed evidence source id(s) "
        "with <source id=\"...\"/> tags. WARNING findings should be "
        "mentioned when clinically relevant; informational findings are "
        "for your context only."
    ]
    for f in findings:
        evidence = ", ".join(f.evidence_source_ids) or "(no source ids)"
        lines.append(
            f"- [{f.severity.upper()}] {f.rule_id}: {f.message} "
            f"(evidence: {evidence})"
        )
    return "\n".join(lines)


def _fallback_panel(
    parsed_results: list[dict[str, Any]],
    v: VerificationResult,
) -> str:
    """Render a clinician-facing summary when the verifier couldn't
    accept the agent's narrative. The Week 1 version dumped raw
    Python `repr` of each tool result — readable for flat FHIR tools
    but illegible for the Week 2 tools that return nested arrays
    (`get_lab_history`, `get_changes_since`, `check_clinical_thresholds`).

    This version walks each tool result, recognizes the shape, and
    emits one clean line per record using only the clinically-
    relevant fields. NO source_id, schema_kind, payload, raw bbox,
    or other plumbing fields appear. The verifier note is preserved
    verbatim because it tells the clinician *why* the answer is
    flagged for review."""

    lines = [
        "I retrieved the chart data below but couldn't produce a fully "
        "verified narrative for this question. Please review the records "
        "directly, or rephrase to focus on a single fact.",
        "",
        f"_{v.note}_",
        "",
    ]

    sections: list[str] = []
    for result in parsed_results:
        if not isinstance(result, dict):
            continue
        sections.extend(_render_tool_result(result))

    if not sections:
        sections.append("(No structured records were retrieved this turn.)")

    return "\n".join(lines + sections)


# Fields we never want to surface to the clinician — they're plumbing
# the agent uses internally.
_HIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "source_id",
        "schema_kind",
        "payload_json",
        "bbox_json",
        "field_or_chunk_id",
        "resolved_test_key",
        "extraction_error",
        "extraction_status",
        "file_hash",
        "content_type",
        "uploaded_by_user_id",
        "extraction_warnings",
        # Counts that the heading already displays — avoid duplication
        # like "**Clinical-rule findings (2):** [...rows...] - n findings: 2"
        "n_findings",
        "total_count",
    }
)


def _render_tool_result(result: dict[str, Any]) -> list[str]:
    """Map a single tool-result dict to one or more bullet lines.
    Recognized top-level shapes route to their per-record renderer;
    anything unrecognized falls back to a generic name/value formatter."""
    out: list[str] = []
    for top_key, value in result.items():
        if top_key in _HIDDEN_KEYS:
            continue

        if top_key == "patient" and isinstance(value, dict):
            out.append(f"**Patient:** {_inline_record(value)}")
        elif top_key == "problems" and isinstance(value, list):
            out.append(f"**Problems** ({len(value)}):")
            out.extend(_bulletize_records(value))
        elif top_key == "medications" and isinstance(value, list):
            out.append(f"**Medications** ({len(value)}):")
            out.extend(_bulletize_records(value))
        elif top_key == "labs" and isinstance(value, list):
            out.append(f"**Recent labs** ({len(value)}):")
            out.extend(_bulletize_records(value))
        elif top_key == "encounters" and isinstance(value, list):
            out.append(f"**Recent encounters** ({len(value)}):")
            out.extend(_bulletize_records(value))
        elif top_key == "history" and isinstance(value, list):
            test = result.get("test_name") or result.get("resolved_test_key") or "Lab"
            out.append(f"**{test} history** ({len(value)}, newest first):")
            out.extend(_bulletize_records(value))
        elif top_key == "all_histories" and isinstance(value, dict):
            for test_name, series in value.items():
                if isinstance(series, list):
                    out.append(
                        f"**{test_name.upper()} history** ({len(series)}, newest first):"
                    )
                    out.extend(_bulletize_records(series))
        elif top_key.startswith("new_") and isinstance(value, list):
            label = top_key.replace("_", " ").capitalize()
            if value:
                out.append(f"**{label}** ({len(value)}):")
                out.extend(_bulletize_records(value))
        elif top_key == "documents" and isinstance(value, list):
            out.append(f"**Uploaded documents** ({len(value)}):")
            out.extend(_bulletize_records(value))
        elif top_key == "findings" and isinstance(value, list):
            if value:
                out.append(f"**Clinical-rule findings** ({len(value)}):")
                for f in value:
                    sev = (f.get("severity") or "info").upper()
                    rid = f.get("rule_id") or "?"
                    msg = f.get("message") or ""
                    out.append(f"- **[{sev}]** `{rid}`: {msg}")
        elif top_key in ("note", "since_date", "test_name"):
            out.append(f"_{top_key.replace('_', ' ')}_: {value}")
        elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
            out.append(f"- {top_key.replace('_', ' ')}: {value}")
        # Anything else (deeply nested, unrecognized) is intentionally
        # skipped rather than dumped as repr.

    if out:
        out.append("")  # spacing between tool-result blocks
    return out


def _bulletize_records(records: list[Any]) -> list[str]:
    bullets: list[str] = []
    for r in records:
        if isinstance(r, dict):
            inline = _inline_record(r)
            if inline:
                bullets.append(f"- {inline}")
        elif isinstance(r, str):
            bullets.append(f"- {r}")
    return bullets


def _inline_record(r: dict[str, Any]) -> str:
    """Format a single record as a single human-readable line. Picks
    the most clinically meaningful fields based on which keys are
    present; ignores plumbing. Returns empty string if there's
    nothing useful to surface."""

    def has(*keys: str) -> bool:
        return all(k in r and r[k] not in (None, "") for k in keys)

    # Lab observation
    if has("name", "value"):
        unit = f" {r['unit']}" if r.get("unit") else ""
        date = f" on {r['date']}" if r.get("date") else ""
        flag = f" ({r['flag']})" if r.get("flag") else ""
        ref = f" - ref {r['reference_range']}" if r.get("reference_range") else ""
        return f"{r['name']}: {r['value']}{unit}{date}{flag}{ref}"

    # Medication
    if has("name", "dose"):
        freq = f" {r['frequency']}" if r.get("frequency") else ""
        started = f" (since {r['started']})" if r.get("started") else ""
        return f"{r['name']} {r['dose']}{freq}{started}"

    # Problem / condition
    if has("description"):
        code = f" [{r['code']}]" if r.get("code") else ""
        status = f" — {r['status']}" if r.get("status") else ""
        onset = f" since {r['onset_date']}" if r.get("onset_date") else ""
        return f"{r['description']}{code}{status}{onset}"

    # Encounter
    if has("date") and (r.get("type") or r.get("chief_complaint")):
        kind = r.get("type", "visit")
        cc = f" - {r['chief_complaint']}" if r.get("chief_complaint") else ""
        provider = f" ({r['provider']})" if r.get("provider") else ""
        return f"{r['date']} {kind}{cc}{provider}"

    # Document
    if has("doc_type"):
        doc_id = r.get("document_id") or r.get("id") or "?"
        uploaded = f" uploaded {r['uploaded_at']}" if r.get("uploaded_at") else ""
        status = f" - {r['extraction_status']}" if r.get("extraction_status") else ""
        return f"{r['doc_type'].replace('_', ' ').title()} #{doc_id}{uploaded}{status}"

    # Patient summary
    if has("name") and (r.get("dob") or r.get("mrn")):
        bits = [r["name"]]
        if r.get("dob"):
            bits.append(f"DOB {r['dob']}")
        if r.get("sex"):
            bits.append(r["sex"])
        if r.get("mrn"):
            bits.append(f"MRN {r['mrn']}")
        return ", ".join(bits)

    # Generic fallback — name + first non-hidden value (no repr).
    visible = {
        k: v for k, v in r.items()
        if k not in _HIDDEN_KEYS
        and isinstance(v, (str, int, float))
        and not isinstance(v, bool)
    }
    if visible:
        return ", ".join(f"{k}: {v}" for k, v in list(visible.items())[:4])
    return ""


def _usage_dict(usage: object) -> dict[str, int]:
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )
    return {f: getattr(usage, f, 0) or 0 for f in fields}


def _elapsed_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
