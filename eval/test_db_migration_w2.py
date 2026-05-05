"""Stage 1 DB migration tests.

Confirms `init_db` creates the new `documents` and
`derived_observations` tables, that running it twice is idempotent
(important because every cold start calls it), and that the FK +
UNIQUE constraints behave as documented.
"""

from __future__ import annotations

from agent.db import connect, init_db


def _table_columns(database_url: str, table: str) -> set[str]:
    with connect(database_url) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def _list_tables(database_url: str) -> set[str]:
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {r["name"] for r in rows}


def test_documents_table_created(config):
    tables = _list_tables(config.database_url)
    assert "documents" in tables
    cols = _table_columns(config.database_url, "documents")
    assert {
        "id", "patient_id", "doc_type", "file_blob", "file_hash",
        "content_type", "uploaded_by_user_id", "uploaded_at",
        "extraction_status", "extraction_error",
    }.issubset(cols)


def test_derived_observations_table_created(config):
    tables = _list_tables(config.database_url)
    assert "derived_observations" in tables
    cols = _table_columns(config.database_url, "derived_observations")
    assert {
        "id", "document_id", "patient_id", "source_id", "schema_kind",
        "payload_json", "confidence", "page_number", "bbox_json",
        "created_at",
    }.issubset(cols)


def test_init_db_idempotent(config):
    """Calling init_db twice must not error and must not duplicate
    tables. The Week 1 migration helper is already tested for users;
    this confirms the W2 additions inherit the same idempotent
    contract."""
    init_db(config.database_url)
    init_db(config.database_url)
    init_db(config.database_url)
    tables = _list_tables(config.database_url)
    assert "documents" in tables
    assert "derived_observations" in tables


def test_documents_unique_per_patient_hash(config, seed_user):
    """The (patient_id, file_hash) UNIQUE constraint is the
    deduplication primitive — re-uploading identical bytes for the same
    patient should hit the storage helper's dedup branch, never raise
    IntegrityError to the caller."""
    import sqlite3

    with connect(config.database_url) as conn:
        conn.execute(
            """INSERT INTO documents
               (patient_id, doc_type, file_blob, file_hash,
                content_type, uploaded_by_user_id, extraction_status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            ("demo-001", "lab_pdf", b"x", "h" * 64, "application/pdf", seed_user.id),
        )
        conn.commit()
        try:
            conn.execute(
                """INSERT INTO documents
                   (patient_id, doc_type, file_blob, file_hash,
                    content_type, uploaded_by_user_id, extraction_status)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                ("demo-001", "lab_pdf", b"y", "h" * 64, "application/pdf", seed_user.id),
            )
            conn.commit()
            raised = False
        except sqlite3.IntegrityError:
            raised = True
    assert raised, "Duplicate (patient_id, file_hash) should be rejected at the DB level"


def test_documents_unique_allows_same_hash_different_patient(config, seed_user):
    """Same bytes for two different patients is legitimate (e.g., a
    standardized intake form template) — the constraint is per-patient,
    not global."""
    with connect(config.database_url) as conn:
        conn.execute(
            """INSERT INTO documents
               (patient_id, doc_type, file_blob, file_hash,
                content_type, uploaded_by_user_id, extraction_status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            ("demo-001", "lab_pdf", b"x", "h" * 64, "application/pdf", seed_user.id),
        )
        conn.execute(
            """INSERT INTO documents
               (patient_id, doc_type, file_blob, file_hash,
                content_type, uploaded_by_user_id, extraction_status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            ("demo-002", "lab_pdf", b"x", "h" * 64, "application/pdf", seed_user.id),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT patient_id FROM documents WHERE file_hash = ?", ("h" * 64,)
        ).fetchall()
    assert {r["patient_id"] for r in rows} == {"demo-001", "demo-002"}


def test_derived_observations_fk_cascade(config, seed_user):
    """Deleting a document should cascade to its derived_observations —
    re-extraction replaces rows; document removal cleans up history."""
    with connect(config.database_url) as conn:
        cur = conn.execute(
            """INSERT INTO documents
               (patient_id, doc_type, file_blob, file_hash,
                content_type, uploaded_by_user_id, extraction_status)
               VALUES (?, ?, ?, ?, ?, ?, 'done')""",
            ("demo-001", "lab_pdf", b"x", "h" * 64, "application/pdf", seed_user.id),
        )
        doc_id = cur.lastrowid
        conn.execute(
            """INSERT INTO derived_observations
               (document_id, patient_id, source_id, schema_kind, payload_json)
               VALUES (?, ?, ?, ?, ?)""",
            (doc_id, "demo-001", "lab-doc-1-glucose", "lab_observation", "{}"),
        )
        conn.commit()
        before = conn.execute(
            "SELECT COUNT(*) AS c FROM derived_observations"
        ).fetchone()["c"]
        assert before == 1
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        after = conn.execute(
            "SELECT COUNT(*) AS c FROM derived_observations"
        ).fetchone()["c"]
    assert after == 0
