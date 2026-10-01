"""Tests for StatusNotifierTray and DBusMenu integration."""

import time
import pytest
from unittest.mock import MagicMock
from smart_dnd.models import Status
from smart_dnd.sni import StatusNotifierTray


def test_sni_menu_items_when_inactive():
    on_toggle = MagicMock(return_value=Status(active=True))
    on_open = MagicMock()
    on_quit = MagicMock()

    tray = StatusNotifierTray(on_toggle_dnd=on_toggle, on_open_gui=on_open, on_quit=on_quit)
    now_ms = time.time() * 1000.0
    future_ms = now_ms + 3600000.0  # 1 hour from now

    tray.update_status(Status(active=False, next_on_ms=future_ms))
    items = tray._get_menu_items()

    # Verify items: Show / Hide, Separator, Activate DND, Next (disabled), Separator, Quit
    assert len(items) == 6
    assert items[0]["label"] == "Show / Hide"
    assert items[0]["enabled"] is True

    assert items[1]["type"] == "separator"

    assert items[2]["label"] == "Activate DND"
    assert items[2]["enabled"] is True

    assert "Next:" in items[3]["label"]
    assert items[3]["enabled"] is False

    assert items[4]["type"] == "separator"

    assert items[5]["label"] == "Quit"
    assert items[5]["enabled"] is True


def test_sni_menu_items_when_active():
    on_toggle = MagicMock()
    on_open = MagicMock()
    on_quit = MagicMock()

    tray = StatusNotifierTray(on_toggle_dnd=on_toggle, on_open_gui=on_open, on_quit=on_quit)
    now_ms = time.time() * 1000.0
    off_ms = now_ms + 1800000.0  # 30 min from now

    tray.update_status(Status(active=True, next_off_ms=off_ms))
    items = tray._get_menu_items()

    assert items[2]["label"] == "Deactivate DND"
    assert items[2]["enabled"] is True
    assert "Active until:" in items[3]["label"]
    assert items[3]["enabled"] is False


def test_sni_handle_clicks():
    on_toggle = MagicMock(return_value=Status(active=True))
    on_open = MagicMock()
    on_quit = MagicMock()

    tray = StatusNotifierTray(on_toggle_dnd=on_toggle, on_open_gui=on_open, on_quit=on_quit)

    # Click item 1: Show / Hide
    tray._handle_menu_item_click(1)
    on_open.assert_called_once()

    # Click item 3: Toggle DND
    tray._handle_menu_item_click(3)
    on_toggle.assert_called_once()
    assert tray.status.active is True

    # Click item 6: Quit
    tray._handle_menu_item_click(6)
    on_quit.assert_called_once()


def test_sni_icon_default_color():
    tray = StatusNotifierTray(on_toggle_dnd=MagicMock())
    assert tray.monochrome is False
    assert tray.icon_name == "com.keithvassallo.SmartDnd"

    # Status update keeps color icon
    tray.update_status(Status(active=True))
    assert tray.icon_name == "com.keithvassallo.SmartDnd"


def test_sni_icon_monochrome_toggle():
    tray = StatusNotifierTray(on_toggle_dnd=MagicMock(), monochrome=True)
    assert tray.monochrome is True
    assert tray.icon_name == "com.keithvassallo.SmartDnd-symbolic"

    # Status update keeps symbolic icon
    tray.update_status(Status(active=True))
    assert tray.icon_name == "com.keithvassallo.SmartDnd-symbolic"

    # Switch to color
    tray.set_monochrome(False)
    assert tray.monochrome is False
    assert tray.icon_name == "com.keithvassallo.SmartDnd"

    # Switch back to monochrome
    tray.set_monochrome(True)
    assert tray.monochrome is True
    assert tray.icon_name == "com.keithvassallo.SmartDnd-symbolic"


def test_find_icon_falls_back_to_xdg_data_dirs(tmp_path, monkeypatch):
    # Packaged install: no source tree, icons under /usr/share-like data dirs.
    from smart_dnd.sni import COLOR_ICON_FILES, find_icon_file

    usr = tmp_path / "usr" / "icons" / "hicolor"
    svg = usr / "scalable" / "apps" / "com.keithvassallo.SmartDnd.svg"
    svg.parent.mkdir(parents=True)
    svg.write_text("<svg/>")
    monkeypatch.setattr("smart_dnd.sni.SOURCE_ICONS_DIR", tmp_path / "missing")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "usr"))
    assert find_icon_file(COLOR_ICON_FILES) == svg

    # A PNG anywhere beats the SVG, regardless of directory order.
    png = tmp_path / "home" / "icons" / "hicolor" / "32x32" / "apps" / "com.keithvassallo.SmartDnd.png"
    png.parent.mkdir(parents=True)
    png.write_bytes(b"")
    assert find_icon_file(COLOR_ICON_FILES) == png


def test_tooltip_names_the_trigger():
    tray = StatusNotifierTray(on_toggle_dnd=MagicMock())
    tray.update_status(Status(active=True, reason="calendar", trigger_name="Team Meeting"))
    _, _, title, _ = tray._get_tooltip()
    assert title == "Smart DND (Active • calendar: Team Meeting)"
