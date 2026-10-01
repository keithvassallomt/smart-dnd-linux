"""Main Application Window in Libadwaita."""

from __future__ import annotations

import datetime
from typing import Any, List, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Adw, Gio, GLib, Gtk

from smart_dnd.config import save_config
from smart_dnd.models import CalendarSource, Config, Status
from smart_dnd.plugins.gui.adwaita.calendar_page import CalendarPage
from smart_dnd.plugins.gui.adwaita.general_dialog import GeneralSettingsDialog
from smart_dnd.plugins.gui.adwaita.schedule_page import SchedulePage


class MainWindow(Adw.ApplicationWindow):
    """Main preferences window for Smart DND."""

    def __init__(self, app: Adw.Application, client: Any, config: Config) -> None:
        super().__init__(application=app, title="Smart DND")
        self.client = client
        self.config = config
        self.set_default_size(780, 680)

        self._available_plugins = self._fetch_plugins()
        self._calendars = self._fetch_calendars()

        self._build_ui()
        self._update_status()

        # Poll status every 3 seconds to reflect live state
        GLib.timeout_add_seconds(3, self._update_status)

    def _fetch_plugins(self) -> dict[str, List[str]]:
        try:
            if self.client and self.client.is_daemon_running():
                return self.client.list_plugins()
        except Exception:
            pass
        return {
            "calendar": ["evolution"],
            "notifications": ["caelestia", "swaync", "dunst"],
            "gui": ["adwaita"],
        }

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

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        # View Stack
        self.stack = Adw.ViewStack()

        # Schedules Page
        self.sched_page = SchedulePage(self.config, self._on_save_config)
        self.stack.add_titled_with_icon(self.sched_page, "schedules", "Schedules", "alarm-symbolic")

        # Calendar Rules Page
        self.cal_page = CalendarPage(self.config, self._calendars, self._on_save_config)
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

    def _on_save_config(self, config: Config) -> None:
        self.config = config
        saved_remotely = False
        if self.client and self.client.is_daemon_running():
            try:
                saved_remotely = self.client.save_config(config)
            except Exception:
                saved_remotely = False
        if not saved_remotely:
            save_config(config)
        self._update_status()

    def _on_toggle_dnd(self, *args) -> None:
        if self.client and self.client.is_daemon_running():
            try:
                self.client.toggle_dnd()
                self._update_status()
            except Exception:
                pass

    def _update_status(self) -> bool:
        daemon_online = self.client.is_daemon_running() if self.client else False

        if not daemon_online:
            self.status_btn.set_label("Daemon Offline")
            self.status_btn.set_sensitive(False)
            self.banner.set_title("Smart DND daemon is not running. Launch 'smart-dnd daemon' or enable the systemd service.")
            self.banner.set_revealed(True)
            return True

        self.status_btn.set_sensitive(True)
        try:
            status: Status = self.client.get_status()
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
        except Exception:
            self.status_btn.set_label("Connected")

        return True

    def open_settings_dialog(self) -> None:
        dialog = GeneralSettingsDialog(self.config, self._available_plugins, self._on_save_config)
        dialog.present(self)

    def open_about_dialog(self) -> None:
        about = Adw.AboutDialog(
            application_name="Smart DND",
            application_icon="com.keithvassallo.SmartDnd",
            version="0.1.0",
            developer_name="Keith Vassallo",
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/keithvassallomt/smart-dnd",
            issue_url="https://github.com/keithvassallomt/smart-dnd/issues",
            comments="Automatically enable Do Not Disturb on schedule or during calendar events with pluggable backends.",
        )
        about.present(self)
