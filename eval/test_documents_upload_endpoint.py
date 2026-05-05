"""Stage 1 upload-endpoint tests for POST /documents/upload.

Pins the contract:
  - 401 without an authenticated session
  - 403 when the caller isn't assigned to the patient
  - 400 for invalid doc_type / content_type / empty / oversized
  - 200 with status=pending on success, audited as DOCUMENT_UPLOADED
  - 200 deduplicated=true on identical re-upload
  - DOCUMENT_UPLOAD_REFUSED on every refusal path
"""

from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient

from agent import audit, documents as doc_storage, rbac
from agent.db import connect


def _audit_events(database_url: str, event_type: str) -> list[dict]:
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE event_type = ? ORDER BY id",
            (event_type,),
        ).fetchall()
    return [
        {
            "user_id": r["user_id"],
            "details": json.loads(r["details"]) if r["details"] else None,
        }
        for r in rows
    ]


def _upload(
    client: TestClient,
    *,
    patient_id: str = "demo-001",
    doc_type: str = "lab_pdf",
    content: bytes = b"%PDF-1.4\n%dummy",
    content_type: str = "application/pdf",
    filename: str = "report.pdf",
):
    return client.post(
        "/documents/upload",
        data={"patient_id": patient_id, "doc_type": doc_type},
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


# ---- Auth gate ----


def test_upload_requires_auth(client: TestClient):
    res = _upload(client)
    assert res.status_code == 401


# ---- Happy path ----


def test_upload_lab_pdf_success(authed_client: TestClient, config):
    res = _upload(authed_client)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "pending"
    assert body["deduplicated"] is False
    assert body["document_id"] >= 1

    stored = doc_storage.get_metadata(config.database_url, body["document_id"])
    assert stored is not None
    assert stored.patient_id == "demo-001"
    assert stored.doc_type == "lab_pdf"
    assert stored.content_type == "application/pdf"

    events = _audit_events(config.database_url, audit.AuditEvent.DOCUMENT_UPLOADED)
    assert len(events) == 1
    details = events[0]["details"]
    assert details["patient_id"] == "demo-001"
    assert details["doc_type"] == "lab_pdf"
    assert details["document_id"] == body["document_id"]
    assert len(details["file_hash"]) == 64
    assert details["deduplicated"] is False
    # PHI-bearing content is never put in the audit details payload —
    # only structural fields. file_bytes is a count, not the content.
    assert "file_blob" not in details
    assert details["file_bytes"] > 0


def test_upload_intake_form_jpeg_success(authed_client: TestClient):
    res = _upload(
        authed_client,
        doc_type="intake_form",
        content=b"\xff\xd8\xff\xe0fake-jpeg",
        content_type="image/jpeg",
        filename="intake.jpg",
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "pending"


def test_upload_dedup_returns_existing(authed_client: TestClient):
    first = _upload(authed_client)
    assert first.status_code == 200
    second = _upload(authed_client)
    assert second.status_code == 200
    assert second.json()["document_id"] == first.json()["document_id"]
    assert second.json()["deduplicated"] is True


# ---- RBAC: assignment gate ----


def test_upload_refused_when_unassigned(authed_client: TestClient, config, seed_user_mfa):
    """Revoke the assignment between login and upload — expect 403 +
    DOCUMENT_UPLOAD_REFUSED audit row."""
    rbac.revoke_assignment(
        config.database_url,
        user_id=seed_user_mfa["user"].id,
        patient_id="demo-001",
    )
    res = _upload(authed_client, patient_id="demo-001")
    assert res.status_code == 403
    refusals = _audit_events(
        config.database_url, audit.AuditEvent.DOCUMENT_UPLOAD_REFUSED
    )
    assert any(e["details"]["reason"] == "unassigned" for e in refusals)


# ---- 400 paths ----


def test_upload_rejects_bad_doc_type(authed_client: TestClient, config):
    res = _upload(authed_client, doc_type="referral_fax")
    assert res.status_code == 400
    refusals = _audit_events(
        config.database_url, audit.AuditEvent.DOCUMENT_UPLOAD_REFUSED
    )
    assert any(e["details"]["reason"] == "invalid_doc_type" for e in refusals)


def test_upload_rejects_lab_pdf_with_image_content_type(
    authed_client: TestClient, config
):
    res = _upload(
        authed_client,
        doc_type="lab_pdf",
        content=b"\xff\xd8\xff\xe0fake-jpeg",
        content_type="image/jpeg",
        filename="not-a-pdf.jpg",
    )
    assert res.status_code == 400
    refusals = _audit_events(
        config.database_url, audit.AuditEvent.DOCUMENT_UPLOAD_REFUSED
    )
    assert any(e["details"]["reason"] == "invalid_content_type" for e in refusals)


def test_upload_rejects_intake_form_with_video(authed_client: TestClient):
    res = _upload(
        authed_client,
        doc_type="intake_form",
        content=b"video-bytes",
        content_type="video/mp4",
        filename="intake.mp4",
    )
    assert res.status_code == 400


def test_upload_rejects_empty_file(authed_client: TestClient, config):
    res = _upload(authed_client, content=b"")
    assert res.status_code == 400
    refusals = _audit_events(
        config.database_url, audit.AuditEvent.DOCUMENT_UPLOAD_REFUSED
    )
    assert any(e["details"]["reason"] == "empty_file" for e in refusals)


def test_upload_rejects_oversize(authed_client: TestClient, config):
    """Configured cap is 10 MB. Send 10 MB + 1 byte to trip the limit."""
    from agent.main import MAX_UPLOAD_BYTES

    too_big = b"%PDF-1.4\n" + (b"x" * (MAX_UPLOAD_BYTES + 1))
    res = _upload(authed_client, content=too_big)
    assert res.status_code == 400
    refusals = _audit_events(
        config.database_url, audit.AuditEvent.DOCUMENT_UPLOAD_REFUSED
    )
    assert any(e["details"]["reason"] == "too_large" for e in refusals)


def test_upload_does_not_log_phi_to_audit(authed_client: TestClient, config):
    """The audit details must contain structural fields only — never the
    file content, never the patient name. This pins the `no_phi_in_logs`
    rubric category for Stage 4."""
    phi_bearing_content = b"PATIENT NAME: Margaret Hayes DOB: 1954-08-12 MRN: 88421"
    res = _upload(
        authed_client,
        content=b"%PDF-1.4\n" + phi_bearing_content,
    )
    assert res.status_code == 200
    events = _audit_events(config.database_url, audit.AuditEvent.DOCUMENT_UPLOADED)
    rendered = json.dumps(events)
    assert "Margaret" not in rendered
    assert "Hayes" not in rendered
    assert "88421" not in rendered
    assert "1954-08-12" not in rendered
