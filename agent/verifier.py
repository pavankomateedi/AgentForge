"""Deterministic verifier (ARCHITECTURE.md §2.5).

Two passes, both pure Python (no LLM):

  1. Source-id matching. Walk every `<source id="..."/>` tag in the response;
     each cited id must exist in this turn's retrieval bundle. A cited id
     not in the bundle is the canonical hallucination signature.

  2. Numeric value-tolerance check. For each cited tag, scan a small window
     of prose immediately preceding the tag for numbers; for each number
     found, compare it to the `value` field of the cited record. If the
     prose claims a number that doesn't match the cited record (within a
     small tolerance), flag it. This catches the failure mode where the
     LLM cites a real source id but transcribes the value wrong (e.g.
     cites lab-001-a1c-2026-03 — a real id — but writes "8.4%" instead
     of "7.4%").

Both passes are deterministic and cheap; running them on every turn is
the verification node in the LangGraph spec (ARCHITECTURE.md §2.3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


SOURCE_TAG_RE = re.compile(r'<source\s+id="([^"]+)"\s*/>', re.IGNORECASE)

# Numbers in clinical prose: optional sign, digits, optional decimal.
# Negative lookbehind/ahead for letters so we don't match the "1" in
# "A1c" or the "5" in "B5" — those are identifiers, not measurements.
# We stop short of scientific notation and ranges; lab values in the
# demo set are plain decimals.
_NUMBER_RE = re.compile(r"(?<![A-Za-z\d])-?\d+(?:\.\d+)?(?![A-Za-z])")

# Numeric tolerance for value-match. Lab values are reported with at most
# one decimal place in the demo set, so 0.05 absolute or 1% relative
# (whichever is larger) is comfortably inside one display digit and won't
# false-positive on legitimate rounding.
_VALUE_ABS_TOL = 0.05
_VALUE_REL_TOL = 0.01

# How many characters of prose preceding a <source/> tag we scan for
# numbers. Long enough to catch "A1c was 7.4% on 2026-03-15" but short
# enough that we don't grab numbers from a previous, separately-cited
# sentence.
_PROSE_WINDOW_CHARS = 140


@dataclass
class ValueMismatch:
    source_id: str
    cited_value: float  # what the prose said
    record_value: float  # what the retrieved record actually has
    snippet: str  # the prose snippet for debugging

    def describe(self) -> str:
        return (
            f"value mismatch on {self.source_id!r}: "
            f"prose says {self.cited_value}, record has {self.record_value} "
            f"(snippet: {self.snippet!r})"
        )


@dataclass
class VerificationResult:
    passed: bool
    cited_ids: list[str]
    unknown_ids: list[str]
    note: str
    value_mismatches: list[ValueMismatch] = field(default_factory=list)


def verify_response(
    response_text: str,
    retrieved_source_ids: set[str],
    record_index: dict[str, dict] | None = None,
) -> VerificationResult:
    """Run both verification passes.

    `retrieved_source_ids` — set of source ids present in this turn's
    retrieval bundle. Required for pass 1.

    `record_index` — optional mapping of source_id → record dict. Required
    for pass 2 (numeric tolerance). When omitted, only pass 1 runs; this
    keeps the verifier callable from contexts that don't have the
    structured records handy (e.g. the existing unit tests).
    """
    cited = SOURCE_TAG_RE.findall(response_text)
    cited_set = set(cited)
    unknown = sorted(cited_set - retrieved_source_ids)

    if unknown:
        return VerificationResult(
            passed=False,
            cited_ids=cited,
            unknown_ids=unknown,
            note=(
                f"Verifier rejected: {len(unknown)} cited source id(s) not in this turn's "
                f"retrieval bundle: {unknown}."
            ),
        )

    mismatches: list[ValueMismatch] = []
    if record_index:
        mismatches = _check_numeric_values(response_text, record_index)

    if mismatches:
        return VerificationResult(
            passed=False,
            cited_ids=cited,
            unknown_ids=[],
            note=(
                f"Verifier rejected: {len(mismatches)} numeric value "
                f"mismatch(es) — "
                + "; ".join(m.describe() for m in mismatches)
            ),
            value_mismatches=mismatches,
        )

    return VerificationResult(
        passed=True,
        cited_ids=cited,
        unknown_ids=[],
        note=f"Verifier passed: all {len(cited)} cited source(s) resolved.",
    )


def _check_numeric_values(
    response_text: str,
    record_index: dict[str, dict],
) -> list[ValueMismatch]:
    """For each <source/> tag, look at the prose window preceding it and,
    if the cited record carries a numeric `value`, confirm at least one
    number in the prose window matches that value within tolerance."""
    mismatches: list[ValueMismatch] = []

    for match in SOURCE_TAG_RE.finditer(response_text):
        source_id = match.group(1)
        record = record_index.get(source_id)
        if record is None:
            continue
        record_value = _coerce_float(record.get("value"))
        if record_value is None:
            # Record has no numeric value to verify against — e.g.
            # demographics, conditions, medications. Pass.
            continue

        window_start = max(0, match.start() - _PROSE_WINDOW_CHARS)
        snippet = response_text[window_start : match.start()]
        numbers = [_coerce_float(n) for n in _NUMBER_RE.findall(snippet)]
        numbers = [n for n in numbers if n is not None]

        if not numbers:
            # Cited a numeric record but didn't actually quote a number
            # in the prose. That's not a mismatch, just an attribution.
            continue

        if not any(_within_tolerance(n, record_value) for n in numbers):
            # The prose mentions numbers, but none match the cited
            # record. Pick the nearest one for the report so the message
            # is actionable.
            nearest = min(numbers, key=lambda n: abs(n - record_value))
            mismatches.append(
                ValueMismatch(
                    source_id=source_id,
                    cited_value=nearest,
                    record_value=record_value,
                    snippet=snippet.strip(),
                )
            )

    return mismatches


def _within_tolerance(prose_n: float, record_n: float) -> bool:
    abs_diff = abs(prose_n - record_n)
    if abs_diff <= _VALUE_ABS_TOL:
        return True
    denom = max(abs(record_n), 1e-9)
    return abs_diff / denom <= _VALUE_REL_TOL


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):  # bool is a subclass of int; reject.
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def collect_source_ids(parsed_tool_results: list[dict]) -> set[str]:
    """Walk parsed tool result dicts; collect every `source_id` field at any depth."""
    found: set[str] = set()

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            sid = node.get("source_id")
            if isinstance(sid, str):
                found.add(sid)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    for r in parsed_tool_results:
        _walk(r)
    return found


def build_record_index(parsed_tool_results: list[dict]) -> dict[str, dict]:
    """Walk parsed tool results and return a map of source_id → record.

    The verifier's value-check needs to look up a record by id without
    re-walking the bundle each time. The index is built once per turn in
    the orchestrator and passed into `verify_response`."""
    index: dict[str, dict] = {}

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            sid = node.get("source_id")
            if isinstance(sid, str) and sid not in index:
                index[sid] = node
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    for r in parsed_tool_results:
        _walk(r)
    return index
