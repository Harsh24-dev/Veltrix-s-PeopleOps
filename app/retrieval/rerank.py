from app.common.logging import trace
from app.config import get_settings
from app.ingest.embed import _pick_device

_reranker = None


def active() -> bool:
    setting = get_settings().rerank_enabled.lower()
    if setting in ("true", "1", "yes", "on"):
        return True
    if setting in ("false", "0", "no", "off"):
        return False
    return _pick_device() == "cuda"


def _load():
    global _reranker
    if _reranker is not None:
        return _reranker
    try:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(get_settings().rerank_model, device=_pick_device())
        trace("reranker_ready", model=get_settings().rerank_model)
    except Exception as exc:
        trace("reranker_disabled", reason=str(exc))
        _reranker = "none"
    return _reranker


def rerank(query: str, chunks, candidates: list[int]) -> list[int]:
    """Reorder candidate chunk indices by cross-encoder relevance."""
    if not active() or not candidates:
        return candidates
    model = _load()
    if model == "none":
        return candidates
    pairs = [[query, f"{chunks[i].context_prefix} {chunks[i].text}"] for i in candidates]
    scores = model.predict(pairs)
    order = sorted(range(len(candidates)), key=lambda k: -scores[k])
    return [candidates[k] for k in order]
