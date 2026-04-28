"""Deterministic verifier (ARCHITECTURE.md §2.5).

Walks an LLM-generated response, extracts <source id="..."/> tags, confirms each id
was retrieved this turn. Pure Python — not an LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass


SOURCE_TAG_RE = re.compile(r'<source\s+id="([^"]+)"\s*/>', re.IGNORECASE)


@dataclass
class VerificationResult:
    passed: bool
    cited_ids: list[str]
    unknown_ids: list[str]
    note: str


def verify_response(response_text: str, retrieved_source_ids: set[str]) -> VerificationResult:
    """Extract every <source id="..."/> tag from the response and confirm each id is
    present in this turn's retrieval bundle. A cited id not in the bundle is the
    canonical hallucination signature.

    Out of scope for v0:
      - Numeric tolerance / value-similarity check between cited record and prose claim.
      - Domain rule checks (lab thresholds, dosage ranges).
      - Catching errors of omission.
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

    return VerificationResult(
        passed=True,
        cited_ids=cited,
        unknown_ids=[],
        note=f"Verifier passed: all {len(cited)} cited source(s) resolved.",
    )


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
