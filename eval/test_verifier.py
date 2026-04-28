"""Verifier unit tests (ARCHITECTURE.md §2.5).

The verifier is pure Python — no network, no LLM. These tests are fast and
deterministic and exercise the source-id matching that backs the verification
guarantee surfaced in the UI.
"""

from __future__ import annotations

from agent.verifier import collect_source_ids, verify_response


# --- collect_source_ids ---

def test_collect_source_ids_walks_nested_tool_results() -> None:
    parsed = [
        {"patient": {"source_id": "patient-1", "name": "X"}},
        {"problems": [{"source_id": "cond-1"}, {"source_id": "cond-2"}]},
    ]
    assert collect_source_ids(parsed) == {"patient-1", "cond-1", "cond-2"}


def test_collect_source_ids_ignores_non_string_source_id() -> None:
    parsed = [{"source_id": 12345}, {"source_id": None}, {"source_id": "ok"}]
    assert collect_source_ids(parsed) == {"ok"}


def test_collect_source_ids_handles_empty() -> None:
    assert collect_source_ids([]) == set()
    assert collect_source_ids([{}]) == set()


# --- verify_response ---

def test_verify_passes_when_every_cited_id_is_in_bundle() -> None:
    text = (
        'A1c 7.4% on 2026-03-15 <source id="lab-001-a1c-2026-03"/>, '
        'above goal of 7.0%. Patient on metformin '
        '<source id="med-001-1"/>.'
    )
    bundle = {"lab-001-a1c-2026-03", "med-001-1", "patient-demo-001"}
    result = verify_response(text, bundle)
    assert result.passed is True
    assert sorted(result.cited_ids) == sorted(
        ["lab-001-a1c-2026-03", "med-001-1"]
    )
    assert result.unknown_ids == []


def test_verify_fails_on_unknown_cited_id() -> None:
    text = 'Patient on lisinopril <source id="med-fabricated-999"/>.'
    bundle = {"med-001-1", "med-001-2"}
    result = verify_response(text, bundle)
    assert result.passed is False
    assert "med-fabricated-999" in result.unknown_ids


def test_verify_passes_with_no_citations() -> None:
    """The verifier is strictly about cited claims — no citations is vacuously
    pass. The 'always cite' rule is enforced by the system prompt, not the
    verifier."""
    result = verify_response("This is a refusal.", {"med-001-1"})
    assert result.passed is True
    assert result.cited_ids == []


def test_verify_handles_repeated_citations() -> None:
    text = (
        'A1c <source id="lab-1"/>; LDL <source id="lab-2"/>; '
        'A1c trend <source id="lab-1"/>.'
    )
    result = verify_response(text, {"lab-1", "lab-2"})
    assert result.passed is True
    # Repeated cites preserved in order.
    assert result.cited_ids == ["lab-1", "lab-2", "lab-1"]


def test_verify_case_insensitive_tag_name() -> None:
    text = 'Foo <SOURCE id="lab-1"/> and <Source id="lab-2"/>.'
    result = verify_response(text, {"lab-1", "lab-2"})
    assert result.passed is True
    assert sorted(result.cited_ids) == ["lab-1", "lab-2"]
