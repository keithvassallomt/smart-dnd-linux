"""Tests for the daemon's evaluate loop and background calendar refresh."""

import datetime
import threading
import time

import pytest
from gi.repository import GLib

from smart_dnd.models import CalendarEvent, CalendarRule, Schedule
from smart_dnd.plugins.calendar.base import CalendarPlugin
from smart_dnd.plugins.notifications.base import NotificationPlugin


class FakeNotifications(NotificationPlugin):
    plugin_id = "fake"

    def __init__(self) -> None:
        self.dnd = False
        self.queries = 0
        self.sets = []

    def is_dnd_enabled(self) -> bool:
        self.queries += 1
        return self.dnd

    def set_dnd(self, enabled: bool) -> bool:
        self.sets.append(enabled)
        self.dnd = enabled
        return True


class FakeCalendar(CalendarPlugin):
    plugin_id = "fake"

    def __init__(self, events=None, gate=None, error=None) -> None:
        self.events = events or []
        self.gate = gate
        self.error = error
        self.fetches = 0

    def list_calendars(self):
        return []

    def get_events(self, start_ts, end_ts):
        self.fetches += 1
        if self.gate is not None:
            self.gate.wait(5)
        if self.error is not None:
            raise self.error
        return list(self.events)


class FakePluginManager:
    calendar = None
    notifications = None

    def __init__(self) -> None:
        self.calendar_plugins = {}
        self.notification_plugins = {}
        self.gui_plugins = {}

    def get_calendar_plugin(self, plugin_id):
        return FakePluginManager.calendar

    def get_notification_plugin(self, plugin_id):
        return FakePluginManager.notifications


@pytest.fixture
def make_daemon(tmp_path, monkeypatch):
    # Keep the IPC socket path away from a real running daemon.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setattr("smart_dnd.daemon.PluginManager", FakePluginManager)
    from smart_dnd.daemon import SmartDndDaemon

    created = []

    def make(calendar=None, schedules=(), rules=()):
        FakePluginManager.calendar = calendar or FakeCalendar()
        FakePluginManager.notifications = FakeNotifications()
        d = SmartDndDaemon(config_path=str(tmp_path / "config.json"))
        d.config.schedules = list(schedules)
        d.config.calendar_rules = list(rules)
        created.append(d)
        return d

    yield make
    for d in created:
        d.stop()


def wait_for_fetch(daemon, timeout=5.0):
    """Pump the default main context until the background fetch has been applied."""
    ctx = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while daemon._fetch_in_flight and time.monotonic() < deadline:
        ctx.iteration(False)
        time.sleep(0.01)
    assert not daemon._fetch_in_flight


def schedule_around_now() -> Schedule:
    """An every-day schedule from an hour ago to an hour ahead (wrapping midnight if needed)."""
    now = datetime.datetime.now()
    minutes = now.hour * 60 + now.minute

    def hhmm(m: int) -> str:
        m %= 1440
        return f"{m // 60:02d}:{m % 60:02d}"

    return Schedule(id="s", name="Focus", days=list(range(7)), start=hhmm(minutes - 60), end=hhmm(minutes + 60))


def test_evaluate_queries_dnd_state_once(make_daemon):
    d = make_daemon(schedules=[schedule_around_now()])
    status = d.evaluate()

    notif = FakePluginManager.notifications
    assert notif.queries == 1
    assert notif.sets == [True]
    assert status.active is True
    assert status.reason == "schedule"
    assert status.trigger_name == "Focus"


def test_calendar_fetch_does_not_block_evaluate(make_daemon):
    now = time.time()
    ev = CalendarEvent(uid="e", summary="Team Meeting", start=now - 600, end=now + 600, all_day=False, source_uid="c")
    gate = threading.Event()
    d = make_daemon(
        calendar=FakeCalendar(events=[ev], gate=gate),
        rules=[CalendarRule(id="r", pattern="meeting")],
    )

    started = time.monotonic()
    status = d.evaluate()
    assert time.monotonic() - started < 1.0  # returned while the backend is still blocked
    assert status.reason == "idle"

    gate.set()
    wait_for_fetch(d)
    assert d.status.active is True
    assert d.status.reason == "calendar"
    assert d.status.trigger_name == "Team Meeting"


def test_failed_fetch_is_retried_after_ttl_not_in_a_loop(make_daemon):
    cal = FakeCalendar(error=RuntimeError("EDS down"))
    d = make_daemon(calendar=cal)
    d.evaluate()
    wait_for_fetch(d)
    d.evaluate()
    assert cal.fetches == 1
    assert d._last_event_fetch_ts > 0


def test_late_result_from_old_backend_is_dropped(make_daemon):
    d = make_daemon()
    old_generation = d._calendar_generation
    d.reload_plugins()
    stale = [CalendarEvent(uid="x", summary="Old", start=0, end=1, all_day=False, source_uid="c")]
    d._fetch_in_flight = True
    d._on_events_fetched(old_generation, stale, time.time())
    assert all(e.uid != "x" for e in d._cached_events)
    wait_for_fetch(d)


def test_refresh_events_blocking_feeds_one_shot_evaluate(make_daemon):
    now = time.time()
    ev = CalendarEvent(uid="e", summary="Standup", start=now - 60, end=now + 60, all_day=False, source_uid="c")
    d = make_daemon(calendar=FakeCalendar(events=[ev]), rules=[CalendarRule(id="r", pattern="stand")])
    d.refresh_events_blocking()
    status = d.evaluate()
    assert status.reason == "calendar"
    assert not d._fetch_in_flight
