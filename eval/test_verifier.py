"""Verifier unit tests (ARCHITECTURE.md §2.5).

The verifier is pure Python — no network, no LLM. These tests are fast and
deterministic and exercise the source-id matching that backs the verification
guarantee surfaced in the UI.
"""

from __future__ import annotations

from agent.verifier import build_record_index, collect_source_ids, verify_response


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


# --- Numeric value-tolerance check ---


def _bundle_with_a1c() -> tuple[set[str], dict[str, dict]]:
    parsed = [
        {
            "labs": [
                {
                    "source_id": "lab-001-a1c-2026-03",
                    "name": "Hemoglobin A1c",
                    "value": 7.4,
                    "unit": "%",
                    "date": "2026-03-15",
                },
                {
                    "source_id": "lab-001-ldl-2026-03",
                    "name": "LDL cholesterol",
                    "value": 92,
                    "unit": "mg/dL",
                    "date": "2026-03-15",
                },
            ]
        }
    ]
    return collect_source_ids(parsed), build_record_index(parsed)


def test_value_check_passes_when_prose_matches_record() -> None:
    ids, index = _bundle_with_a1c()
    text = 'A1c is 7.4% on 2026-03-15 <source id="lab-001-a1c-2026-03"/>.'
    result = verify_response(text, ids, index)
    assert result.passed is True
    assert result.value_mismatches == []


def test_value_check_passes_within_tolerance() -> None:
    """0.04 absolute drift sits inside the 0.05 tolerance."""
    ids, index = _bundle_with_a1c()
    text = 'A1c is 7.44% <source id="lab-001-a1c-2026-03"/>.'
    result = verify_response(text, ids, index)
    assert result.passed is True


def test_value_check_fails_when_prose_misquotes_value() -> None:
    """The lab value drift case the reviewer asked for: real source id,
    but the prose number doesn't match the record."""
    ids, index = _bundle_with_a1c()
    text = 'A1c is 8.4% on 2026-03-15 <source id="lab-001-a1c-2026-03"/>.'
    result = verify_response(text, ids, index)
    assert result.passed is False
    assert len(result.value_mismatches) == 1
    mm = result.value_mismatches[0]
    assert mm.source_id == "lab-001-a1c-2026-03"
    assert mm.cited_value == 8.4
    assert mm.record_value == 7.4


def test_value_check_skips_records_with_no_numeric_value() -> None:
    """Demographics, conditions, medications carry no `value` field —
    the value pass should be a no-op for them."""
    parsed = [
        {
            "patient": {
                "source_id": "patient-demo-001",
                "name": "Margaret Hayes",
                "dob": "1962-04-14",
            }
        }
    ]
    ids = collect_source_ids(parsed)
    index = build_record_index(parsed)
    text = (
        "Margaret Hayes, born 1962-04-14 "
        '<source id="patient-demo-001"/>.'
    )
    # 1962 is in the prose, but the record has no `value` so we skip.
    result = verify_response(text, ids, index)
    assert result.passed is True


def test_value_check_skips_when_prose_carries_no_number() -> None:
    """An attribution like 'A1c was elevated <source id=.../>' cites a
    numeric record but doesn't quote a number — that's an underspecified
    claim, not a mismatch. We don't flag it; the system prompt is what
    pushes the LLM to quote values."""
    ids, index = _bundle_with_a1c()
    text = 'A1c was elevated <source id="lab-001-a1c-2026-03"/>.'
    result = verify_response(text, ids, index)
    assert result.passed is True


def test_value_check_passes_when_record_index_omitted() -> None:
    """Backward compat: callers that don't pass record_index still get
    pass-1 (source-id matching) only."""
    text = 'A1c is 8.4% <source id="lab-001-a1c-2026-03"/>.'
    result = verify_response(text, {"lab-001-a1c-2026-03"})
    assert result.passed is True  # value mismatch not detected without index
    assert result.value_mismatches == []


def test_unknown_id_takes_priority_over_value_check() -> None:
    """If a cited id isn't in the bundle, that's the headline failure —
    we don't bother with the value-pass on top."""
    ids, index = _bundle_with_a1c()
    text = (
        'A1c is 8.4% <source id="lab-001-a1c-2026-03"/> and creatinine '
        'is 9.9 <source id="lab-fabricated-cr"/>.'
    )
    result = verify_response(text, ids, index)
    assert result.passed is False
    assert "lab-fabricated-cr" in result.unknown_ids
    # unknown-ids path doesn't run the value pass
    assert result.value_mismatches == []


# --- build_record_index ---


def test_build_record_index_returns_record_by_id() -> None:
    parsed = [
        {"patient": {"source_id": "patient-1", "name": "X"}},
        {
            "labs": [
                {"source_id": "lab-1", "value": 7.4},
                {"source_id": "lab-2", "value": 92},
            ]
        },
    ]
    index = build_record_index(parsed)
    assert index["patient-1"]["name"] == "X"
    assert index["lab-1"]["value"] == 7.4
    assert index["lab-2"]["value"] == 92


def test_build_record_index_first_occurrence_wins() -> None:
    parsed = [
        {"a": {"source_id": "x", "v": 1}},
        {"b": {"source_id": "x", "v": 2}},
    ]
    index = build_record_index(parsed)
    assert index["x"]["v"] == 1
