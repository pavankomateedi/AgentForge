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
        # Soft-delete columns added in the chart-reset migration.
        "deleted_at", "deleted_by_user_id",
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


def test_documents_unique_allows_same_hash_after_soft_delete(config, seed_user):
    """The partial unique index excludes soft-deleted rows, so the same
    bytes for the same patient can be re-inserted as a fresh row after
    the prior one is marked deleted. This is the chart-reset contract."""
    with connect(config.database_url) as conn:
        # Insert + soft-delete the first row.
        conn.execute(
            """INSERT INTO documents
               (patient_id, doc_type, file_blob, file_hash,
                content_type, uploaded_by_user_id, extraction_status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            ("demo-001", "lab_pdf", b"x", "h" * 64, "application/pdf", seed_user.id),
        )
        conn.execute(
            "UPDATE documents SET deleted_at = datetime('now') "
            "WHERE patient_id = ? AND file_hash = ?",
            ("demo-001", "h" * 64),
        )
        # Same patient + same hash should now be allowed (deleted row
        # falls outside the partial unique index).
        conn.execute(
            """INSERT INTO documents
               (patient_id, doc_type, file_blob, file_hash,
                content_type, uploaded_by_user_id, extraction_status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            ("demo-001", "lab_pdf", b"x", "h" * 64, "application/pdf", seed_user.id),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT id, deleted_at FROM documents "
            "WHERE patient_id = ? AND file_hash = ? ORDER BY id",
            ("demo-001", "h" * 64),
        ).fetchall()
    assert len(rows) == 2
    assert rows[0]["deleted_at"] is not None
    assert rows[1]["deleted_at"] is None


def test_legacy_documents_table_migrates_to_partial_index(tmp_path):
    """Simulate a database created BEFORE the soft-delete migration: it
    has the legacy table-level UNIQUE(patient_id, file_hash) constraint
    and no deleted_at column. _migrate must rebuild the table, copy
    rows preserving ids, drop the table-level UNIQUE, and create the
    partial index."""
    import sqlite3

    from agent.db import _migrate

    db_path = tmp_path / "legacy.db"
    legacy_conn = sqlite3.connect(db_path)
    legacy_conn.row_factory = sqlite3.Row
    legacy_conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'physician',
            is_active INTEGER NOT NULL DEFAULT 1,
            failed_login_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT,
            totp_secret TEXT,
            totp_enrolled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            file_blob BLOB NOT NULL,
            file_hash TEXT NOT NULL,
            content_type TEXT NOT NULL,
            uploaded_by_user_id INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
            extraction_status TEXT NOT NULL DEFAULT 'pending',
            extraction_error TEXT,
            UNIQUE(patient_id, file_hash),
            FOREIGN KEY (uploaded_by_user_id) REFERENCES users(id)
        );
        INSERT INTO users (id, username, email, password_hash) VALUES
            (1, 'legacy', 'legacy@example.com', 'x');
        """
    )
    legacy_conn.execute(
        """INSERT INTO documents
            (id, patient_id, doc_type, file_blob, file_hash,
             content_type, uploaded_by_user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (10, "demo-001", "lab_pdf", b"\x00", "a" * 64, "application/pdf", 1),
    )
    legacy_conn.execute(
        """INSERT INTO documents
            (id, patient_id, doc_type, file_blob, file_hash,
             content_type, uploaded_by_user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (11, "demo-002", "lab_pdf", b"\x01", "b" * 64, "application/pdf", 1),
    )
    legacy_conn.commit()

    # Sanity: legacy schema is in place — table-level UNIQUE present,
    # deleted_at column absent.
    sql = legacy_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents'"
    ).fetchone()["sql"]
    assert "UNIQUE(patient_id, file_hash)" in sql
    cols = {
        r["name"]
        for r in legacy_conn.execute("PRAGMA table_info(documents)").fetchall()
    }
    assert "deleted_at" not in cols

    # Run the migration.
    _migrate(legacy_conn)
    legacy_conn.commit()

    # Post-migration: deleted_at exists, partial unique index exists,
    # table-level UNIQUE is gone, and pre-existing row ids are preserved.
    cols_after = {
        r["name"]
        for r in legacy_conn.execute("PRAGMA table_info(documents)").fetchall()
    }
    assert "deleted_at" in cols_after
    assert "deleted_by_user_id" in cols_after
    has_partial_idx = legacy_conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' "
        "AND name='idx_documents_unique_active'"
    ).fetchone()
    assert has_partial_idx is not None
    sql_after = legacy_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents'"
    ).fetchone()["sql"]
    assert "UNIQUE(patient_id, file_hash)" not in sql_after
    ids = [r["id"] for r in legacy_conn.execute(
        "SELECT id FROM documents ORDER BY id"
    ).fetchall()]
    assert ids == [10, 11]

    # Migration is idempotent on a second pass.
    _migrate(legacy_conn)
    legacy_conn.commit()
    legacy_conn.close()


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
