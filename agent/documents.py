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
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from agent.db import connect
from agent.schemas.document import DocType, ExtractionStatus

log = logging.getLogger(__name__)


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
