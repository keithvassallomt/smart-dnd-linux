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
    ) -> None:
        super().__init__(title="General Settings")
        self.config = config
        self.on_save = on_save

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

        # 2. Plugins group
        plugin_group = Adw.PreferencesGroup(
            title="Active Plugins",
            description="Select which backends and frontends are active",
        )
        page.add(plugin_group)

        # Notification backend
        notif_plugins = available_plugins.get("notifications", ["caelestia"])
        if config.notification_backend not in notif_plugins:
            notif_plugins.append(config.notification_backend)
        self.notif_combo = Adw.ComboRow(
            title="Notification System",
            subtitle="Desktop environment or daemon to control",
            model=Gtk.StringList.new(notif_plugins),
        )
        if config.notification_backend in notif_plugins:
            self.notif_combo.set_selected(notif_plugins.index(config.notification_backend))
        self.notif_combo.connect("notify::selected", self._on_changed)
        plugin_group.add(self.notif_combo)

        # Calendar backend
        cal_plugins = available_plugins.get("calendar", ["evolution"])
        if config.calendar_backend not in cal_plugins:
            cal_plugins.append(config.calendar_backend)
        self.cal_combo = Adw.ComboRow(
            title="Calendar Backend",
            subtitle="Source provider for calendar events",
            model=Gtk.StringList.new(cal_plugins),
        )
        if config.calendar_backend in cal_plugins:
            self.cal_combo.set_selected(cal_plugins.index(config.calendar_backend))
        self.cal_combo.connect("notify::selected", self._on_changed)
        plugin_group.add(self.cal_combo)

        self.available_plugins = available_plugins

    def _on_changed(self, *args) -> None:
        self.config.master_enabled = self.master_switch.get_active()
        self.config.ignore_all_day = self.allday_switch.get_active()

        notif_items = self.available_plugins.get("notifications", ["caelestia"])
        if self.notif_combo.get_selected() < len(notif_items):
            self.config.notification_backend = notif_items[self.notif_combo.get_selected()]

        cal_items = self.available_plugins.get("calendar", ["evolution"])
        if self.cal_combo.get_selected() < len(cal_items):
            self.config.calendar_backend = cal_items[self.cal_combo.get_selected()]

        self.on_save(self.config)
