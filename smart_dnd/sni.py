"""StatusNotifierItem (SNI / Tray Icon) implementation for Smart DND."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib

from smart_dnd.format import format_when
from smart_dnd.models import Status

logger = logging.getLogger(__name__)

SNI_XML = """
<node>
  <interface name='org.kde.StatusNotifierItem'>
    <property name='Category' type='s' access='read'/>
    <property name='Id' type='s' access='read'/>
    <property name='Title' type='s' access='read'/>
    <property name='Status' type='s' access='read'/>
    <property name='IconName' type='s' access='read'/>
    <property name='IconPixmap' type='a(iiay)' access='read'/>
    <property name='IconThemePath' type='s' access='read'/>
    <property name='ItemIsMenu' type='b' access='read'/>
    <property name='Menu' type='o' access='read'/>
    <property name='WindowId' type='i' access='read'/>
    <property name='ToolTip' type='(sa(iiay)ss)' access='read'/>
    <method name='Activate'>
      <arg type='i' direction='in'/>
      <arg type='i' direction='in'/>
    </method>
    <method name='SecondaryActivate'>
      <arg type='i' direction='in'/>
      <arg type='i' direction='in'/>
    </method>
    <method name='ContextMenu'>
      <arg type='i' direction='in'/>
      <arg type='i' direction='in'/>
    </method>
    <method name='Scroll'>
      <arg type='i' direction='in'/>
      <arg type='s' direction='in'/>
    </method>
    <signal name='NewToolTip'/>
    <signal name='NewStatus'>
      <arg type='s' direction='out'/>
    </signal>
    <signal name='NewIcon'/>
  </interface>
</node>
"""


def ensure_icons_installed() -> None:
    """Ensure icons exist in ~/.local/share/icons/hicolor so compositors find them."""
    icons_src = Path(__file__).resolve().parents[1] / "data" / "icons"
    icons_dst = Path.home() / ".local" / "share" / "icons"

    if not icons_src.exists():
        return

    try:
        for s in (16, 32, 48, 64, 128, 256, 512):
            src = icons_src / "hicolor" / f"{s}x{s}" / "apps" / "com.keithvassallo.SmartDnd.png"
            dst = icons_dst / "hicolor" / f"{s}x{s}" / "apps" / "com.keithvassallo.SmartDnd.png"
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)

        for t in ("scalable", "symbolic"):
            suffix = "-symbolic.svg" if t == "symbolic" else ".svg"
            src = icons_src / "hicolor" / t / "apps" / f"com.keithvassallo.SmartDnd{suffix}"
            dst = icons_dst / "hicolor" / t / "apps" / f"com.keithvassallo.SmartDnd{suffix}"
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)
    except Exception as e:
        logger.debug("Icon auto-installation notice: %s", e)


def load_icon_pixmap(png_path: Path, size: int = 24) -> Optional[Tuple[int, int, bytes]]:
    """Convert a PNG file to network byte-order ARGB32 pixmap required by SNI."""
    if not png_path.exists():
        return None
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(png_path), size, size, True)
        w, h = pixbuf.get_width(), pixbuf.get_height()
        rowstride = pixbuf.get_rowstride()
        n_channels = pixbuf.get_n_channels()
        pixels = pixbuf.get_pixels()

        argb = bytearray()
        for y in range(h):
            for x in range(w):
                idx = y * rowstride + x * n_channels
                r, g, b = pixels[idx], pixels[idx + 1], pixels[idx + 2]
                a = pixels[idx + 3] if n_channels == 4 else 255
                argb.extend([a, r, g, b])
        return (w, h, bytes(argb))
    except Exception as e:
        logger.debug("Failed loading icon pixmap: %s", e)
        return None


class StatusNotifierTray:
    """Publishes a StatusNotifierItem on the user D-Bus session for system tray integration."""

    def __init__(
        self,
        on_toggle_dnd: Callable[[], Status],
        on_open_gui: Optional[Callable[[], None]] = None,
    ) -> None:
        self.on_toggle_dnd = on_toggle_dnd
        self.on_open_gui = on_open_gui or self._default_open_gui

        self.status = Status()
        self.icon_name = "com.keithvassallo.SmartDnd"
        self._bus: Optional[Gio.DBusConnection] = None
        self._reg_id: int = 0

        repo_root = Path(__file__).resolve().parents[1]
        self._icon_theme_path = str(Path.home() / ".local" / "share" / "icons")

        # Preload ARGB pixmaps for tray hosts that don't load themed icon names
        png_32 = repo_root / "data" / "icons" / "hicolor" / "32x32" / "apps" / "com.keithvassallo.SmartDnd.png"
        self._normal_pixmap = load_icon_pixmap(png_32, 24)

    def _default_open_gui(self) -> None:
        try:
            logger.info("Tray clicked. Launching Smart DND GUI...")
            subprocess.Popen(["smart-dnd", "gui"])
        except Exception as e:
            logger.error("Failed launching GUI from tray: %s", e)

    def start(self) -> None:
        ensure_icons_installed()

        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            node_info = Gio.DBusNodeInfo.new_for_xml(SNI_XML)

            self._reg_id = self._bus.register_object(
                "/StatusNotifierItem",
                node_info.interfaces[0],
                self._handle_method_call,
                self._handle_get_property,
                None,
            )

            # Register with StatusNotifierWatcher
            self._register_with_watcher()
            logger.info("StatusNotifierItem registered on Session Bus")
        except Exception as e:
            logger.warning("Could not initialize StatusNotifierItem: %s", e)

    def _register_with_watcher(self) -> None:
        if not self._bus:
            return
        try:
            watcher = Gio.DBusProxy.new_sync(
                self._bus,
                Gio.DBusProxyFlags.NONE,
                None,
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                None,
            )
            watcher.call_sync(
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", ("/StatusNotifierItem",)),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
        except Exception as e:
            logger.debug("StatusNotifierWatcher registration notice: %s", e)

    def update_status(self, status: Status) -> None:
        self.status = status
        self.icon_name = (
            "notifications-disabled-symbolic" if status.active else "com.keithvassallo.SmartDnd"
        )
        if self._bus and self._reg_id:
            try:
                self._bus.emit_signal(
                    None,
                    "/StatusNotifierItem",
                    "org.kde.StatusNotifierItem",
                    "NewToolTip",
                    None,
                )
                self._bus.emit_signal(
                    None,
                    "/StatusNotifierItem",
                    "org.kde.StatusNotifierItem",
                    "NewIcon",
                    None,
                )
            except Exception as e:
                logger.debug("Failed emitting SNI signal: %s", e)

    def _get_tooltip(self) -> tuple[str, list, str, str]:
        import time
        now_ms = time.time() * 1000.0

        if self.status.active:
            title = f"Smart DND (Active • {self.status.reason})"
            if self.status.next_off_ms:
                desc = f"DND is ON. Next transition: {format_when(now_ms, self.status.next_off_ms)}"
            else:
                desc = "DND is ON."
        else:
            title = "Smart DND (Inactive)"
            if self.status.next_on_ms:
                desc = f"DND is OFF. Next scheduled: {format_when(now_ms, self.status.next_on_ms)}"
            else:
                desc = "DND is OFF. No upcoming events or schedules."

        desc += "\nClick: Open Settings • Middle-click: Toggle DND"
        return (self.icon_name, [], title, desc)

    def _handle_get_property(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        prop_name: str,
        *args: Any,
    ) -> Optional[GLib.Variant]:
        if prop_name == "Category":
            return GLib.Variant("s", "ApplicationStatus")
        elif prop_name == "Id":
            return GLib.Variant("s", "com.keithvassallo.SmartDnd")
        elif prop_name == "Title":
            return GLib.Variant("s", "Smart DND")
        elif prop_name == "Status":
            return GLib.Variant("s", "Active")
        elif prop_name == "IconName":
            return GLib.Variant("s", self.icon_name)
        elif prop_name == "IconPixmap":
            pixmaps = [self._normal_pixmap] if self._normal_pixmap else []
            return GLib.Variant("a(iiay)", pixmaps)
        elif prop_name == "IconThemePath":
            return GLib.Variant("s", self._icon_theme_path)
        elif prop_name == "ItemIsMenu":
            return GLib.Variant("b", False)
        elif prop_name == "Menu":
            return GLib.Variant("o", "/MenuBar")
        elif prop_name == "WindowId":
            return GLib.Variant("i", 0)
        elif prop_name == "ToolTip":
            icon, pixmaps, title, desc = self._get_tooltip()
            return GLib.Variant("(sa(iiay)ss)", (icon, pixmaps, title, desc))
        return None

    def _handle_method_call(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        method_name: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
        *args: Any,
    ) -> None:
        if method_name == "Activate":
            self.on_open_gui()
            invocation.return_value(None)
        elif method_name in ("SecondaryActivate", "ContextMenu"):
            new_status = self.on_toggle_dnd()
            self.update_status(new_status)
            invocation.return_value(None)
        elif method_name == "Scroll":
            invocation.return_value(None)
        else:
            invocation.return_value(None)

    def stop(self) -> None:
        if self._bus and self._reg_id:
            try:
                self._bus.unregister_object(self._reg_id)
            except Exception:
                pass
            self._reg_id = 0
