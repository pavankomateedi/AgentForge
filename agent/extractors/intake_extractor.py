"""Claude vision extractor for intake forms.

Same pipeline shape as `lab_extractor`, but the document can be a PDF
or an image (phone-camera scan). The vision-call helper branches on
content_type to use the correct content block.

For images, fragment extraction yields nothing (pdfplumber can't read
rasters), so the prompt is image-only. For PDFs we still pass the
fragment table so the VLM can cite line-IDs.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic
from pydantic import ValidationError

from agent.extractors._vision import (
    VisionExtractionError,
    call_vision_image,
    call_vision_pdf,
    render_fragment_context,
)
from agent.extractors.pdf_fragments import Fragment, extract_fragments
from agent.schemas.intake import IntakeForm

log = logging.getLogger(__name__)


_INTAKE_SYSTEM_PROMPT = """You are a clinical intake-form extraction assistant.

Read the attached document (PDF or image) and the fragment table (when
provided). Return ONE JSON object that matches the IntakeForm schema.

For each cited field, set `citation.field_or_chunk_id` to the exact
`fragment_id` from the fragment table when available. For images
(no fragment table), use `field_or_chunk_id = "image-region"` and
`page_or_section = "page-1"`.

Output STRICT JSON. No prose, no markdown fences. If a field is
missing from the form, OMIT it (don't invent). If the document isn't
an intake form, return a minimal record with the citation pointing at
whatever section you can identify and add a warning.

Schema (Pydantic):
{
  "patient_id": "<string from caller>",
  "document_id": <int from caller>,
  "demographics": {
    "name": "string",
    "name_citation": { ... },
    "dob": "YYYY-MM-DD or null",
    "dob_citation": { ... } or null,
    "sex": "male" | "female" | "other" | "unknown" | null,
    "sex_citation": { ... } or null,
    "mrn": "string or null",
    "mrn_citation": { ... } or null
  },
  "chief_concern": "string or null",
  "chief_concern_citation": { ... } or null,
  "current_medications": [
    { "name": "string", "dose": "string or null",
      "frequency": "string or null", "citation": { ... } }
  ],
  "allergies": [
    { "substance": "string", "reaction": "string or null",
      "severity": "mild|moderate|severe|anaphylactic" | null,
      "citation": { ... } }
  ],
  "family_history": ["string", ...],
  "extraction_warnings": []
}

Each citation object:
{
  "source_type": "intake_form",
  "source_id": "<patient_id>-doc-<document_id>",
  "page_or_section": "page-<N>",
  "field_or_chunk_id": "<fragment_id>" or "image-region",
  "quote_or_value": "<supporting text>",
  "bbox": null
}
"""


def _build_user_prompt(
    *, patient_id: str, document_id: int, fragments: list[Fragment]
) -> str:
    fragment_table = render_fragment_context(fragments)
    return (
        f"patient_id = {patient_id}\n"
        f"document_id = {document_id}\n\n"
        f"Fragment table:\n{fragment_table}\n\n"
        "Return a single JSON object matching the IntakeForm schema."
    )


def _attach_bboxes_intake(form: IntakeForm, fragments: list[Fragment]) -> IntakeForm:
    """Walk every citation in the form and stamp bbox + page_or_section
    from our fragment map. Unknown fragment_ids fall back gracefully."""
    by_id = {f.fragment_id: f for f in fragments}

    def _stamp(citation):
        if citation is None:
            return
        f = by_id.get(citation.field_or_chunk_id)
        if f is not None:
            citation.bbox = f.bbox
            citation.page_or_section = f"page-{f.page}"
        else:
            citation.bbox = None

    _stamp(form.demographics.name_citation)
    _stamp(form.demographics.dob_citation)
    _stamp(form.demographics.sex_citation)
    _stamp(form.demographics.mrn_citation)
    _stamp(form.chief_concern_citation)
    for med in form.current_medications:
        _stamp(med.citation)
    for allergy in form.allergies:
        _stamp(allergy.citation)
    return form


async def extract_intake_form(
    *,
    blob: bytes,
    document_id: int,
    patient_id: str,
    content_type: str,
    client: anthropic.AsyncAnthropic,
    model: str,
) -> IntakeForm:
    """Run the full intake-form extraction pipeline.

    Branches on content_type: PDFs go through `call_vision_pdf` with a
    fragment table; images use `call_vision_image` with no table
    (pdfplumber can't see rasters)."""
    if content_type == "application/pdf":
        fragments = extract_fragments(blob)
    else:
        fragments = []

    log.info(
        "intake_extractor: %d fragments for document_id=%d patient_id=%s ctype=%s",
        len(fragments), document_id, patient_id, content_type,
    )

    user_prompt = _build_user_prompt(
        patient_id=patient_id, document_id=document_id, fragments=fragments
    )

    if content_type == "application/pdf":
        raw: dict[str, Any] = await call_vision_pdf(
            client=client,
            model=model,
            blob=blob,
            system=_INTAKE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
    else:
        raw = await call_vision_image(
            client=client,
            model=model,
            blob=blob,
            media_type=content_type,
            system=_INTAKE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

    raw.setdefault("patient_id", patient_id)
    raw.setdefault("document_id", document_id)
    raw.setdefault("extraction_warnings", [])

    try:
        form = IntakeForm.model_validate(raw)
    except ValidationError:
        raise

    return _attach_bboxes_intake(form, fragments)


__all__ = ["extract_intake_form", "VisionExtractionError"]
