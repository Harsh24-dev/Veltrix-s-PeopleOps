import sqlite3

import pytest

from app.config import get_settings
from app.db import migrate
from app.retrieval import store

# Seed data: E1 (employee) and E3 (employee) both report to E2 (manager).
# E9 is HR. E4 is an employee under a different manager (E5).
_EMPLOYEES = [
    ("E1", "Asha Rao", "asha@veltrix.example", "+91 9000000001", "IN", "2020-01-01", "L3", "employee", "E2"),
    ("E2", "Ravi Menon", "ravi@veltrix.example", "+91 9000000002", "IN", "2018-01-01", "L5", "manager", None),
    ("E3", "Chen Li", "chen@veltrix.example", "+91 9000000003", "IN", "2021-01-01", "L3", "employee", "E2"),
    ("E4", "Mia Gomez", "mia@veltrix.example", "+91 9000000004", "US", "2022-01-01", "L3", "employee", "E5"),
    ("E5", "Tom Park", "tom@veltrix.example", "+91 9000000005", "US", "2017-01-01", "L5", "manager", None),
    ("E9", "Nina Shah", "nina@veltrix.example", "+91 9000000009", "IN", "2016-01-01", "L6", "hr", None),
]
_BALANCES = [("E1", "annual", 10.0), ("E1", "sick", 5.0), ("E3", "annual", 8.0)]


def _seed(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS employees (
            employee_id TEXT PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT,
            region TEXT, join_date TEXT, level TEXT, role TEXT, manager_id TEXT);
        CREATE TABLE IF NOT EXISTS leave_balances (
            employee_id TEXT, leave_type TEXT, balance_days REAL,
            PRIMARY KEY (employee_id, leave_type));
        CREATE TABLE IF NOT EXISTS leave_requests (
            request_id TEXT PRIMARY KEY, employee_id TEXT, leave_type TEXT,
            start_date TEXT, end_date TEXT, working_days INTEGER, status TEXT, created_at TEXT);
        """
    )
    conn.executemany("INSERT INTO employees VALUES (?,?,?,?,?,?,?,?,?)", _EMPLOYEES)
    conn.executemany("INSERT INTO leave_balances VALUES (?,?,?)", _BALANCES)
    conn.commit()
    conn.close()


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    """A fresh SQLite DB seeded with a few employees, and no LLM key so the
    service uses its deterministic fallbacks."""
    db = tmp_path / "veltrix.db"
    monkeypatch.setenv("DB_PATH", str(db))
    monkeypatch.setenv("APP_TODAY", "2026-10-19")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()
    migrate()          # creates the new tables (holidays, sessions, proposals, ...)
    _seed(str(db))     # creates + fills the existing tables (employees, balances)
    store.clear_cache()
    yield db
    get_settings.cache_clear()
    store.clear_cache()
