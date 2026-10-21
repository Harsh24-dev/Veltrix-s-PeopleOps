import hashlib

import numpy as np

from app.common.logging import trace
from app.config import get_settings

_model = None
_dim = 384


def _pick_device() -> str:
    choice = get_settings().embedding_device.lower()
    if choice in ("cpu", "cuda"):
        return choice
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _load():
    """Load the configured sentence-transformer once. Fall back to a
    deterministic hashing embedder so the service still runs offline."""
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        device = _pick_device()
        _model = SentenceTransformer(get_settings().embedding_model, device=device)
        trace("embedder_ready", model=get_settings().embedding_model, device=device)
    except Exception as exc:
        trace("embedder_fallback", reason=str(exc))
        _model = "hash"
    return _model


def _hash_embed(texts: list[str]) -> np.ndarray:
    vecs = np.zeros((len(texts), _dim), dtype=np.float32)
    for i, text in enumerate(texts):
        for token in text.lower().split():
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vecs[i, h % _dim] += 1.0
    return vecs


def embed(texts: list[str], query: bool = False) -> np.ndarray:
    model = _load()
    if model == "hash":
        vecs = _hash_embed(texts)
    else:
        if query:
            texts = [f"Represent this sentence for searching relevant passages: {t}" for t in texts]
        vecs = np.asarray(model.encode(texts), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.clip(norms, 1e-9, None)
