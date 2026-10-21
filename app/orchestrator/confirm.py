import json

from app.db import connect, transaction


def save(session_id: str, tool: str, args: dict, working_days: int) -> None:
    from datetime import datetime

    with transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO proposals (session_id, tool, args, working_days, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, tool, json.dumps(args), working_days, datetime.utcnow().isoformat()),
        )


def load(session_id: str) -> dict | None:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM proposals WHERE session_id = ?", (session_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"tool": row["tool"], "args": json.loads(row["args"]), "working_days": row["working_days"]}


def clear(session_id: str) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM proposals WHERE session_id = ?", (session_id,))


def is_confirmation(message: str) -> bool:
    return message.strip().lower() in {"yes", "confirm", "go ahead", "ok", "yes please", "do it"}
