from app.config import get_settings
from app.retrieval.store import ChunkRow


def pack(chunks: list[ChunkRow], ranked: list[int]) -> tuple[list[int], int]:
    """Add chunks in ranked order until the corpus-token budget is reached."""
    budget = get_settings().corpus_token_budget
    picked, total = [], 0
    for idx in ranked:
        tokens = chunks[idx].token_len
        if total + tokens > budget:
            continue
        picked.append(idx)
        total += tokens
    return picked, total


def render(chunks: list[ChunkRow], picked: list[int]) -> str:
    blocks = []
    for n, idx in enumerate(picked, start=1):
        c = chunks[idx]
        blocks.append(f"[S{n}] {c.context_prefix}\n{c.text}")
    return "\n\n".join(blocks)
