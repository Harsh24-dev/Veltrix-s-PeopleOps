# Design

Some notes on how the assistant is put together and why. The rule I kept coming back to: keep all
the actual rules in plain Python and let the LLM only read documents and phrase the answer. That way
the behaviour stays predictable and I can test it.

## Ingesting tables and the scanned document

`app/ingest/parsers.py` reads each format: PyMuPDF for PDF, `python-docx` for DOCX, BeautifulSoup
for HTML, and a plain read for Markdown.

For tables, DOCX tables are flattened row by row into `cell | cell | cell` lines so the numbers stay
next to their labels. Holiday calendars go a step further: `holidays.py` pulls each date and its
name out of the text and stores them in a `holidays` table, so the leave maths works off structured
dates instead of free text.

For the scanned PDF, `parse_pdf` checks how much selectable text a file has. If there's almost none
(under 100 characters) it treats the file as scanned, renders each page to an image, and runs it
through Tesseract OCR. Nothing is ever typed in by hand.

## Chunking and retrieval

Chunking (`chunker.py`) splits on headings first, then packs paragraphs up to about 280 tokens, with
a hard cap of 400. Each chunk keeps its heading and page, which is exactly what the citations need
later.

Retrieval (`hybrid.py`) runs dense vector search (bge-small embeddings) alongside a keyword scorer
and fuses the two with Reciprocal Rank Fusion. Dense search catches meaning, keyword search catches
exact terms like "sabbatical", and leave policies have plenty of both. There's an optional
cross-encoder re-rank on the top few results when a GPU is around.

The context packer (`packer.py`) adds chunks in rank order until it hits 3,000 corpus tokens
(`cl100k_base`), and every LLM call logs that count.

Why this shape: 30 documents is small, so getting the right answer matters more than speed, and
hybrid search means I don't miss an answer just because the wording was different.

## The Section 5 rules (which document applies)

This is done in code, in two steps.

First, eligibility (`retrieval/eligibility.py`, `is_eligible`): keep a document only if the role is
allowed to read its `access_level`, its region matches or is `GLOBAL`, and its effective date is on
or before the reference date. This runs before retrieval, so an off-limits document never gets near
the LLM.

Then precedence (`precedence/engine.py`, `resolve`): rank the survivors by authority
(policy/addendum/memo/handbook/calendar over faq/wiki), then scope (region over global), then
recency (newer effective date). If the top two still tie, both are returned and the answer says they
conflict rather than picking one. `upcoming()` finds a future-dated document that would win on its
own effective date, so the answer can mention it as an upcoming change.

The reference date is today (`APP_TODAY`) unless the question names a past year, which `dates.py`
handles.

## Where access control lives

Two gates, both in code, never in the prompt.

Documents are gated in `retrieval/eligibility.py` (`is_eligible`), called from
`orchestrator/engine.py` (`_handle_rag`) before search runs.

Leave data is gated inside each tool in `tools/leave_tools.py`, using `tools/permissions.py`
(`can_view_leave`, `direct_report_ids`). The check reads the employee ID from the request header, so
whatever arguments the LLM picks can't get around it. Identity itself is handled in `main.py`: 401
for an unknown ID, and 403 when a session is reused by a different employee.

## Keeping personal data out of logs and prompts

`common/pii.py` is the single place for this. Logs (`common/logging.py`) run every string through
`scrub()`, which strips emails and phone numbers, so logs only ever carry employee IDs. Answers that
go back to the user run through `redact_answer()`, which removes phone numbers and masks emails to
`r***@domain`. Prompts only get the requester's own data when a tool actually needs it; the corpus
text sent to the model is policy content, not people.

## Failure modes I ran into

- The model inventing citations. Fixed by having it only write `[S1]` markers and letting the code
  map those to the real `doc_id` and locator (`verify.py`).
- An out-of-date FAQ out-ranking a real policy. Fixed by making authority the first precedence test,
  and telling the answer prompt never to answer from an FAQ when a policy covers the same thing.
- ISO dates getting caught by the phone-number scrub. Fixed by requiring 10+ digits in the phone
  pattern so `2026-10-19` is left alone.
- No LLM key configured. Handled by falling back to a local hashing embedder and an extractive
  answer, so the service still boots and `/health` passes.

## What breaks first at 10,000 documents

The keyword scorer that runs in-process, and loading every embedding into memory on each request.
Both are fine for 30 docs but won't hold at 10k. The fix is to move keyword search into SQLite FTS5
(or a real search engine) and keep the vectors in a proper store like FAISS or Qdrant, queried with
approximate nearest-neighbour instead of a full scan. The eligibility filter would also move out of
a Python loop and into an indexed SQL `WHERE` clause. The rest, precedence, tools and access
control, stays the same.
