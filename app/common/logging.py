import json
import logging
import sys

from app.common.pii import scrub

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
_log = logging.getLogger("veltrix")


def trace(event: str, **fields) -> None:
    """Emit one structured, PII-safe log line per event."""
    safe = {k: scrub(v) if isinstance(v, str) else v for k, v in fields.items()}
    _log.info(json.dumps({"event": event, **safe}))


def step(request_id: str, name: str, **fields) -> None:
    """Log one step of handling a request, so the full path can be followed
    by request_id. Pass only IDs, counts and doc_ids here — never names/emails."""
    trace("step", request_id=request_id, step=name, **fields)
