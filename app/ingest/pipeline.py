import json
import os
import uuid
from datetime import datetime

import numpy as np

from app.common.logging import trace
from app.common.tokens import count
from app.config import get_settings
from app.db import transaction
from app.ingest import holidays
from app.ingest.chunker import chunk
from app.ingest.embed import embed
from app.ingest.parsers import parse
from app.precedence.engine import authority_rank


def _context_prefix(doc: dict, heading: str | None) -> str:
    regions = ",".join(doc["regions"])
    parts = [doc["title"], doc["doc_type"], regions, f"eff {doc['effective_date']}"]
    if heading:
        parts.append(heading)
    return "[" + " · ".join(parts) + "]"


def _ingest_document(conn, doc: dict, corpus_dir: str) -> None:
    path = os.path.join(corpus_dir, doc["file"])
    segments, page_count = parse(path)
    chunks = chunk(segments)
    has_headings = 1 if any(c.heading for c in chunks) else 0

    conn.execute(
        """INSERT OR REPLACE INTO documents
           (doc_id, file, title, doc_type, regions, effective_date,
            access_level, authority_rank, has_headings, page_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            doc["doc_id"], doc["file"], doc["title"], doc["doc_type"],
            json.dumps(doc["regions"]), doc["effective_date"], doc["access_level"],
            authority_rank(doc["doc_type"]), has_headings, page_count,
        ),
    )

    prefixes = [_context_prefix(doc, c.heading) for c in chunks]
    vectors = embed([f"{p}\n{c.text}" for p, c in zip(prefixes, chunks)])
    for ord_, (c, prefix, vec) in enumerate(zip(chunks, prefixes, vectors)):
        conn.execute(
            """INSERT INTO chunks
               (chunk_id, doc_id, ord, heading_path, page, text, context_prefix, token_len, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), doc["doc_id"], ord_, c.heading, c.page,
                c.text, prefix, count(prefix + "\n" + c.text),
                np.asarray(vec, dtype=np.float32).tobytes(),
            ),
        )

    if doc["doc_type"] == "calendar":
        region = next((r for r in doc["regions"] if r != "GLOBAL"), "GLOBAL")
        for row in holidays.extract(segments, region, doc["doc_id"]):
            conn.execute(
                """INSERT OR IGNORE INTO holidays (region, date, name, type, source_doc_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (row["region"], row["date"], row["name"], row["type"], row["source_doc_id"]),
            )


def run() -> None:
    settings = get_settings()
    with open(settings.manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    with transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ingest_status (id, state, finished_at) VALUES (1, 'running', NULL)"
        )

    with transaction() as conn:
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM holidays")
        for doc in manifest:
            try:
                _ingest_document(conn, doc, settings.corpus_dir)
            except Exception as exc:
                trace("ingest_error", doc_id=doc["doc_id"], error=str(exc))

    _warm()

    with transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ingest_status (id, state, finished_at) VALUES (1, 'done', ?)",
            (datetime.utcnow().isoformat(),),
        )
    trace("ingest_done", documents=len(manifest))


def _warm() -> None:
    from app.ingest.embed import embed
    from app.retrieval.rerank import rerank
    from app.retrieval.store import load_index

    chunks, _, _ = load_index(force=True)
    if not chunks:
        return
    embed(["warm up"], query=True)
    rerank("warm up", chunks, list(range(min(3, len(chunks)))))
