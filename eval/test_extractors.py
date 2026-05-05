"""Tests for the lab + intake extractors.

The Anthropic vision call surface is monkeypatched so these tests are
fast, free, and deterministic. The point isn't to test the model — it
is to pin the schema-validation behavior, the bbox-attachment logic,
and the PHI-safe logging contract.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.extractors import _vision, intake_extractor, lab_extractor
from agent.extractors._vision import VisionExtractionError


fpdf = pytest.importorskip("fpdf")


def _make_pdf(lines: list[str]) -> bytes:
    pdf = fpdf.FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in lines:
        pdf.cell(0, 10, line)
        pdf.ln()
    return bytes(pdf.output())


# ---- _vision._strip_to_json ----


def test_strip_to_json_handles_fences():
    fenced = '```json\n{"a": 1}\n```'
    assert _vision._strip_to_json(fenced) == '{"a": 1}'


def test_strip_to_json_handles_preamble():
    preamble = "Here is your response:\n{\"a\": 1}"
    assert _vision._strip_to_json(preamble) == '{"a": 1}'


def test_parse_json_response_raises_on_garbage():
    with pytest.raises(VisionExtractionError):
        _vision._parse_json_response("not even close to JSON")


# ---- render_fragment_context ----


def test_render_fragment_context_groups_by_page():
    pdf_bytes = _make_pdf(["alpha beta", "gamma delta"])
    from agent.extractors.pdf_fragments import extract_fragments

    fragments = extract_fragments(pdf_bytes)
    rendered = _vision.render_fragment_context(fragments)
    assert "--- page 1 ---" in rendered
    for f in fragments:
        assert f.fragment_id in rendered


def test_render_fragment_context_empty():
    assert "no extractable text fragments" in _vision.render_fragment_context([])


# ---- lab_extractor.extract_lab_report ----


def _stub_lab_response(fragment_id: str, frag_text: str) -> dict[str, Any]:
    return {
        "patient_id": "demo-001",
        "document_id": 7,
        "ordering_provider": "Dr. Chen",
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
                    "source_id": "demo-001-doc-7",
                    "page_or_section": "page-1",
                    "field_or_chunk_id": fragment_id,
                    "quote_or_value": frag_text,
                    "bbox": None,
                },
                "confidence": 0.95,
            }
        ],
        "extraction_warnings": [],
    }


async def test_lab_extractor_attaches_bbox_from_fragment_map(monkeypatch):
    pdf_bytes = _make_pdf(["HbA1c 8.5%", "Glucose 145 mg/dL"])

    from agent.extractors.pdf_fragments import extract_fragments

    fragments = extract_fragments(pdf_bytes)
    target_frag = next(f for f in fragments if "HbA1c" in f.text)

    async def _fake(**kwargs):
        return _stub_lab_response(target_frag.fragment_id, target_frag.text)

    monkeypatch.setattr(lab_extractor, "call_vision_pdf", _fake)

    report = await lab_extractor.extract_lab_report(
        blob=pdf_bytes,
        document_id=7,
        patient_id="demo-001",
        client=object(),  # not used; _fake ignores it
        model="claude-opus-4-7",
    )
    assert len(report.values) == 1
    cit = report.values[0].citation
    assert cit.field_or_chunk_id == target_frag.fragment_id
    assert cit.bbox is not None, "bbox must be stamped from fragment map"
    assert cit.bbox.x1 > cit.bbox.x0
    assert cit.page_or_section == "page-1"


async def test_lab_extractor_warns_on_unknown_fragment(monkeypatch):
    pdf_bytes = _make_pdf(["HbA1c 8.5%"])

    async def _fake(**kwargs):
        return _stub_lab_response("p99-l999", "made up")  # ID not in fragment table

    monkeypatch.setattr(lab_extractor, "call_vision_pdf", _fake)

    report = await lab_extractor.extract_lab_report(
        blob=pdf_bytes,
        document_id=7,
        patient_id="demo-001",
        client=object(),
        model="claude-opus-4-7",
    )
    assert report.values[0].citation.bbox is None
    assert any("p99-l999" in w for w in report.extraction_warnings)


async def test_lab_extractor_propagates_validation_error(monkeypatch):
    """A VLM response missing a required field should surface as
    pydantic.ValidationError so the extraction lifecycle marks the
    document `failed` rather than persisting partial garbage."""
    from pydantic import ValidationError

    async def _bad(**kwargs):
        return {"patient_id": "demo-001"}  # missing collection_date, document_id, etc.

    monkeypatch.setattr(lab_extractor, "call_vision_pdf", _bad)

    with pytest.raises(ValidationError):
        await lab_extractor.extract_lab_report(
            blob=_make_pdf(["x"]),
            document_id=1,
            patient_id="demo-001",
            client=object(),
            model="claude-opus-4-7",
        )


async def test_lab_extractor_propagates_vision_error(monkeypatch):
    async def _err(**kwargs):
        raise VisionExtractionError("transport blew up")

    monkeypatch.setattr(lab_extractor, "call_vision_pdf", _err)

    with pytest.raises(VisionExtractionError):
        await lab_extractor.extract_lab_report(
            blob=_make_pdf(["x"]),
            document_id=1,
            patient_id="demo-001",
            client=object(),
            model="claude-opus-4-7",
        )


# ---- intake_extractor.extract_intake_form ----


def _stub_intake_response(fragment_id: str = "p1-l000") -> dict[str, Any]:
    return {
        "patient_id": "demo-001",
        "document_id": 9,
        "demographics": {
            "name": "Margaret Hayes",
            "name_citation": {
                "source_type": "intake_form",
                "source_id": "demo-001-doc-9",
                "page_or_section": "page-1",
                "field_or_chunk_id": fragment_id,
                "quote_or_value": "Margaret Hayes",
                "bbox": None,
            },
        },
        "chief_concern": "Persistent fatigue",
        "chief_concern_citation": {
            "source_type": "intake_form",
            "source_id": "demo-001-doc-9",
            "page_or_section": "page-1",
            "field_or_chunk_id": "image-region",
            "quote_or_value": "Fatigue 3 weeks",
            "bbox": None,
        },
        "current_medications": [],
        "allergies": [
            {
                "substance": "Penicillin",
                "reaction": "Hives",
                "severity": "moderate",
                "citation": {
                    "source_type": "intake_form",
                    "source_id": "demo-001-doc-9",
                    "page_or_section": "page-1",
                    "field_or_chunk_id": "image-region",
                    "quote_or_value": "Penicillin -> hives",
                    "bbox": None,
                },
            }
        ],
        "family_history": ["mother: T2DM"],
        "extraction_warnings": [],
    }


async def test_intake_extractor_pdf_path(monkeypatch):
    pdf_bytes = _make_pdf(["Margaret Hayes  DOB 1954-08-12"])

    from agent.extractors.pdf_fragments import extract_fragments

    fragments = extract_fragments(pdf_bytes)
    name_frag_id = fragments[0].fragment_id

    async def _fake(**kwargs):
        return _stub_intake_response(name_frag_id)

    monkeypatch.setattr(intake_extractor, "call_vision_pdf", _fake)

    form = await intake_extractor.extract_intake_form(
        blob=pdf_bytes,
        document_id=9,
        patient_id="demo-001",
        content_type="application/pdf",
        client=object(),
        model="claude-opus-4-7",
    )
    assert form.demographics.name == "Margaret Hayes"
    # Name was cited with a real fragment_id → bbox stamped.
    assert form.demographics.name_citation.bbox is not None
    # Allergy was cited with image-region → bbox cleared.
    assert form.allergies[0].citation.bbox is None


async def test_intake_extractor_image_path_uses_image_call(monkeypatch):
    img_bytes = b"\xff\xd8\xff\xe0fake-jpeg"
    called = {"pdf": False, "image": False}

    async def _fake_pdf(**kwargs):
        called["pdf"] = True
        return _stub_intake_response()

    async def _fake_image(**kwargs):
        called["image"] = True
        assert kwargs["media_type"] == "image/jpeg"
        return _stub_intake_response()

    monkeypatch.setattr(intake_extractor, "call_vision_pdf", _fake_pdf)
    monkeypatch.setattr(intake_extractor, "call_vision_image", _fake_image)

    await intake_extractor.extract_intake_form(
        blob=img_bytes,
        document_id=9,
        patient_id="demo-001",
        content_type="image/jpeg",
        client=object(),
        model="claude-opus-4-7",
    )
    assert called["image"] is True
    assert called["pdf"] is False
