import re

from app.common.logging import step
from app.llm import client
from app.orchestrator import prompts

# Deterministic guards.
BULK = re.compile(r"\b(everyone|all employees|every employee|everybody|all staff)\b", re.I)
OVERRIDE = re.compile(r"\b(ignore (your|previous|all)|system prompt|you are now|disregard|reveal your)\b", re.I)

# A question that mixes the current balance with the accrual/carry-forward rules
# (e.g. "how many annual days will I have by December?") needs both tools and docs.
FUTURE = re.compile(r"\b(by (dec|december)|year[- ]?end|end of (the )?year|accru\w*|carry[- ]?(forward|over))\b", re.I)
LEAVEISH = re.compile(r"\b(leave|days|balance)\b", re.I)

# Clear tool intents we can route without the LLM. Entitlement questions
# ("how many sick days do I GET") deliberately fall through to RAG.
TOOL_PATTERNS = [
    re.compile(r"\bbalance\b", re.I),
    re.compile(r"how many .*(left|remaining|do i have)", re.I),
    re.compile(r"\bmy (leave )?requests?\b", re.I),
    re.compile(r"\b(list|show) my leave\b", re.I),
    re.compile(r"\b(apply|book|take) .{0,20}leave\b", re.I),
    re.compile(r"\bcancel\b.*\b(leave|request)\b|\bcancel my\b", re.I),
    re.compile(r"\b(team|my reports?).{0,15}leave\b|\bwho is on leave\b", re.I),
]


ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": ["rag", "tool", "hybrid", "clarify", "refuse"]},
        "topic": {"type": "string"},
    },
    "required": ["route", "topic"],
    "additionalProperties": False,
}


def _deterministic(message: str) -> str | None:
    if BULK.search(message) or OVERRIDE.search(message):
        return "refuse"
    if FUTURE.search(message) and LEAVEISH.search(message):
        return "hybrid"
    if any(p.search(message) for p in TOOL_PATTERNS):
        return "tool"
    return None


def classify(message: str, request_id: str = "-") -> dict:
    """Rules first; the LLM only decides what our rules can't."""
    route = _deterministic(message)
    if route:
        step(request_id, "classify", by="rule", route=route)
        return {"route": route, "topic": ""}

    if client.available():
        result = client.complete_schema(prompts.ROUTER, message, ROUTE_SCHEMA)
        route = result.get("route")
        if route in ("rag", "tool", "hybrid", "clarify", "refuse"):
            step(request_id, "classify", by="llm", route=route)
            return {"route": route, "topic": result.get("topic", "")}

    # No LLM configured: assume it is an in-scope document question.
    step(request_id, "classify", by="fallback", route="rag")
    return {"route": "rag", "topic": message}
