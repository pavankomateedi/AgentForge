"""Document ingest metadata.

Mirrors the `documents` table row shape so the upload endpoint and the
DB layer agree on field names. Two of these enum types
(`DocType`, `ExtractionStatus`) are also used as the canonical string
constants throughout the codebase — import them rather than hardcoding
the literals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DocType = Literal["lab_pdf", "intake_form"]
"""The two document types in scope for Week 2. Adding a third (referral
fax, med-list reconciliation) is gated on the first two extracting
reliably end-to-end — see W2_ARCHITECTURE.md §1."""


ExtractionStatus = Literal["pending", "extracting", "done", "failed"]
"""State machine for the async extraction pipeline. `pending` is the
state on insert (before the background task picks it up); `extracting`
is set when the worker starts; terminal states are `done` and `failed`.
"""


class DocumentMetadata(BaseModel):
    """Server-side projection of a `documents` row. The blob itself is
    deliberately not in the metadata model — it ships only on explicit
    download requests so list/status responses stay small."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., ge=1)
    patient_id: str = Field(..., min_length=1, max_length=128)
    doc_type: DocType
    file_hash: str = Field(..., min_length=64, max_length=64)
    content_type: str = Field(..., min_length=1, max_length=128)
    uploaded_by_user_id: int = Field(..., ge=1)
    uploaded_at: datetime
    extraction_status: ExtractionStatus
    extraction_error: str | None = Field(default=None, max_length=2048)


class UploadResponse(BaseModel):
    """Returned from POST /documents/upload."""

    model_config = ConfigDict(extra="forbid")

    document_id: int
    status: ExtractionStatus
    deduplicated: bool = Field(
        default=False,
        description=(
            "True if the upload matched an existing (patient_id, "
            "file_hash) row; we returned the existing document_id "
            "instead of inserting a duplicate."
        ),
    )


class UploadAcceptedTypes:
    """Allowed MIME types per doc_type.

    PDFs (Adobe), JPEG/PNG/HEIC images for phone-camera intake forms.
    The type check happens at the upload endpoint; the extractor can
    be stricter still (e.g., lab PDFs that aren't PDFs are rejected).
    """

    LAB_PDF: tuple[str, ...] = ("application/pdf",)
    INTAKE_FORM: tuple[str, ...] = (
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/heic",
    )

    @classmethod
    def for_doc_type(cls, doc_type: str) -> tuple[str, ...]:
        if doc_type == "lab_pdf":
            return cls.LAB_PDF
        if doc_type == "intake_form":
            return cls.INTAKE_FORM
        return ()
