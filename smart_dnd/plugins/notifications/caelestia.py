"""Caelestia Shell Notification / DND Plugin."""

from __future__ import annotations

import logging
import subprocess

from smart_dnd.host import host_argv, which_host
from smart_dnd.plugins.notifications.base import NotificationPlugin

logger = logging.getLogger(__name__)


class CaelestiaNotificationPlugin(NotificationPlugin):
    """Integrates with Caelestia's shell IPC for DND toggling."""

    plugin_id = "caelestia"
    name = "Caelestia Shell"
    description = "Controls Do Not Disturb via Caelestia's Quickshell IPC."

    def __init__(self) -> None:
        self._bin = which_host("caelestia")
        if not self._bin:
            logger.warning("Caelestia binary not found in PATH.")

    def is_dnd_enabled(self) -> bool:
        if not self._bin:
            return False
        try:
            res = subprocess.run(
                host_argv([self._bin, "shell", "notifs", "isDndEnabled"]),
                capture_output=True,
                text=True,
                timeout=5,
            )
            return res.stdout.strip().lower() == "true"
        except Exception as e:
            logger.error("Failed querying Caelestia DND status: %s", e)
            return False

    def set_dnd(self, enabled: bool) -> bool:
        if not self._bin:
            return False
        cmd = "enableDnd" if enabled else "disableDnd"
        try:
            subprocess.run(
                host_argv([self._bin, "shell", "notifs", cmd]),
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            logger.info("Caelestia DND set to %s", enabled)
            return True
        except Exception as e:
            logger.error("Failed setting Caelestia DND (%s): %s", cmd, e)
            return False
