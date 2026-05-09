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
from agent.schemas.intake import IntakeForm

log = logging.getLogger(__name__)


def _short_error(exc: BaseException) -> str:
    """Truncated, PHI-safe error string for audit + extraction_error.
    Includes class name + short message; caps at 256 chars."""
    msg = f"{type(exc).__name__}: {exc}"
    return msg[:256]


def _normalize_name(s: str | None) -> str:
    """Lowercase + collapse whitespace for fuzzy-equal name comparison.
    Catches differences in case and spacing without going down the
    nickname / middle-name rabbit hole. The synthetic demo data uses
    canonical names so an exact match on normalized form is the right
    bar for v0; a real deployment would want a soundex / fuzz-ratio
    pass plus an explicit overrides table for known aliases."""
    if not s:
        return ""
    return " ".join(s.lower().split())


def _check_identity_against_assigned(
    *,
    extracted: IntakeForm,
    assigned_patient_id: str,
) -> list[str]:
    """Compare extracted demographics against the assigned patient's
    on-file identity. Returns a list of mismatch reasons (empty list if
    everything matches or the assigned patient has no demographics on
    file). Lab PDFs aren't checked here because LabReport doesn't carry
    patient demographics in its schema (see W2 follow-up: extend
    LabReport with patient_name + dob to enable parity)."""
    # Lazy import — demo_data is large; only load when we need it.
    from agent.demo_data import DEMO_PATIENTS

    record = DEMO_PATIENTS.get(assigned_patient_id)
    if not record:
        return []
    assigned = record.get("patient", {})
    assigned_name = assigned.get("name")
    assigned_dob = assigned.get("dob")

    extracted_demographics = extracted.demographics
    extracted_name = extracted_demographics.name
    extracted_dob = extracted_demographics.dob

    reasons: list[str] = []

    if extracted_name and assigned_name:
        if _normalize_name(extracted_name) != _normalize_name(assigned_name):
            # PHI-light log: include names because this warning is shown
            # back to the clinician. Audit-log scrubbing happens at the
            # audit layer, not here.
            reasons.append(
                f"Patient name mismatch: extracted={extracted_name!r}, "
                f"assigned={assigned_name!r}"
            )

    if extracted_dob and assigned_dob:
        # extracted_dob is a date object, assigned_dob is a YYYY-MM-DD string.
        if str(extracted_dob) != str(assigned_dob):
            reasons.append(
                f"Patient DOB mismatch: extracted={extracted_dob}, "
                f"assigned={assigned_dob}"
            )

    return reasons


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
    identity_warnings: list[str] = []
    try:
        rows_persisted, extracted_intake = await _dispatch_and_persist(
            database_url=database_url,
            blob=blob,
            content_type=content_type,
            metadata=metadata,
            anthropic_client=anthropic_client,
            model=model,
        )
        # Systematic patient-identity check. Currently only intake forms
        # carry patient demographics in their schema; lab PDFs skip the
        # check (see _check_identity_against_assigned for the gap). The
        # check runs AFTER persist so the document is queryable but
        # gated behind needs_review until a clinician approves.
        if extracted_intake is not None:
            identity_warnings = _check_identity_against_assigned(
                extracted=extracted_intake,
                assigned_patient_id=metadata.patient_id,
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

    if identity_warnings:
        # Identity mismatch — gate the document behind clinician review.
        # extraction_error carries the warning text since the documents
        # table doesn't have a separate warnings column; reusing the
        # existing field avoids a schema migration. Approve clears it.
        warning_msg = "; ".join(identity_warnings)
        doc_storage.set_status(
            database_url,
            document_id=document_id,
            status="needs_review",
            error=warning_msg,
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
                "needs_review_reason": "identity_mismatch",
                "warning_count": len(identity_warnings),
            },
        )
        log.warning(
            "run_extraction: document_id=%d needs_review (%d identity warning(s))",
            document_id, len(identity_warnings),
        )
        return

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
) -> tuple[int, IntakeForm | None]:
    """Branch on doc_type, run the extractor, persist derived_observations.
    Returns (rows_persisted, extracted_intake) — the IntakeForm is
    returned only for intake_form docs so the caller can run the
    systematic patient-identity check; None for lab PDFs (their schema
    doesn't carry patient demographics)."""
    if metadata.doc_type == "lab_pdf":
        report = await extract_lab_report(
            blob=blob,
            document_id=metadata.id,
            patient_id=metadata.patient_id,
            client=anthropic_client,
            model=model,
        )
        return doc_storage.persist_lab_report(database_url, report), None

    if metadata.doc_type == "intake_form":
        form = await extract_intake_form(
            blob=blob,
            document_id=metadata.id,
            patient_id=metadata.patient_id,
            content_type=content_type,
            client=anthropic_client,
            model=model,
        )
        return doc_storage.persist_intake_form(database_url, form), form

    raise ValueError(f"unknown doc_type: {metadata.doc_type!r}")


__all__ = ["run_extraction"]
