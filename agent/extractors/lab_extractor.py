"""Claude vision extractor for lab PDFs.

Pipeline (per W2_ARCHITECTURE.md §3):
  1. pdf_fragments → list of (fragment_id, page, text, bbox)
  2. Build the VLM prompt: schema-guided system + user message that
     includes the rendered PDF + fragment table.
  3. Vision call returns JSON; ask for `fragment_id` per cited value.
  4. Pydantic validates against LabReport — failures surface as
     `extraction_warnings` + a `failed` document status.
  5. Caller persists each LabValue as one `derived_observations` row.

The extractor is a pure async function: input bytes + context, output
LabReport. Persistence happens elsewhere (`agent/documents.py`).
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic
from pydantic import ValidationError

from agent.extractors._vision import (
    call_vision_pdf,
    render_fragment_context,
)
from agent.extractors.pdf_fragments import Fragment, extract_fragments
from agent.schemas.citation import BBox, Citation
from agent.schemas.lab import LabReport

log = logging.getLogger(__name__)


_LAB_SYSTEM_PROMPT = """You are a clinical lab-report extraction assistant.

Read the attached PDF and the fragment table. For each lab measurement
you can identify, return ONE entry in the `values` array. Cite the
fragment whose text supports the value via `citation.field_or_chunk_id`
— that field MUST be the exact `fragment_id` from the fragment table.

Output STRICT JSON matching the schema below. No prose, no markdown
fences. If a field can't be determined from the document, OMIT it
(don't invent values). If the document isn't a lab report, return
`values: []` and add an entry to `extraction_warnings` saying so.

Confidence is YOUR confidence in the extraction itself (0.0-1.0).

Schema (Pydantic):
{
  "patient_id": "<string from caller>",
  "document_id": <int from caller>,
  "ordering_provider": "string or null",
  "lab_name": "string or null",
  "collection_date": "YYYY-MM-DD",
  "values": [
    {
      "test_name": "HbA1c",
      "value": 8.5,
      "unit": "%",
      "reference_range": "<7.0",
      "collection_date": "YYYY-MM-DD",
      "abnormal_flag": "high" | "low" | "normal" | "critical" | null,
      "citation": {
        "source_type": "lab_pdf",
        "source_id": "<patient_id>-doc-<document_id>",
        "page_or_section": "page-<N>",
        "field_or_chunk_id": "<fragment_id>",
        "quote_or_value": "<the text from the fragment>",
        "bbox": null
      },
      "confidence": 0.95
    }
  ],
  "extraction_warnings": []
}
"""


def _build_user_prompt(*, patient_id: str, document_id: int, fragments: list[Fragment]) -> str:
    fragment_table = render_fragment_context(fragments)
    return (
        f"patient_id = {patient_id}\n"
        f"document_id = {document_id}\n\n"
        f"Fragment table:\n{fragment_table}\n\n"
        "Return a single JSON object matching the LabReport schema in the system prompt."
    )


def _attach_bboxes(report: LabReport, fragments: list[Fragment]) -> LabReport:
    """The VLM cites by `fragment_id`; we own the bbox map. After
    validation, walk the report and attach the bbox for each citation
    whose fragment_id we recognize. Unknown fragment_ids leave bbox=None
    (the UI degrades to page-only). This keeps the VLM honest: it can't
    invent a bbox, only cite a fragment we already extracted."""
    by_id = {f.fragment_id: f for f in fragments}
    for value in report.values:
        cited_id = value.citation.field_or_chunk_id
        f = by_id.get(cited_id)
        if f is not None:
            value.citation.bbox = f.bbox
            value.citation.page_or_section = f"page-{f.page}"
        else:
            value.citation.bbox = None
            report.extraction_warnings.append(
                f"value.test_name={value.test_name!r}: cited fragment_id "
                f"{cited_id!r} not found in fragment table — bbox cleared"
            )
    return report


async def extract_lab_report(
    *,
    blob: bytes,
    document_id: int,
    patient_id: str,
    client: anthropic.AsyncAnthropic,
    model: str,
) -> LabReport:
    """Run the full lab-PDF extraction pipeline.

    Raises VisionExtractionError if the VLM fails or returns
    un-parseable JSON. Raises pydantic.ValidationError if the JSON
    parses but doesn't match the LabReport schema. The caller is
    responsible for translating either failure into a `failed`
    document status + audit event.
    """
    fragments = extract_fragments(blob)
    log.info(
        "lab_extractor: %d fragments for document_id=%d patient_id=%s",
        len(fragments), document_id, patient_id,
    )

    user_prompt = _build_user_prompt(
        patient_id=patient_id, document_id=document_id, fragments=fragments
    )
    raw: dict[str, Any] = await call_vision_pdf(
        client=client,
        model=model,
        blob=blob,
        system=_LAB_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    raw.setdefault("patient_id", patient_id)
    raw.setdefault("document_id", document_id)
    raw.setdefault("extraction_warnings", [])

    try:
        report = LabReport.model_validate(raw)
    except ValidationError:
        raise

    return _attach_bboxes(report, fragments)


__all__ = ["extract_lab_report", "BBox", "Citation"]
