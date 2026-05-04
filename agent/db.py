"""SQLite database init and connection helpers.

v0 uses stdlib `sqlite3` with sync calls — fine for low-volume demo. Schema is
created on first run; idempotent. For production, swap to Postgres or use
Railway Volumes for persistence (Railway's filesystem is ephemeral by default,
which means each redeploy clears the SQLite DB).

Tables: users, audit_log, password_reset_tokens, patient_assignments,
daily_token_usage, documents, derived_observations.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
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
    -- Opt-in bypass of the MFA challenge for clearly-labeled
    -- synthetic-data demo accounts. NEVER set on a user that touches
    -- real ePHI. Defaults to 0 so existing accounts keep mandatory MFA.
    bypass_mfa INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    event_type TEXT NOT NULL,
    ip_address TEXT,
    details TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_reset_tokens_token_hash ON password_reset_tokens(token_hash);

CREATE TABLE IF NOT EXISTS patient_assignments (
    user_id INTEGER NOT NULL,
    patient_id TEXT NOT NULL,
    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, patient_id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_assignments_user_id ON patient_assignments(user_id);

CREATE TABLE IF NOT EXISTS daily_token_usage (
    user_id INTEGER NOT NULL,
    usage_date TEXT NOT NULL,  -- YYYY-MM-DD UTC
    tokens_used INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, usage_date),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_daily_usage_user_date ON daily_token_usage(user_id, usage_date);

-- Week 2: multimodal document ingestion.
-- documents holds the source-of-truth blob; derived_observations holds
-- the schema-validated facts extracted from it. Re-extraction replaces
-- rows in derived_observations without touching the original document.
-- See W2_ARCHITECTURE.md §3 for rationale.
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    doc_type TEXT NOT NULL,                    -- 'lab_pdf' | 'intake_form'
    file_blob BLOB NOT NULL,
    file_hash TEXT NOT NULL,                   -- SHA-256 hex of file_blob, for dedup
    content_type TEXT NOT NULL,
    uploaded_by_user_id INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    extraction_status TEXT NOT NULL DEFAULT 'pending',
    extraction_error TEXT,
    UNIQUE(patient_id, file_hash),
    FOREIGN KEY (uploaded_by_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_documents_patient ON documents(patient_id);
CREATE INDEX IF NOT EXISTS idx_documents_uploader ON documents(uploaded_by_user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(extraction_status);

CREATE TABLE IF NOT EXISTS derived_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    patient_id TEXT NOT NULL,                  -- denormalized for query speed
    source_id TEXT NOT NULL,                   -- e.g. 'lab-doc-42-glucose'
    schema_kind TEXT NOT NULL,                 -- 'lab_observation' | 'intake_field'
    payload_json TEXT NOT NULL,
    confidence REAL,
    page_number INTEGER,
    bbox_json TEXT,                            -- JSON {x0,y0,x1,y1} or NULL
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_derived_obs_patient ON derived_observations(patient_id);
CREATE INDEX IF NOT EXISTS idx_derived_obs_doc ON derived_observations(document_id);
CREATE INDEX IF NOT EXISTS idx_derived_obs_source_id ON derived_observations(source_id);
"""


def _path_from_url(database_url: str) -> Path:
    if database_url.startswith("sqlite:///"):
        return Path(database_url[len("sqlite:///") :])
    raise ValueError(f"Only sqlite:/// URLs are supported, got {database_url!r}")


def init_db(database_url: str) -> None:
    """Create tables if missing. Idempotent. Also runs lightweight
    column-level migrations for fields added after a DB was first
    created — required because CREATE TABLE IF NOT EXISTS is a no-op
    against an existing table even if columns are missing."""
    path = _path_from_url(database_url)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_url) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns that postdate the original schema. Each block is
    idempotent: it checks PRAGMA table_info and only ALTERs if the
    column is missing. Keeps the function safe to run on every cold
    start (which is what init_db does)."""
    user_cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }
    if "bypass_mfa" not in user_cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN bypass_mfa INTEGER NOT NULL DEFAULT 0"
        )


@contextmanager
def connect(database_url: str) -> Iterator[sqlite3.Connection]:
    path = _path_from_url(database_url)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()
