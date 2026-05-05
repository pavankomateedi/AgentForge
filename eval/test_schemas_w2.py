"""Stage 1 schema tests — Week 2 multimodal extraction.

Validates Pydantic strict-schema behavior so a malformed VLM response
is caught at the schema boundary rather than polluting
`derived_observations`. The schemas are the contract every later stage
depends on; failures here cascade to extractor + supervisor + eval.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from agent.schemas import (
    Allergy,
    BBox,
    Citation,
    Demographics,
    DocumentMetadata,
    IntakeForm,
    LabReport,
    LabValue,
    Medication,
)


# ---- Citation + BBox ----


def _good_bbox() -> BBox:
    return BBox(x0=100, y0=200, x1=300, y1=220)


def _good_citation(source_type: str = "lab_pdf") -> Citation:
    return Citation(
        source_type=source_type,  # type: ignore[arg-type]
        source_id="doc-1",
        page_or_section="page-1",
        field_or_chunk_id="frag-3",
        quote_or_value="HbA1c 8.5%",
        bbox=_good_bbox(),
    )


def test_bbox_rejects_x1_le_x0():
    with pytest.raises(ValidationError):
        BBox(x0=300, y0=10, x1=100, y1=20)


def test_bbox_rejects_y1_le_y0():
    with pytest.raises(ValidationError):
        BBox(x0=10, y0=300, x1=20, y1=100)


def test_bbox_allows_zero_origin():
    bb = BBox(x0=0, y0=0, x1=10, y1=10)
    assert bb.x0 == 0


def test_citation_requires_all_fields():
    with pytest.raises(ValidationError):
        Citation(  # missing field_or_chunk_id, quote_or_value
            source_type="lab_pdf",
            source_id="doc-1",
            page_or_section="page-1",
        )  # type: ignore[call-arg]


def test_citation_rejects_unknown_source_type():
    with pytest.raises(ValidationError):
        Citation(
            source_type="invented_type",  # type: ignore[arg-type]
            source_id="doc-1",
            page_or_section="page-1",
            field_or_chunk_id="frag-3",
            quote_or_value="x",
        )


def test_citation_bbox_optional():
    c = Citation(
        source_type="guideline_chunk",
        source_id="ada-2024-a1c",
        page_or_section="section-targets",
        field_or_chunk_id="ada-2024-a1c#0",
        quote_or_value="A1c goal <7%",
        bbox=None,
    )
    assert c.bbox is None


def test_citation_forbids_extra_fields():
    with pytest.raises(ValidationError):
        Citation(
            source_type="lab_pdf",
            source_id="doc-1",
            page_or_section="page-1",
            field_or_chunk_id="frag-3",
            quote_or_value="x",
            extra_field="not allowed",  # type: ignore[call-arg]
        )


# ---- LabValue / LabReport ----


def test_lab_value_accepts_numeric_or_categorical():
    LabValue(
        test_name="HbA1c", value=8.5, unit="%",
        collection_date=date(2026, 1, 1),
        citation=_good_citation(), confidence=0.9,
    )
    LabValue(
        test_name="HCG", value="positive", unit=None,
        collection_date=date(2026, 1, 1),
        citation=_good_citation(), confidence=0.9,
    )


def test_lab_value_confidence_bounded():
    with pytest.raises(ValidationError):
        LabValue(
            test_name="HbA1c", value=8.5,
            collection_date=date(2026, 1, 1),
            citation=_good_citation(), confidence=1.5,
        )
    with pytest.raises(ValidationError):
        LabValue(
            test_name="HbA1c", value=8.5,
            collection_date=date(2026, 1, 1),
            citation=_good_citation(), confidence=-0.1,
        )


def test_lab_value_abnormal_flag_constrained():
    LabValue(
        test_name="HbA1c", value=8.5,
        collection_date=date(2026, 1, 1),
        abnormal_flag="high",
        citation=_good_citation(), confidence=0.9,
    )
    with pytest.raises(ValidationError):
        LabValue(
            test_name="HbA1c", value=8.5,
            collection_date=date(2026, 1, 1),
            abnormal_flag="elevated",  # type: ignore[arg-type]
            citation=_good_citation(), confidence=0.9,
        )


def test_lab_report_accepts_empty_values_with_warning():
    """A report with no extractable rows is a valid (recorded) outcome —
    the warning surfaces why."""
    report = LabReport(
        patient_id="demo-001",
        document_id=1,
        collection_date=date(2026, 1, 1),
        values=[],
        extraction_warnings=["No tabular structure detected on page 2"],
    )
    assert report.values == []
    assert "tabular" in report.extraction_warnings[0]


def test_lab_report_serializes_round_trip():
    report = LabReport(
        patient_id="demo-001",
        document_id=42,
        collection_date=date(2026, 1, 1),
        values=[
            LabValue(
                test_name="HbA1c", value=8.5, unit="%",
                collection_date=date(2026, 1, 1),
                citation=_good_citation(), confidence=0.9,
            )
        ],
    )
    dumped = report.model_dump_json()
    rehydrated = LabReport.model_validate_json(dumped)
    assert rehydrated.values[0].test_name == "HbA1c"
    assert rehydrated.values[0].citation.source_id == "doc-1"


# ---- Intake form ----


def _good_demographics() -> Demographics:
    return Demographics(
        name="Margaret Hayes",
        name_citation=_good_citation("intake_form"),
    )


def test_intake_minimal():
    form = IntakeForm(
        patient_id="demo-001",
        document_id=1,
        demographics=_good_demographics(),
    )
    assert form.allergies == []
    assert form.current_medications == []


def test_intake_with_allergies_and_meds():
    form = IntakeForm(
        patient_id="demo-001",
        document_id=1,
        demographics=_good_demographics(),
        allergies=[
            Allergy(
                substance="Penicillin",
                reaction="Hives",
                severity="moderate",
                citation=_good_citation("intake_form"),
            )
        ],
        current_medications=[
            Medication(
                name="Metformin",
                dose="500mg",
                frequency="BID",
                citation=_good_citation("intake_form"),
            )
        ],
    )
    assert form.allergies[0].severity == "moderate"
    assert form.current_medications[0].name == "Metformin"


def test_intake_demographics_requires_name_citation():
    with pytest.raises(ValidationError):
        Demographics(name="X")  # type: ignore[call-arg]


# ---- DocumentMetadata ----


def test_document_metadata_validates_hash_length():
    from datetime import datetime

    DocumentMetadata(
        id=1,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_hash="a" * 64,
        content_type="application/pdf",
        uploaded_by_user_id=1,
        uploaded_at=datetime(2026, 5, 4, 12, 0),
        extraction_status="pending",
    )
    with pytest.raises(ValidationError):
        DocumentMetadata(
            id=1,
            patient_id="demo-001",
            doc_type="lab_pdf",
            file_hash="too_short",
            content_type="application/pdf",
            uploaded_by_user_id=1,
            uploaded_at=datetime(2026, 5, 4, 12, 0),
            extraction_status="pending",
        )
