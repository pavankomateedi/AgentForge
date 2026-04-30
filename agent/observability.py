"""Langfuse wiring (ARCHITECTURE.md §2.7).

Thin wrapper around the Langfuse Python SDK (4.x) so the rest of the
codebase can call `with turn(...)`, `log_generation(...)`,
`log_span(...)`, `score(...)` without caring whether Langfuse is
actually configured. When the keys are unset the wrapper returns no-op
context managers so dev/CI/test paths don't break.

The case-study doc demands the system answer four questions from logs:
  1. What did the agent do, in what order?
  2. How long did each step take?
  3. Did any tools fail, and why?
  4. How many tokens consumed, and at what cost?

We answer (1)+(2) with a top-level trace and one observation per
LangGraph node (plan / retrieve / reason / verify), (3) with a span per
tool dispatch carrying `level=ERROR` + status_message on failure, and
(4) with the `generation` observation kind which auto-computes cost
from token usage_details.

PHI containment: ARCHITECTURE.md §2.7 calls for self-hosted Langfuse in
a HIPAA-covered deployment. Week 1 uses Langfuse Cloud because all data
is synthetic demo PHI (case-study doc explicitly permits this); v1
hardening to self-hosted is a documented next step.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

try:
    from langfuse import Langfuse  # type: ignore
except ImportError:  # pragma: no cover
    Langfuse = None  # type: ignore


log = logging.getLogger(__name__)


_client: "Langfuse | None" = None
_enabled: bool = False


def init(
    *,
    public_key: str | None,
    secret_key: str | None,
    host: str,
) -> None:
    """Initialize the Langfuse client. Safe to call multiple times.
    No-op if keys are missing or the SDK isn't installed."""
    global _client, _enabled

    if not (public_key and secret_key) or Langfuse is None:
        log.info(
            "langfuse: disabled (keys=%s, sdk=%s)",
            "set" if public_key and secret_key else "unset",
            "installed" if Langfuse else "missing",
        )
        _enabled = False
        return

    _client = Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
    )
    _enabled = True
    log.info("langfuse: enabled (host=%s)", host)


def is_enabled() -> bool:
    return _enabled


def shutdown() -> None:
    """Flush pending events. Call from FastAPI lifespan on shutdown."""
    if _client is not None:
        try:
            _client.flush()
        except Exception as exc:  # pragma: no cover
            log.warning("langfuse: flush failed: %s", exc)


# --- Turn lifecycle ---


class _NullCtx:
    """Stand-in for a Langfuse observation when tracing is disabled."""

    def __enter__(self) -> "_NullCtx":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def update(self, **_kwargs: Any) -> None:
        return None

    def update_trace(self, **_kwargs: Any) -> None:
        return None


@contextmanager
def turn(
    *,
    trace_id: str,
    user_id: str | None,
    user_role: str | None,
    patient_id_hash: str,
    user_message: str,
) -> Iterator[Any]:
    """Open a Langfuse trace for one /chat turn. Yields the root span
    (or a no-op when disabled)."""
    if not _enabled or _client is None:
        yield _NullCtx()
        return

    try:
        with _client.start_as_current_observation(
            name="chat_turn",
            as_type="span",
            input={"message": user_message},
            metadata={
                "trace_id": trace_id,
                "user_id": user_id or "anonymous",
                "user_role": user_role,
                "patient_id_hash": patient_id_hash,
            },
        ) as span:
            yield span
    except Exception as exc:  # pragma: no cover
        log.warning("langfuse: turn span failed: %s", exc)
        yield _NullCtx()


# --- Per-node helpers ---


def log_generation(
    *,
    name: str,
    model: str,
    input_messages: list[dict[str, Any]] | str,
    output: str,
    usage: dict[str, int],
    duration_ms: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an LLM call as a generation observation (cost auto-computed
    by Langfuse from usage_details + the registered model)."""
    if not _enabled or _client is None:
        return
    try:
        usage_details = {
            "input": usage.get("input_tokens", 0),
            "output": usage.get("output_tokens", 0),
            "cache_read_input_tokens": usage.get(
                "cache_read_input_tokens", 0
            ),
            "cache_creation_input_tokens": usage.get(
                "cache_creation_input_tokens", 0
            ),
        }
        with _client.start_as_current_observation(
            name=name,
            as_type="generation",
            model=model,
            input=input_messages,
            output=output,
            metadata={**(metadata or {}), "duration_ms": duration_ms},
            usage_details=usage_details,
        ):
            pass
    except Exception as exc:  # pragma: no cover
        log.warning("langfuse: generation %r failed: %s", name, exc)


def log_span(
    *,
    name: str,
    duration_ms: int,
    metadata: dict[str, Any] | None = None,
    output: Any | None = None,
    error: str | None = None,
) -> None:
    """Record a non-LLM step (retrieve, verify, etc.). On failure, set
    level=ERROR + status_message so the doc's question 3 ('did tools
    fail, and why?') is answerable from the dashboard."""
    if not _enabled or _client is None:
        return
    try:
        kwargs: dict[str, Any] = {
            "name": name,
            "as_type": "span",
            "metadata": {**(metadata or {}), "duration_ms": duration_ms},
        }
        if output is not None:
            kwargs["output"] = output
        if error:
            kwargs["level"] = "ERROR"
            kwargs["status_message"] = error
        with _client.start_as_current_observation(**kwargs):
            pass
    except Exception as exc:  # pragma: no cover
        log.warning("langfuse: span %r failed: %s", name, exc)


def score(name: str, value: float | bool, *, comment: str | None = None) -> None:
    """Attach a score to the current trace. Used for verification.passed,
    regenerated, etc. — gives the dashboard a verifier-pass-rate view."""
    if not _enabled or _client is None:
        return
    try:
        if isinstance(value, bool):
            _client.score_current_trace(
                name=name,
                value=float(int(value)),
                data_type="BOOLEAN",
                comment=comment,
            )
        else:
            _client.score_current_trace(
                name=name,
                value=float(value),
                comment=comment,
            )
    except Exception as exc:  # pragma: no cover
        log.warning("langfuse: score %r failed: %s", name, exc)


def trace_url(trace_id: str) -> str | None:
    """Return a Langfuse URL for the given trace_id so the operator can
    click through from the /chat response. Returns None when disabled."""
    if not _enabled or _client is None:
        return None
    try:
        return _client.get_trace_url(trace_id=trace_id)
    except Exception:  # pragma: no cover
        return None
