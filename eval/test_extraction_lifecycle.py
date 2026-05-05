"""End-to-end tests for `extractors.extraction.run_extraction`.

The lifecycle is: pending -> extracting -> done | failed, with one
audit event per transition. These tests stub the vision-call surface
and assert: (1) status transitions correctly, (2) audit events fire,
(3) derived_observations rows are persisted, (4) PHI is not leaked
to audit details.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent import audit, documents as doc_storage
from agent.db import connect
from agent.extractors import extraction, intake_extractor, lab_extractor


fpdf = pytest.importorskip("fpdf")


def _make_pdf(lines: list[str]) -> bytes:
    pdf = fpdf.FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in lines:
        pdf.cell(0, 10, line)
        pdf.ln()
    return bytes(pdf.output())


def _audit_events(database_url: str, event_type: str) -> list[dict]:
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE event_type = ? ORDER BY id",
            (event_type,),
        ).fetchall()
    return [
        {
            "user_id": r["user_id"],
            "details": json.loads(r["details"]) if r["details"] else None,
        }
        for r in rows
    ]


def _stub_lab_response(fragment_id: str = "p1-l000") -> dict[str, Any]:
    return {
        "patient_id": "demo-001",
        "document_id": 1,  # filled by extractor anyway
        "ordering_provider": None,
        "lab_name": "Quest",
        "collection_date": "2026-01-15",
        "values": [
            {
                "test_name": "HbA1c",
                "value": 8.5,
                "unit": "%",
                "reference_range": "<7.0",
                "collection_date": "2026-01-15",
                "abnormal_flag": "high",
                "citation": {
                    "source_type": "lab_pdf",
                    "source_id": "demo-001-doc-1",
                    "page_or_section": "page-1",
                    "field_or_chunk_id": fragment_id,
                    "quote_or_value": "HbA1c 8.5%",
                    "bbox": None,
                },
                "confidence": 0.93,
            }
        ],
        "extraction_warnings": [],
    }


def _stub_intake_response() -> dict[str, Any]:
    return {
        "patient_id": "demo-001",
        "document_id": 1,
        "demographics": {
            "name": "Margaret Hayes",
            "name_citation": {
                "source_type": "intake_form",
                "source_id": "demo-001-doc-1",
                "page_or_section": "page-1",
                "field_or_chunk_id": "image-region",
                "quote_or_value": "Margaret Hayes",
                "bbox": None,
            },
        },
        "current_medications": [],
        "allergies": [],
        "family_history": [],
        "extraction_warnings": [],
    }


async def test_lifecycle_lab_pdf_happy_path(config, seed_user, monkeypatch):
    pdf_bytes = _make_pdf(["HbA1c 8.5%"])
    stored = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=pdf_bytes,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )

    from agent.extractors.pdf_fragments import extract_fragments

    fragments = extract_fragments(pdf_bytes)
    frag_id = fragments[0].fragment_id

    async def _fake_pdf(**kwargs):
        return _stub_lab_response(frag_id)

    monkeypatch.setattr(lab_extractor, "call_vision_pdf", _fake_pdf)

    await extraction.run_extraction(
        database_url=config.database_url,
        document_id=stored.id,
        anthropic_client=object(),
        model="claude-opus-4-7",
    )

    refreshed = doc_storage.get_metadata(config.database_url, stored.id)
    assert refreshed is not None
    assert refreshed.extraction_status == "done"
    assert refreshed.extraction_error is None

    # Audit lifecycle: started + completed.
    started = _audit_events(
        config.database_url, audit.AuditEvent.DOCUMENT_EXTRACTION_STARTED
    )
    completed = _audit_events(
        config.database_url, audit.AuditEvent.DOCUMENT_EXTRACTION_COMPLETED
    )
    assert len(started) == 1
    assert len(completed) == 1
    assert completed[0]["details"]["rows_persisted"] == 1
    assert completed[0]["details"]["latency_ms"] >= 0

    # derived_observations populated with the lab value + bbox.
    derived = doc_storage.list_derived_for_patient(
        config.database_url, "demo-001"
    )
    assert len(derived) == 1
    assert derived[0]["schema_kind"] == "lab_observation"
    assert derived[0]["payload"]["test_name"] == "HbA1c"
    assert derived[0]["bbox"] is not None  # bbox stamped from fragment map


async def test_lifecycle_marks_failed_on_validation_error(
    config, seed_user, monkeypatch
):
    pdf_bytes = _make_pdf(["x"])
    stored = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=pdf_bytes,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )

    async def _bad(**kwargs):
        return {"patient_id": "demo-001"}  # missing required fields

    monkeypatch.setattr(lab_extractor, "call_vision_pdf", _bad)

    await extraction.run_extraction(
        database_url=config.database_url,
        document_id=stored.id,
        anthropic_client=object(),
        model="claude-opus-4-7",
    )

    refreshed = doc_storage.get_metadata(config.database_url, stored.id)
    assert refreshed is not None
    assert refreshed.extraction_status == "failed"
    assert refreshed.extraction_error is not None
    assert "ValidationError" in refreshed.extraction_error

    failed = _audit_events(
        config.database_url, audit.AuditEvent.DOCUMENT_EXTRACTION_FAILED
    )
    assert len(failed) == 1


async def test_lifecycle_marks_failed_on_vision_error(
    config, seed_user, monkeypatch
):
    pdf_bytes = _make_pdf(["x"])
    stored = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=pdf_bytes,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )

    from agent.extractors._vision import VisionExtractionError

    async def _err(**kwargs):
        raise VisionExtractionError("simulated transport failure")

    monkeypatch.setattr(lab_extractor, "call_vision_pdf", _err)

    await extraction.run_extraction(
        database_url=config.database_url,
        document_id=stored.id,
        anthropic_client=object(),
        model="claude-opus-4-7",
    )

    refreshed = doc_storage.get_metadata(config.database_url, stored.id)
    assert refreshed is not None
    assert refreshed.extraction_status == "failed"
    assert "VisionExtractionError" in (refreshed.extraction_error or "")


async def test_lifecycle_intake_form_image(config, seed_user, monkeypatch):
    img_bytes = b"\xff\xd8\xff\xe0fake-jpeg-content"
    stored = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="intake_form",
        file_blob=img_bytes,
        content_type="image/jpeg",
        uploaded_by_user_id=seed_user.id,
    )

    async def _fake_image(**kwargs):
        return _stub_intake_response()

    monkeypatch.setattr(intake_extractor, "call_vision_image", _fake_image)

    await extraction.run_extraction(
        database_url=config.database_url,
        document_id=stored.id,
        anthropic_client=object(),
        model="claude-opus-4-7",
    )

    refreshed = doc_storage.get_metadata(config.database_url, stored.id)
    assert refreshed is not None
    assert refreshed.extraction_status == "done"

    derived = doc_storage.list_derived_for_patient(
        config.database_url, "demo-001"
    )
    # Demographics row at minimum; no meds/allergies in stub.
    schemas = {d["schema_kind"] for d in derived}
    assert "intake_demographics" in schemas


async def test_lifecycle_idempotent_on_already_done(
    config, seed_user, monkeypatch
):
    pdf_bytes = _make_pdf(["x"])
    stored = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=pdf_bytes,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    doc_storage.set_status(
        config.database_url, document_id=stored.id, status="done"
    )

    call_count = {"n": 0}

    async def _fake(**kwargs):
        call_count["n"] += 1
        return _stub_lab_response("p1-l000")

    monkeypatch.setattr(lab_extractor, "call_vision_pdf", _fake)

    await extraction.run_extraction(
        database_url=config.database_url,
        document_id=stored.id,
        anthropic_client=object(),
        model="claude-opus-4-7",
    )

    # Already-done document should not re-run extraction.
    assert call_count["n"] == 0


async def test_lifecycle_audit_details_have_no_phi(
    config, seed_user, monkeypatch
):
    """Stub returns extraction containing PHI strings; audit details
    should only carry structural fields, not the extracted content."""
    pdf_bytes = _make_pdf(["x"])
    stored = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="intake_form",
        file_blob=pdf_bytes,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )

    async def _fake(**kwargs):
        resp = _stub_intake_response()
        resp["demographics"]["name"] = "Margaret Q PHI Hayes"
        resp["chief_concern"] = "PHI-MARKER concern text"
        resp["chief_concern_citation"] = {
            "source_type": "intake_form",
            "source_id": "demo-001-doc-1",
            "page_or_section": "page-1",
            "field_or_chunk_id": "image-region",
            "quote_or_value": "PHI-MARKER",
            "bbox": None,
        }
        return resp

    monkeypatch.setattr(intake_extractor, "call_vision_pdf", _fake)

    await extraction.run_extraction(
        database_url=config.database_url,
        document_id=stored.id,
        anthropic_client=object(),
        model="claude-opus-4-7",
    )

    started = _audit_events(
        config.database_url, audit.AuditEvent.DOCUMENT_EXTRACTION_STARTED
    )
    completed = _audit_events(
        config.database_url, audit.AuditEvent.DOCUMENT_EXTRACTION_COMPLETED
    )
    rendered = json.dumps(started + completed)
    assert "Margaret" not in rendered
    assert "PHI-MARKER" not in rendered
    # patient_id IS allowed in details (it's the row key, not the name).
    assert "demo-001" in rendered
