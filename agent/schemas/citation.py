"""Citation contract — every clinical claim, every schema field.

A `Citation` ties an extracted fact to its origin: which document, which
page, which fragment of text, optionally with the bounding box rectangle
on the rendered page so the UI can draw an overlay. The verifier (Week
1's two-pass pure-Python check) walks `source_id` and rejects citations
that don't appear in the turn's retrieval bundle.

The contract is identical for FHIR records, lab PDFs, intake forms, and
guideline chunks — single shape, four storage backends.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BBox(BaseModel):
    """PDF coordinate bounding box. Origin is bottom-left per PDF
    convention (pdfplumber returns coordinates in this space). The UI
    overlay component flips y when rendering on top of the rasterized
    page image. All four values are page-relative points (1/72 inch)."""

    model_config = ConfigDict(extra="forbid")

    x0: float = Field(..., ge=0)
    y0: float = Field(..., ge=0)
    x1: float = Field(..., ge=0)
    y1: float = Field(..., ge=0)

    @model_validator(mode="after")
    def _check_ordering(self) -> "BBox":
        if self.x1 <= self.x0:
            raise ValueError(
                f"BBox.x1 ({self.x1}) must be > x0 ({self.x0})"
            )
        if self.y1 <= self.y0:
            raise ValueError(
                f"BBox.y1 ({self.y1}) must be > y0 ({self.y0})"
            )
        return self


CitationSourceType = Literal[
    "lab_pdf",
    "intake_form",
    "guideline_chunk",
    "fhir_record",
]


class Citation(BaseModel):
    """The atomic provenance unit. Required everywhere a fact is asserted.

    The verifier matches `source_id` against the retrieval bundle; the
    `field_or_chunk_id` and `bbox` are richer evidence for the UI but
    not part of the verifier contract (citation correctness is decided
    at the source level)."""

    model_config = ConfigDict(extra="forbid")

    source_type: CitationSourceType
    source_id: str = Field(..., min_length=1, max_length=256)
    page_or_section: str = Field(..., min_length=1, max_length=128)
    field_or_chunk_id: str = Field(..., min_length=1, max_length=256)
    quote_or_value: str = Field(..., min_length=1, max_length=2048)
    bbox: BBox | None = None
