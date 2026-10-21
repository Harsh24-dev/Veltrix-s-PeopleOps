from app.identity import load_requester, resolve_employee
from app.tools.permissions import can_view_leave


def test_employee_sees_only_self(temp_env):
    e1 = load_requester("E1")
    assert can_view_leave(e1, "E1")
    assert not can_view_leave(e1, "E3")   # a peer
    assert not can_view_leave(e1, "E9")   # HR


def test_manager_sees_own_reports_only(temp_env):
    e2 = load_requester("E2")
    assert can_view_leave(e2, "E2")       # self
    assert can_view_leave(e2, "E1")       # direct report
    assert can_view_leave(e2, "E3")       # direct report
    assert not can_view_leave(e2, "E4")   # someone else's report


def test_hr_sees_anyone(temp_env):
    e9 = load_requester("E9")
    for target in ("E1", "E2", "E3", "E4", "E5"):
        assert can_view_leave(e9, target)


def test_resolve_employee_by_id_and_name(temp_env):
    assert resolve_employee("E1") == "E1"
    assert resolve_employee("e1") == "E1"
    assert resolve_employee("Chen Li") == "E3"
    assert resolve_employee("chen li") == "E3"


def test_resolve_employee_unknown_is_none(temp_env):
    # Unknown name and unknown id both resolve to None -> same fixed refusal
    assert resolve_employee("Nobody Here") is None
    assert resolve_employee("E999") is None
