"""Background extraction lifecycle.

`run_extraction` is the top-level coroutine the upload endpoint
schedules after a successful insert. It owns the state machine:

    pending -> extracting -> done | failed

and writes one audit event per transition. Transport / parse / schema
failures all land on `failed` with an error string — the upload
endpoint already returned 200 by the time we get here, so failures
must NEVER raise out of this function.

PHI policy: error strings written to audit_log + extraction_error are
exception class names + short reasons (e.g., "ValidationError: missing
collection_date"). The raw VLM text is never logged.
"""

from __future__ import annotations

import logging
import time

import anthropic

from agent import audit
from agent import documents as doc_storage
from agent.extractors.intake_extractor import extract_intake_form
from agent.extractors.lab_extractor import extract_lab_report

log = logging.getLogger(__name__)


def _short_error(exc: BaseException) -> str:
    """Truncated, PHI-safe error string for audit + extraction_error.
    Includes class name + short message; caps at 256 chars."""
    msg = f"{type(exc).__name__}: {exc}"
    return msg[:256]


async def run_extraction(
    *,
    database_url: str,
    document_id: int,
    anthropic_client: anthropic.AsyncAnthropic,
    model: str,
) -> None:
    """Run the lifecycle for one document. Never raises."""
    metadata = doc_storage.get_metadata(database_url, document_id)
    if metadata is None:
        log.warning("run_extraction: document_id=%d not found", document_id)
        return
    if metadata.extraction_status not in ("pending",):
        # A prior extraction already started (or finished). Stay
        # idempotent: re-running shouldn't double-process. If the user
        # explicitly wants re-extraction we'd reset status -> pending
        # in a separate "/documents/{id}/reextract" path; not in v0.
        log.info(
            "run_extraction: document_id=%d status=%s — skipping",
            document_id, metadata.extraction_status,
        )
        return

    blob_pair = doc_storage.get_blob(database_url, document_id)
    if blob_pair is None:
        log.warning("run_extraction: blob missing for document_id=%d", document_id)
        return
    blob, content_type = blob_pair

    doc_storage.set_status(
        database_url, document_id=document_id, status="extracting"
    )
    audit.record(
        database_url,
        audit.AuditEvent.DOCUMENT_EXTRACTION_STARTED,
        user_id=metadata.uploaded_by_user_id,
        details={
            "document_id": document_id,
            "patient_id": metadata.patient_id,
            "doc_type": metadata.doc_type,
            "content_type": content_type,
        },
    )

    started = time.perf_counter()
    try:
        rows_persisted = await _dispatch_and_persist(
            database_url=database_url,
            blob=blob,
            content_type=content_type,
            metadata=metadata,
            anthropic_client=anthropic_client,
            model=model,
        )
    except Exception as exc:  # noqa: BLE001 — never raise out of background
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        err = _short_error(exc)
        log.warning(
            "run_extraction: document_id=%d failed after %dms: %s",
            document_id, elapsed_ms, err,
        )
        doc_storage.set_status(
            database_url,
            document_id=document_id,
            status="failed",
            error=err,
        )
        audit.record(
            database_url,
            audit.AuditEvent.DOCUMENT_EXTRACTION_FAILED,
            user_id=metadata.uploaded_by_user_id,
            details={
                "document_id": document_id,
                "patient_id": metadata.patient_id,
                "doc_type": metadata.doc_type,
                "error": err,
                "latency_ms": elapsed_ms,
            },
        )
        return

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    doc_storage.set_status(
        database_url, document_id=document_id, status="done"
    )
    audit.record(
        database_url,
        audit.AuditEvent.DOCUMENT_EXTRACTION_COMPLETED,
        user_id=metadata.uploaded_by_user_id,
        details={
            "document_id": document_id,
            "patient_id": metadata.patient_id,
            "doc_type": metadata.doc_type,
            "rows_persisted": rows_persisted,
            "latency_ms": elapsed_ms,
        },
    )
    log.info(
        "run_extraction: document_id=%d done in %dms (%d rows)",
        document_id, elapsed_ms, rows_persisted,
    )


async def _dispatch_and_persist(
    *,
    database_url: str,
    blob: bytes,
    content_type: str,
    metadata: doc_storage.StoredDocument,
    anthropic_client: anthropic.AsyncAnthropic,
    model: str,
) -> int:
    """Branch on doc_type, run the extractor, persist derived_observations.
    Returns number of rows written."""
    if metadata.doc_type == "lab_pdf":
        report = await extract_lab_report(
            blob=blob,
            document_id=metadata.id,
            patient_id=metadata.patient_id,
            client=anthropic_client,
            model=model,
        )
        return doc_storage.persist_lab_report(database_url, report)

    if metadata.doc_type == "intake_form":
        form = await extract_intake_form(
            blob=blob,
            document_id=metadata.id,
            patient_id=metadata.patient_id,
            content_type=content_type,
            client=anthropic_client,
            model=model,
        )
        return doc_storage.persist_intake_form(database_url, form)

    raise ValueError(f"unknown doc_type: {metadata.doc_type!r}")


__all__ = ["run_extraction"]
