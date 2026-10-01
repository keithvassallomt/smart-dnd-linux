"""Helpers for running inside a Flatpak sandbox."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

IN_FLATPAK = os.path.exists("/.flatpak-info")


def host_argv(argv: Sequence[str]) -> List[str]:
    """Wrap a command so it runs on the host when sandboxed.

    Notification daemons are controlled through host CLIs (caelestia, swaync-client,
    dunstctl) that do not exist inside the sandbox. Needs the manifest's
    --talk-name=org.freedesktop.Flatpak permission.
    """
    if IN_FLATPAK:
        return ["flatpak-spawn", "--host", *argv]
    return list(argv)


def which_host(name: str) -> Optional[str]:
    """Like shutil.which, but looks on the host when sandboxed."""
    if not IN_FLATPAK:
        return shutil.which(name)
    try:
        res = subprocess.run(
            host_argv(["sh", "-c", 'command -v "$0"', name]),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as e:
        logger.debug("Host lookup for %s failed: %s", name, e)
        return None
    return res.stdout.strip() or None


def daemon_log_path() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state_home) / "smart-dnd" / "daemon.log"


def start_daemon_detached() -> None:
    """Start the daemon so that it outlives the caller (the GUI).

    Natively that's a process in its own session. In a Flatpak a child process would
    not survive: when a Flatpak's main process exits, everything else in its sandbox is
    killed. flatpak-spawn (without --host) asks the Flatpak portal for a new instance
    of this app instead, which outlives the caller.
    """
    if IN_FLATPAK:
        argv = ["flatpak-spawn", "smart-dnd", "daemon"]
    else:
        argv = [sys.executable, "-m", "smart_dnd.cli", "daemon"]
    log_path = daemon_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "wb") as log:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    logger.info("Started the Smart DND daemon; logging to %s", log_path)
