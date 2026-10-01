"""Tests for plugin architecture and custom plugin loading."""

from pathlib import Path
from smart_dnd.plugins.calendar.base import CalendarPlugin
from smart_dnd.plugins.manager import PluginManager
from smart_dnd.plugins.notifications.base import NotificationPlugin


def test_builtin_plugins_discovered():
    pm = PluginManager()
    assert "evolution" in pm.calendar_plugins
    assert "caelestia" in pm.notification_plugins
    assert "swaync" in pm.notification_plugins
    assert "dunst" in pm.notification_plugins
    assert "adwaita" in pm.gui_plugins


def test_instantiate_plugins():
    pm = PluginManager()
    cal = pm.get_calendar_plugin("evolution")
    assert isinstance(cal, CalendarPlugin)
    assert cal.plugin_id == "evolution"

    notif = pm.get_notification_plugin("caelestia")
    assert isinstance(notif, NotificationPlugin)
    assert notif.plugin_id == "caelestia"


def test_custom_user_plugin_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr("smart_dnd.plugins.manager.USER_PLUGIN_DIR", tmp_path)
    cal_dir = tmp_path / "calendar"
    cal_dir.mkdir(parents=True)

    plugin_code = """
from smart_dnd.plugins.calendar.base import CalendarPlugin

class CustomMockCalendar(CalendarPlugin):
    plugin_id = "mock_cal"
    name = "Mock Calendar"
    description = "Mock calendar plugin"
    def list_calendars(self):
        return []
    def get_events(self, start, end):
        return []
"""
    (cal_dir / "mock_cal.py").write_text(plugin_code)

    pm = PluginManager()
    assert "mock_cal" in pm.calendar_plugins
    plugin = pm.get_calendar_plugin("mock_cal")
    assert plugin.name == "Mock Calendar"
