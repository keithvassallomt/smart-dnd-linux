"""Smart DND Daemon runner with GLib event loop, timers, and DBus sleep/resume hooks."""

from __future__ import annotations

import datetime
import logging
import signal
import sys
import time
from typing import Any, Dict, List, Optional

import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib

from smart_dnd.config import load_config, save_config
from smart_dnd.coordinator import compute_desired, reconcile
from smart_dnd.ipc import IpcServer
from smart_dnd.matcher import (
    calendar_next_transition,
    next_enable,
    rules_active_at,
)
from smart_dnd.models import CalendarEvent, Config, Status
from smart_dnd.plugins.manager import PluginManager
from smart_dnd.scheduler import (
    any_active_at,
    next_start,
    next_transition,
    py_to_js_dow,
)
from smart_dnd.sni import StatusNotifierTray

logger = logging.getLogger(__name__)


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
            on_toggle_dnd=self._toggle_dnd_tray,
            on_open_gui=self._toggle_gui_tray,
            on_quit=self.stop,
        )
        self._cached_events: List[CalendarEvent] = []
        self._last_event_fetch_ts: float = 0.0

    def _toggle_gui_tray(self) -> None:
        from smart_dnd.sni import toggle_gui
        toggle_gui()

    def _toggle_dnd_tray(self) -> Status:
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

    def _get_events(self, now_sec: float) -> List[CalendarEvent]:
        # Cache events for 60 seconds unless invalidated
        if now_sec - self._last_event_fetch_ts > 60.0 or not self._cached_events:
            start_range = now_sec - 86400.0
            end_range = now_sec + 7 * 86400.0
            try:
                self._cached_events = self._calendar_plugin.get_events(start_range, end_range)
                self._last_event_fetch_ts = now_sec
            except Exception as e:
                logger.error("Error fetching calendar events: %s", e)
        return self._cached_events

    def evaluate(self) -> Status:
        now_sec = time.time()
        now_ms = now_sec * 1000.0
        now_dt = datetime.datetime.fromtimestamp(now_sec)
        dow = py_to_js_dow(now_dt.weekday())
        minutes = now_dt.hour * 60 + now_dt.minute

        events = self._get_events(now_sec)

        schedule_active = any_active_at(self.config.schedules, dow, minutes)
        calendar_active = rules_active_at(self.config.calendar_rules, events, now_ms, self.config.ignore_all_day)

        desired = compute_desired(self.config.master_enabled, schedule_active, calendar_active)
        dnd_on = self._notification_plugin.is_dnd_enabled()

        rec = reconcile(desired, self._last_desired, self._owned, dnd_on)
        self._owned = rec.owned
        self._last_desired = desired

        if rec.action == "on":
            logger.info("Enabling DND (Triggered by Smart DND)")
            self._notification_plugin.set_dnd(True)
        elif rec.action == "off":
            logger.info("Disabling DND (Smart DND window ended)")
            self._notification_plugin.set_dnd(False)

        # Calculate reason
        reason = "idle"
        trigger_name = None
        if desired:
            if schedule_active:
                reason = "schedule"
            elif calendar_active:
                reason = "calendar"
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
            active=self._notification_plugin.is_dnd_enabled(),
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
        self._last_event_fetch_ts = 0.0

    def _dispatch_ipc(self, method: str, params: Dict[str, Any]) -> Any:
        if method == "get_status":
            return self.status.to_dict()
        elif method == "get_config":
            return self.config.to_dict()
        elif method == "save_config":
            new_conf_dict = params.get("config", {})
            self.config = Config.from_dict(new_conf_dict)
            save_config(self.config, self.config_path)
            self.reload_plugins()
            self.evaluate()
            return True
        elif method == "evaluate":
            return self.evaluate().to_dict()
        elif method == "toggle_dnd":
            cur = self._notification_plugin.is_dnd_enabled()
            self._notification_plugin.set_dnd(not cur)
            # Manual toggle releases daemon ownership if turning off
            if cur:
                self._owned = False
            return self.evaluate().to_dict()
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
