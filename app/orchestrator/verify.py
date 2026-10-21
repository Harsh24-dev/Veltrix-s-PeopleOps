import re

from app.retrieval.store import ChunkRow
from app.schemas import Citation

_MARKER = re.compile(r"\[S(\d+)\]")


def locator(chunk: ChunkRow, has_headings: bool) -> str:
    if has_headings and chunk.heading_path:
        return chunk.heading_path
    return f"p. {chunk.page}" if chunk.page else "p. 1"


def bind_citations(answer: str, chunks: list[ChunkRow], picked: list[int], docs: dict) -> list[Citation]:
    """Map the [S#] markers the model used back to real doc_id + locator.
    The model never writes doc_ids or locators itself."""
    used = {int(n) for n in _MARKER.findall(answer)}
    citations, seen = [], set()
    for n in sorted(used):
        if n < 1 or n > len(picked):
            continue
        chunk = chunks[picked[n - 1]]
        has_headings = bool(docs.get(chunk.doc_id, {}).get("has_headings", 1))
        loc = locator(chunk, has_headings)
        key = (chunk.doc_id, loc)
        if key not in seen:
            seen.add(key)
            citations.append(Citation(doc_id=chunk.doc_id, locator=loc))
    return citations


def strip_markers(answer: str) -> str:
    return _MARKER.sub("", answer).replace("  ", " ").strip()
