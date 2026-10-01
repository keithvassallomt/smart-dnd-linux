"""Tests for calendar rule matching logic mirroring smart-dnd test suite."""

from smart_dnd.matcher import (
    calendar_next_transition,
    next_enable,
    rules_active_at,
    source_allowed,
    title_matches,
)
from smart_dnd.models import CalendarEvent, CalendarRule

S = 1000.0  # seconds to ms


def make_rule(**kwargs) -> CalendarRule:
    d = {
        "id": "r1",
        "name": "R",
        "match_type": "contains",
        "pattern": "Meeting",
        "calendars": [],
        "enable_offset_min": 0,
        "disable_offset_min": 0,
        "enabled": True,
    }
    d.update(kwargs)
    return CalendarRule(**d)


def test_title_matches_contains_case_insensitive():
    r = make_rule()
    assert title_matches(r, "Team meeting") is True
    assert title_matches(r, "Lunch") is False


def test_title_matches_starts_with_and_ends_with():
    r_start = make_rule(match_type="startsWith", pattern="Stand")
    assert title_matches(r_start, "Standup") is True
    assert title_matches(r_start, "up") is False

    r_end = make_rule(match_type="endsWith", pattern="up")
    assert title_matches(r_end, "Standup") is True


def test_title_matches_regex_safe():
    r_reg = make_rule(match_type="regex", pattern=r"^Sync\d+$")
    assert title_matches(r_reg, "Sync12") is True
    assert title_matches(r_reg, "Sync") is False

    # Invalid regex does not throw, returns False
    r_inv = make_rule(match_type="regex", pattern=r"(")
    assert title_matches(r_inv, "anything") is False


def test_title_matches_non_string():
    r = make_rule()
    assert title_matches(r, None) is False
    assert title_matches(r, 123) is False


def test_source_allowed_honours_filter():
    r_all = make_rule(calendars=[])
    assert source_allowed(r_all, "uid-x") is True

    r_filt = make_rule(calendars=["uid-a"])
    assert source_allowed(r_filt, "uid-a") is True
    assert source_allowed(r_filt, "uid-b") is False


ev = CalendarEvent(uid="1", summary="Team Meeting", start=1000.0, end=4600.0, all_day=False, source_uid="uid-a")


def test_rules_active_at_inside_window():
    r = make_rule()
    assert rules_active_at([r], [ev], 2000.0 * S, ignore_all_day=True) is True
    assert rules_active_at([r], [ev], 5000.0 * S, ignore_all_day=True) is False
    assert rules_active_at([r], [ev], 4600.0 * S, ignore_all_day=True) is False  # off is exclusive


def test_offsets_shift_window():
    # Enable 10 min before start: on = (1000 - 600)s = 400s
    r_offset = make_rule(enable_offset_min=-10)
    assert rules_active_at([r_offset], [ev], 500.0 * S, ignore_all_day=True) is True
    assert rules_active_at([make_rule()], [ev], 500.0 * S, ignore_all_day=True) is False


def test_all_day_skipped_when_ignore_all_day():
    allday_ev = CalendarEvent(uid="2", summary="Team Meeting", start=1000.0, end=4600.0, all_day=True, source_uid="uid-a")
    r = make_rule()
    assert rules_active_at([r], [allday_ev], 2000.0 * S, ignore_all_day=True) is False
    assert rules_active_at([r], [allday_ev], 2000.0 * S, ignore_all_day=False) is True


def test_calendar_next_transition():
    r = make_rule()
    assert calendar_next_transition([r], [ev], 2000.0 * S, ignore_all_day=True) == 4600.0 * S
    assert calendar_next_transition([r], [ev], 500.0 * S, ignore_all_day=True) == 1000.0 * S
    assert calendar_next_transition([r], [ev], 5000.0 * S, ignore_all_day=True) is None


def test_next_enable():
    r = make_rule()
    assert next_enable([r], [ev], 500.0 * S, ignore_all_day=True) == 1000.0 * S
    assert next_enable([r], [ev], 1000.0 * S, ignore_all_day=True) is None
