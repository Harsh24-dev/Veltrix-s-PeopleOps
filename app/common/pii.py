import re

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")
# Phone numbers have 10+ digits (optionally a + prefix). The {9,} run keeps
# this from matching an 8-digit ISO date like 2026-10-19, which is not PII.
_PHONE = re.compile(r"\+?\d[\d\s\-]{9,}\d")


def mask_email(email: str) -> str:
    email = email.strip()
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    first = local[0] if local else ""
    return f"{first}***@{domain}"


def scrub(text: str) -> str:
    """Remove emails and phone numbers from free text headed for logs."""
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[phone]", text)
    return text


def redact_answer(text: str) -> str:
    """Final safety pass on a user-facing answer: mask any email address and
    remove any phone number, per the personal-data rules."""
    text = _EMAIL.sub(lambda m: mask_email(m.group(0)), text)
    text = _PHONE.sub("[contact HR]", text)
    return text
