import re
from datetime import datetime

from app.ingest.parsers import Segment

MONTH_ABBR = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}

_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_DMY = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b")
_MDY = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b")
_NOISE = re.compile(r"\b(effective|version|page|owner|classification|applies)\b", re.I)
_BAD_NAME = re.compile(r"\b(applies|effective|document|owner|classification|intranet|version|internal)\b", re.I)


def _to_iso(day: str, month: str, year: str) -> str | None:
    key = month[:3].lower()
    if key not in MONTH_ABBR:
        return None
    try:
        return datetime.strptime(f"{day} {key} {year}", "%d %b %Y").date().isoformat()
    except ValueError:
        return None


def _parse_date(line: str) -> str | None:
    if _ISO.search(line):
        return _ISO.search(line).group(0)
    m = _DMY.search(line)
    if m:
        return _to_iso(m.group(1), m.group(2), m.group(3))
    m = _MDY.search(line)
    if m:
        return _to_iso(m.group(2), m.group(1), m.group(3))
    return None


def _name_from(line: str) -> str:
    s = line
    for pat in (_ISO, _DMY, _MDY):
        s = pat.sub("", s, count=1)
    words = s.split()
    while words and words[0].lower() in WEEKDAYS:
        words.pop(0)
    return " ".join(words).strip(" .|-")[:80]


def _flatten(segments: list[Segment]) -> list[str]:
    lines = []
    for seg in segments:
        if seg.heading:
            lines.append(seg.heading)
        lines += seg.text.splitlines()
    return [l.strip() for l in lines if l.strip()]


def extract(segments: list[Segment], region: str, doc_id: str) -> list[dict]:
    lines = _flatten(segments)
    rows, seen, restricted = [], set(), False
    for i, line in enumerate(lines):
        if "restricted" in line.lower():
            restricted = True
        if _NOISE.search(line):
            continue
        iso = _parse_date(line)
        if not iso or iso in seen:
            continue
        name = _name_from(line)
        if not name:  # date was on its own line; the name follows it
            for nxt in lines[i + 1 : i + 4]:
                if nxt.lower() in WEEKDAYS or _parse_date(nxt):
                    continue
                name = nxt.strip(" .|-")[:80]
                break
        if not name or _BAD_NAME.search(name):
            continue
        seen.add(iso)
        rows.append({
            "region": region,
            "date": iso,
            "name": name,
            "type": "restricted" if restricted else "public",
            "source_doc_id": doc_id,
        })
    return rows
