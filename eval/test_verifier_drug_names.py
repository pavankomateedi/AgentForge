"""Tests for the verifier's drug-name pass.

Symmetric to the existing numeric value-mismatch tests
(eval/test_verifier.py): pin pass-cases, fail-cases, and the
intentional non-firings (lab/condition citations + attribution-only).
"""

from __future__ import annotations

from agent.verifier import verify_response


def _make_records():
    return {
        "med-001-1": {
            "source_id": "med-001-1",
            "name": "Metformin",
            "dose": "1000 mg",
        },
        "med-001-2": {
            "source_id": "med-001-2",
            "name": "Lisinopril",
            "dose": "10 mg",
        },
        "med-001-3": {
            "source_id": "med-001-3",
            "name": "Atorvastatin",
            "dose": "20 mg",
        },
        "lab-001-a1c-2026-03": {
            "source_id": "lab-001-a1c-2026-03",
            "name": "Hemoglobin A1c",
            "value": 7.4,
        },
    }


# ---- Pass cases ----


def test_correct_drug_name_passes():
    text = 'Patient is on metformin <source id="med-001-1"/> daily.'
    records = _make_records()
    result = verify_response(
        text, set(records.keys()), records
    )
    assert result.passed
    assert result.name_mismatches == []


def test_correct_drug_with_strength_passes():
    """Prose mentions a strength descriptor with the drug — still matches."""
    text = 'Started metformin 1000 mg <source id="med-001-1"/> twice daily.'
    records = _make_records()
    result = verify_response(text, set(records.keys()), records)
    assert result.passed


def test_attribution_only_citation_passes():
    """No drug-name token in the prose window — pure attribution. The
    verifier MUST NOT flag this."""
    text = (
        'Per the chart medication list, the patient is well-managed '
        '<source id="med-001-1"/>.'
    )
    records = _make_records()
    result = verify_response(text, set(records.keys()), records)
    assert result.passed
    assert result.name_mismatches == []


def test_lab_citation_skips_name_check():
    """Lab `<source/>` tags are NOT subject to drug-name verification.
    The verifier still runs pass 2 (numeric tolerance) on them."""
    text = 'A1c is 7.4% <source id="lab-001-a1c-2026-03"/>.'
    records = _make_records()
    result = verify_response(text, set(records.keys()), records)
    assert result.passed
    assert result.name_mismatches == []


# ---- Fail cases ----


def test_wrong_drug_name_fails():
    """The classic regression: cite the right source_id but write the
    wrong drug name in the prose."""
    text = 'Patient is on lisinopril <source id="med-001-1"/> daily.'
    records = _make_records()
    result = verify_response(text, set(records.keys()), records)
    assert not result.passed
    assert len(result.name_mismatches) == 1
    nm = result.name_mismatches[0]
    assert nm.source_id == "med-001-1"
    assert nm.cited_drug == "lisinopril"
    assert nm.record_name == "Metformin"


def test_swapped_statin_name_fails():
    """Atorvastatin record cited but prose names a different statin."""
    text = 'Switched to rosuvastatin <source id="med-001-3"/>.'
    records = _make_records()
    result = verify_response(text, set(records.keys()), records)
    assert not result.passed
    assert any(nm.source_id == "med-001-3" for nm in result.name_mismatches)


def test_multiple_med_citations_each_checked_independently():
    text = (
        'Patient is on lisinopril <source id="med-001-1"/> and '
        'metformin <source id="med-001-2"/>.'
    )
    records = _make_records()
    result = verify_response(text, set(records.keys()), records)
    # med-001-1 is Metformin (prose: lisinopril) — mismatch.
    # med-001-2 is Lisinopril (prose: metformin) — mismatch.
    assert not result.passed
    assert len(result.name_mismatches) == 2
    by_sid = {nm.source_id: nm for nm in result.name_mismatches}
    assert by_sid["med-001-1"].cited_drug == "lisinopril"
    assert by_sid["med-001-2"].cited_drug == "metformin"


def test_value_mismatch_takes_precedence_in_note():
    """When BOTH numeric AND name passes find issues, the verifier
    surfaces both lists but the human-readable `note` leads with the
    higher-priority numeric mismatch (Week 1 contract)."""
    text = (
        'Patient is on lisinopril <source id="med-001-1"/> with A1c '
        'of 8.4 <source id="lab-001-a1c-2026-03"/>.'
    )
    records = _make_records()
    result = verify_response(text, set(records.keys()), records)
    assert not result.passed
    assert len(result.value_mismatches) == 1
    assert len(result.name_mismatches) == 1


def test_describe_includes_both_names():
    nm = verify_response(
        'On lisinopril <source id="med-001-1"/>.',
        {"med-001-1"},
        _make_records(),
    ).name_mismatches[0]
    desc = nm.describe()
    assert "Metformin" in desc
    assert "lisinopril" in desc
