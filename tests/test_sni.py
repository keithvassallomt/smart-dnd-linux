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
