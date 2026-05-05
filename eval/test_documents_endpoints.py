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
