import threading
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse

from app.common import pii
from app.common.logging import trace
from app.config import get_settings
from app.db import connect, migrate
from app.identity import bind_session, load_requester
from app.ingest import pipeline
from app.orchestrator import engine
from app.schemas import ChatRequest


def _ingest_background():
    try:
        pipeline.run()
    except Exception as exc:
        trace("ingest_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO ingest_status (id, state, finished_at) VALUES (1, 'running', NULL)"
    )
    conn.commit()
    conn.close()
    threading.Thread(target=_ingest_background, daemon=True).start()
    yield


app = FastAPI(
    title="Veltrix PeopleOps Assistant",
    version="0.1.0",
    description="HR assistant: answers from the document corpus with citations and manages "
    "leave through tools. Send requests to POST /chat with an X-Employee-Id header.",
    lifespan=lifespan,
)

_CHAT_OPENAPI = {
    "parameters": [
        {
            "name": "X-Employee-Id",
            "in": "header",
            "required": True,
            "schema": {"type": "string", "example": "E2004"},
            "description": "The logged-in employee's ID. Identity, role and region come from this.",
        }
    ],
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["message"],
                    "properties": {
                        "session_id": {"type": "string", "description": "Optional; a fresh one is created if omitted. Reuse it for multi-turn (e.g. confirming a leave request)."},
                        "message": {"type": "string"},
                    },
                },
                "example": {"message": "How many sick leave days do I get?"},
            }
        },
    },
}


def _ready() -> bool:
    conn = connect()
    try:
        row = conn.execute("SELECT state FROM ingest_status WHERE id = 1").fetchone()
    finally:
        conn.close()
    return row is not None and row["state"] == "done"


@app.get("/health")
def health():
    if _ready():
        return {"status": "ok"}
    return JSONResponse(status_code=503, content={"status": "starting"})


@app.post("/chat", openapi_extra=_CHAT_OPENAPI)
async def chat(request: Request, x_employee_id: str | None = Header(default=None)):
    if not x_employee_id:
        return JSONResponse(status_code=401, content={"error": "missing X-Employee-Id"})

    requester = load_requester(x_employee_id)
    if requester is None:
        return JSONResponse(status_code=401, content={"error": "unknown employee"})

    try:
        body = ChatRequest(**(await request.json()))
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid body"})

    session_id = body.session_id.strip() or str(uuid.uuid4())
    if not bind_session(session_id, x_employee_id):
        return JSONResponse(status_code=403, content={"error": "session belongs to another employee"})

    settings = get_settings()
    response = engine.handle(requester, session_id, body.message, settings.today())
    response.answer = pii.redact_answer(response.answer)
    return response.model_dump()
