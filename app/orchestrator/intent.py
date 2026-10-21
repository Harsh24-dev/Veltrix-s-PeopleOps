from datetime import date

from app.llm import client

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string",
                   "enum": ["balance", "list_requests", "team", "apply", "cancel", "other"]},
        "leave_type": {"type": "string"},   # "annual" | "sick" | ""
        "start_date": {"type": "string"},   # YYYY-MM-DD | ""
        "end_date": {"type": "string"},     # YYYY-MM-DD | ""
        "which_request": {"type": "string"},  # phrase identifying a request to cancel | ""
        "target": {"type": "string"},       # another person's name or employee id | ""
    },
    "required": ["action", "leave_type", "start_date", "end_date", "which_request", "target"],
    "additionalProperties": False,
}

PROMPT = """Extract the employee's leave intent as JSON.
action: "balance" (a leave balance), "list_requests" (see leave requests),
"team" (a manager asking who on their team is on leave), "apply" (book/take leave),
"cancel" (cancel a request), or "other".
leave_type: "annual" or "sick" only if the user states it, otherwise "".
start_date / end_date: YYYY-MM-DD, resolved against today's date. A date with no year means 2026.
"next Friday" is the first Friday after today; "next week" is Monday-Friday of the following week.
A single day means start_date equals end_date. For "team", use the date range they ask about.
If no dates are given, use "".
which_request: a short phrase identifying which existing request to cancel (e.g. "november",
"the sick one"), otherwise "".
target: if the question is about ANOTHER named person (not the user themselves), put that person's
name or employee id here, otherwise "".
Resolve nothing you are unsure about — leave it "". Never invent dates."""

_KEYS = ("action", "leave_type", "start_date", "end_date", "which_request", "target")


def extract(message: str, today: date, pending: dict | None = None) -> dict:
    user = f"Today's date is {today.isoformat()}."
    if pending:
        user += f"\nThere is a pending {pending['tool']} proposal: {pending['args']}. The message may change it."
    user += f"\n\nMessage: {message}"
    data = client.complete_schema(PROMPT, user, INTENT_SCHEMA) if client.available() else {}
    return {k: (data.get(k) or "") for k in _KEYS} if data else _fallback(message)


def _fallback(message: str) -> dict:
    """No-LLM heuristic: only the read actions are reliable without an LLM."""
    m = message.lower()
    if "cancel" in m:
        action = "cancel"
    elif "request" in m:
        action = "list_requests"
    elif any(w in m for w in ("apply", "book", "take leave")):
        action = "apply"
    else:
        action = "balance"
    return {"action": action, "leave_type": "", "start_date": "", "end_date": "",
            "which_request": message, "target": ""}
