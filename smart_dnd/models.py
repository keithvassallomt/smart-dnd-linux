"""Data models for Smart DND."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional


@dataclass
class Schedule:
    id: str
    name: str = "Schedule"
    days: List[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])  # 0=Sun, 1=Mon, ..., 6=Sat
    start: str = "22:00"
    end: str = "07:00"
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Schedule:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "Schedule")),
            days=list(data.get("days", [1, 2, 3, 4, 5])),
            start=str(data.get("start", "22:00")),
            end=str(data.get("end", "07:00")),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class CalendarRule:
    id: str
    name: str = "Rule"
    match_type: str = "contains"  # contains, startsWith, endsWith, regex
    pattern: str = ""
    calendars: List[str] = field(default_factory=list)  # Empty means all calendars
    enable_offset_min: int = 0
    disable_offset_min: int = 0
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalendarRule:
        # Support both camelCase and snake_case for interoperability
        match_type = data.get("match_type") or data.get("matchType", "contains")
        enable_offset = data.get("enable_offset_min")
        if enable_offset is None:
            enable_offset = data.get("enableOffsetMin", 0)
        disable_offset = data.get("disable_offset_min")
        if disable_offset is None:
            disable_offset = data.get("disableOffsetMin", 0)

        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "Rule")),
            match_type=str(match_type),
            pattern=str(data.get("pattern", "")),
            calendars=list(data.get("calendars", [])),
            enable_offset_min=int(enable_offset),
            disable_offset_min=int(disable_offset),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class CalendarSource:
    uid: str
    name: str
    color: Optional[str] = None
    enabled: bool = True


@dataclass
class CalendarEvent:
    uid: str
    summary: str
    start: float  # Unix timestamp in seconds
    end: float  # Unix timestamp in seconds
    all_day: bool
    source_uid: str
    source_name: Optional[str] = None


@dataclass
class Status:
    active: bool = False
    reason: str = "idle"  # idle, schedule, calendar, manual
    trigger_name: Optional[str] = None
    next_on_ms: Optional[float] = None
    next_off_ms: Optional[float] = None
    owned: bool = False
    notification_backend: str = ""
    calendar_backend: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Config:
    master_enabled: bool = True
    ignore_all_day: bool = True
    calendar_backend: str = "evolution"
    notification_backend: str = "caelestia"
    gui_backend: str = "adwaita"
    monochrome_tray_icon: bool = False
    schedules: List[Schedule] = field(default_factory=list)
    calendar_rules: List[CalendarRule] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "master_enabled": self.master_enabled,
            "ignore_all_day": self.ignore_all_day,
            "calendar_backend": self.calendar_backend,
            "notification_backend": self.notification_backend,
            "gui_backend": self.gui_backend,
            "monochrome_tray_icon": self.monochrome_tray_icon,
            "schedules": [asdict(s) for s in self.schedules],
            "calendar_rules": [asdict(r) for r in self.calendar_rules],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        schedules = [Schedule.from_dict(s) for s in data.get("schedules", [])]
        calendar_rules = [CalendarRule.from_dict(r) for r in data.get("calendar_rules", [])]
        monochrome = data.get("monochrome_tray_icon")
        if monochrome is None:
            monochrome = data.get("monochromeTrayIcon", False)
        return cls(
            master_enabled=bool(data.get("master_enabled", True)),
            ignore_all_day=bool(data.get("ignore_all_day", True)),
            calendar_backend=str(data.get("calendar_backend", "evolution")),
            notification_backend=str(data.get("notification_backend", "caelestia")),
            gui_backend=str(data.get("gui_backend", "adwaita")),
            monochrome_tray_icon=bool(monochrome),
            schedules=schedules,
            calendar_rules=calendar_rules,
        )
