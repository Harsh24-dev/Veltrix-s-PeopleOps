import uuid
from datetime import date, datetime

from app.common.pii import mask_email
from app.db import connect, transaction
from app.identity import Requester
from app.tools import permissions
from app.tools.calendar import date_range, working_days

REFUSAL = "I can't share information about that employee."


class ToolError(Exception):
    pass


def get_leave_balance(requester: Requester, employee_id: str, leave_type: str | None = None):
    if not permissions.can_view_leave(requester, employee_id):
        raise ToolError(REFUSAL)
    conn = connect()
    try:
        query = "SELECT leave_type, balance_days FROM leave_balances WHERE employee_id = ?"
        params = [employee_id]
        if leave_type:
            query += " AND leave_type = ?"
            params.append(leave_type)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return {r["leave_type"]: r["balance_days"] for r in rows}


def list_leave_requests(requester: Requester, employee_id: str, status: str | None = None):
    if not permissions.can_view_leave(requester, employee_id):
        raise ToolError(REFUSAL)
    conn = connect()
    try:
        query = "SELECT * FROM leave_requests WHERE employee_id = ?"
        params = [employee_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_team_leave(requester: Requester, start_date: str, end_date: str):
    if requester.role != "manager":
        raise ToolError("Only managers can view team leave.")
    reports = permissions.direct_report_ids(requester.employee_id)
    if not reports:
        return []
    conn = connect()
    try:
        placeholders = ",".join("?" * len(reports))
        rows = conn.execute(
            f"""SELECT * FROM leave_requests
                WHERE employee_id IN ({placeholders})
                AND status IN ('pending', 'approved')
                AND NOT (end_date < ? OR start_date > ?)""",
            (*reports, start_date, end_date),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _overlaps_existing(conn, employee_id: str, start: date, end: date) -> bool:
    rows = conn.execute(
        """SELECT start_date, end_date FROM leave_requests
           WHERE employee_id = ? AND status IN ('pending', 'approved')""",
        (employee_id,),
    ).fetchall()
    wanted = set(date_range(start, end))
    for r in rows:
        existing = set(date_range(date.fromisoformat(r["start_date"]), date.fromisoformat(r["end_date"])))
        if wanted & existing:
            return True
    return False


def validate_apply(requester: Requester, leave_type: str, start: date, end: date, today: date) -> int:
    if leave_type not in ("annual", "sick"):
        raise ToolError("Leave type must be annual or sick.")
    if start.year != 2026 or end.year != 2026:
        raise ToolError("Leave must fall within the 2026 calendar year.")
    if start < today:
        raise ToolError("Start date must be today or later.")
    if end < start:
        raise ToolError("End date must be on or after the start date.")

    days = working_days(start, end, requester.region)
    if days == 0:
        raise ToolError("That range has no working days.")

    conn = connect()
    try:
        balance = conn.execute(
            "SELECT balance_days FROM leave_balances WHERE employee_id = ? AND leave_type = ?",
            (requester.employee_id, leave_type),
        ).fetchone()
        if balance is None or days > balance["balance_days"]:
            raise ToolError("That exceeds your available balance.")
        if _overlaps_existing(conn, requester.employee_id, start, end):
            raise ToolError("That overlaps an existing request.")
    finally:
        conn.close()
    return days


def apply_leave(requester: Requester, leave_type: str, start: date, end: date, today: date) -> dict:
    days = validate_apply(requester, leave_type, start, end, today)
    request_id = str(uuid.uuid4())
    with transaction() as conn:
        conn.execute(
            """INSERT INTO leave_requests
               (request_id, employee_id, leave_type, start_date, end_date, working_days, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (request_id, requester.employee_id, leave_type, start.isoformat(),
             end.isoformat(), days, datetime.utcnow().isoformat()),
        )
        conn.execute(
            "UPDATE leave_balances SET balance_days = balance_days - ? WHERE employee_id = ? AND leave_type = ?",
            (days, requester.employee_id, leave_type),
        )
    return {"request_id": request_id, "working_days": days}


def cancel_leave(requester: Requester, request_id: str, today: date) -> dict:
    with transaction() as conn:
        row = conn.execute(
            "SELECT * FROM leave_requests WHERE request_id = ? AND employee_id = ?",
            (request_id, requester.employee_id),
        ).fetchone()
        if row is None:
            raise ToolError("No such request.")
        if row["status"] not in ("pending", "approved"):
            raise ToolError("That request cannot be cancelled.")
        if date.fromisoformat(row["start_date"]) <= today:
            raise ToolError("Only future requests can be cancelled.")
        conn.execute("UPDATE leave_requests SET status = 'cancelled' WHERE request_id = ?", (request_id,))
        conn.execute(
            "UPDATE leave_balances SET balance_days = balance_days + ? WHERE employee_id = ? AND leave_type = ?",
            (row["working_days"], requester.employee_id, row["leave_type"]),
        )
    return {"request_id": request_id, "restored_days": row["working_days"]}
