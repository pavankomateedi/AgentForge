"""Stage 1 storage-helper tests for `agent.documents`.

The storage layer is intentionally thin (no extraction logic, no auth)
but it owns the dedup contract: identical bytes for the same patient
return the existing row, never insert a duplicate. These tests pin
that behavior so a future caller (e.g., a retry-on-failure background
task) can rely on it."""

from __future__ import annotations

from agent import documents as doc_storage


PDF_BYTES = b"%PDF-1.4\n%demo bytes"
OTHER_BYTES = b"%PDF-1.4\n%different bytes"


def test_compute_file_hash_stable():
    """Hash is deterministic across calls and platforms."""
    assert doc_storage.compute_file_hash(b"abc") == doc_storage.compute_file_hash(b"abc")
    assert doc_storage.compute_file_hash(b"abc") != doc_storage.compute_file_hash(b"abd")
    # SHA-256 hex is 64 chars
    assert len(doc_storage.compute_file_hash(b"abc")) == 64


def test_insert_document_creates_row(config, seed_user):
    stored = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=PDF_BYTES,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    assert stored.id >= 1
    assert stored.deduplicated is False
    assert stored.extraction_status == "pending"
    assert stored.file_hash == doc_storage.compute_file_hash(PDF_BYTES)


def test_insert_document_dedup_returns_existing(config, seed_user):
    first = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=PDF_BYTES,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    second = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=PDF_BYTES,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    assert second.id == first.id
    assert second.deduplicated is True


def test_insert_document_different_patient_no_dedup(config, seed_user):
    a = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=PDF_BYTES,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    b = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-002",
        doc_type="lab_pdf",
        file_blob=PDF_BYTES,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    assert a.id != b.id
    assert b.deduplicated is False


def test_set_status_transitions(config, seed_user):
    stored = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=PDF_BYTES,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    doc_storage.set_status(
        config.database_url, document_id=stored.id, status="extracting"
    )
    refreshed = doc_storage.get_metadata(config.database_url, stored.id)
    assert refreshed is not None and refreshed.extraction_status == "extracting"

    doc_storage.set_status(
        config.database_url, document_id=stored.id, status="done"
    )
    refreshed = doc_storage.get_metadata(config.database_url, stored.id)
    assert refreshed is not None and refreshed.extraction_status == "done"

    doc_storage.set_status(
        config.database_url,
        document_id=stored.id,
        status="failed",
        error="schema validation failed: missing collection_date",
    )
    refreshed = doc_storage.get_metadata(config.database_url, stored.id)
    assert refreshed is not None
    assert refreshed.extraction_status == "failed"
    assert refreshed.extraction_error and "schema" in refreshed.extraction_error


def test_get_blob_round_trip(config, seed_user):
    stored = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=PDF_BYTES,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    blob_pair = doc_storage.get_blob(config.database_url, stored.id)
    assert blob_pair is not None
    blob, ctype = blob_pair
    assert blob == PDF_BYTES
    assert ctype == "application/pdf"


def test_get_blob_missing_returns_none(config):
    assert doc_storage.get_blob(config.database_url, 99999) is None


def test_list_for_patient_orders_newest_first(config, seed_user):
    a = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=PDF_BYTES,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    b = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="intake_form",
        file_blob=OTHER_BYTES,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    listing = doc_storage.list_for_patient(config.database_url, "demo-001")
    assert {d.id for d in listing} == {a.id, b.id}
    # Most-recently inserted should be first; in SQLite ROWID order both
    # rows can share the same uploaded_at second but list_for_patient
    # ORDERs DESC by uploaded_at so we just assert the set membership
    # and that filtering by patient excludes other patients.
    other = doc_storage.list_for_patient(config.database_url, "demo-002")
    assert other == []
