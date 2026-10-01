"""Calendar rule matching logic ported from smart-dnd."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

from smart_dnd.models import CalendarEvent, CalendarRule

logger = logging.getLogger(__name__)


def title_matches(rule: CalendarRule, summary: Any) -> bool:
    """Check if event summary matches the rule's pattern and match type."""
    if not isinstance(summary, str) or not isinstance(rule.pattern, str):
        return False

    hay = summary.lower()
    needle = rule.pattern.lower()

    if rule.match_type == "contains":
        return needle in hay
    elif rule.match_type == "startsWith":
        return hay.startswith(needle)
    elif rule.match_type == "endsWith":
        return hay.endswith(needle)
    elif rule.match_type == "regex":
        try:
            return bool(re.search(rule.pattern, summary, re.IGNORECASE))
        except re.error as e:
            logger.warning("smart-dnd: invalid regex '%s': %s", rule.pattern, e)
            return False
    return False


def source_allowed(rule: CalendarRule, source_uid: str) -> bool:
    """Check if the rule applies to this calendar source UID."""
    return len(rule.calendars) == 0 or source_uid in rule.calendars


def event_window(rule: CalendarRule, event: CalendarEvent) -> Dict[str, float]:
    """Calculate the active window for an event in milliseconds."""
    return {
        "on": (event.start + rule.enable_offset_min * 60) * 1000.0,
        "off": (event.end + rule.disable_offset_min * 60) * 1000.0,
    }


def _matches(
    rules: List[CalendarRule],
    events: List[CalendarEvent],
    ignore_all_day: bool,
) -> Iterator[Tuple[CalendarRule, CalendarEvent]]:
    """Yield every (rule, event) pair where the rule applies to the event."""
    for rule in rules:
        if not rule.enabled:
            continue
        for ev in events:
            if ignore_all_day and ev.all_day:
                continue
            if not source_allowed(rule, ev.source_uid):
                continue
            if not title_matches(rule, ev.summary):
                continue
            yield rule, ev


def matching_windows(
    rules: List[CalendarRule],
    events: List[CalendarEvent],
    ignore_all_day: bool,
) -> List[Dict[str, float]]:
    """Return all active time windows from matching rules and events."""
    return [event_window(rule, ev) for rule, ev in _matches(rules, events, ignore_all_day)]


def active_match_at(
    rules: List[CalendarRule],
    events: List[CalendarEvent],
    now_ms: float,
    ignore_all_day: bool,
) -> Optional[Tuple[CalendarRule, CalendarEvent]]:
    """Return the first (rule, event) pair whose window contains now_ms, if any."""
    for rule, ev in _matches(rules, events, ignore_all_day):
        w = event_window(rule, ev)
        if w["on"] <= now_ms < w["off"]:
            return rule, ev
    return None


def rules_active_at(
    rules: List[CalendarRule],
    events: List[CalendarEvent],
    now_ms: float,
    ignore_all_day: bool,
) -> bool:
    """Return True if any calendar rule is currently active."""
    return active_match_at(rules, events, now_ms, ignore_all_day) is not None


def calendar_next_transition(
    rules: List[CalendarRule],
    events: List[CalendarEvent],
    now_ms: float,
    ignore_all_day: bool,
) -> Optional[float]:
    """Find earliest on/off boundary in the future from calendar rules."""
    best: Optional[float] = None
    for w in matching_windows(rules, events, ignore_all_day):
        for edge in (w["on"], w["off"]):
            if edge > now_ms and (best is None or edge < best):
                best = edge
    return best


def next_enable(
    rules: List[CalendarRule],
    events: List[CalendarEvent],
    now_ms: float,
    ignore_all_day: bool,
) -> Optional[float]:
    """Find earliest upcoming 'on' boundary strictly after now_ms."""
    best: Optional[float] = None
    for w in matching_windows(rules, events, ignore_all_day):
        if w["on"] > now_ms and (best is None or w["on"] < best):
            best = w["on"]
    return best
