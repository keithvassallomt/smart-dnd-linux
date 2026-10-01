# Plugin Development Guide

Smart DND is designed to be easily extensible. You can write your own plugins for:
1. **Calendar Backends** (e.g. CalDAV, Google Calendar API, local .ics files)
2. **Notification Backends** (e.g. SwayNC, Mako, Dunst, custom scripts)
3. **GUI Frontends** (e.g. Qt/QML, CLI, Web)

Plugins can be loaded in two ways:
1. **Drop-in files**: Placed in `~/.config/smart-dnd/plugins/{calendar,notifications,gui}/*.py`
2. **Python packages**: Declaring entry points in `pyproject.toml`

> **Contributing**: If you develop a plugin that could be useful to others, please consider [submitting a Pull Request](#5-contributing-your-plugin-upstream) to have it officially included in Smart DND!

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

---

## 5. Contributing Your Plugin Upstream

Have you built a plugin for a notification daemon, calendar service, or desktop environment that isn't yet supported out of the box? **We warmly encourage you to submit a Pull Request to have it officially included in Smart DND!**

Having your plugin officially included provides several benefits:
- **Zero setup for other users**: Anyone running your desktop environment or notification service can use Smart DND out of the box without manual installation.
- **Maintenance & compatibility**: Your plugin will be covered by test suites and kept up to date alongside internal architecture changes.
- **Visibility**: Your integration will be listed in documentation, CLI output, and application settings.

### How to Submit Your Plugin

1. **Fork the repository** on GitHub: [smart-dnd-linux](https://github.com/keithvassallomt/smart-dnd-linux).
2. **Add your plugin module**:
   Place your plugin implementation under the appropriate directory in `smart_dnd/plugins/`:
   - `smart_dnd/plugins/calendar/` for calendar backends.
   - `smart_dnd/plugins/notifications/` for notification daemons.
   - `smart_dnd/plugins/gui/` for GUI frontends.
3. **Register your plugin**:
   - Add the entry point under the corresponding category in `pyproject.toml` (e.g. `[project.entry-points."smart_dnd.notifications"]`).
   - Register it in `_register_builtins()` within `smart_dnd/plugins/manager.py` so it can be resolved as a built-in fallback.
4. **Add tests**:
   - Add unit tests in `tests/test_plugins.py` verifying that the plugin is discovered and instantiated cleanly. Mock any external CLI binaries or DBus interfaces where appropriate.
5. **Open a Pull Request**:
   - Open a PR describing what backend/desktop your plugin supports and how to test it.
   - We are happy to help review your implementation and get it merged!
