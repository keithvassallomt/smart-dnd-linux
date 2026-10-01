"""Smart DND Daemon runner with GLib event loop, timers, and DBus sleep/resume hooks."""

from __future__ import annotations

import datetime
import logging
import signal
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib

from smart_dnd.config import load_config, save_config
from smart_dnd.coordinator import compute_desired, reconcile
from smart_dnd.ipc import IpcServer
from smart_dnd.matcher import (
    active_match_at,
    calendar_next_transition,
    next_enable,
)
from smart_dnd.models import CalendarEvent, Config, Status
from smart_dnd.plugins.manager import PluginManager
from smart_dnd.scheduler import (
    first_active_at,
    next_start,
    next_transition,
    py_to_js_dow,
)
from smart_dnd.sni import StatusNotifierTray

logger = logging.getLogger(__name__)

# Calendar events are re-fetched in the background once the cache is older than this.
EVENT_CACHE_TTL_SEC = 60.0


class SmartDndDaemon:
    """Core daemon service managing schedules, calendar monitoring, and DND state."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        self.config_path = config_path
        self.config: Config = load_config(config_path)
        self.plugin_manager = PluginManager()

        self._calendar_plugin = self.plugin_manager.get_calendar_plugin(self.config.calendar_backend)
        self._notification_plugin = self.plugin_manager.get_notification_plugin(self.config.notification_backend)

        self._owned: bool = False
        self._last_desired: bool = False
        self._timer_id: Optional[int] = None
        self._sleep_sub_id: int = 0
        self._main_loop = GLib.MainLoop()

        self.status = Status(
            notification_backend=self.config.notification_backend,
            calendar_backend=self.config.calendar_backend,
        )

        self._ipc_server = IpcServer(self._dispatch_ipc)
        self.tray = StatusNotifierTray(
            on_toggle_dnd=self.toggle_dnd,
            on_open_gui=self._toggle_gui_tray,
            on_quit=self.stop,
            monochrome=self.config.monochrome_tray_icon,
        )
        self._cached_events: List[CalendarEvent] = []
        self._last_event_fetch_ts: float = 0.0
        self._fetch_in_flight: bool = False
        # Bumped when the calendar plugin changes, so a late result from the old one is dropped.
        self._calendar_generation: int = 0
        self._stopped: bool = False

    def _toggle_gui_tray(self) -> None:
        from smart_dnd.sni import toggle_gui
        toggle_gui()

    def toggle_dnd(self) -> Status:
        """Flip DND by hand. Turning it off releases daemon ownership."""
        cur = self._notification_plugin.is_dnd_enabled()
        self._notification_plugin.set_dnd(not cur)
        if cur:
            self._owned = False
        return self.evaluate()

    def start(self) -> None:
        logger.info("Starting Smart DND Daemon...")

        # 1. Listen on Unix IPC socket
        server_sock = self._ipc_server.start()
        GLib.io_add_watch(server_sock.fileno(), GLib.IOCondition.IN, self._on_socket_ready, server_sock)

        # 2. Start StatusNotifierItem Tray
        self.tray.start()

        # 2. Hook systemd logind PrepareForSleep signal
        try:
            self._system_bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            self._sleep_sub_id = self._system_bus.signal_subscribe(
                "org.freedesktop.login1",
                "org.freedesktop.login1.Manager",
                "PrepareForSleep",
                "/org/freedesktop/login1",
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_prepare_for_sleep,
                None,
            )
        except Exception as e:
            self._system_bus = None
            logger.warning("Could not subscribe to PrepareForSleep: %s", e)

        # 3. Setup signals (SIGINT, SIGTERM)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._on_stop_signal, None)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._on_stop_signal, None)

        # 4. Initial evaluation
        self.evaluate()

        # 5. Run main loop
        try:
            self._main_loop.run()
        finally:
            self.stop()

    def stop(self) -> None:
        # Runs twice on a signal: once from the handler, again from start()'s finally.
        if self._stopped:
            return
        self._stopped = True
        logger.info("Stopping Smart DND Daemon...")
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

        if self._sleep_sub_id and getattr(self, "_system_bus", None):
            self._system_bus.signal_unsubscribe(self._sleep_sub_id)
            self._sleep_sub_id = 0

        # Release DND if we owned it and it is still on
        if self._owned:
            try:
                if self._notification_plugin.is_dnd_enabled():
                    self._notification_plugin.set_dnd(False)
            except Exception as e:
                logger.error("Failed releasing DND on shutdown: %s", e)
            self._owned = False

        self.tray.stop()
        self._ipc_server.close()
        if self._main_loop.is_running():
            self._main_loop.quit()

    def _on_stop_signal(self, user_data: Any) -> bool:
        self.stop()
        return GLib.SOURCE_REMOVE

    def _on_prepare_for_sleep(
        self,
        connection: Gio.DBusConnection,
        sender_name: str,
        object_path: str,
        interface_name: str,
        signal_name: str,
        parameters: GLib.Variant,
    ) -> None:
        about_to_sleep = parameters.get_child_value(0).get_boolean()
        if not about_to_sleep:
            logger.info("System resumed from sleep. Re-evaluating rules...")
            self._last_event_fetch_ts = 0.0  # Invalidate event cache
            self.evaluate()

    def _on_socket_ready(self, source_fd: int, condition: GLib.IOCondition, server_sock: Any) -> bool:
        if condition & GLib.IOCondition.IN:
            try:
                client_sock, _ = server_sock.accept()
                self._ipc_server.handle_client(client_sock)
            except Exception as e:
                logger.debug("Socket accept error: %s", e)
        return GLib.SOURCE_CONTINUE

    @staticmethod
    def _event_range(now_sec: float) -> Tuple[float, float]:
        return now_sec - 86400.0, now_sec + 7 * 86400.0

    def _get_events(self, now_sec: float) -> List[CalendarEvent]:
        """Return cached events, starting a background refresh when the cache is stale.

        Fetching runs off the main loop so a slow calendar backend (an EDS factory
        starting up, a remote CalDAV source) never blocks IPC, the tray or timers.
        Stale events still give correct timings until the refresh lands.
        """
        if now_sec - self._last_event_fetch_ts > EVENT_CACHE_TTL_SEC:
            self._start_event_refresh(now_sec)
        return self._cached_events

    def _start_event_refresh(self, now_sec: float) -> None:
        if self._fetch_in_flight:
            return
        self._fetch_in_flight = True
        plugin = self._calendar_plugin
        generation = self._calendar_generation
        start_range, end_range = self._event_range(now_sec)

        def worker() -> None:
            events: Optional[List[CalendarEvent]]
            try:
                events = plugin.get_events(start_range, end_range)
            except Exception as e:
                logger.error("Error fetching calendar events: %s", e)
                events = None
            GLib.idle_add(self._on_events_fetched, generation, events, now_sec)

        threading.Thread(target=worker, name="smart-dnd-calendar", daemon=True).start()

    def _on_events_fetched(
        self,
        generation: int,
        events: Optional[List[CalendarEvent]],
        fetched_at: float,
    ) -> bool:
        self._fetch_in_flight = False
        if generation == self._calendar_generation:
            if events is not None:
                self._cached_events = events
            # Stamp failures too, so a broken backend is retried after the TTL rather than in a loop.
            self._last_event_fetch_ts = fetched_at
        self.evaluate()
        return GLib.SOURCE_REMOVE

    def refresh_events_blocking(self) -> None:
        """Fetch events synchronously, for one-shot use without a main loop (`smart-dnd eval`)."""
        now_sec = time.time()
        start_range, end_range = self._event_range(now_sec)
        try:
            self._cached_events = self._calendar_plugin.get_events(start_range, end_range)
        except Exception as e:
            logger.error("Error fetching calendar events: %s", e)
        self._last_event_fetch_ts = now_sec

    def evaluate(self) -> Status:
        now_sec = time.time()
        now_ms = now_sec * 1000.0
        now_dt = datetime.datetime.fromtimestamp(now_sec)
        dow = py_to_js_dow(now_dt.weekday())
        minutes = now_dt.hour * 60 + now_dt.minute

        events = self._get_events(now_sec)

        active_schedule = first_active_at(self.config.schedules, dow, minutes)
        active_match = active_match_at(self.config.calendar_rules, events, now_ms, self.config.ignore_all_day)
        schedule_active = active_schedule is not None
        calendar_active = active_match is not None

        desired = compute_desired(self.config.master_enabled, schedule_active, calendar_active)
        # Query once per evaluation: shell-based backends spawn a process per call.
        dnd_on = self._notification_plugin.is_dnd_enabled()

        rec = reconcile(desired, self._last_desired, self._owned, dnd_on)
        self._owned = rec.owned
        self._last_desired = desired

        if rec.action == "on":
            logger.info("Enabling DND (Triggered by Smart DND)")
            if self._notification_plugin.set_dnd(True):
                dnd_on = True
        elif rec.action == "off":
            logger.info("Disabling DND (Smart DND window ended)")
            if self._notification_plugin.set_dnd(False):
                dnd_on = False

        # Calculate reason
        reason = "idle"
        trigger_name = None
        if desired:
            if active_schedule is not None:
                reason, trigger_name = "schedule", active_schedule.name
            elif active_match is not None:
                reason, trigger_name = "calendar", active_match[1].summary
        elif dnd_on and not self._owned:
            reason = "manual"

        # Calculate next transition
        candidates_on: List[float] = []
        candidates_off: List[float] = []

        sched_trans = next_transition(self.config.schedules, now_ms)
        cal_trans = calendar_next_transition(self.config.calendar_rules, events, now_ms, self.config.ignore_all_day)

        if self.config.master_enabled:
            s_start = next_start(self.config.schedules, now_ms)
            c_start = next_enable(self.config.calendar_rules, events, now_ms, self.config.ignore_all_day)
            if s_start is not None:
                candidates_on.append(s_start)
            if c_start is not None:
                candidates_on.append(c_start)

        if sched_trans is not None:
            candidates_off.append(sched_trans)
        if cal_trans is not None:
            candidates_off.append(cal_trans)

        next_on_ms = min(candidates_on) if candidates_on else None
        next_off_ms = min(candidates_off) if (desired and candidates_off) else None

        self.status = Status(
            active=dnd_on,
            reason=reason,
            trigger_name=trigger_name,
            next_on_ms=next_on_ms,
            next_off_ms=next_off_ms,
            owned=self._owned,
            notification_backend=self.config.notification_backend,
            calendar_backend=self.config.calendar_backend,
        )

        self._arm_timer(now_ms, candidates_off + candidates_on)
        self.tray.update_status(self.status)
        return self.status

    def _arm_timer(self, now_ms: float, candidates: List[float]) -> None:
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

        future_candidates = [c for c in candidates if c > now_ms]
        if not future_candidates:
            # Poll at least once every 15 minutes as a fallback
            seconds_delay = 900
        else:
            earliest_next = min(future_candidates)
            seconds_delay = max(1, int((earliest_next - now_ms) / 1000.0) + 1)
            # Cap maximum sleep to 15 minutes so calendar changes are picked up
            seconds_delay = min(seconds_delay, 900)

        logger.debug("Next timer wake in %d seconds", seconds_delay)
        self._timer_id = GLib.timeout_add_seconds(seconds_delay, self._on_timer_fired, None)

    def _on_timer_fired(self, user_data: Any) -> bool:
        self._timer_id = None
        self.evaluate()
        return GLib.SOURCE_REMOVE

    def reload_plugins(self) -> None:
        self._calendar_plugin = self.plugin_manager.get_calendar_plugin(self.config.calendar_backend)
        self._notification_plugin = self.plugin_manager.get_notification_plugin(self.config.notification_backend)
        self._calendar_generation += 1
        self._cached_events = []
        self._last_event_fetch_ts = 0.0

    def _dispatch_ipc(self, method: str, params: Dict[str, Any]) -> Any:
        if method == "get_status":
            return self.status.to_dict()
        elif method == "get_config":
            return self.config.to_dict()
        elif method == "save_config":
            new_conf_dict = params.get("config", {})
            new_config = Config.from_dict(new_conf_dict)
            plugins_changed = (
                new_config.calendar_backend != self.config.calendar_backend
                or new_config.notification_backend != self.config.notification_backend
            )
            self.config = new_config
            save_config(self.config, self.config_path)
            if plugins_changed:
                self.reload_plugins()
            self.tray.set_monochrome(self.config.monochrome_tray_icon)
            self.evaluate()
            return True
        elif method == "evaluate":
            return self.evaluate().to_dict()
        elif method == "toggle_dnd":
            return self.toggle_dnd().to_dict()
        elif method == "list_calendars":
            return [
                {"uid": c.uid, "name": c.name, "color": c.color, "enabled": c.enabled}
                for c in self._calendar_plugin.list_calendars()
            ]
        elif method == "get_events":
            now_sec = time.time()
            events = self._get_events(now_sec)
            return [
                {
                    "uid": e.uid,
                    "summary": e.summary,
                    "start": e.start,
                    "end": e.end,
                    "all_day": e.all_day,
                    "source_uid": e.source_uid,
                    "source_name": e.source_name,
                }
                for e in events
            ]
        elif method == "list_plugins":
            return {
                "calendar": list(self.plugin_manager.calendar_plugins.keys()),
                "notifications": list(self.plugin_manager.notification_plugins.keys()),
                "gui": list(self.plugin_manager.gui_plugins.keys()),
            }
        else:
            raise ValueError(f"Unknown IPC method: {method}")
