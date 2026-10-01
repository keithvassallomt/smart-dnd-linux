"""StatusNotifierItem (SNI / Tray Icon) implementation for Smart DND."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib

from smart_dnd.format import format_when
from smart_dnd.models import Status

logger = logging.getLogger(__name__)

WATCHER_NAME = "org.kde.StatusNotifierWatcher"

# Only present in a checkout or editable install; the wheel ships smart_dnd/ alone.
SOURCE_ICONS_DIR = Path(__file__).resolve().parents[1] / "data" / "icons" / "hicolor"

COLOR_ICON_FILES = (
    "32x32/apps/com.keithvassallo.SmartDnd.png",
    "scalable/apps/com.keithvassallo.SmartDnd.svg",
)
SYMBOLIC_ICON_FILES = (
    "symbolic/apps/com.keithvassallo.SmartDnd-symbolic.png",
    "symbolic/apps/com.keithvassallo.SmartDnd-symbolic.svg",
)

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

DBUSMENU_XML = """
<node>
  <interface name='com.canonical.dbusmenu'>
    <method name='GetLayout'>
      <arg name='parent_id' type='i' direction='in'/>
      <arg name='recursion_depth' type='i' direction='in'/>
      <arg name='property_names' type='as' direction='in'/>
      <arg type='u' direction='out'/>
      <arg type='(ia{sv}av)' direction='out'/>
    </method>
    <method name='GetGroupProperties'>
      <arg name='ids' type='ai' direction='in'/>
      <arg name='property_names' type='as' direction='in'/>
      <arg type='a(ia{sv})' direction='out'/>
    </method>
    <method name='GetProperty'>
      <arg name='id' type='i' direction='in'/>
      <arg name='name' type='s' direction='in'/>
      <arg type='v' direction='out'/>
    </method>
    <method name='Event'>
      <arg name='id' type='i' direction='in'/>
      <arg name='event_id' type='s' direction='in'/>
      <arg name='data' type='v' direction='in'/>
      <arg name='timestamp' type='u' direction='in'/>
    </method>
    <method name='EventGroup'>
      <arg name='events' type='a(isvu)' direction='in'/>
      <arg type='ai' direction='out'/>
    </method>
    <method name='AboutToShow'>
      <arg name='id' type='i' direction='in'/>
      <arg type='b' direction='out'/>
    </method>
    <method name='AboutToShowGroup'>
      <arg name='ids' type='ai' direction='in'/>
      <arg type='ai' direction='out'/>
      <arg type='ai' direction='out'/>
    </method>
    <signal name='ItemsPropertiesUpdated'>
      <arg name='updated_props' type='a(ia{sv})'/>
      <arg name='removed_props' type='a(ias)'/>
    </signal>
    <signal name='LayoutUpdated'>
      <arg name='revision' type='u'/>
      <arg name='parent' type='i'/>
    </signal>
    <property name='IconThemePath' type='as' access='read'/>
    <property name='Status' type='s' access='read'/>
    <property name='TextDirection' type='s' access='read'/>
    <property name='Version' type='u' access='read'/>
  </interface>
</node>
"""


def icon_search_dirs() -> List[Path]:
    """hicolor directories to search: the source tree, then the XDG data dirs.

    Distro packages install icons under /usr/share and the Flatpak under /app/share,
    both of which are on $XDG_DATA_DIRS.
    """
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs = [SOURCE_ICONS_DIR]
    for d in [data_home, *data_dirs.split(":")]:
        if d:
            dirs.append(Path(d) / "icons" / "hicolor")
    return dirs


def find_icon_file(candidates: Sequence[str]) -> Optional[Path]:
    """Return the first candidate (in order of preference) found in any icon directory."""
    dirs = icon_search_dirs()
    for rel in candidates:
        for base in dirs:
            path = base / rel
            if path.is_file():
                return path
    return None


def ensure_icons_installed() -> None:
    """Ensure icons exist in ~/.local/share/icons/hicolor so compositors find them."""
    icons_src = SOURCE_ICONS_DIR
    icons_dst = Path.home() / ".local" / "share" / "icons" / "hicolor"

    if not icons_src.exists():
        return

    try:
        updated = False
        for src_file in icons_src.rglob("*"):
            if src_file.is_file():
                rel = src_file.relative_to(icons_src)
                dst_file = icons_dst / rel
                if not dst_file.exists() or dst_file.stat().st_size != src_file.stat().st_size:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src_file, dst_file)
                    updated = True

        if updated and shutil.which("gtk-update-icon-cache"):
            try:
                subprocess.run(
                    ["gtk-update-icon-cache", "-q", "-t", str(icons_dst)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
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


def toggle_gui() -> None:
    """Toggle GUI visibility if already running on D-Bus, or launch it if not."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        owner = bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "GetNameOwner",
            GLib.Variant("(s)", ("com.keithvassallo.SmartDnd",)),
            GLib.VariantType("(s)"),
            Gio.DBusCallFlags.NONE,
            200,
            None,
        )
        if owner:
            bus.call_sync(
                "com.keithvassallo.SmartDnd",
                "/com/keithvassallo/SmartDnd",
                "org.freedesktop.Application",
                "ActivateAction",
                GLib.Variant("(sava{sv})", ("toggle", [], {})),
                None,
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
            return
    except Exception:
        pass

    try:
        logger.info("Launching Smart DND GUI...")
        # Use the daemon's own interpreter: under systemd, PATH may not include
        # ~/.local/bin or a venv, so a bare "smart-dnd" is not reliably found.
        subprocess.Popen([sys.executable, "-m", "smart_dnd.cli", "gui"])
    except Exception as e:
        logger.error("Failed launching GUI from tray: %s", e)


class StatusNotifierTray:
    """Publishes a StatusNotifierItem and DBusMenu on the user D-Bus session."""

    def __init__(
        self,
        on_toggle_dnd: Callable[[], Status],
        on_open_gui: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        monochrome: bool = False,
    ) -> None:
        self.on_toggle_dnd = on_toggle_dnd
        self.on_open_gui = on_open_gui or toggle_gui
        self.on_quit = on_quit or self._default_quit
        self.monochrome = monochrome

        self.status = Status()
        self.icon_name = (
            "com.keithvassallo.SmartDnd-symbolic" if self.monochrome else "com.keithvassallo.SmartDnd"
        )
        self._bus: Optional[Gio.DBusConnection] = None
        self._reg_id: int = 0
        self._menu_reg_id: int = 0
        self._name_owner_id: int = 0
        self._watcher_watch_id: int = 0
        self._menu_revision: int = 1

        self._icon_theme_path = str(Path.home() / ".local" / "share" / "icons")

        self._reload_pixmap()

    def _reload_pixmap(self) -> None:
        candidates = SYMBOLIC_ICON_FILES + COLOR_ICON_FILES if self.monochrome else COLOR_ICON_FILES
        icon_path = find_icon_file(candidates)
        if icon_path is None:
            logger.debug("No tray icon file found; hosts will fall back to IconName lookup")
        self._normal_pixmap = load_icon_pixmap(icon_path, 24) if icon_path else None

    def set_monochrome(self, monochrome: bool) -> None:
        if self.monochrome == monochrome:
            return
        self.monochrome = monochrome
        self.icon_name = (
            "com.keithvassallo.SmartDnd-symbolic" if self.monochrome else "com.keithvassallo.SmartDnd"
        )
        self._reload_pixmap()
        if self._bus and self._reg_id:
            try:
                self._bus.emit_signal(
                    None,
                    "/StatusNotifierItem",
                    "org.kde.StatusNotifierItem",
                    "NewIcon",
                    None,
                )
            except Exception as e:
                logger.debug("Failed emitting NewIcon on monochrome change: %s", e)

    def _default_quit(self) -> None:
        logger.info("Quit requested from tray.")
        self.stop()

    def start(self) -> None:
        ensure_icons_installed()

        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

            # 1. Register StatusNotifierItem on /StatusNotifierItem
            sni_node = Gio.DBusNodeInfo.new_for_xml(SNI_XML)
            self._reg_id = self._bus.register_object(
                "/StatusNotifierItem",
                sni_node.interfaces[0],
                self._handle_method_call,
                self._handle_get_property,
                None,
            )

            # 2. Register DBusMenu on /MenuBar
            menu_node = Gio.DBusNodeInfo.new_for_xml(DBUSMENU_XML)
            self._menu_reg_id = self._bus.register_object(
                "/MenuBar",
                menu_node.interfaces[0],
                self._handle_menu_method_call,
                self._handle_menu_get_property,
                None,
            )

            # The spec's well-known name; some hosts discover items by it.
            self._name_owner_id = Gio.bus_own_name_on_connection(
                self._bus,
                f"org.kde.StatusNotifierItem-{os.getpid()}-1",
                Gio.BusNameOwnerFlags.NONE,
                None,
                None,
            )

            # Register now, and again whenever the watcher restarts (e.g. the shell
            # reloads). Otherwise the icon vanishes until the daemon restarts.
            self._watcher_watch_id = Gio.bus_watch_name_on_connection(
                self._bus,
                WATCHER_NAME,
                Gio.BusNameWatcherFlags.NONE,
                self._on_watcher_appeared,
                None,
            )
            logger.info("StatusNotifierItem and DBusMenu registered on Session Bus")
        except Exception as e:
            logger.warning("Could not initialize StatusNotifierItem: %s", e)

    def _on_watcher_appeared(self, connection: Gio.DBusConnection, name: str, owner: str) -> None:
        self._register_with_watcher()

    def _register_with_watcher(self) -> None:
        if not self._bus:
            return
        # Async: a hung watcher must not block the daemon's main loop.
        self._bus.call(
            WATCHER_NAME,
            "/StatusNotifierWatcher",
            WATCHER_NAME,
            "RegisterStatusNotifierItem",
            GLib.Variant("(s)", ("/StatusNotifierItem",)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            self._on_registered,
        )

    def _on_registered(self, bus: Gio.DBusConnection, result: Gio.AsyncResult, *args: Any) -> None:
        try:
            bus.call_finish(result)
            logger.debug("Registered with %s", WATCHER_NAME)
        except Exception as e:
            logger.debug("StatusNotifierWatcher registration notice: %s", e)

    def update_status(self, status: Status) -> None:
        self.status = status
        self.icon_name = (
            "com.keithvassallo.SmartDnd-symbolic" if self.monochrome else "com.keithvassallo.SmartDnd"
        )
        self._menu_revision += 1

        if self._bus:
            if self._reg_id:
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
                        "NewStatus",
                        GLib.Variant("(s)", ("Active" if status.active else "Passive",)),
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

            if self._menu_reg_id:
                try:
                    self._bus.emit_signal(
                        None,
                        "/MenuBar",
                        "com.canonical.dbusmenu",
                        "LayoutUpdated",
                        GLib.Variant("(ui)", (self._menu_revision, 0)),
                    )
                except Exception as e:
                    logger.debug("Failed emitting MenuBar LayoutUpdated: %s", e)

    def _get_tooltip(self) -> tuple[str, list, str, str]:
        import time
        now_ms = time.time() * 1000.0

        if self.status.active:
            if self.status.trigger_name:
                title = f"Smart DND (Active • {self.status.reason}: {self.status.trigger_name})"
            else:
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

        desc += "\nClick: Show / Hide • Right-click: Menu"
        return (self.icon_name, [], title, desc)

    def _get_menu_items(self) -> list[dict[str, Any]]:
        import time
        now_ms = time.time() * 1000.0

        if self.status.active:
            dnd_label = "Deactivate DND"
            dnd_icon = "notifications-disabled-symbolic"
            if self.status.next_off_ms:
                next_label = f"Active until: {format_when(now_ms, self.status.next_off_ms)}"
            elif self.status.next_on_ms:
                next_label = f"Next: {format_when(now_ms, self.status.next_on_ms)}"
            else:
                next_label = "Active (manual)"
        else:
            dnd_label = "Activate DND"
            dnd_icon = "notifications-symbolic"
            if self.status.next_on_ms:
                next_label = f"Next: {format_when(now_ms, self.status.next_on_ms)}"
            else:
                next_label = "Next: None scheduled"

        return [
            {
                "id": 1,
                "label": "Show / Hide",
                "icon-name": "preferences-system-symbolic",
                "enabled": True,
                "visible": True,
            },
            {
                "id": 2,
                "type": "separator",
                "visible": True,
            },
            {
                "id": 3,
                "label": dnd_label,
                "icon-name": dnd_icon,
                "enabled": True,
                "visible": True,
            },
            {
                "id": 4,
                "label": next_label,
                "icon-name": "alarm-symbolic",
                "enabled": False,
                "visible": True,
            },
            {
                "id": 5,
                "type": "separator",
                "visible": True,
            },
            {
                "id": 6,
                "label": "Quit",
                "icon-name": "application-exit-symbolic",
                "enabled": True,
                "visible": True,
            },
        ]

    def _handle_menu_item_click(self, item_id: int) -> None:
        if item_id == 1:
            self.on_open_gui()
        elif item_id == 3:
            new_status = self.on_toggle_dnd()
            self.update_status(new_status)
        elif item_id == 6:
            self.on_quit()

    def _handle_menu_get_property(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        path: str,
        interface: str,
        prop_name: str,
        *args: Any,
    ) -> Optional[GLib.Variant]:
        if prop_name == "Version":
            return GLib.Variant("u", 3)
        elif prop_name == "Status":
            return GLib.Variant("s", "normal")
        elif prop_name == "TextDirection":
            return GLib.Variant("s", "ltr")
        elif prop_name == "IconThemePath":
            return GLib.Variant("as", [self._icon_theme_path])
        return None

    def _handle_menu_method_call(
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
        if method_name == "GetLayout":
            parent_id, depth, prop_names = parameters.unpack()
            items = self._get_menu_items()
            children = []
            if depth != 0:
                for it in items:
                    props = {}
                    for k in ("type", "label", "enabled", "visible", "icon-name"):
                        if k in it and (not prop_names or k in prop_names):
                            val = it[k]
                            props[k] = GLib.Variant("b", val) if isinstance(val, bool) else GLib.Variant("s", val)
                    children.append(GLib.Variant("(ia{sv}av)", (it["id"], props, [])))
            root = (0, {"children-display": GLib.Variant("s", "submenu")}, children)
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self._menu_revision, root)))

        elif method_name == "GetGroupProperties":
            ids, prop_names = parameters.unpack()
            items_by_id = {it["id"]: it for it in self._get_menu_items()}
            res = []
            for mid in ids:
                if mid in items_by_id:
                    it = items_by_id[mid]
                    props = {}
                    for k in ("type", "label", "enabled", "visible", "icon-name"):
                        if k in it and (not prop_names or k in prop_names):
                            val = it[k]
                            props[k] = GLib.Variant("b", val) if isinstance(val, bool) else GLib.Variant("s", val)
                    res.append((mid, props))
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (res,)))

        elif method_name == "GetProperty":
            mid, name = parameters.unpack()
            items_by_id = {it["id"]: it for it in self._get_menu_items()}
            if mid in items_by_id and name in items_by_id[mid]:
                val = items_by_id[mid][name]
                var = GLib.Variant("b", val) if isinstance(val, bool) else GLib.Variant("s", val)
                invocation.return_value(GLib.Variant("(v)", (var,)))
            else:
                invocation.return_value(GLib.Variant("(v)", (GLib.Variant("s", ""),)))

        elif method_name == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))

        elif method_name == "AboutToShowGroup":
            ids = parameters.unpack()[0]
            invocation.return_value(GLib.Variant("(aiai)", ([], ids)))

        elif method_name == "Event":
            mid, event_type, data, ts = parameters.unpack()
            if event_type == "clicked":
                self._handle_menu_item_click(mid)
            invocation.return_value(None)

        elif method_name == "EventGroup":
            events = parameters.unpack()[0]
            for mid, event_type, data, ts in events:
                if event_type == "clicked":
                    self._handle_menu_item_click(mid)
            invocation.return_value(GLib.Variant("(ai)", ([],)))

        else:
            invocation.return_value(None)

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
        elif method_name == "SecondaryActivate":
            new_status = self.on_toggle_dnd()
            self.update_status(new_status)
            invocation.return_value(None)
        elif method_name == "ContextMenu":
            if self._bus and self._menu_reg_id:
                try:
                    self._bus.emit_signal(
                        None,
                        "/MenuBar",
                        "com.canonical.dbusmenu",
                        "LayoutUpdated",
                        GLib.Variant("(ui)", (self._menu_revision, 0)),
                    )
                except Exception:
                    pass
            invocation.return_value(None)
        elif method_name == "Scroll":
            invocation.return_value(None)
        else:
            invocation.return_value(None)

    def stop(self) -> None:
        if self._watcher_watch_id:
            Gio.bus_unwatch_name(self._watcher_watch_id)
            self._watcher_watch_id = 0
        if self._name_owner_id:
            Gio.bus_unown_name(self._name_owner_id)
            self._name_owner_id = 0
        if self._bus:
            if self._reg_id:
                try:
                    self._bus.unregister_object(self._reg_id)
                except Exception:
                    pass
                self._reg_id = 0
            if self._menu_reg_id:
                try:
                    self._bus.unregister_object(self._menu_reg_id)
                except Exception:
                    pass
                self._menu_reg_id = 0
