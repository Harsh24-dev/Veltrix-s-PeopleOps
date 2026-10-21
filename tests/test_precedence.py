from datetime import date

from app.precedence.engine import Doc, resolve, upcoming

V1 = Doc("V1", "policy", ["GLOBAL"], date(2025, 1, 1))
V2 = Doc("V2", "policy", ["GLOBAL"], date(2026, 4, 1))
V3 = Doc("V3", "policy", ["GLOBAL"], date(2027, 1, 1))
FAQ = Doc("FAQ", "faq", ["GLOBAL"], date(2026, 5, 1))
DE = Doc("DE", "addendum", ["DE"], date(2025, 6, 1))


def test_recency_breaks_tie_between_versions():
    ordered, conflict = resolve([V1, V2], "IN")
    assert ordered[0].doc_id == "V2"
    assert not conflict


def test_authority_beats_recency():
    ordered, _ = resolve([V2, FAQ], "IN")
    assert ordered[0].doc_id == "V2"


def test_region_beats_global_on_scope():
    ordered, _ = resolve([V2, DE], "DE")
    assert ordered[0].doc_id == "DE"


def test_upcoming_version_detected():
    assert [d.doc_id for d in upcoming([V1, V2, V3], "IN", date(2026, 9, 15))] == ["V3"]
