from app.common.pii import mask_email, redact_answer, scrub


def test_mask_email():
    assert mask_email("rohan.bhat@veltrix.example") == "r***@veltrix.example"


def test_redact_masks_email_in_answer():
    out = redact_answer("Email hr@veltrix.example for help.")
    assert "hr@veltrix.example" not in out
    assert "h***@veltrix.example" in out


def test_redact_removes_phone():
    out = redact_answer("Call +91 98221 51875 now")
    assert "98221" not in out


def test_scrub_keeps_dates_and_ids():
    out = scrub("emp E1001 on 2026-10-19 region IN level L7")
    assert "E1001" in out and "2026-10-19" in out and "L7" in out


def test_scrub_hides_contact():
    out = scrub("meera.krishnan@veltrix.example +91 98221 51875")
    assert "@veltrix" not in out and "98221" not in out
