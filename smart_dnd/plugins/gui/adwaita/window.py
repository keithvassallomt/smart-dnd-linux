"""Main Application Window in Libadwaita."""

from __future__ import annotations

import datetime
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Adw, Gio, GLib, Gtk

from smart_dnd import __version__, autostart
from smart_dnd.config import save_config
from smart_dnd.host import IN_FLATPAK
from smart_dnd.models import CalendarSource, Config, Status
from smart_dnd.plugins.gui.adwaita.calendar_page import CalendarPage
from smart_dnd.plugins.gui.adwaita.general_dialog import GeneralSettingsDialog
from smart_dnd.plugins.gui.adwaita.schedule_page import SchedulePage

# Edits are written once typing pauses for this long.
SAVE_DEBOUNCE_MS = 400

FALLBACK_PLUGINS: Dict[str, List[str]] = {
    "calendar": ["evolution"],
    "notifications": ["caelestia", "swaync", "dunst"],
    "gui": ["adwaita"],
}


class MainWindow(Adw.ApplicationWindow):
    """Main preferences window for Smart DND.

    Every daemon call runs on one background worker, so the GTK main thread never
    waits on IPC. The daemon is single-threaded and each evaluation shells out to
    the notification backend, so a call can take hundreds of milliseconds.
    """

    def __init__(self, app: Adw.Application, client: Any, config: Config) -> None:
        super().__init__(application=app, title="Smart DND")
        self.client = client
        self.config = config
        self.set_default_size(780, 680)

        self._available_plugins: Dict[str, List[str]] = {k: list(v) for k, v in FALLBACK_PLUGINS.items()}
        self._calendars: List[CalendarSource] = []
        self._events: List[Any] = []

        # A single worker keeps daemon calls in order and stops saves piling up as parallel requests.
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="smart-dnd-ipc")
        self._save_timer_id: Optional[int] = None
        self._save_lock = threading.Lock()
        self._pending_save: Optional[Dict[str, Any]] = None
        self._status_in_flight = False

        self._build_ui()
        self.connect("close-request", self._on_close_request)

        self._refresh_status()
        # Own thread, not the IPC worker: a cold Evolution Data Server can take several
        # seconds here, and saves and status updates must not queue behind it.
        self._run_in_background(self._load_data, self._apply_data, serial=False)

        # Poll status every 3 seconds to reflect live state
        GLib.timeout_add_seconds(3, self._on_poll)

    # -- Background work -----------------------------------------------------

    def _run_in_background(
        self,
        fn: Callable[[], Any],
        on_done: Optional[Callable[[Any, Optional[Exception]], None]] = None,
        serial: bool = True,
    ) -> None:
        """Run fn off the main thread and hand (result, error) to on_done on the main thread.

        serial=True queues it on the IPC worker; False gives it a thread of its own.
        """

        def task() -> None:
            try:
                result, error = fn(), None
            except Exception as e:
                result, error = None, e
            if on_done is not None:
                GLib.idle_add(self._deliver, on_done, result, error)

        if serial:
            self._worker.submit(task)
        else:
            threading.Thread(target=task, daemon=True).start()

    @staticmethod
    def _deliver(on_done: Callable[[Any, Optional[Exception]], None], result: Any, error: Optional[Exception]) -> bool:
        on_done(result, error)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _offline_as_none(fn: Callable[[], Any]) -> Any:
        """Call the daemon; None means it is not reachable."""
        try:
            return fn()
        except OSError:
            return None

    def _load_data(self) -> Tuple[Dict[str, List[str]], List[CalendarSource], List[Any]]:
        return self._fetch_plugins(), self._fetch_calendars(), self._fetch_events()

    def _apply_data(self, result: Any, error: Optional[Exception]) -> None:
        if error is not None or result is None:
            return
        plugins, cals, events = result
        self._available_plugins = plugins
        self._calendars = cals
        self._events = events
        self.cal_page.set_calendar_data(cals, events)

    def _fetch_plugins(self) -> Dict[str, List[str]]:
        try:
            if self.client and self.client.is_daemon_running():
                return self.client.list_plugins()
        except Exception:
            pass
        return {k: list(v) for k, v in FALLBACK_PLUGINS.items()}

    def _fetch_calendars(self) -> List[CalendarSource]:
        try:
            if self.client and self.client.is_daemon_running():
                return self.client.list_calendars()
        except Exception:
            pass
        # Fallback to direct Evolution plugin if daemon isn't running
        try:
            from smart_dnd.plugins.calendar.evolution import EvolutionCalendarPlugin
            return EvolutionCalendarPlugin().list_calendars()
        except Exception:
            return []

    def _fetch_events(self) -> List[Any]:
        if self.client and self.client.is_daemon_running():
            try:
                events = self.client.get_events()
                if events:
                    return events
            except Exception:
                pass
        try:
            from smart_dnd.plugins.manager import PluginManager
            pm = PluginManager()
            cal_plugin = pm.get_calendar_plugin(self.config.calendar_backend)
            import time
            now_sec = time.time()
            return cal_plugin.get_events(now_sec - 86400, now_sec + 7 * 86400)
        except Exception:
            return []

    # -- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        self.toast_overlay = Adw.ToastOverlay(child=toolbar)
        self.set_content(self.toast_overlay)

        # View Stack
        self.stack = Adw.ViewStack()

        # Schedules Page
        self.sched_page = SchedulePage(self.config, self._on_save_config)
        self.stack.add_titled_with_icon(self.sched_page, "schedules", "Schedules", "alarm-symbolic")

        # Calendar Rules Page
        self.cal_page = CalendarPage(self.config, self._calendars, self._events, self._on_save_config)
        self.stack.add_titled_with_icon(self.cal_page, "calendar", "Calendar Rules", "x-office-calendar-symbolic")

        # Header bar
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header = Adw.HeaderBar(title_widget=switcher)
        toolbar.add_top_bar(header)

        # Status Toggle Button in Header
        self.status_btn = Gtk.Button(label="Checking...", valign=Gtk.Align.CENTER)
        self.status_btn.connect("clicked", self._on_toggle_dnd)
        header.pack_start(self.status_btn)

        # Menu Button
        menu = Gio.Menu()
        menu.append("General Settings", "app.settings")
        menu.append("About Smart DND", "app.about")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_btn)

        # Live Status Banner
        self.banner = Adw.Banner(revealed=False)
        toolbar.add_top_bar(self.banner)

        toolbar.set_content(self.stack)

    # -- Saving --------------------------------------------------------------

    def _on_save_config(self, config: Config) -> None:
        self.config = config
        if self._save_timer_id:
            GLib.source_remove(self._save_timer_id)
        self._save_timer_id = GLib.timeout_add(SAVE_DEBOUNCE_MS, self._flush_save)

    def _flush_save(self) -> bool:
        self._save_timer_id = None
        # Snapshot on the main thread: the pages keep editing self.config in place.
        snapshot = self.config.to_dict()
        with self._save_lock:
            already_queued = self._pending_save is not None
            self._pending_save = snapshot
        if not already_queued:
            self._run_in_background(self._write_pending_save, self._on_saved)
        return GLib.SOURCE_REMOVE

    def _write_pending_save(self) -> None:
        """Worker thread. Writes the newest snapshot; edits made while queued are folded in."""
        with self._save_lock:
            data, self._pending_save = self._pending_save, None
        if data is None:
            return
        config = Config.from_dict(data)
        if self.client:
            try:
                if self.client.save_config(config):
                    return
            except Exception:
                pass
        save_config(config)

    def _on_saved(self, result: Any, error: Optional[Exception]) -> None:
        self._refresh_status()

    def _on_close_request(self, *args: Any) -> bool:
        # Flush an edit still waiting on the debounce. The worker finishes it before the process exits.
        if self._save_timer_id:
            GLib.source_remove(self._save_timer_id)
            self._flush_save()
        return False

    # -- Status --------------------------------------------------------------

    def _on_toggle_dnd(self, *args: Any) -> None:
        if not self.client:
            return
        self.status_btn.set_sensitive(False)
        self._run_in_background(lambda: self._offline_as_none(self.client.toggle_dnd), self._show_status)

    def _on_poll(self) -> bool:
        self._refresh_status()
        return GLib.SOURCE_CONTINUE

    def _refresh_status(self) -> None:
        if self._status_in_flight or not self.client:
            return
        self._status_in_flight = True
        self._run_in_background(lambda: self._offline_as_none(self.client.get_status), self._apply_status)

    def _apply_status(self, status: Optional[Status], error: Optional[Exception]) -> None:
        self._status_in_flight = False
        self._show_status(status, error)

    def _show_status(self, status: Optional[Status], error: Optional[Exception]) -> None:
        if status is None and error is None:
            self.status_btn.set_label("Daemon Offline")
            self.status_btn.set_sensitive(False)
            if IN_FLATPAK:
                self.banner.set_title("Smart DND daemon is not running. Close and reopen Smart DND to start it.")
            else:
                self.banner.set_title("Smart DND daemon is not running. Start it with 'smart-dnd daemon'.")
            self.banner.set_revealed(True)
            return

        self.status_btn.set_sensitive(True)
        if error is not None or status is None:
            self.status_btn.set_label("Connected")
            return

        if status.active:
            self.status_btn.set_label("DND Active")
            self.status_btn.set_css_classes(["suggested-action"])
            if status.next_off_ms:
                off_dt = datetime.datetime.fromtimestamp(status.next_off_ms / 1000.0)
                msg = f"DND is active ({status.reason}). Next transition at {off_dt.strftime('%H:%M')}."
            else:
                msg = f"DND is active ({status.reason})."
        else:
            self.status_btn.set_label("DND Inactive")
            self.status_btn.set_css_classes([])
            if status.next_on_ms:
                on_dt = datetime.datetime.fromtimestamp(status.next_on_ms / 1000.0)
                msg = f"DND is inactive. Next scheduled activation at {on_dt.strftime('%a %H:%M')}."
            else:
                msg = "DND is inactive. No upcoming triggers."

        self.banner.set_title(msg)
        self.banner.set_revealed(False)  # Keep subtle unless needed

    # -- Dialogs -------------------------------------------------------------

    def open_settings_dialog(self) -> None:
        dialog = GeneralSettingsDialog(
            self.config,
            self._available_plugins,
            self._on_save_config,
            autostart_enabled=autostart.is_enabled(),
            on_autostart=self._set_autostart,
        )
        dialog.present(self)

    def _set_autostart(self, enabled: bool) -> None:
        # Own thread: in the Flatpak this is a portal call, which may wait on the desktop.
        self._run_in_background(lambda: autostart.set_enabled(enabled), self._on_autostart_set, serial=False)

    def _on_autostart_set(self, result: Any, error: Optional[Exception]) -> None:
        if error is not None:
            self.toast_overlay.add_toast(Adw.Toast(title=f"Couldn't change start at login: {error}"))

    def open_about_dialog(self) -> None:
        about = Adw.AboutDialog(
            application_name="Smart DND",
            application_icon="com.keithvassallo.SmartDnd",
            version=__version__,
            developer_name="Keith Vassallo",
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/keithvassallomt/smart-dnd-linux",
            issue_url="https://github.com/keithvassallomt/smart-dnd-linux/issues",
            comments="Automatically enable Do Not Disturb on schedule or during calendar events with pluggable backends.",
        )
        about.present(self)
