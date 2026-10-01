"""Tests for scheduler logic mirroring original smart-dnd test suite."""

import datetime
from smart_dnd.models import Schedule
from smart_dnd.scheduler import (
    any_active_at,
    next_start,
    next_transition,
    schedule_active_at,
    to_minutes,
)

weeknights = Schedule(id="w", name="W", days=[1, 2, 3, 4, 5], start="22:00", end="07:00", enabled=True)
daytime = Schedule(id="d", name="D", days=[3], start="09:00", end="17:00", enabled=True)


def test_to_minutes():
    assert to_minutes("07:30") == 450
    assert to_minutes("00:00") == 0
    assert to_minutes("23:59") == 1439


def test_same_day_window_active_inside_inactive_outside():
    assert schedule_active_at(daytime, 3, to_minutes("12:00")) is True  # Wed noon
    assert schedule_active_at(daytime, 3, to_minutes("08:59")) is False
    assert schedule_active_at(daytime, 4, to_minutes("12:00")) is False  # Thu, not in days


def test_end_boundary_is_exclusive():
    assert schedule_active_at(daytime, 3, to_minutes("17:00")) is False
    assert schedule_active_at(daytime, 3, to_minutes("09:00")) is True


def test_midnight_crossing_head_on_start_day():
    assert schedule_active_at(weeknights, 1, to_minutes("23:00")) is True  # Mon 23:00


def test_midnight_crossing_tail_belongs_to_next_day():
    assert schedule_active_at(weeknights, 2, to_minutes("06:00")) is True  # Tue 06:00 = Mon window tail
    assert schedule_active_at(weeknights, 6, to_minutes("06:00")) is True  # Sat 06:00 = Fri window tail
    assert schedule_active_at(weeknights, 0, to_minutes("06:00")) is False  # Sun 06:00 = Sat has no window
    assert schedule_active_at(weeknights, 1, to_minutes("06:00")) is False  # Mon 06:00 = Sun has no window


def test_disabled_and_zero_length_never_active():
    disabled_d = Schedule(id="d", name="D", days=[3], start="09:00", end="17:00", enabled=False)
    zero_d = Schedule(id="d", name="D", days=[3], start="09:00", end="09:00", enabled=True)
    assert schedule_active_at(disabled_d, 3, to_minutes("12:00")) is False
    assert schedule_active_at(zero_d, 3, to_minutes("09:00")) is False


def test_any_active_at():
    assert any_active_at([daytime, weeknights], 1, to_minutes("23:00")) is True
    assert any_active_at([daytime, weeknights], 0, to_minutes("12:00")) is False


def test_next_transition_finds_next_boundary():
    # Wed 2026-01-07 08:00 local; daytime rule starts 09:00 same day.
    now_dt = datetime.datetime(2026, 1, 7, 8, 0, 0)
    now_ms = now_dt.astimezone().timestamp() * 1000.0
    next_ts = next_transition([daytime], now_ms)
    expected_dt = datetime.datetime(2026, 1, 7, 9, 0, 0)
    assert next_ts == expected_dt.astimezone().timestamp() * 1000.0


def test_next_transition_returns_none_with_no_schedules():
    assert next_transition([], datetime.datetime.now().timestamp() * 1000.0) is None


def test_next_transition_catches_wrap_window_ending_today():
    # Mon-Fri 22:00-07:00. now = Tue 03:00, inside Monday's window tail.
    # The next boundary is Tue 07:00 (DND turns off), not Tue 22:00.
    s = Schedule(id="w", name="W", days=[1, 2, 3, 4, 5], start="22:00", end="07:00", enabled=True)
    now_dt = datetime.datetime(2026, 1, 6, 3, 0)  # 2026-01-06 is a Tuesday
    now_ms = now_dt.astimezone().timestamp() * 1000.0
    next_ts = next_transition([s], now_ms)
    expected_dt = datetime.datetime(2026, 1, 6, 7, 0)
    assert next_ts == expected_dt.astimezone().timestamp() * 1000.0


def test_next_start_finds_todays_upcoming_start():
    # Thu 2026-07-02 08:00; schedule starts 22:00 on Thursdays (dow 4)
    sched = Schedule(id="w", name="W", days=[4], start="22:00", end="23:00", enabled=True)
    now_dt = datetime.datetime(2026, 7, 2, 8, 0)
    now_ms = now_dt.astimezone().timestamp() * 1000.0
    res = next_start([sched], now_ms)
    expected = datetime.datetime(2026, 7, 2, 22, 0).astimezone().timestamp() * 1000.0
    assert res == expected


def test_next_start_rolls_to_next_matching_day():
    sched = Schedule(id="w", name="W", days=[4], start="22:00", end="23:00", enabled=True)
    now_dt = datetime.datetime(2026, 7, 2, 23, 0)
    now_ms = now_dt.astimezone().timestamp() * 1000.0
    res = next_start([sched], now_ms)
    expected = datetime.datetime(2026, 7, 9, 22, 0).astimezone().timestamp() * 1000.0
    assert res == expected
