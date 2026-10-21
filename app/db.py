import sqlite3
from contextlib import contextmanager

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    file TEXT NOT NULL,
    title TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    regions TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    access_level TEXT NOT NULL,
    authority_rank INTEGER NOT NULL,
    has_headings INTEGER NOT NULL DEFAULT 1,
    page_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id),
    ord INTEGER NOT NULL,
    heading_path TEXT,
    page INTEGER,
    text TEXT NOT NULL,
    context_prefix TEXT NOT NULL,
    token_len INTEGER NOT NULL,
    embedding BLOB
);

CREATE TABLE IF NOT EXISTS holidays (
    region TEXT NOT NULL,
    date TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    source_doc_id TEXT,
    PRIMARY KEY (region, date, name)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proposals (
    session_id TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    args TEXT NOT NULL,
    working_days INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL,
    finished_at TEXT
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_settings().db_path, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate() -> None:
    with transaction() as conn:
        conn.executescript(SCHEMA)
