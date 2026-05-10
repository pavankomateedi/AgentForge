"""Tests for /documents/list, /documents/{id}/blob, /documents/{id}/derived."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from agent import documents as doc_storage


def _upload_one(client: TestClient, *, content: bytes = b"%PDF-1.4\n%dummy"):
    return client.post(
        "/documents/upload",
        data={"patient_id": "demo-001", "doc_type": "lab_pdf"},
        files={"file": ("rep.pdf", io.BytesIO(content), "application/pdf")},
    )


def test_list_requires_auth(client: TestClient):
    res = client.get("/documents/list?patient_id=demo-001")
    assert res.status_code == 401


def test_list_returns_uploaded_docs(authed_client: TestClient):
    _upload_one(authed_client)
    res = authed_client.get("/documents/list?patient_id=demo-001")
    assert res.status_code == 200
    body = res.json()
    assert body["patient_id"] == "demo-001"
    assert len(body["documents"]) == 1
    d = body["documents"][0]
    assert d["doc_type"] == "lab_pdf"
    assert d["extraction_status"] == "pending"
    assert d["uploaded_at"]
    # File hash should be truncated for display.
    assert d["file_hash"].endswith("...")


def test_list_refused_when_unassigned(
    authed_client: TestClient, config, seed_user_mfa
):
    from agent import rbac

    rbac.revoke_assignment(
        config.database_url,
        user_id=seed_user_mfa["user"].id,
        patient_id="demo-001",
    )
    res = authed_client.get("/documents/list?patient_id=demo-001")
    assert res.status_code == 403


def test_blob_returns_original_bytes(authed_client: TestClient):
    payload = b"%PDF-1.4\n%blob test"
    upload_res = _upload_one(authed_client, content=payload)
    doc_id = upload_res.json()["document_id"]

    res = authed_client.get(f"/documents/{doc_id}/blob")
    assert res.status_code == 200
    assert res.content == payload
    assert res.headers["content-type"] == "application/pdf"


def test_blob_404_for_missing_doc(authed_client: TestClient):
    res = authed_client.get("/documents/99999/blob")
    assert res.status_code == 404


def test_blob_refused_for_other_patient(
    authed_client: TestClient, config, seed_user_mfa
):
    """Upload doc as assigned user, then revoke their assignment to that
    patient. Blob fetch must be refused."""
    from agent import rbac

    upload_res = _upload_one(authed_client)
    doc_id = upload_res.json()["document_id"]

    rbac.revoke_assignment(
        config.database_url,
        user_id=seed_user_mfa["user"].id,
        patient_id="demo-001",
    )
    res = authed_client.get(f"/documents/{doc_id}/blob")
    assert res.status_code == 403


def test_derived_returns_extracted_rows(
    authed_client: TestClient, config, seed_user_mfa
):
    from datetime import date

    from agent.schemas.citation import BBox, Citation
    from agent.schemas.lab import LabReport, LabValue

    upload_res = _upload_one(authed_client)
    doc_id = upload_res.json()["document_id"]
    doc_storage.persist_lab_report(
        config.database_url,
        LabReport(
            patient_id="demo-001",
            document_id=doc_id,
            collection_date=date(2026, 1, 1),
            values=[
                LabValue(
                    test_name="HbA1c",
                    value=8.5,
                    unit="%",
                    collection_date=date(2026, 1, 1),
                    citation=Citation(
                        source_type="lab_pdf",
                        source_id=f"demo-001-doc-{doc_id}",
                        page_or_section="page-1",
                        field_or_chunk_id="p1-l000",
                        quote_or_value="HbA1c 8.5%",
                        bbox=BBox(x0=10, y0=20, x1=100, y1=40),
                    ),
                    confidence=0.9,
                )
            ],
        ),
    )

    res = authed_client.get(f"/documents/{doc_id}/derived")
    assert res.status_code == 200
    body = res.json()
    assert body["document_id"] == doc_id
    assert len(body["rows"]) == 1
    assert body["rows"][0]["payload"]["test_name"] == "HbA1c"
    assert body["rows"][0]["bbox"]["x0"] == 10


# ---- Soft-delete endpoints ----


def test_delete_document_requires_auth(client: TestClient):
    """Unauthenticated DELETE returns 401, not a 200 or a server error."""
    res = client.delete("/documents/1")
    assert res.status_code == 401


def test_delete_document_removes_from_list(authed_client: TestClient):
    upload_res = _upload_one(authed_client)
    doc_id = upload_res.json()["document_id"]

    delete_res = authed_client.delete(f"/documents/{doc_id}")
    assert delete_res.status_code == 200
    assert delete_res.json() == {"document_id": doc_id, "deleted": True}

    listing = authed_client.get("/documents/list?patient_id=demo-001").json()
    assert listing["documents"] == []


def test_delete_document_404_for_missing(authed_client: TestClient):
    res = authed_client.delete("/documents/99999")
    assert res.status_code == 404


def test_delete_document_idempotent_after_first_call(authed_client: TestClient):
    """Second DELETE is a 404 (the row is already invisible to active
    reads). Confirms the endpoint doesn't accidentally restore-then-
    re-delete or otherwise mutate the row."""
    upload_res = _upload_one(authed_client)
    doc_id = upload_res.json()["document_id"]
    first = authed_client.delete(f"/documents/{doc_id}")
    second = authed_client.delete(f"/documents/{doc_id}")
    assert first.status_code == 200
    assert second.status_code == 404


def test_delete_document_refused_for_other_patient(
    authed_client: TestClient, config, seed_user_mfa
):
    from agent import rbac

    upload_res = _upload_one(authed_client)
    doc_id = upload_res.json()["document_id"]

    rbac.revoke_assignment(
        config.database_url,
        user_id=seed_user_mfa["user"].id,
        patient_id="demo-001",
    )
    res = authed_client.delete(f"/documents/{doc_id}")
    assert res.status_code == 403


def test_delete_document_writes_audit_event(
    authed_client: TestClient, config, seed_user_mfa
):
    """DOCUMENT_DELETED event lands in audit_log with structural-only
    details — patient_id, doc_type, previous_status, document_id. No
    raw extracted text or other PHI."""
    import json

    from agent.db import connect

    upload_res = _upload_one(authed_client)
    doc_id = upload_res.json()["document_id"]
    authed_client.delete(f"/documents/{doc_id}")

    with connect(config.database_url) as conn:
        rows = conn.execute(
            "SELECT event_type, details FROM audit_log "
            "WHERE event_type = 'document_deleted' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchall()
    assert len(rows) == 1
    details = json.loads(rows[0]["details"])
    assert details["document_id"] == doc_id
    assert details["patient_id"] == "demo-001"
    assert details["doc_type"] == "lab_pdf"
    assert "previous_status" in details


def test_delete_document_then_reupload_is_fresh_row(
    authed_client: TestClient,
):
    """Soft-delete + re-upload of the same bytes should produce a NEW
    document_id, not a dedup hit. This is the 'reset chart and
    re-demo' behavior the user asked for."""
    upload_res = _upload_one(authed_client)
    doc_id = upload_res.json()["document_id"]
    authed_client.delete(f"/documents/{doc_id}")
    second = _upload_one(authed_client)
    assert second.status_code == 200
    body = second.json()
    assert body["document_id"] != doc_id
    assert body["deduplicated"] is False


def test_reset_patient_chart_bulk_delete(authed_client: TestClient):
    _upload_one(authed_client, content=b"%PDF-1.4\n%a")
    _upload_one(authed_client, content=b"%PDF-1.4\n%b")
    _upload_one(authed_client, content=b"%PDF-1.4\n%c")

    res = authed_client.delete("/patients/demo-001/documents")
    assert res.status_code == 200
    body = res.json()
    assert body["patient_id"] == "demo-001"
    assert body["deleted_count"] == 3

    listing = authed_client.get("/documents/list?patient_id=demo-001").json()
    assert listing["documents"] == []


def test_reset_patient_chart_requires_auth(client: TestClient):
    res = client.delete("/patients/demo-001/documents")
    assert res.status_code == 401


def test_reset_patient_chart_refused_for_unassigned(
    authed_client: TestClient, config, seed_user_mfa
):
    from agent import rbac

    rbac.revoke_assignment(
        config.database_url,
        user_id=seed_user_mfa["user"].id,
        patient_id="demo-001",
    )
    res = authed_client.delete("/patients/demo-001/documents")
    assert res.status_code == 403


def test_reset_patient_chart_writes_audit_event(
    authed_client: TestClient, config
):
    import json

    from agent.db import connect

    _upload_one(authed_client, content=b"%PDF-1.4\n%audit-a")
    _upload_one(authed_client, content=b"%PDF-1.4\n%audit-b")
    authed_client.delete("/patients/demo-001/documents")

    with connect(config.database_url) as conn:
        rows = conn.execute(
            "SELECT event_type, details FROM audit_log "
            "WHERE event_type = 'patient_chart_reset' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchall()
    assert len(rows) == 1
    details = json.loads(rows[0]["details"])
    assert details["patient_id"] == "demo-001"
    assert details["deleted_count"] == 2


def test_reset_patient_chart_count_zero_when_empty(authed_client: TestClient):
    """Reset on an empty chart still succeeds and returns deleted_count=0
    (lets the UI button stay unconditionally available)."""
    res = authed_client.delete("/patients/demo-001/documents")
    assert res.status_code == 200
    assert res.json()["deleted_count"] == 0
