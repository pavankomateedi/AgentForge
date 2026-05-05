"""Document blob storage + metadata helpers.

Thin layer over the `documents` table — keeps the SQL out of the upload
endpoint so `main.py` stays at orchestration height. Extraction logic
itself lives in `agent/extractors/` (Stage 1c+); this module only
handles the byte-store + dedup + status transitions.

Dedup contract: a (patient_id, file_hash) pair is unique. Re-upload of
the same bytes for the same patient returns the existing row instead
of erroring — keeps the UI idempotent under retries.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from agent.db import connect
from agent.schemas.document import DocType, ExtractionStatus
from agent.schemas.intake import IntakeForm
from agent.schemas.lab import LabReport

log = logging.getLogger(__name__)


def _page_number_from_section(section: str | None) -> int | None:
    """Citations carry `page_or_section` like 'page-2' or 'section-allergies'.
    Extract the numeric page when present so derived_observations.page_number
    is queryable. Non-page sections store NULL."""
    if section is None:
        return None
    if section.startswith("page-"):
        try:
            return int(section[len("page-") :])
        except ValueError:
            return None
    return None


def compute_file_hash(blob: bytes) -> str:
    """SHA-256 hex digest of the file bytes. Stable across runs and OSes;
    used as the dedup key alongside patient_id."""
    return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class StoredDocument:
    id: int
    patient_id: str
    doc_type: DocType
    file_hash: str
    content_type: str
    uploaded_by_user_id: int
    uploaded_at: datetime
    extraction_status: ExtractionStatus
    extraction_error: str | None
    deduplicated: bool = False


def _row_to_stored(row: sqlite3.Row, *, deduplicated: bool = False) -> StoredDocument:
    return StoredDocument(
        id=row["id"],
        patient_id=row["patient_id"],
        doc_type=row["doc_type"],
        file_hash=row["file_hash"],
        content_type=row["content_type"],
        uploaded_by_user_id=row["uploaded_by_user_id"],
        uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
        extraction_status=row["extraction_status"],
        extraction_error=row["extraction_error"],
        deduplicated=deduplicated,
    )


def find_by_hash(
    database_url: str, *, patient_id: str, file_hash: str
) -> StoredDocument | None:
    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE patient_id = ? AND file_hash = ?",
            (patient_id, file_hash),
        ).fetchone()
    return _row_to_stored(row, deduplicated=True) if row else None


def insert_document(
    database_url: str,
    *,
    patient_id: str,
    doc_type: DocType,
    file_blob: bytes,
    content_type: str,
    uploaded_by_user_id: int,
) -> StoredDocument:
    """Store a new document. If (patient_id, file_hash) already exists,
    returns the existing row with `deduplicated=True` instead of raising.

    Caller is responsible for RBAC and assignment checks before calling
    this — the storage layer assumes authorization is already settled.
    """
    file_hash = compute_file_hash(file_blob)
    existing = find_by_hash(
        database_url, patient_id=patient_id, file_hash=file_hash
    )
    if existing is not None:
        log.info(
            "documents: dedup hit for patient=%s hash=%s existing_id=%d",
            patient_id, file_hash[:12], existing.id,
        )
        return existing

    with connect(database_url) as conn:
        cursor = conn.execute(
            """INSERT INTO documents (
                patient_id, doc_type, file_blob, file_hash, content_type,
                uploaded_by_user_id, extraction_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (
                patient_id,
                doc_type,
                file_blob,
                file_hash,
                content_type,
                uploaded_by_user_id,
            ),
        )
        new_id = cursor.lastrowid
        conn.commit()
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (new_id,)
        ).fetchone()
    log.info(
        "documents: inserted patient=%s doc_type=%s id=%d hash=%s",
        patient_id, doc_type, new_id, file_hash[:12],
    )
    return _row_to_stored(row, deduplicated=False)


def set_status(
    database_url: str,
    *,
    document_id: int,
    status: ExtractionStatus,
    error: str | None = None,
) -> None:
    """Update extraction_status (and optionally extraction_error). The
    extractor calls this on transition: pending -> extracting -> done|failed.
    """
    with connect(database_url) as conn:
        conn.execute(
            "UPDATE documents SET extraction_status = ?, extraction_error = ? "
            "WHERE id = ?",
            (status, error, document_id),
        )
        conn.commit()


def get_blob(database_url: str, document_id: int) -> tuple[bytes, str] | None:
    """Returns (blob, content_type) or None if missing."""
    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT file_blob, content_type FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
    if row is None:
        return None
    return (row["file_blob"], row["content_type"])


def get_metadata(
    database_url: str, document_id: int
) -> StoredDocument | None:
    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
    return _row_to_stored(row) if row else None


# --- Derived-observations persistence (Week 2) ---


def _replace_derived_observations(
    conn: sqlite3.Connection,
    *,
    document_id: int,
    rows: list[tuple[str, str, str, float | None, int | None, str | None]],
) -> None:
    """Replace ALL derived_observations rows for a given document. Re-
    extraction (after a prompt improvement) calls this to swap the
    facts without touching the source blob — the document_id contract
    stays stable, only the rows beneath it churn.

    Each tuple is (patient_id, source_id, schema_kind, payload_json,
    confidence, page_number, bbox_json). Caller is responsible for
    serializing payload_json + bbox_json with json.dumps.
    """
    conn.execute(
        "DELETE FROM derived_observations WHERE document_id = ?", (document_id,)
    )
    conn.executemany(
        """INSERT INTO derived_observations
           (document_id, patient_id, source_id, schema_kind, payload_json,
            confidence, page_number, bbox_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(document_id, *r) for r in rows],
    )


def persist_lab_report(database_url: str, report: LabReport) -> int:
    """Write one derived_observations row per LabValue. Replaces any
    prior rows for this document_id (re-extraction is idempotent).
    Returns the count of inserted rows."""
    rows: list[tuple] = []
    for idx, value in enumerate(report.values):
        slug = (
            value.test_name.lower()
            .replace(" ", "-")
            .replace("/", "-")
        )
        source_id = f"lab-doc-{report.document_id}-{slug}-{idx}"
        bbox_json = (
            json.dumps(value.citation.bbox.model_dump())
            if value.citation.bbox is not None
            else None
        )
        rows.append(
            (
                report.patient_id,
                source_id,
                "lab_observation",
                json.dumps(value.model_dump(mode="json")),
                value.confidence,
                _page_number_from_section(value.citation.page_or_section),
                bbox_json,
            )
        )

    with connect(database_url) as conn:
        _replace_derived_observations(
            conn, document_id=report.document_id, rows=rows
        )
        conn.commit()
    log.info(
        "documents: persisted %d lab values for document_id=%d",
        len(rows), report.document_id,
    )
    return len(rows)


def persist_intake_form(database_url: str, form: IntakeForm) -> int:
    """Write derived_observations rows for the citable parts of the
    form: demographics (one row), chief_concern (one row if present),
    one row per medication, one row per allergy, family_history (one
    row if non-empty). Returns total inserted count."""
    rows: list[tuple] = []

    rows.append(
        (
            form.patient_id,
            f"intake-doc-{form.document_id}-demographics",
            "intake_demographics",
            json.dumps(form.demographics.model_dump(mode="json")),
            None,
            _page_number_from_section(
                form.demographics.name_citation.page_or_section
            ),
            (
                json.dumps(form.demographics.name_citation.bbox.model_dump())
                if form.demographics.name_citation.bbox is not None
                else None
            ),
        )
    )

    if form.chief_concern is not None and form.chief_concern_citation is not None:
        cc = form.chief_concern_citation
        rows.append(
            (
                form.patient_id,
                f"intake-doc-{form.document_id}-chief-concern",
                "intake_chief_concern",
                json.dumps({"chief_concern": form.chief_concern}),
                None,
                _page_number_from_section(cc.page_or_section),
                json.dumps(cc.bbox.model_dump()) if cc.bbox is not None else None,
            )
        )

    for idx, med in enumerate(form.current_medications):
        rows.append(
            (
                form.patient_id,
                f"intake-doc-{form.document_id}-med-{idx}",
                "intake_medication",
                json.dumps(med.model_dump(mode="json")),
                None,
                _page_number_from_section(med.citation.page_or_section),
                (
                    json.dumps(med.citation.bbox.model_dump())
                    if med.citation.bbox is not None
                    else None
                ),
            )
        )

    for idx, allergy in enumerate(form.allergies):
        rows.append(
            (
                form.patient_id,
                f"intake-doc-{form.document_id}-allergy-{idx}",
                "intake_allergy",
                json.dumps(allergy.model_dump(mode="json")),
                None,
                _page_number_from_section(allergy.citation.page_or_section),
                (
                    json.dumps(allergy.citation.bbox.model_dump())
                    if allergy.citation.bbox is not None
                    else None
                ),
            )
        )

    if form.family_history:
        rows.append(
            (
                form.patient_id,
                f"intake-doc-{form.document_id}-family-history",
                "intake_family_history",
                json.dumps({"items": form.family_history}),
                None,
                None,
                None,
            )
        )

    with connect(database_url) as conn:
        _replace_derived_observations(
            conn, document_id=form.document_id, rows=rows
        )
        conn.commit()
    log.info(
        "documents: persisted %d intake rows for document_id=%d",
        len(rows), form.document_id,
    )
    return len(rows)


def list_derived_for_patient(
    database_url: str, patient_id: str
) -> list[dict]:
    """Read all extracted facts for a patient, newest-first by document.
    Returned dicts are the row values (payload_json deserialized).
    Used by the evidence_retriever worker to fold extracted facts into
    the retrieval bundle."""
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT id, document_id, source_id, schema_kind, payload_json, "
            "confidence, page_number, bbox_json, created_at "
            "FROM derived_observations "
            "WHERE patient_id = ? ORDER BY document_id DESC, id ASC",
            (patient_id,),
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "document_id": r["document_id"],
                "source_id": r["source_id"],
                "schema_kind": r["schema_kind"],
                "payload": json.loads(r["payload_json"]),
                "confidence": r["confidence"],
                "page_number": r["page_number"],
                "bbox": json.loads(r["bbox_json"]) if r["bbox_json"] else None,
                "created_at": r["created_at"],
            }
        )
    return out


def list_for_patient(
    database_url: str, patient_id: str
) -> list[StoredDocument]:
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE patient_id = ? "
            "ORDER BY uploaded_at DESC",
            (patient_id,),
        ).fetchall()
    return [_row_to_stored(r) for r in rows]
