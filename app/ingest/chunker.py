from app.common.tokens import count
from app.ingest.parsers import Segment

TARGET = 280
MAX = 400


class Chunk:
    def __init__(self, text: str, heading: str | None, page: int | None):
        self.text = text
        self.heading = heading
        self.page = page


def _split_long(text: str) -> list[str]:
    paras = [p for p in text.split("\n") if p.strip()]
    out, buf = [], ""
    for para in paras:
        candidate = f"{buf}\n{para}".strip()
        if count(candidate) > MAX and buf:
            out.append(buf)
            buf = para
        else:
            buf = candidate
    if buf:
        out.append(buf)
    return out


def chunk(segments: list[Segment]) -> list[Chunk]:
    chunks = []
    for seg in segments:
        pieces = [seg.text] if count(seg.text) <= MAX else _split_long(seg.text)
        for piece in pieces:
            chunks.append(Chunk(piece, seg.heading, seg.page))
    return chunks
