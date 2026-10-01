"""Abstract base class for GUI frontend plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from smart_dnd.models import Config


class GuiPlugin(ABC):
    """Base class for GUI frontends (Libadwaita, Qt, etc.)."""

    plugin_id: str = "base"
    name: str = "Base GUI Plugin"
    description: str = ""

    @abstractmethod
    def launch(self, client: Any, config: Config) -> None:
        """Launch the GUI window with a client connected to the daemon."""
        raise NotImplementedError
