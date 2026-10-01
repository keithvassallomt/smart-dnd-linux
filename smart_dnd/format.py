"""Timestamp formatting utilities for Smart DND."""

from __future__ import annotations

import datetime
from typing import Optional

DAYS_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
DAYS_FULL = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAY_MS = 24 * 60 * 60 * 1000.0


def start_of_day_ms(dt: datetime.datetime) -> float:
    d = datetime.datetime(dt.year, dt.month, dt.day)
    return d.astimezone().timestamp() * 1000.0


def py_to_js_dow(py_weekday: int) -> int:
    return (py_weekday + 1) % 7


def format_when(now_ms: float, target_ms: Optional[float]) -> str:
    """Format a target timestamp relative to now_ms.

    e.g. 'Today, 22:00', 'Tomorrow, 07:00', 'Wednesday, 09:00', 'Wed 14 Oct, 18:00'.
    """
    if target_ms is None:
        return "None"

    now_dt = datetime.datetime.fromtimestamp(now_ms / 1000.0)
    tgt_dt = datetime.datetime.fromtimestamp(target_ms / 1000.0)

    time_str = tgt_dt.strftime("%H:%M")
    diff_days = round((start_of_day_ms(tgt_dt) - start_of_day_ms(now_dt)) / DAY_MS)
    dow = py_to_js_dow(tgt_dt.weekday())

    if diff_days == 0:
        return f"Today, {time_str}"
    elif diff_days == 1:
        return f"Tomorrow, {time_str}"
    elif 2 <= diff_days <= 6:
        return f"{DAYS_FULL[dow]}, {time_str}"
    else:
        return f"{DAYS_SHORT[dow]} {tgt_dt.day} {MONTHS[tgt_dt.month - 1]}, {time_str}"
