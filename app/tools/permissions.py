from app.db import connect
from app.identity import Requester


def direct_report_ids(manager_id: str) -> set[str]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT employee_id FROM employees WHERE manager_id = ?", (manager_id,)
        ).fetchall()
    finally:
        conn.close()
    return {r["employee_id"] for r in rows}


def can_view_leave(requester: Requester, target_id: str) -> bool:
    if target_id == requester.employee_id:
        return True
    if requester.role == "hr":
        return True
    if requester.role == "manager":
        return target_id in direct_report_ids(requester.employee_id)
    return False
