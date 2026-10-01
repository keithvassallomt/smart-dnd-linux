"""General settings dialog in Libadwaita."""

from __future__ import annotations

from typing import Callable, List

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from smart_dnd.models import Config


class GeneralSettingsDialog(Adw.PreferencesDialog):
    """Preferences dialog for global settings and plugin selection."""

    def __init__(
        self,
        config: Config,
        available_plugins: dict[str, List[str]],
        on_save: Callable[[Config], None],
        autostart_enabled: bool,
        on_autostart: Callable[[bool], None],
    ) -> None:
        super().__init__(title="General Settings")
        self.config = config
        self.on_save = on_save
        self.on_autostart = on_autostart

        page = Adw.PreferencesPage()
        self.add(page)

        # 1. Automation group
        auto_group = Adw.PreferencesGroup(title="Automation")
        page.add(auto_group)

        self.master_switch = Adw.SwitchRow(
            title="Enable automation",
            subtitle="Master switch for schedule and calendar automation",
            active=config.master_enabled,
        )
        self.master_switch.connect("notify::active", self._on_changed)
        auto_group.add(self.master_switch)

        self.allday_switch = Adw.SwitchRow(
            title="Ignore all-day events",
            subtitle="Do not trigger DND for all-day calendar events",
            active=config.ignore_all_day,
        )
        self.allday_switch.connect("notify::active", self._on_changed)
        auto_group.add(self.allday_switch)

        # Not part of config.json: it's an autostart entry in ~/.config/autostart.
        self.autostart_switch = Adw.SwitchRow(
            title="Start at login",
            subtitle="Run Smart DND in the background whenever you log in",
            active=autostart_enabled,
        )
        self.autostart_switch.connect(
            "notify::active", lambda row, _pspec: self.on_autostart(row.get_active())
        )
        auto_group.add(self.autostart_switch)

        # 2. Plugins group
        plugin_group = Adw.PreferencesGroup(
            title="Active Plugins",
            description="Select which backends and frontends are active",
        )
        page.add(plugin_group)

        # Combo indices map onto these copies; the caller's lists are left untouched.
        self._notif_items = list(available_plugins.get("notifications", ["caelestia"]))
        if config.notification_backend not in self._notif_items:
            self._notif_items.append(config.notification_backend)
        self._cal_items = list(available_plugins.get("calendar", ["evolution"]))
        if config.calendar_backend not in self._cal_items:
            self._cal_items.append(config.calendar_backend)

        # Notification backend
        self.notif_combo = Adw.ComboRow(
            title="Notification System",
            subtitle="Desktop environment or daemon to control",
            model=Gtk.StringList.new(self._notif_items),
        )
        self.notif_combo.set_selected(self._notif_items.index(config.notification_backend))
        self.notif_combo.connect("notify::selected", self._on_changed)
        plugin_group.add(self.notif_combo)

        # Calendar backend
        self.cal_combo = Adw.ComboRow(
            title="Calendar Backend",
            subtitle="Source provider for calendar events",
            model=Gtk.StringList.new(self._cal_items),
        )
        self.cal_combo.set_selected(self._cal_items.index(config.calendar_backend))
        self.cal_combo.connect("notify::selected", self._on_changed)
        plugin_group.add(self.cal_combo)

        # 3. System Tray group
        tray_group = Adw.PreferencesGroup(
            title="System Tray",
            description="StatusNotifierItem (SNI) tray icon appearance",
        )
        page.add(tray_group)

        self.monochrome_switch = Adw.SwitchRow(
            title="Monochrome tray icon",
            subtitle="Use symbolic monochrome icon instead of full-color icon (for platforms like GNOME that support recoloring)",
            active=config.monochrome_tray_icon,
        )
        self.monochrome_switch.connect("notify::active", self._on_changed)
        tray_group.add(self.monochrome_switch)

    def _on_changed(self, *args) -> None:
        self.config.master_enabled = self.master_switch.get_active()
        self.config.ignore_all_day = self.allday_switch.get_active()
        self.config.monochrome_tray_icon = self.monochrome_switch.get_active()

        if self.notif_combo.get_selected() < len(self._notif_items):
            self.config.notification_backend = self._notif_items[self.notif_combo.get_selected()]

        if self.cal_combo.get_selected() < len(self._cal_items):
            self.config.calendar_backend = self._cal_items[self.cal_combo.get_selected()]

        self.on_save(self.config)
