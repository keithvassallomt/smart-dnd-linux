"""SwayNotificationCenter (swaync) Plugin."""

from __future__ import annotations

import logging
import shutil
import subprocess

from smart_dnd.plugins.notifications.base import NotificationPlugin

logger = logging.getLogger(__name__)


class SwayNCNotificationPlugin(NotificationPlugin):
    """Integrates with SwayNotificationCenter (swaync)."""

    plugin_id = "swaync"
    name = "SwayNotificationCenter"
    description = "Controls DND mode via swaync-client."

    def __init__(self) -> None:
        self._bin = shutil.which("swaync-client")

    def is_dnd_enabled(self) -> bool:
        if not self._bin:
            return False
        try:
            res = subprocess.run([self._bin, "-D"], capture_output=True, text=True, timeout=5)
            return res.stdout.strip().lower() == "true"
        except Exception as e:
            logger.error("Failed querying swaync DND status: %s", e)
            return False

    def set_dnd(self, enabled: bool) -> bool:
        if not self._bin:
            return False
        current = self.is_dnd_enabled()
        if current == enabled:
            return True
        try:
            # swaync-client -d toggles DND
            subprocess.run([self._bin, "-d"], capture_output=True, text=True, check=True, timeout=5)
            return True
        except Exception as e:
            logger.error("Failed toggling swaync DND: %s", e)
            return False
