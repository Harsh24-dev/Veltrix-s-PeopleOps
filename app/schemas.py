from typing import Any, Literal

from pydantic import BaseModel

Route = Literal["rag", "tool", "hybrid", "clarify", "no_answer", "refuse"]


class ChatRequest(BaseModel):
    session_id: str = ""
    message: str


class Citation(BaseModel):
    doc_id: str
    locator: str


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = {}
    status: Literal["pending_confirmation", "success", "error"]


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    route: Route
    citations: list[Citation] = []
    tool_calls: list[ToolCall] = []
    pending_confirmation: bool = False
