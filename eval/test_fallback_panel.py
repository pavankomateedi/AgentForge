"""Tests for `agent.graph._fallback_panel`.

Pinning the contract that when the verifier can't accept a narrative,
the displayed text is CLINICAL DATA — not Python repr, not metadata,
not nested-dict dumps. The Week 2 tools introduced nested-array
return shapes (`get_lab_history`, `get_changes_since`,
`check_clinical_thresholds`) that exposed the original fallback's
key-value-dump approach as illegible. These tests prove the new
fallback formats every shape cleanly.
"""

from __future__ import annotations

import pytest

from agent.graph import _fallback_panel, _inline_record
from agent.verifier import VerificationResult


def _v(note: str) -> VerificationResult:
    return VerificationResult(
        passed=False,
        cited_ids=["lab-001-a1c-2026-03"],
        unknown_ids=["fabricated-id"],
        note=note,
    )


# ---- Plumbing fields are never surfaced ----


_HIDDEN_FIELDS = (
    "source_id",
    "schema_kind",
    "payload_json",
    "bbox_json",
    "field_or_chunk_id",
    "resolved_test_key",
    "n_findings",
    "total_count",
    "file_hash",
    "uploaded_by_user_id",
    "content_type",
    "extraction_warnings",
)


@pytest.mark.parametrize("plumbing_key", _HIDDEN_FIELDS)
def test_plumbing_keys_never_surface(plumbing_key):
    """Every key the agent uses internally must be hidden from the
    clinician-facing fallback. Add to _HIDDEN_KEYS in graph.py if a
    new plumbing field appears."""
    parsed = [{plumbing_key: "should-not-appear-in-output"}]
    out = _fallback_panel(parsed, _v("test"))
    assert "should-not-appear-in-output" not in out
    assert plumbing_key.replace("_", " ") not in out.lower()


# ---- No raw Python repr leaks ----


def test_no_python_repr_for_lab_history():
    parsed = [
        {
            "test_name": "A1c",
            "history": [
                {
                    "source_id": "lab-001-a1c-2026-03",
                    "name": "Hemoglobin A1c",
                    "value": 7.4,
                    "unit": "%",
                    "reference_range": "<7.0",
                    "date": "2026-03-15",
                    "flag": "high",
                },
            ],
        }
    ]
    out = _fallback_panel(parsed, _v("rejected"))
    assert "{'source_id'" not in out
    assert "'name': 'Hemoglobin A1c'" not in out
    # Clean content present.
    assert "Hemoglobin A1c" in out
    assert "7.4" in out
    assert "2026-03-15" in out
    assert "high" in out


def test_no_python_repr_for_findings():
    parsed = [
        {
            "findings": [
                {
                    "rule_id": "A1C_UNCONTROLLED",
                    "severity": "critical",
                    "message": "A1c 10.5% exceeds threshold.",
                    "evidence_source_ids": ["lab-003-a1c-2026-04"],
                    "category": "lab_threshold",
                },
            ],
            "n_findings": 1,
        }
    ]
    out = _fallback_panel(parsed, _v("rejected"))
    assert "[{'rule_id'" not in out
    assert "evidence_source_ids" not in out
    assert "A1C_UNCONTROLLED" in out
    assert "CRITICAL" in out
    # The "n_findings: 1" line must NOT appear (heading already shows count).
    assert "n findings: 1" not in out.lower()


def test_no_python_repr_for_changes_since():
    parsed = [
        {
            "since_date": "2025-09-01",
            "new_problems": [],
            "new_medications": [],
            "new_labs": [
                {
                    "source_id": "lab-001-a1c-2026-03",
                    "name": "Hemoglobin A1c",
                    "value": 7.4,
                    "unit": "%",
                    "date": "2026-03-15",
                    "flag": "high",
                },
            ],
            "new_encounters": [
                {
                    "source_id": "enc-001-2026-03",
                    "date": "2026-03-15",
                    "type": "office visit",
                    "chief_complaint": "Diabetes follow-up",
                    "provider": "Dr. Chen",
                },
            ],
        }
    ]
    out = _fallback_panel(parsed, _v("rejected"))
    assert "[{'source_id'" not in out
    assert "Diabetes follow-up" in out
    assert "Hemoglobin A1c" in out


# ---- Per-shape rendering ----


def test_inline_lab_observation():
    s = _inline_record(
        {
            "source_id": "lab-001-a1c-2026-03",
            "name": "Hemoglobin A1c",
            "value": 7.4,
            "unit": "%",
            "reference_range": "<7.0",
            "date": "2026-03-15",
            "flag": "high",
        }
    )
    assert "Hemoglobin A1c" in s
    assert "7.4" in s
    assert "%" in s
    assert "high" in s
    # No leaked plumbing.
    assert "source_id" not in s
    assert "lab-001-a1c-2026-03" not in s


def test_inline_medication():
    s = _inline_record(
        {
            "source_id": "med-001-1",
            "name": "Metformin",
            "dose": "1000 mg",
            "frequency": "twice daily",
            "started": "2018-03-22",
        }
    )
    assert s == "Metformin 1000 mg twice daily (since 2018-03-22)"


def test_inline_problem():
    s = _inline_record(
        {
            "source_id": "cond-001-1",
            "code": "E11.9",
            "description": "Type 2 diabetes mellitus",
            "onset_date": "2018-03-22",
            "status": "active",
        }
    )
    assert "Type 2 diabetes mellitus" in s
    assert "E11.9" in s
    assert "active" in s
    assert "since 2018-03-22" in s


def test_inline_encounter():
    s = _inline_record(
        {
            "source_id": "enc-001-2026-03",
            "date": "2026-03-15",
            "type": "office visit",
            "chief_complaint": "Diabetes follow-up",
            "provider": "Dr. Chen",
        }
    )
    assert s == "2026-03-15 office visit - Diabetes follow-up (Dr. Chen)"


def test_inline_document():
    s = _inline_record(
        {
            "source_id": "doc-7",
            "document_id": 7,
            "doc_type": "lab_pdf",
            "uploaded_at": "2026-04-12T08:30:00",
            "extraction_status": "done",
            "content_type": "application/pdf",
        }
    )
    assert "#7" in s
    assert "Lab Pdf" in s  # title-case'd
    assert "done" in s
    assert "doc-7" not in s


def test_inline_patient_summary():
    s = _inline_record(
        {
            "source_id": "patient-demo-001",
            "name": "Margaret Hayes",
            "dob": "1962-04-14",
            "sex": "female",
            "mrn": "MRN-DEMO-001",
        }
    )
    assert "Margaret Hayes" in s
    assert "1962-04-14" in s
    assert "MRN-DEMO-001" in s


# ---- Top-level rendering ----


def test_panel_includes_verifier_note():
    parsed: list = []
    out = _fallback_panel(parsed, _v("Verifier rejected: missing 'foo'"))
    assert "Verifier rejected: missing 'foo'" in out


def test_panel_handles_empty_parsed_results():
    out = _fallback_panel([], _v("nothing"))
    assert "No structured records" in out


def test_panel_rendering_for_demo_003_critical_stack():
    """End-to-end: demo-003's worst-case Robert Mitchell. Verify the
    output reads cleanly without any plumbing leakage."""
    parsed = [
        {
            "labs": [
                {
                    "source_id": "lab-003-a1c-2026-04",
                    "name": "Hemoglobin A1c",
                    "value": 10.5,
                    "unit": "%",
                    "reference_range": "<7.0",
                    "date": "2026-04-12",
                    "flag": "high",
                },
                {
                    "source_id": "lab-003-cr-2026-04",
                    "name": "Creatinine",
                    "value": 1.8,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2026-04-12",
                    "flag": "high",
                },
            ],
        },
        {
            "findings": [
                {
                    "rule_id": "A1C_UNCONTROLLED",
                    "severity": "critical",
                    "message": "Uncontrolled type 2 diabetes.",
                    "evidence_source_ids": ["lab-003-a1c-2026-04"],
                    "category": "lab_threshold",
                },
                {
                    "rule_id": "METFORMIN_RENAL_CONTRAINDICATION",
                    "severity": "critical",
                    "message": "Hold metformin.",
                    "evidence_source_ids": ["lab-003-cr-2026-04", "med-003-1"],
                    "category": "interaction",
                },
            ],
            "n_findings": 2,
        },
    ]
    out = _fallback_panel(parsed, _v("rejected"))

    # Clinical content present.
    assert "Hemoglobin A1c" in out
    assert "10.5" in out
    assert "Creatinine" in out
    assert "1.8" in out
    assert "A1C_UNCONTROLLED" in out
    assert "METFORMIN_RENAL_CONTRAINDICATION" in out

    # Plumbing absent.
    assert "lab-003-a1c-2026-04" not in out
    assert "evidence_source_ids" not in out
    assert "lab_threshold" not in out
    assert "n_findings" not in out
    assert "n findings" not in out
    assert "[{" not in out
