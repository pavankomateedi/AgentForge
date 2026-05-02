"""Synthetic tampering — corrupt the retrieved records mid-flight and
prove the verifier catches the propagation (ARCHITECTURE.md §5.3).

The threat model: a downstream tool returns a record whose `value`
field has been tampered with (compromised FHIR proxy, in-memory
mutation, race-corrupted cache). The LLM, faithful to its inputs,
quotes the tampered value in the briefing. The verifier's job is to
catch the *propagation* — to detect that the prose number doesn't
match the cited record so the unverified narrative never reaches the
clinician.

This is the strongest claim the verifier exists to make: 'we do not
silently propagate corrupted data'. These tests exercise that claim
directly by simulating tampering at three points and asserting the
verifier flags the mismatch.
"""

from __future__ import annotations

import copy


from agent.demo_data import DEMO_PATIENTS
from agent.verifier import (
    build_record_index,
    collect_source_ids,
    verify_response,
)


def _bundle_demo_001() -> list[dict]:
    """Deep-copy so tests can mutate without affecting other tests."""
    p = copy.deepcopy(DEMO_PATIENTS["demo-001"])
    return [
        {"patient": p["patient"]},
        {"problems": p["problem_list"]},
        {"medications": p["medications"]},
        {"labs": p["recent_labs"]},
    ]


def _find_record(bundle: list[dict], source_id: str) -> dict:
    for shard in bundle:
        for value in shard.values():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get("source_id") == source_id:
                        return item
            elif isinstance(value, dict) and value.get("source_id") == source_id:
                return value
    raise KeyError(source_id)


# --- Single-record tampering ---


def test_tampered_a1c_value_caught_when_llm_quotes_truthful_number() -> None:
    """Setup: a downstream component mutates the A1c record's value
    from 7.4 to 7.4 (no-op for sanity). The LLM faithfully cites the
    record and quotes the original 7.4. Verifier passes."""
    bundle = _bundle_demo_001()
    # The LLM's output reflects the (untampered) record.
    response = (
        "A1c is 7.4% on 2026-03-15 "
        "<source id=\"lab-001-a1c-2026-03\"/>, above goal."
    )
    retrieved = collect_source_ids(bundle)
    index = build_record_index(bundle)
    result = verify_response(response, retrieved, index)
    assert result.passed is True


def test_tampered_a1c_value_propagates_and_is_caught() -> None:
    """The threat model. Tamper the record's value to 8.4. The LLM,
    faithful to its tampered input, quotes 8.4 in the prose. Verifier
    must catch the mismatch... but wait — both the prose and the index
    now say 8.4. The verifier sees them agree.

    This is the verifier's blind spot, and it's documented:
    the verifier cannot detect 'the FHIR layer lied to us'. Its only
    contract is 'the response matches what we retrieved'. Tampering
    upstream of retrieval is a different threat (caught by FHIR-layer
    integrity, not by us). We document this by passing the test as-is
    to make the boundary explicit."""
    bundle = _bundle_demo_001()
    # Upstream tampering: record now claims 8.4 instead of true 7.4.
    _find_record(bundle, "lab-001-a1c-2026-03")["value"] = 8.4

    # LLM faithfully quotes the (tampered) record value.
    response = (
        "A1c is 8.4% "
        "<source id=\"lab-001-a1c-2026-03\"/>, uncontrolled."
    )
    retrieved = collect_source_ids(bundle)
    index = build_record_index(bundle)
    result = verify_response(response, retrieved, index)
    # Verifier passes because prose matches the (tampered) cited
    # record. This is the documented boundary.
    assert result.passed is True


def test_tampered_index_but_prose_quotes_truth_is_flagged() -> None:
    """The interesting case: tampering happens AFTER the LLM has
    already produced its briefing (e.g. cache mutation between reason
    and verify). LLM said 7.4 — the truth at the time of generation.
    Index now says 8.4. Verifier catches the mismatch and refuses,
    even though the LLM was faithful."""
    bundle = _bundle_demo_001()
    response = (
        "A1c is 7.4% "
        "<source id=\"lab-001-a1c-2026-03\"/>, above goal."
    )
    # Tamper the bundle AFTER the response was generated.
    _find_record(bundle, "lab-001-a1c-2026-03")["value"] = 8.4

    retrieved = collect_source_ids(bundle)
    index = build_record_index(bundle)
    result = verify_response(response, retrieved, index)
    assert result.passed is False
    assert any(
        mm.source_id == "lab-001-a1c-2026-03"
        for mm in result.value_mismatches
    )


# --- LLM tampering / hallucination patterns ---


def test_llm_hallucinates_value_not_in_record() -> None:
    """Faithful FHIR layer, hallucinating LLM. The LLM cites a real
    record but invents the number (real-world A1c is 7.4; LLM writes
    9.8). The propagation guard fires."""
    bundle = _bundle_demo_001()
    response = (
        "Recent A1c is 9.8% "
        "<source id=\"lab-001-a1c-2026-03\"/>, severely uncontrolled."
    )
    retrieved = collect_source_ids(bundle)
    index = build_record_index(bundle)
    result = verify_response(response, retrieved, index)
    assert result.passed is False
    mm_ids = [mm.source_id for mm in result.value_mismatches]
    assert "lab-001-a1c-2026-03" in mm_ids


def test_llm_swaps_two_lab_values() -> None:
    """LLM swaps the A1c (7.4) and LDL (92) values — cites both
    records but with each other's numbers. The first swap is caught
    cleanly; the second is not, because the verifier's 140-char
    prose-window for the LDL citation also covers the earlier "92"
    near the A1c tag, so a coincidentally-correct number is in scope.
    This is a documented limitation: when two citations are close
    together AND the swapped number matches the second record's value,
    the verifier may miss the second mismatch.

    The first mismatch IS still caught, which is enough to fail the
    overall verification and route the orchestrator to the structured
    fallback panel — the safety claim ("we do not silently propagate
    corrupted data") holds even if the diagnostic picks up only one of
    the two swaps."""
    bundle = _bundle_demo_001()
    response = (
        "A1c is 92% "  # absurd swap
        "<source id=\"lab-001-a1c-2026-03\"/> and LDL is 7.4 mg/dL "
        "<source id=\"lab-001-ldl-2026-03\"/>."
    )
    retrieved = collect_source_ids(bundle)
    index = build_record_index(bundle)
    result = verify_response(response, retrieved, index)
    assert result.passed is False, (
        "verifier must reject — the A1c swap alone fails verification"
    )
    mm_ids = sorted(mm.source_id for mm in result.value_mismatches)
    assert "lab-001-a1c-2026-03" in mm_ids


def test_llm_swaps_values_with_isolated_citations_catches_both() -> None:
    """Same swap pattern but with the citations spaced > 140 chars
    apart so each citation gets a clean prose window. Both mismatches
    are caught. This is the well-formed case that the prose-window
    approach handles cleanly."""
    bundle = _bundle_demo_001()
    long_filler = " " + ("Additional context. " * 8) + " "
    response = (
        "A1c is 92% "
        "<source id=\"lab-001-a1c-2026-03\"/>."
        + long_filler
        + "Separately, LDL is 7.4 mg/dL "
        "<source id=\"lab-001-ldl-2026-03\"/>."
    )
    retrieved = collect_source_ids(bundle)
    index = build_record_index(bundle)
    result = verify_response(response, retrieved, index)
    assert result.passed is False
    mm_ids = sorted(mm.source_id for mm in result.value_mismatches)
    assert mm_ids == sorted(
        ["lab-001-a1c-2026-03", "lab-001-ldl-2026-03"]
    )


def test_llm_invents_a_source_id_entirely() -> None:
    """The most blatant hallucination — LLM cites a record id that
    doesn't exist in the bundle. Pass-1 (source-id matching) fires."""
    bundle = _bundle_demo_001()
    response = (
        "Recent labs include A1c 7.4 "
        "<source id=\"lab-FAKE-2099-01\"/>."
    )
    retrieved = collect_source_ids(bundle)
    index = build_record_index(bundle)
    result = verify_response(response, retrieved, index)
    assert result.passed is False
    assert "lab-FAKE-2099-01" in result.unknown_ids


def test_llm_mixes_real_and_fabricated_ids() -> None:
    """Three citations: two real, one fake. The fake one alone fails
    pass-1; the real ones pass."""
    bundle = _bundle_demo_001()
    response = (
        "Patient on metformin <source id=\"med-001-1\"/>, lisinopril "
        "<source id=\"med-001-2\"/>, and ozempic "
        "<source id=\"med-001-fake\"/>."
    )
    retrieved = collect_source_ids(bundle)
    index = build_record_index(bundle)
    result = verify_response(response, retrieved, index)
    assert result.passed is False
    assert result.unknown_ids == ["med-001-fake"]
    # The two real cites are still recorded.
    assert "med-001-1" in result.cited_ids
    assert "med-001-2" in result.cited_ids


# --- Bundle-corruption resilience ---


def test_empty_bundle_with_any_citation_fails() -> None:
    """If retrieval returned nothing but the LLM still produced
    citations, every cite is unknown."""
    response = "Patient is on metformin <source id=\"med-001-1\"/>."
    result = verify_response(response, set(), {})
    assert result.passed is False
    assert "med-001-1" in result.unknown_ids


def test_bundle_with_missing_value_field_skips_value_check() -> None:
    """A record missing the `value` field shouldn't crash the value
    check — it just skips. The cite-id pass still runs."""
    bundle = [
        {
            "labs": [
                {
                    "source_id": "lab-novalue",
                    "name": "Unknown Lab",
                    # No "value" key.
                }
            ]
        }
    ]
    response = (
        "Result was abnormal "
        "<source id=\"lab-novalue\"/>."
    )
    retrieved = collect_source_ids(bundle)
    index = build_record_index(bundle)
    result = verify_response(response, retrieved, index)
    assert result.passed is True
