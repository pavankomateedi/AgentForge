"""Tests for `agent.extractors.pdf_fragments`.

Pure pdfplumber wrapper — no VLM. Generates a tiny PDF with fpdf2 so
tests are self-contained and don't depend on a checked-in fixture.
"""

from __future__ import annotations

import pytest

from agent.extractors.pdf_fragments import _LINE_BAND_TOLERANCE, extract_fragments


fpdf = pytest.importorskip("fpdf")


def _make_pdf(lines: list[str]) -> bytes:
    pdf = fpdf.FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in lines:
        pdf.cell(0, 10, line)
        pdf.ln()
    return bytes(pdf.output())


def test_extract_fragments_basic_lab_pdf():
    pdf_bytes = _make_pdf(["HbA1c 8.5%", "Glucose 145 mg/dL", "Creatinine 1.2 mg/dL"])
    fragments = extract_fragments(pdf_bytes)
    assert len(fragments) == 3
    texts = [f.text for f in fragments]
    assert "HbA1c 8.5%" in texts
    assert "Glucose 145 mg/dL" in texts
    assert "Creatinine 1.2 mg/dL" in texts


def test_fragment_ids_are_stable_and_unique():
    pdf_bytes = _make_pdf(["Line A", "Line B", "Line C"])
    a = extract_fragments(pdf_bytes)
    b = extract_fragments(pdf_bytes)
    assert [f.fragment_id for f in a] == [f.fragment_id for f in b]
    assert len({f.fragment_id for f in a}) == len(a), "fragment_ids must be unique"


def test_fragment_bbox_invariants():
    pdf_bytes = _make_pdf(["Sample line"])
    [f] = extract_fragments(pdf_bytes)
    assert f.bbox.x1 > f.bbox.x0
    assert f.bbox.y1 > f.bbox.y0
    assert f.page == 1


def test_extract_fragments_empty_input():
    """Garbage / non-PDF input should return [] rather than raise — the
    extractor downstream decides whether to fall back or audit failed."""
    assert extract_fragments(b"") == []
    assert extract_fragments(b"definitely-not-a-pdf") == []


def test_line_band_tolerance_is_reasonable():
    """3pt is small enough to keep visually-distinct lines separate but
    large enough to absorb baseline jitter from scanned PDFs. Pinning
    the constant prevents accidental drift."""
    assert 1 < _LINE_BAND_TOLERANCE < 10


def test_extract_fragments_collapses_words_on_same_line():
    pdf_bytes = _make_pdf(["First Last word here"])
    fragments = extract_fragments(pdf_bytes)
    assert len(fragments) == 1
    assert "First" in fragments[0].text
    assert "word" in fragments[0].text


def test_multipage_assigns_correct_page_number():
    pdf = fpdf.FPDF()
    pdf.set_font("Helvetica", size=12)
    pdf.add_page()
    pdf.cell(0, 10, "page one content")
    pdf.add_page()
    pdf.cell(0, 10, "page two content")
    out = bytes(pdf.output())
    fragments = extract_fragments(out)
    pages = sorted({f.page for f in fragments})
    assert pages == [1, 2]
    p1_texts = [f.text for f in fragments if f.page == 1]
    p2_texts = [f.text for f in fragments if f.page == 2]
    assert any("one" in t for t in p1_texts)
    assert any("two" in t for t in p2_texts)
