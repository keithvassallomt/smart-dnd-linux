"""Start the Smart DND daemon at login, through XDG autostart entries.

GNOME, KDE and UWSM-managed sessions run the entries in the autostart directories
at login. The native packages install a system-wide entry, so the daemon starts for
every user by default; each user can switch it off with a `Hidden=true` override of
the same name in ~/.config/autostart, which is what the GUI toggle writes.

Flatpak installs can't add anything at install time. There the Background portal
manages the entry on desktops that implement it (GNOME, KDE); elsewhere the sandbox
writes it directly, which needs --filesystem=xdg-config/autostart:create.
"""

from __future__ import annotations

import configparser
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from smart_dnd.host import IN_FLATPAK

logger = logging.getLogger(__name__)

APP_ID = "com.keithvassallo.SmartDnd"
# Matches the name the Background portal uses for a Flatpak's entry.
ENTRY_NAME = f"{APP_ID}.desktop"
FLATPAK_DAEMON_COMMAND = f"flatpak run --command=smart-dnd {APP_ID} daemon"

# D-Bus errors meaning "this desktop has no Background portal".
_NO_PORTAL_ERRORS = {
    "org.freedesktop.DBus.Error.ServiceUnknown",
    "org.freedesktop.DBus.Error.UnknownInterface",
    "org.freedesktop.DBus.Error.UnknownMethod",
    "org.freedesktop.DBus.Error.UnknownObject",
}


def user_autostart_dir() -> Path:
    # Inside a Flatpak, XDG_CONFIG_HOME points into ~/.var/app; the entry belongs in the host's.
    if IN_FLATPAK:
        config_home = os.environ.get("HOST_XDG_CONFIG_HOME") or str(Path.home() / ".config")
    else:
        config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config_home) / "autostart"


def system_autostart_dirs() -> List[Path]:
    if IN_FLATPAK:
        return []  # the sandbox's /etc/xdg is the runtime's, not the host's
    config_dirs = os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    return [Path(d) / "autostart" for d in config_dirs.split(":") if d]


def system_entry() -> Optional[Path]:
    """The entry installed by a native package, if any."""
    for d in system_autostart_dirs():
        path = d / ENTRY_NAME
        if path.is_file():
            return path
    return None


def _entry_disabled(path: Path) -> bool:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # keys are case-sensitive
    try:
        parser.read(path, encoding="utf-8")
        entry = parser["Desktop Entry"]
    except (configparser.Error, KeyError, OSError):
        return True  # an unreadable entry won't start anything
    return (
        entry.get("Hidden", "false").strip().lower() == "true"
        or entry.get("X-GNOME-Autostart-enabled", "true").strip().lower() == "false"
    )


def is_enabled() -> bool:
    """Whether the daemon will start at the next login.

    A user entry overrides a system entry of the same name (XDG autostart spec).
    """
    user = user_autostart_dir() / ENTRY_NAME
    if user.exists():
        return not _entry_disabled(user)
    return system_entry() is not None


def _desktop_exec_quote(arg: str) -> str:
    if not any(c in arg for c in ' \t\n"\'\\><~|&;$*?#()`'):
        return arg
    escaped = "".join("\\" + c if c in '"`$\\' else c for c in arg)
    return f'"{escaped}"'


def native_daemon_command() -> str:
    """Absolute command for a user entry: the login PATH may not include venvs or ~/.local/bin."""
    exe = shutil.which("smart-dnd")
    if exe:
        return f"{_desktop_exec_quote(exe)} daemon"
    return f"{_desktop_exec_quote(sys.executable)} -m smart_dnd.cli daemon"


def _write_entry(path: Path, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(["[Desktop Entry]", *lines]) + "\n", encoding="utf-8")
    # Rename rather than write in place: an existing entry may be a symlink into dotfiles.
    tmp.replace(path)


def _write_start_entry(path: Path, command: str) -> None:
    _write_entry(path, [
        "Type=Application",
        "Name=Smart DND",
        "Comment=Turns Do Not Disturb on and off in the background",
        f"Exec={command}",
        f"Icon={APP_ID}",
        "NoDisplay=true",
    ])


def _request_background(enabled: bool) -> bool:
    """Ask the Background portal to add or remove the Flatpak's entry.

    Returns False when the desktop has no Background portal.
    """
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    options = {
        "reason": GLib.Variant("s", "Smart DND turns Do Not Disturb on and off in the background."),
        "autostart": GLib.Variant("b", enabled),
        "commandline": GLib.Variant("as", ["smart-dnd", "daemon"]),
    }
    try:
        bus.call_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Background",
            "RequestBackground",
            GLib.Variant("(sa{sv})", ("", options)),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE,
            5000,
            None,
        )
    except GLib.Error as e:
        if Gio.DBusError.is_remote_error(e) and Gio.DBusError.get_remote_error(e) in _NO_PORTAL_ERRORS:
            return False
        raise
    return True


def set_enabled(enabled: bool) -> None:
    user = user_autostart_dir() / ENTRY_NAME

    if IN_FLATPAK:
        # On GNOME/KDE the portal writes or removes the entry (and may ask the user first).
        if _request_background(enabled):
            if not enabled:
                user.unlink(missing_ok=True)
            return
        logger.info("No Background portal; managing %s directly", user)
        if enabled:
            _write_start_entry(user, FLATPAK_DAEMON_COMMAND)
        else:
            user.unlink(missing_ok=True)
        return

    if system_entry() is not None:
        if enabled:
            user.unlink(missing_ok=True)  # fall back to the package's entry
        else:
            _write_entry(user, ["Type=Application", "Name=Smart DND", "Hidden=true"])
    elif enabled:
        _write_start_entry(user, native_daemon_command())
    else:
        user.unlink(missing_ok=True)


def enable_by_default_once() -> None:
    """Turn start-at-login on at a Flatpak's first launch, since installing it can't.

    Runs once per user; switching it off later in the GUI sticks.
    """
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    marker = Path(state_home) / "smart-dnd" / "autostart-default-applied"
    if marker.exists():
        return
    try:
        set_enabled(True)
    except Exception as e:
        logger.warning("Could not set up start at login: %s", e)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
