"""Abstract base class for Calendar plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List, Optional

from smart_dnd.models import CalendarEvent, CalendarSource


class CalendarPlugin(ABC):
    """Base class that calendar backend plugins must inherit from."""

    plugin_id: str = "base"
    name: str = "Base Calendar Plugin"
    description: str = ""

    @abstractmethod
    def list_calendars(self) -> List[CalendarSource]:
        """Return all available calendars/sources from this backend."""
        raise NotImplementedError

    @abstractmethod
    def get_events(self, start_ts: float, end_ts: float) -> List[CalendarEvent]:
        """Fetch all calendar events occurring between start_ts and end_ts (in seconds)."""
        raise NotImplementedError

    def watch(self, on_change_callback: Callable[[], None]) -> None:
        """Optional hook to listen for calendar database updates / sync signals."""
        pass
