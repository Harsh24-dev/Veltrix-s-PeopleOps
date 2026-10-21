import re
from datetime import date

_YEAR = re.compile(r"\b(20\d{2})\b")


def reference_date(message: str, today: date) -> date:
    """Today, unless the user clearly asks about a specific past year."""
    match = _YEAR.search(message)
    if match:
        year = int(match.group(1))
        if year < today.year:
            return date(year, 12, 31)
    return today
