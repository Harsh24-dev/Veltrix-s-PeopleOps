from datetime import date

from app.tools import calendar


def test_weekends_excluded(monkeypatch):
    monkeypatch.setattr(calendar, "holidays_for", lambda region, year: set())
    # Mon 2026-10-19 .. Sun 2026-10-25 -> 5 working days
    assert calendar.working_days(date(2026, 10, 19), date(2026, 10, 25), "IN") == 5


def test_holiday_excluded(monkeypatch):
    monkeypatch.setattr(calendar, "holidays_for", lambda region, year: {date(2026, 10, 20)})
    assert calendar.working_days(date(2026, 10, 19), date(2026, 10, 23), "IN") == 4


def test_reversed_range_is_zero(monkeypatch):
    monkeypatch.setattr(calendar, "holidays_for", lambda region, year: set())
    assert calendar.working_days(date(2026, 10, 25), date(2026, 10, 19), "IN") == 0
