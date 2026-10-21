import re
from dataclasses import dataclass
from datetime import datetime

from app.db import connect, transaction

_EMP_ID = re.compile(r"[Ee]\d+")


@dataclass
class Requester:
    employee_id: str
    full_name: str
    email: str
    phone: str
    region: str
    role: str
    manager_id: str | None


def load_requester(employee_id: str) -> Requester | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return Requester(
        employee_id=row["employee_id"],
        full_name=row["full_name"],
        email=row["email"],
        phone=row["phone"],
        region=row["region"],
        role=row["role"],
        manager_id=row["manager_id"],
    )


def resolve_employee(target: str) -> str | None:
    """Turn a message reference (an employee ID like 'E1005' or an exact full
    name) into an employee_id. Returns None if it is not an unambiguous match,
    so the caller gives the same fixed refusal whether the person exists or not."""
    target = (target or "").strip()
    if not target:
        return None
    conn = connect()
    try:
        if _EMP_ID.fullmatch(target):
            row = conn.execute(
                "SELECT employee_id FROM employees WHERE employee_id = ?", (target.upper(),)
            ).fetchone()
            return row["employee_id"] if row else None
        rows = conn.execute(
            "SELECT employee_id FROM employees WHERE lower(full_name) = ?", (target.lower(),)
        ).fetchall()
        return rows[0]["employee_id"] if len(rows) == 1 else None
    finally:
        conn.close()


def employee_name(employee_id: str) -> str | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT full_name FROM employees WHERE employee_id = ?", (employee_id,)
        ).fetchone()
    finally:
        conn.close()
    return row["full_name"] if row else None


def bind_session(session_id: str, employee_id: str) -> bool:
    """Bind a session to the first employee that used it. Returns False on a
    later mismatch, which the caller turns into a 403."""
    with transaction() as conn:
        row = conn.execute(
            "SELECT employee_id FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO sessions (session_id, employee_id, created_at) VALUES (?, ?, ?)",
                (session_id, employee_id, datetime.utcnow().isoformat()),
            )
            return True
        return row["employee_id"] == employee_id
