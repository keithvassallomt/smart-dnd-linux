# Plugin Development Guide

Smart DND is designed to be easily extensible. You can write your own plugins for:
1. **Calendar Backends** (e.g. CalDAV, Google Calendar API, local .ics files)
2. **Notification Backends** (e.g. SwayNC, Mako, Dunst, custom scripts)
3. **GUI Frontends** (e.g. Qt/QML, CLI, Web)

Plugins can be loaded in two ways:
1. **Drop-in files**: Placed in `~/.config/smart-dnd/plugins/{calendar,notifications,gui}/*.py`
2. **Python packages**: Declaring entry points in `pyproject.toml`

---

## 1. Writing a Calendar Plugin

Inherit from `smart_dnd.plugins.calendar.base.CalendarPlugin`:

```python
# ~/.config/smart-dnd/plugins/calendar/my_custom_calendar.py
from typing import List
from smart_dnd.models import CalendarEvent, CalendarSource
from smart_dnd.plugins.calendar.base import CalendarPlugin

class CustomCalendarPlugin(CalendarPlugin):
    plugin_id = "custom_cal"
    name = "Custom Calendar"
    description = "Loads calendar events from an API or file."

    def list_calendars(self) -> List[CalendarSource]:
        return [
            CalendarSource(uid="cal-1", name="Work Calendar", enabled=True),
        ]

    def get_events(self, start_ts: float, end_ts: float) -> List[CalendarEvent]:
        # Return events between start_ts and end_ts (seconds since Unix epoch)
        return [
            CalendarEvent(
                uid="event-101",
                summary="Client Presentation",
                start=start_ts + 3600,
                end=start_ts + 7200,
                all_day=False,
                source_uid="cal-1",
            )
        ]
```

---

## 2. Writing a Notification Plugin

Inherit from `smart_dnd.plugins.notifications.base.NotificationPlugin`:

```python
# ~/.config/smart-dnd/plugins/notifications/my_notifier.py
import subprocess
from smart_dnd.plugins.notifications.base import NotificationPlugin

class MakoNotificationPlugin(NotificationPlugin):
    plugin_id = "mako"
    name = "Mako Notifier"
    description = "Controls Mako notification daemon via makoctl."

    def is_dnd_enabled(self) -> bool:
        res = subprocess.run(["makoctl", "mode"], capture_output=True, text=True)
        return "do-not-disturb" in res.stdout

    def set_dnd(self, enabled: bool) -> bool:
        cmd = ["makoctl", "mode", "-a" if enabled else "-r", "do-not-disturb"]
        subprocess.run(cmd, check=True)
        return True
```

---

## 3. Writing a GUI Frontend Plugin

Inherit from `smart_dnd.plugins.gui.base.GuiPlugin`:

```python
# ~/.config/smart-dnd/plugins/gui/my_gui.py
from smart_dnd.models import Config
from smart_dnd.plugins.gui.base import GuiPlugin

class CustomGuiPlugin(GuiPlugin):
    plugin_id = "custom_gui"
    name = "Custom GUI"
    description = "Custom graphical interface."

    def launch(self, client, config: Config) -> None:
        print("Launching custom GUI...")
        # Use client to communicate with daemon over IPC
```

---

## 4. Entrypoint Configuration

To distribute a plugin as a pip package:

```toml
[project.entry-points."smart_dnd.calendar"]
my_cal = "my_package.plugin:MyCalendarPlugin"

[project.entry-points."smart_dnd.notifications"]
my_notif = "my_package.plugin:MyNotificationPlugin"

[project.entry-points."smart_dnd.gui"]
my_gui = "my_package.plugin:MyGuiPlugin"
```
