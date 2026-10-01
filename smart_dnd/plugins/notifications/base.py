"""Abstract base class for Notification plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationPlugin(ABC):
    """Base class that notification/DND backend plugins must inherit from."""

    plugin_id: str = "base"
    name: str = "Base Notification Plugin"
    description: str = ""

    @abstractmethod
    def is_dnd_enabled(self) -> bool:
        """Check if Do Not Disturb is currently active on the system."""
        raise NotImplementedError

    @abstractmethod
    def set_dnd(self, enabled: bool) -> bool:
        """Enable or disable Do Not Disturb. Return True on success."""
        raise NotImplementedError
