"""Schedule evaluation logic ported from smart-dnd with DST and midnight-crossing support."""

from __future__ import annotations

import datetime
from typing import List, Optional

from smart_dnd.models import Schedule


def to_minutes(hhmm: str) -> int:
    """Parse 'HH:MM' string to total minutes from midnight."""
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def prev_dow(dow: int) -> int:
    """Get previous day of week (0=Sun, ..., 6=Sat)."""
    return (dow + 6) % 7


def py_to_js_dow(py_weekday: int) -> int:
    """Convert Python weekday (0=Mon..6=Sun) to JS DOW (0=Sun..6=Sat)."""
    return (py_weekday + 1) % 7


def local_date_offset(base_date: datetime.date, day_offset: int) -> datetime.date:
    """Add day_offset to a date."""
    return base_date + datetime.timedelta(days=day_offset)


def local_ts(now_dt: datetime.datetime, day_offset: int, minutes: int) -> float:
    """Local wall-clock timestamp in milliseconds on (now_dt.date() + day_offset).

    Interpreting fields as local wall clock ensures correctness across DST transitions.
    """
    target_date = local_date_offset(now_dt.date(), day_offset)
    target_dt = datetime.datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        minutes // 60,
        minutes % 60,
        0,
    )
    return target_dt.astimezone().timestamp() * 1000.0


def local_dow(now_dt: datetime.datetime, day_offset: int) -> int:
    """Get day of week (0=Sun..6=Sat) on (now_dt.date() + day_offset)."""
    target_date = local_date_offset(now_dt.date(), day_offset)
    return py_to_js_dow(target_date.weekday())


def schedule_active_at(schedule: Schedule, dow: int, minutes: int) -> bool:
    """Check if a single schedule is active at given day-of-week and minute of day."""
    if not schedule.enabled:
        return False
    start = to_minutes(schedule.start)
    end = to_minutes(schedule.end)
    if start == end:
        return False

    starts_today = dow in schedule.days
    if start < end:
        return starts_today and (start <= minutes < end)

    # Wraps midnight: head today (>= start) or tail from yesterday's window (< end)
    head = starts_today and (minutes >= start)
    tail = (prev_dow(dow) in schedule.days) and (minutes < end)
    return head or tail


def any_active_at(schedules: List[Schedule], dow: int, minutes: int) -> bool:
    """Return True if any enabled schedule is active at dow and minute."""
    return any(schedule_active_at(s, dow, minutes) for s in schedules)


def next_transition(schedules: List[Schedule], now_ms: float) -> Optional[float]:
    """Find the earliest boundary timestamp (start or end) strictly after now_ms."""
    enabled = [s for s in schedules if s.enabled and to_minutes(s.start) != to_minutes(s.end)]
    if not enabled:
        return None

    now_dt = datetime.datetime.fromtimestamp(now_ms / 1000.0)
    best: Optional[float] = None

    for s in enabled:
        start = to_minutes(s.start)
        end = to_minutes(s.end)
        wraps = start > end

        # Start at d = -1 so a window that began yesterday and wraps past midnight
        # still has its end (which falls today) counted.
        for d in range(-1, 9):
            d_dow = local_dow(now_dt, d)
            if d_dow in s.days:
                start_ts = local_ts(now_dt, d, start)
                if start_ts > now_ms and (best is None or start_ts < best):
                    best = start_ts

                end_ts = local_ts(now_dt, d + (1 if wraps else 0), end)
                if end_ts > now_ms and (best is None or end_ts < best):
                    best = end_ts

    return best


def next_start(schedules: List[Schedule], now_ms: float) -> Optional[float]:
    """Find the earliest start boundary timestamp strictly after now_ms."""
    enabled = [s for s in schedules if s.enabled and to_minutes(s.start) != to_minutes(s.end)]
    if not enabled:
        return None

    now_dt = datetime.datetime.fromtimestamp(now_ms / 1000.0)
    best: Optional[float] = None

    for s in enabled:
        start = to_minutes(s.start)
        for d in range(0, 8):
            if local_dow(now_dt, d) in s.days:
                ts = local_ts(now_dt, d, start)
                if ts > now_ms and (best is None or ts < best):
                    best = ts

    return best
