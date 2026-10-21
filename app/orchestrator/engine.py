import uuid
from datetime import date

from app import identity
from app.common.logging import step
from app.identity import Requester
from app.llm import client
from app.orchestrator import confirm, intent, prompts, router, verify
from app.orchestrator.dates import reference_date
from app.precedence.engine import Doc
from app.retrieval import hybrid
from app.retrieval.eligibility import is_eligible
from app.retrieval.packer import pack, render
from app.retrieval.store import load_index
from app.schemas import ChatResponse, ToolCall
from app.tools import leave_tools, permissions

NO_ANSWER = "The documents don't cover that. Please contact the HR team."
OUT_OF_SCOPE = "I can help with HR policies, holidays and your leave. I can't help with that."

_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS_FULL = ["", "january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december"]


# ---------- formatting helpers ----------
def _fmt_days(n):
    n = int(n) if float(n).is_integer() else n
    return f"{n} day" if n == 1 else f"{n} days"


def _fmt_date(iso):
    y, m, d = iso.split("-")
    return f"{int(d)} {_MONTHS[int(m)]} {y}"


def _fmt_balance(data, name=None):
    who_has = f"{name} has" if name else "You currently have"
    if not data:
        return f"{name} has no leave balance on record." if name else "You have no leave balance on record."
    parts = [f"{_fmt_days(v)} of {k} leave" for k, v in sorted(data.items())]
    return f"{who_has} " + " and ".join(parts) + " remaining."


def _fmt_requests(rows, name=None):
    who = name or "You"
    verb = "has" if name else "have"
    if not rows:
        return f"{who} {verb} no leave requests on record."
    lines = []
    for r in rows:
        span = _fmt_date(r["start_date"])
        if r["end_date"] != r["start_date"]:
            span += f" to {_fmt_date(r['end_date'])}"
        lines.append(f"- {_fmt_days(r['working_days'])} of {r['leave_type']} leave, {span} ({r['status']})")
    return f"{who} {verb} {len(rows)} leave request(s):\n" + "\n".join(lines)


def _fmt_team(rows):
    if not rows:
        return "No one on your team has pending or approved leave in that range."
    lines = []
    for r in rows:
        name = identity.employee_name(r["employee_id"]) or r["employee_id"]
        span = _fmt_date(r["start_date"])
        if r["end_date"] != r["start_date"]:
            span += f" to {_fmt_date(r['end_date'])}"
        lines.append(f"- {name}: {r['leave_type']} leave, {span} ({r['status']})")
    return "Here's your team's leave:\n" + "\n".join(lines)


# ---------- response builders ----------
def _clarify(rid, text):
    return ChatResponse(request_id=rid, answer=text, route="clarify")


def _tool_error(rid, name, reason):
    return ChatResponse(request_id=rid, answer=reason, route="tool",
                        tool_calls=[ToolCall(name=name, args={}, status="error")])


def _propose(rid, name, args, summary):
    return ChatResponse(request_id=rid, answer=summary, route="tool", pending_confirmation=True,
                        tool_calls=[ToolCall(name=name, args=args, status="pending_confirmation")])


def _precedence_key(chunk, docs, region):
    m = docs[chunk.doc_id]
    doc = Doc(m["doc_id"], m["doc_type"], m["regions"], date.fromisoformat(m["effective_date"]))
    return doc.rank_key(region)


# ---------- top-level ----------
def handle(requester: Requester, session_id: str, message: str, today) -> ChatResponse:
    request_id = str(uuid.uuid4())
    step(request_id, "received", employee_id=requester.employee_id, role=requester.role,
         region=requester.region, chars=len(message))

    pending = confirm.load(session_id)
    if pending:
        if confirm.is_confirmation(message):
            step(request_id, "confirm", tool=pending["tool"])
            return _execute(request_id, requester, session_id, pending, today)
        new_intent = intent.extract(message, today, pending)
        if new_intent["action"] in ("apply", "cancel"):
            step(request_id, "reproposal", action=new_intent["action"])
            confirm.clear(session_id)
            return _handle_write(request_id, requester, session_id, new_intent, today)
        confirm.clear(session_id)  # discard and handle normally

    decision = router.classify(message, request_id)
    route = decision["route"]
    step(request_id, "routed", route=route)

    if route == "refuse":
        return ChatResponse(request_id=request_id, answer=OUT_OF_SCOPE, route="refuse")
    if route == "clarify":
        return _clarify(request_id, "Could you tell me the leave type and the exact dates?")
    if route == "tool":
        return _handle_tool(request_id, requester, session_id, message, today)
    if route == "hybrid":
        return _handle_hybrid(request_id, requester, message, today)
    return _handle_rag(request_id, requester, message, today)


# ---------- tool dispatch ----------
def _handle_tool(request_id, requester, session_id, message, today):
    data = intent.extract(message, today)
    action = data["action"]
    step(request_id, "intent", action=action)

    if action in ("apply", "cancel"):
        return _handle_write(request_id, requester, session_id, data, today)
    if action == "team":
        return _handle_team(request_id, requester, data, today)
    return _handle_read(request_id, requester, action, data)


def _resolve_target(requester, data):
    """Which employee is this request about? Returns (employee_id, display_name).
    display_name is None for the requester themselves. Returns (None, None) when
    the target can't be read — the caller then gives the fixed refusal."""
    target = (data.get("target") or "").strip()
    if not target or target.upper() == requester.employee_id:
        return requester.employee_id, None
    emp_id = identity.resolve_employee(target)
    if emp_id is None or not permissions.can_view_leave(requester, emp_id):
        return None, None
    return emp_id, identity.employee_name(emp_id)


def _handle_read(request_id, requester, action, data):
    emp_id, name = _resolve_target(requester, data)
    if emp_id is None:
        step(request_id, "leave_denied")
        return ChatResponse(request_id=request_id, answer=leave_tools.REFUSAL, route="refuse")
    try:
        if action == "list_requests":
            rows = leave_tools.list_leave_requests(requester, emp_id)
            answer, tool = _fmt_requests(rows, name), "list_leave_requests"
        else:
            bal = leave_tools.get_leave_balance(requester, emp_id)
            answer, tool = _fmt_balance(bal, name), "get_leave_balance"
    except leave_tools.ToolError:
        return ChatResponse(request_id=request_id, answer=leave_tools.REFUSAL, route="refuse")
    step(request_id, "tool_call", tool=tool, status="success")
    return ChatResponse(request_id=request_id, answer=answer, route="tool",
                        tool_calls=[ToolCall(name=tool, args={"employee_id": emp_id}, status="success")])


def _handle_team(request_id, requester, data, today):
    if requester.role != "manager":
        return ChatResponse(request_id=request_id, answer=leave_tools.REFUSAL, route="refuse")
    start, end = data.get("start_date", ""), data.get("end_date", "")
    if not start or not end:
        return _clarify(request_id, "Which dates should I check for your team? Give a start and end date.")
    try:
        rows = leave_tools.get_team_leave(requester, start, end)
    except leave_tools.ToolError as exc:
        return _tool_error(request_id, "get_team_leave", str(exc))
    step(request_id, "tool_call", tool="get_team_leave", status="success")
    return ChatResponse(request_id=request_id, answer=_fmt_team(rows), route="tool",
                        tool_calls=[ToolCall(name="get_team_leave",
                                             args={"start_date": start, "end_date": end}, status="success")])


# ---------- write: propose ----------
def _handle_write(request_id, requester, session_id, data, today):
    if data["action"] == "apply":
        return _propose_apply(request_id, requester, session_id, data, today)
    return _propose_cancel(request_id, requester, session_id, data, today)


def _propose_apply(request_id, requester, session_id, data, today):
    lt, s, e = data["leave_type"], data["start_date"], data["end_date"]
    if lt not in ("annual", "sick"):
        return _clarify(request_id, "Would you like annual or sick leave, and for which dates?")
    if not s or not e:
        return _clarify(request_id, "What start and end dates would you like? (both must be in 2026)")
    try:
        start, end = date.fromisoformat(s), date.fromisoformat(e)
    except ValueError:
        return _clarify(request_id, "I couldn't read those dates. Please give a start and end date in 2026.")
    try:
        days = leave_tools.validate_apply(requester, lt, start, end, today)
    except leave_tools.ToolError as exc:
        step(request_id, "propose_rejected", reason=str(exc))
        return _tool_error(request_id, "apply_leave", str(exc))

    args = {"leave_type": lt, "start_date": s, "end_date": e}
    confirm.save(session_id, "apply_leave", args, days)
    step(request_id, "proposed", tool="apply_leave", working_days=days)
    span = _fmt_date(s) + (f" to {_fmt_date(e)}" if e != s else "")
    return _propose(request_id, "apply_leave", args,
                    f"You'd like {_fmt_days(days)} of {lt} leave on {span}. Shall I submit it? (yes to confirm)")


def _cancellable(requester, today):
    rows = leave_tools.list_leave_requests(requester, requester.employee_id)
    return [r for r in rows
            if r["status"] in ("pending", "approved") and date.fromisoformat(r["start_date"]) > today]


def _match_request(cands, hint):
    hint = (hint or "").lower().strip()
    if len(cands) == 1 and not hint:
        return cands[0]
    scored = []
    for r in cands:
        mo = _MONTHS_FULL[int(r["start_date"].split("-")[1])]
        hay = f"{r['leave_type']} {r['start_date']} {mo}"
        if any(tok in hay for tok in hint.split() if len(tok) > 2):
            scored.append(r)
    return scored[0] if len(scored) == 1 else None


def _propose_cancel(request_id, requester, session_id, data, today):
    cands = _cancellable(requester, today)
    if not cands:
        return _tool_error(request_id, "cancel_leave", "You have no future leave requests that can be cancelled.")
    match = _match_request(cands, data["which_request"])
    if match is None:
        return _clarify(request_id, "Which request should I cancel?\n" + _fmt_requests(cands))
    args = {"request_id": match["request_id"]}
    confirm.save(session_id, "cancel_leave", args, match["working_days"])
    step(request_id, "proposed", tool="cancel_leave")
    span = _fmt_date(match["start_date"])
    return _propose(request_id, "cancel_leave", args,
                    f"You'd like to cancel {_fmt_days(match['working_days'])} of {match['leave_type']} "
                    f"leave starting {span}. Shall I cancel it? (yes to confirm)")


# ---------- write: execute ----------
def _execute(request_id, requester, session_id, pending, today):
    confirm.clear(session_id)
    tool, args = pending["tool"], pending["args"]
    try:
        if tool == "apply_leave":
            res = leave_tools.apply_leave(requester, args["leave_type"],
                                          date.fromisoformat(args["start_date"]),
                                          date.fromisoformat(args["end_date"]), today)
            answer = (f"Done. Your {args['leave_type']} leave is submitted "
                      f"({_fmt_days(res['working_days'])}), pending approval.")
        else:
            res = leave_tools.cancel_leave(requester, args["request_id"], today)
            answer = f"Done. That request is cancelled and {_fmt_days(res['restored_days'])} returned to your balance."
        step(request_id, "executed", tool=tool, status="success")
        return ChatResponse(request_id=request_id, answer=answer, route="tool",
                            tool_calls=[ToolCall(name=tool, args=args, status="success")])
    except leave_tools.ToolError as exc:
        step(request_id, "executed", tool=tool, status="error")
        return ChatResponse(request_id=request_id, answer=str(exc), route="tool",
                            tool_calls=[ToolCall(name=tool, args=args, status="error")])


# ---------- rag ----------
def _handle_rag(request_id, requester, message, today):
    reference = reference_date(message, today)
    step(request_id, "reference_date", date=reference.isoformat())

    chunks, vectors, docs = load_index()
    allowed = [i for i, c in enumerate(chunks)
               if c.doc_id in docs and is_eligible(docs[c.doc_id], requester.role, requester.region, reference)]
    step(request_id, "eligibility", eligible_chunks=len(allowed), total_chunks=len(chunks))

    ranked = hybrid.search(message, chunks, vectors, allowed)
    step(request_id, "retrieved", candidates=len(ranked),
         top_docs=sorted({chunks[i].doc_id for i in ranked[:5]}))
    if not ranked:
        return ChatResponse(request_id=request_id, answer=NO_ANSWER, route="no_answer")

    picked, corpus_tokens = pack(chunks, ranked)
    picked.sort(key=lambda i: _precedence_key(chunks[i], docs, requester.region), reverse=True)
    step(request_id, "packed", chunks=len(picked), corpus_tokens=corpus_tokens,
         source_docs=[chunks[i].doc_id for i in picked])

    context = render(chunks, picked)
    used_llm = client.available()
    step(request_id, "llm_call", provider_available=used_llm, corpus_tokens=corpus_tokens)
    if used_llm:
        user = f"Today's date is {reference.isoformat()}.\n\nSources:\n{context}\n\nQuestion: {message}"
        raw = client.complete(prompts.ANSWER, user)
    else:
        raw = f"{chunks[picked[0]].text} [S1]"

    citations = verify.bind_citations(raw, chunks, picked, docs)
    answer = verify.strip_markers(raw)
    step(request_id, "citations", cited=[c.doc_id for c in citations])
    if not citations:
        return ChatResponse(request_id=request_id, answer=NO_ANSWER, route="no_answer")
    return ChatResponse(request_id=request_id, answer=answer, route="rag", citations=citations)


# ---------- hybrid (balance + policy, e.g. "how many will I have by December?") ----------
def _handle_hybrid(request_id, requester, message, today):
    try:
        bal = leave_tools.get_leave_balance(requester, requester.employee_id)
    except leave_tools.ToolError:
        bal = {}
    tool_calls = [ToolCall(name="get_leave_balance",
                           args={"employee_id": requester.employee_id}, status="success")]

    reference = reference_date(message, today)
    chunks, vectors, docs = load_index()
    allowed = [i for i, c in enumerate(chunks)
               if c.doc_id in docs and is_eligible(docs[c.doc_id], requester.role, requester.region, reference)]
    ranked = hybrid.search(message, chunks, vectors, allowed)
    picked, corpus_tokens = pack(chunks, ranked) if ranked else ([], 0)
    picked.sort(key=lambda i: _precedence_key(chunks[i], docs, requester.region), reverse=True)
    step(request_id, "llm_call", provider_available=client.available(), corpus_tokens=corpus_tokens)

    citations = []
    if client.available() and picked:
        bal_text = ", ".join(f"{_fmt_days(v)} of {k}" for k, v in sorted(bal.items())) or "no balance on record"
        user = (f"Today's date is {reference.isoformat()}.\n\n"
                f"The employee's current leave balance: {bal_text}.\n\n"
                f"Sources:\n{render(chunks, picked)}\n\nQuestion: {message}\n\n"
                "Combine the current balance with the accrual and carry-forward rules in the sources, "
                "and show the calculation.")
        raw = client.complete(prompts.ANSWER, user)
        citations = verify.bind_citations(raw, chunks, picked, docs)
        answer = verify.strip_markers(raw)
    else:
        answer = (_fmt_balance(bal) +
                  " I can't project future accrual here — please check the leave policy or ask HR.")

    route = "hybrid" if citations else "tool"
    step(request_id, "citations", cited=[c.doc_id for c in citations])
    return ChatResponse(request_id=request_id, answer=answer, route=route,
                        citations=citations, tool_calls=tool_calls)
