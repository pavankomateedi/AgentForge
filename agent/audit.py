"""Audit log. Append-only writes. Failures here log but never block a request."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent.db import connect

log = logging.getLogger(__name__)


class AuditEvent:
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED_BAD_PASSWORD = "login_failed_bad_password"
    LOGIN_FAILED_NO_USER = "login_failed_no_user"
    LOGIN_FAILED_LOCKED = "login_failed_locked"
    LOGIN_FAILED_INACTIVE = "login_failed_inactive"
    ACCOUNT_LOCKED = "account_locked"
    LOGOUT = "logout"
    SESSION_EXPIRED = "session_expired"
    USER_CREATED = "user_created"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    MFA_ENROLLMENT_STARTED = "mfa_enrollment_started"
    MFA_ENROLLED = "mfa_enrolled"
    MFA_VERIFIED = "mfa_verified"
    MFA_FAILED = "mfa_failed"
    # Login that skipped the MFA challenge because the account was
    # explicitly flagged bypass_mfa=true in EXTRA_USERS_JSON. Distinct
    # from MFA_VERIFIED so the audit trail makes the carve-out
    # auditable; HIPAA_COMPLIANCE.md §164.312(d) calls this out.
    LOGIN_MFA_BYPASSED = "login_mfa_bypassed"
    CHAT_REQUEST = "chat_request"
    CHAT_REFUSED_UNASSIGNED = "chat_refused_unassigned"
    PATIENT_ASSIGNED = "patient_assigned"
    PATIENT_UNASSIGNED = "patient_unassigned"
    BUDGET_EXCEEDED = "budget_exceeded"
    # Week 2 multimodal ingestion. Details payload carries only
    # structural fields (document_id, doc_type, file_hash, latency_ms,
    # extraction_status). PHI-bearing extracted text is NEVER written
    # to the audit log — see HIPAA_COMPLIANCE.md and W2_ARCHITECTURE.md
    # §9.
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_UPLOAD_REFUSED = "document_upload_refused"
    DOCUMENT_EXTRACTION_STARTED = "document_extraction_started"
    DOCUMENT_EXTRACTION_COMPLETED = "document_extraction_completed"
    DOCUMENT_EXTRACTION_FAILED = "document_extraction_failed"
    EVIDENCE_RETRIEVAL = "evidence_retrieval"
    SUPERVISOR_ROUTING_DECISION = "supervisor_routing_decision"


def record(
    database_url: str,
    event_type: str,
    *,
    user_id: int | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    try:
        with connect(database_url) as conn:
            conn.execute(
                """INSERT INTO audit_log (user_id, event_type, ip_address, details)
                   VALUES (?, ?, ?, ?)""",
                (
                    user_id,
                    event_type,
                    ip_address,
                    json.dumps(details) if details else None,
                ),
            )
            conn.commit()
    except Exception:
        log.exception(
            "audit log write failed for event=%s user_id=%s", event_type, user_id
        )
