import json
from dataclasses import dataclass

import numpy as np

from app.db import connect


@dataclass
class ChunkRow:
    chunk_id: str
    doc_id: str
    heading_path: str | None
    page: int | None
    text: str
    context_prefix: str
    token_len: int


_cache = None


def clear_cache():
    global _cache
    _cache = None


def load_index(force: bool = False):
    global _cache
    if _cache is not None and not force:
        return _cache
    _cache = _build_index()
    return _cache


def _build_index():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT chunk_id, doc_id, heading_path, page, text, context_prefix, token_len, embedding "
            "FROM chunks ORDER BY doc_id, ord"
        ).fetchall()
        docs = {
            d["doc_id"]: {**dict(d), "regions": json.loads(d["regions"])}
            for d in conn.execute("SELECT * FROM documents").fetchall()
        }
    finally:
        conn.close()

    chunks = [
        ChunkRow(r["chunk_id"], r["doc_id"], r["heading_path"], r["page"],
                 r["text"], r["context_prefix"], r["token_len"])
        for r in rows
    ]
    vectors = (
        np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
        if rows else np.zeros((0, 384), dtype=np.float32)
    )
    return chunks, vectors, docs


def dense_rank(query_vec: np.ndarray, vectors: np.ndarray, allowed: list[int], k: int) -> list[int]:
    if not allowed:
        return []
    scores = vectors[allowed] @ query_vec
    order = np.argsort(-scores)[:k]
    return [allowed[i] for i in order]


def lexical_rank(query: str, chunks: list[ChunkRow], allowed: list[int], k: int) -> list[int]:
    terms = set(query.lower().split())
    scored = []
    for i in allowed:
        words = chunks[i].text.lower().split()
        if not words:
            continue
        overlap = sum(1 for w in words if w in terms)
        if overlap:
            scored.append((overlap / len(words) ** 0.5, i))
    scored.sort(reverse=True)
    return [i for _, i in scored[:k]]
