"""Evolution Data Server (EDS) Calendar Plugin using ECal 2.0."""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from smart_dnd.models import CalendarEvent, CalendarSource
from smart_dnd.plugins.calendar.base import CalendarPlugin

logger = logging.getLogger(__name__)


class EvolutionCalendarPlugin(CalendarPlugin):
    """Integrates with Evolution Data Server (Google, CalDAV, Nextcloud, local)."""

    plugin_id = "evolution"
    name = "Evolution Data Server"
    description = "Syncs with GNOME Online Accounts, Google, Nextcloud, CalDAV, and local calendars."

    def __init__(self) -> None:
        try:
            import gi
            gi.require_version("ECal", "2.0")
            gi.require_version("EDataServer", "1.2")
            from gi.repository import ECal, EDataServer, ICalGLib
            self._gi_loaded = True
            self._ECal = ECal
            self._EDataServer = EDataServer
            self._ICalGLib = ICalGLib
            self._registry = EDataServer.SourceRegistry.new_sync(None)
        except Exception as e:
            logger.warning("Failed to initialize Evolution Data Server: %s", e)
            self._gi_loaded = False
            self._registry = None
        self._clients: dict[str, Any] = {}

    def list_calendars(self) -> List[CalendarSource]:
        if not self._gi_loaded or not self._registry:
            return []

        sources: List[CalendarSource] = []
        try:
            raw_sources = self._EDataServer.SourceRegistry.list_sources(
                self._registry, self._EDataServer.SOURCE_EXTENSION_CALENDAR
            )
            for s in raw_sources:
                if not s.get_enabled():
                    continue
                uid = s.get_uid()
                name = s.get_display_name()
                sources.append(CalendarSource(uid=uid, name=name, enabled=True))
        except Exception as e:
            logger.error("Failed to list Evolution calendars: %s", e)
        return sources

    def get_events(self, start_ts: float, end_ts: float) -> List[CalendarEvent]:
        if not self._gi_loaded or not self._registry:
            return []

        events: List[CalendarEvent] = []
        start_sec = int(start_ts)
        end_sec = int(end_ts)

        try:
            raw_sources = self._EDataServer.SourceRegistry.list_sources(
                self._registry, self._EDataServer.SOURCE_EXTENSION_CALENDAR
            )
        except Exception as e:
            logger.error("Failed to get sources from registry: %s", e)
            return []

        for source in raw_sources:
            if not source.get_enabled():
                continue
            source_uid = source.get_uid()
            source_name = source.get_display_name()

            client = self._clients.get(source_uid)
            if client is None:
                try:
                    client = self._ECal.Client.connect_sync(
                        source, self._ECal.ClientSourceType.EVENTS, 1, None
                    )
                    self._clients[source_uid] = client
                except Exception as e:
                    logger.debug("Could not connect to calendar '%s': %s", source_name, e)
                    continue

            def instance_cb(comp, instance_start, instance_end, user_data, cancellable):
                try:
                    summary = comp.get_summary() or ""
                    dtstart = comp.get_dtstart()
                    all_day = dtstart.is_date() if dtstart else False

                    # Timezone resolution: use as_timet_with_zone to get exact UTC epoch timestamp
                    tz = instance_start.get_timezone()
                    if not tz and dtstart:
                        tz = dtstart.get_timezone()

                    if tz:
                        s_ts = float(instance_start.as_timet_with_zone(tz))
                    else:
                        s_ts = float(instance_start.as_timet())

                    end_tz = instance_end.get_timezone()
                    if not end_tz:
                        end_tz = tz
                    if end_tz:
                        e_ts = float(instance_end.as_timet_with_zone(end_tz))
                    else:
                        e_ts = float(instance_end.as_timet())

                    uid = comp.get_uid() or f"{source_uid}_{int(s_ts)}"

                    events.append(
                        CalendarEvent(
                            uid=uid,
                            summary=summary,
                            start=s_ts,
                            end=e_ts,
                            all_day=all_day,
                            source_uid=source_uid,
                            source_name=source_name,
                        )
                    )
                except Exception as ex:
                    logger.debug("Error processing component instance: %s", ex)
                return True

            try:
                client.generate_instances_sync(start_sec, end_sec, None, instance_cb, None)
            except Exception as e:
                logger.debug("Failed generating instances for '%s': %s", source_name, e)

        return events
