from datetime import date

from app.retrieval.eligibility import is_eligible

TODAY = date(2026, 10, 19)


def doc(regions, effective, access="all", doc_type="policy"):
    return {"regions": regions, "effective_date": effective, "access_level": access, "doc_type": doc_type}


def test_future_doc_not_eligible():
    assert not is_eligible(doc(["GLOBAL"], "2027-01-01"), "employee", "IN", TODAY)


def test_wrong_region_not_eligible():
    assert not is_eligible(doc(["DE"], "2025-01-01"), "employee", "IN", TODAY)


def test_global_is_eligible_for_any_region():
    assert is_eligible(doc(["GLOBAL"], "2025-01-01"), "employee", "US", TODAY)


def test_employee_cannot_read_hr_doc():
    assert not is_eligible(doc(["GLOBAL"], "2025-01-01", access="hr"), "employee", "IN", TODAY)
    assert is_eligible(doc(["GLOBAL"], "2025-01-01", access="hr"), "hr", "IN", TODAY)
