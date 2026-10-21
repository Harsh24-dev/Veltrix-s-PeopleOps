from datetime import date

import pytest

from app.identity import load_requester
from app.tools import leave_tools

TODAY = date(2026, 10, 19)


def test_rejects_leave_outside_2026(temp_env):
    with pytest.raises(leave_tools.ToolError):
        leave_tools.validate_apply(load_requester("E1"), "annual",
                                   date(2027, 1, 5), date(2027, 1, 6), TODAY)


def test_rejects_start_in_the_past(temp_env):
    with pytest.raises(leave_tools.ToolError):
        leave_tools.validate_apply(load_requester("E1"), "annual",
                                   date(2026, 10, 1), date(2026, 10, 2), TODAY)


def test_rejects_end_before_start(temp_env):
    with pytest.raises(leave_tools.ToolError):
        leave_tools.validate_apply(load_requester("E1"), "annual",
                                   date(2026, 11, 5), date(2026, 11, 3), TODAY)


def test_rejects_zero_working_days(temp_env):
    # Sat + Sun only
    with pytest.raises(leave_tools.ToolError):
        leave_tools.validate_apply(load_requester("E1"), "annual",
                                   date(2026, 11, 7), date(2026, 11, 8), TODAY)


def test_rejects_over_balance(temp_env):
    # E1 has 10 annual days; this range is 20 working days
    with pytest.raises(leave_tools.ToolError):
        leave_tools.validate_apply(load_requester("E1"), "annual",
                                   date(2026, 11, 2), date(2026, 11, 27), TODAY)


def test_rejects_invalid_type(temp_env):
    with pytest.raises(leave_tools.ToolError):
        leave_tools.validate_apply(load_requester("E1"), "vacation",
                                   date(2026, 11, 2), date(2026, 11, 4), TODAY)


def test_apply_decrements_then_cancel_restores(temp_env):
    r = load_requester("E1")
    before = leave_tools.get_leave_balance(r, "E1")["annual"]

    res = leave_tools.apply_leave(r, "annual", date(2026, 11, 2), date(2026, 11, 4), TODAY)  # Mon-Wed = 3
    assert res["working_days"] == 3
    assert leave_tools.get_leave_balance(r, "E1")["annual"] == before - 3

    # a request overlapping the new one is rejected
    with pytest.raises(leave_tools.ToolError):
        leave_tools.validate_apply(r, "annual", date(2026, 11, 3), date(2026, 11, 5), TODAY)

    restored = leave_tools.cancel_leave(r, res["request_id"], TODAY)
    assert restored["restored_days"] == 3
    assert leave_tools.get_leave_balance(r, "E1")["annual"] == before


def test_cannot_cancel_a_started_request(temp_env):
    r = load_requester("E1")
    # book future leave, then try to cancel it as if today were after it started
    res = leave_tools.apply_leave(r, "annual", date(2026, 11, 2), date(2026, 11, 4), TODAY)
    with pytest.raises(leave_tools.ToolError):
        leave_tools.cancel_leave(r, res["request_id"], date(2026, 11, 3))
