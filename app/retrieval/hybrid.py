from app.ingest.embed import embed
from app.retrieval.rerank import rerank
from app.retrieval.store import ChunkRow, dense_rank, lexical_rank

RRF_K = 60


def _rrf(rankings: list[list[int]]) -> list[int]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
    return [i for i, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


def search(query: str, chunks: list[ChunkRow], vectors, allowed: list[int], top_k: int = 15) -> list[int]:
    if not allowed:
        return []
    query_vec = embed([query], query=True)[0]
    dense = dense_rank(query_vec, vectors, allowed, 20)
    lexical = lexical_rank(query, chunks, allowed, 20)
    fused = _rrf([dense, lexical])[:top_k]
    return rerank(query, chunks, fused[:8]) + fused[8:]
