"""Libadwaita Application entry and GuiPlugin."""

from __future__ import annotations

import sys
from typing import Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Adw, Gio

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
