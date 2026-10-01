"""Dunst Notification Plugin."""

from __future__ import annotations

import logging
import shutil
import subprocess

from smart_dnd.plugins.notifications.base import NotificationPlugin

logger = logging.getLogger(__name__)


class DunstNotificationPlugin(NotificationPlugin):
    """Integrates with Dunst via dunstctl."""

    plugin_id = "dunst"
    name = "Dunst"
    description = "Controls pause mode via dunstctl."

    def __init__(self) -> None:
        self._bin = shutil.which("dunstctl")

    def is_dnd_enabled(self) -> bool:
        if not self._bin:
            return False
        try:
            res = subprocess.run([self._bin, "is-paused"], capture_output=True, text=True, timeout=5)
            return res.stdout.strip().lower() == "true"
        except Exception as e:
            logger.error("Failed querying Dunst paused state: %s", e)
            return False

    def set_dnd(self, enabled: bool) -> bool:
        if not self._bin:
            return False
        try:
            val = "true" if enabled else "false"
            subprocess.run([self._bin, "set-paused", val], capture_output=True, text=True, check=True, timeout=5)
            return True
        except Exception as e:
            logger.error("Failed setting Dunst paused state: %s", e)
            return False
