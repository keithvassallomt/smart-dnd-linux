"""Plugin discovery and lifecycle manager."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import inspect
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Type

from smart_dnd.plugins.calendar.base import CalendarPlugin
from smart_dnd.plugins.gui.base import GuiPlugin
from smart_dnd.plugins.notifications.base import NotificationPlugin

logger = logging.getLogger(__name__)

USER_PLUGIN_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "smart-dnd" / "plugins"


class PluginManager:
    """Discovers and manages Calendar, Notification, and GUI plugins."""

    def __init__(self) -> None:
        self.calendar_plugins: Dict[str, Type[CalendarPlugin]] = {}
        self.notification_plugins: Dict[str, Type[NotificationPlugin]] = {}
        self.gui_plugins: Dict[str, Type[GuiPlugin]] = {}
        self._discover_all()

    def _discover_all(self) -> None:
        # 1. Discover via entry points
        self._discover_entry_points("smart_dnd.calendar", self.calendar_plugins, CalendarPlugin)
        self._discover_entry_points("smart_dnd.notifications", self.notification_plugins, NotificationPlugin)
        self._discover_entry_points("smart_dnd.gui", self.gui_plugins, GuiPlugin)

        # 2. Discover built-in plugins directly if not yet registered
        self._register_builtins()

        # 3. Discover user drop-in plugins from ~/.config/smart-dnd/plugins/
        self._discover_user_plugins("calendar", self.calendar_plugins, CalendarPlugin)
        self._discover_user_plugins("notifications", self.notification_plugins, NotificationPlugin)
        self._discover_user_plugins("gui", self.gui_plugins, GuiPlugin)

    def _discover_entry_points(
        self,
        group: str,
        target_dict: Dict[str, Type[Any]],
        expected_base: Type[Any],
    ) -> None:
        try:
            entry_points = importlib.metadata.entry_points(group=group)
            for ep in entry_points:
                try:
                    plugin_cls = ep.load()
                    if issubclass(plugin_cls, expected_base):
                        target_dict[ep.name] = plugin_cls
                        logger.debug("Loaded plugin '%s' from entrypoint group '%s'", ep.name, group)
                except Exception as e:
                    logger.warning("Failed to load plugin entrypoint '%s': %s", ep.name, e)
        except Exception as e:
            logger.debug("Entry points search failed for group %s: %s", group, e)

    def _register_builtins(self) -> None:
        # Calendar: Evolution
        if "evolution" not in self.calendar_plugins:
            try:
                from smart_dnd.plugins.calendar.evolution import EvolutionCalendarPlugin
                self.calendar_plugins["evolution"] = EvolutionCalendarPlugin
            except Exception as e:
                logger.debug("Evolution plugin not available: %s", e)

        # Notifications: Caelestia
        if "caelestia" not in self.notification_plugins:
            try:
                from smart_dnd.plugins.notifications.caelestia import CaelestiaNotificationPlugin
                self.notification_plugins["caelestia"] = CaelestiaNotificationPlugin
            except Exception as e:
                logger.debug("Caelestia plugin not available: %s", e)

        # Notifications: SwayNC
        if "swaync" not in self.notification_plugins:
            try:
                from smart_dnd.plugins.notifications.swaync import SwayNCNotificationPlugin
                self.notification_plugins["swaync"] = SwayNCNotificationPlugin
            except Exception as e:
                logger.debug("SwayNC plugin not available: %s", e)

        # Notifications: Dunst
        if "dunst" not in self.notification_plugins:
            try:
                from smart_dnd.plugins.notifications.dunst import DunstNotificationPlugin
                self.notification_plugins["dunst"] = DunstNotificationPlugin
            except Exception as e:
                logger.debug("Dunst plugin not available: %s", e)

        # GUI: Adwaita
        if "adwaita" not in self.gui_plugins:
            try:
                from smart_dnd.plugins.gui.adwaita.app import AdwaitaGuiPlugin
                self.gui_plugins["adwaita"] = AdwaitaGuiPlugin
            except Exception as e:
                logger.debug("Adwaita GUI plugin not available: %s", e)

    def _discover_user_plugins(
        self,
        subfolder: str,
        target_dict: Dict[str, Type[Any]],
        expected_base: Type[Any],
    ) -> None:
        folder = USER_PLUGIN_DIR / subfolder
        if not folder.is_dir():
            return

        for py_file in folder.glob("*.py"):
            if py_file.name.startswith(("_", ".")):
                continue
            module_name = f"smart_dnd_user_{subfolder}_{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    for _, obj in inspect.getmembers(mod, inspect.isclass):
                        if issubclass(obj, expected_base) and obj is not expected_base:
                            pid = getattr(obj, "plugin_id", py_file.stem)
                            target_dict[pid] = obj
                            logger.info("Loaded custom user plugin '%s' from %s", pid, py_file)
            except Exception as e:
                logger.warning("Failed to load user plugin from %s: %s", py_file, e)

    def get_calendar_plugin(self, plugin_id: str) -> CalendarPlugin:
        cls = self.calendar_plugins.get(plugin_id)
        if not cls:
            available = list(self.calendar_plugins.keys())
            raise ValueError(f"Calendar plugin '{plugin_id}' not found. Available: {available}")
        return cls()

    def get_notification_plugin(self, plugin_id: str) -> NotificationPlugin:
        cls = self.notification_plugins.get(plugin_id)
        if not cls:
            available = list(self.notification_plugins.keys())
            raise ValueError(f"Notification plugin '{plugin_id}' not found. Available: {available}")
        return cls()

    def get_gui_plugin(self, plugin_id: str) -> GuiPlugin:
        cls = self.gui_plugins.get(plugin_id)
        if not cls:
            available = list(self.gui_plugins.keys())
            raise ValueError(f"GUI plugin '{plugin_id}' not found. Available: {available}")
        return cls()
