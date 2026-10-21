from datetime import date, timedelta

from app.db import connect


def holidays_for(region: str, year: int) -> set[date]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT date FROM holidays WHERE region = ? AND type = 'public'",
            (region,),
        ).fetchall()
    finally:
        conn.close()
    days = {date.fromisoformat(r["date"]) for r in rows}
    return {d for d in days if d.year == year}


def working_days(start: date, end: date, region: str) -> int:
    if end < start:
        return 0
    holidays = holidays_for(region, start.year)
    count = 0
    day = start
    while day <= end:
        if day.weekday() < 5 and day not in holidays:
            count += 1
        day += timedelta(days=1)
    return count


def date_range(start: date, end: date) -> list[date]:
    out = []
    day = start
    while day <= end:
        out.append(day)
        day += timedelta(days=1)
    return out
