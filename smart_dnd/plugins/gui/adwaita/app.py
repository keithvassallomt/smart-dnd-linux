"""Libadwaita Application entry and GuiPlugin."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Adw, Gdk, Gio, Gtk

from smart_dnd.models import Config
from smart_dnd.plugins.gui.adwaita.window import MainWindow
from smart_dnd.plugins.gui.base import GuiPlugin


class SmartDndApp(Adw.Application):
    """GTK4 / Libadwaita Application for Smart DND."""

    def __init__(self, client: Any, config: Config) -> None:
        super().__init__(
            application_id="com.keithvassallo.SmartDnd",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.client = client
        self.config = config
        self.win: MainWindow | None = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)

        display = Gdk.Display.get_default()
        if display:
            icon_theme = Gtk.IconTheme.get_for_display(display)
            repo_icons = Path(__file__).resolve().parents[4] / "data" / "icons"
            if repo_icons.exists() and str(repo_icons) not in icon_theme.get_search_path():
                icon_theme.add_search_path(str(repo_icons))
            user_icons = Path.home() / ".local" / "share" / "icons"
            if user_icons.exists() and str(user_icons) not in icon_theme.get_search_path():
                icon_theme.add_search_path(str(user_icons))

        toggle_act = Gio.SimpleAction.new("toggle", None)
        toggle_act.connect("activate", lambda *_: self.toggle_window())
        self.add_action(toggle_act)

    def do_activate(self) -> None:
        if not self.win or self.win not in self.get_windows():
            self.win = MainWindow(self, self.client, self.config)

            # Setup actions
            settings_act = Gio.SimpleAction.new("settings", None)
            settings_act.connect("activate", lambda *_: self.win.open_settings_dialog())
            self.add_action(settings_act)

            about_act = Gio.SimpleAction.new("about", None)
            about_act.connect("activate", lambda *_: self.win.open_about_dialog())
            self.add_action(about_act)

        self.win.present()

    def toggle_window(self) -> None:
        if not self.win or self.win not in self.get_windows():
            self.do_activate()
        elif self.win.is_visible():
            self.win.set_visible(False)
        else:
            self.win.present()


class AdwaitaGuiPlugin(GuiPlugin):
    """Libadwaita (GTK 4) GUI Frontend Plugin."""

    plugin_id = "adwaita"
    name = "Libadwaita (GNOME HIG)"
    description = "Polished modern GTK4/Libadwaita graphical interface matching GNOME and modern Wayland desktops."

    def launch(self, client: Any, config: Config) -> None:
        app = SmartDndApp(client, config)
        app.run(sys.argv[:1])
