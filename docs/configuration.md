# Configuration Reference

Smart DND stores its configuration in JSON format at:
```
~/.config/smart-dnd/config.json
```

---

## Schema Overview

```json
{
  "master_enabled": true,
  "ignore_all_day": true,
  "calendar_backend": "evolution",
  "notification_backend": "caelestia",
  "gui_backend": "adwaita",
  "monochrome_tray_icon": false,
  "schedules": [
    {
      "id": "work-hours",
      "name": "Work Focus",
      "days": [1, 2, 3, 4, 5],
      "start": "09:00",
      "end": "17:00",
      "enabled": true
    }
  ],
  "calendar_rules": [
    {
      "id": "meeting-rule",
      "name": "Meetings",
      "match_type": "contains",
      "pattern": "Meeting",
      "calendars": [],
      "enable_offset_min": -5,
      "disable_offset_min": 0,
      "enabled": true
    }
  ]
}
```

---

## Fields

### Root Settings
- `master_enabled` *(boolean, default: `true`)*: Master toggle. When `false`, Smart DND does not perform automated activations.
- `ignore_all_day` *(boolean, default: `true`)*: When `true`, all-day calendar events are ignored and will not trigger DND.
- `calendar_backend` *(string, default: `"evolution"`)*: Active calendar plugin ID.
- `notification_backend` *(string, default: `"caelestia"`)*: Active notification plugin ID.
- `gui_backend` *(string, default: `"adwaita"`)*: Active GUI frontend plugin ID.
- `monochrome_tray_icon` *(boolean, default: `false`)*: When `true`, uses a symbolic monochrome icon for the SNI system tray (recommended for desktops like GNOME that support symbolic icon recoloring). When `false`, uses the full-color icon (recommended for desktops like Caelestia/KDE in dark mode).

### Schedule Object
- `id` *(string)*: Unique identifier.
- `name` *(string)*: Human-readable name.
- `days` *(array of integers)*: Days of the week where `0 = Sunday`, `1 = Monday`, ..., `6 = Saturday`.
- `start` *(string)*: Start time in `HH:MM` format.
- `end` *(string)*: End time in `HH:MM` format. Supports midnight wrapping (e.g. `22:00` to `07:00`).
- `enabled` *(boolean)*: Whether this schedule is active.

### Calendar Rule Object
- `id` *(string)*: Unique identifier.
- `name` *(string)*: Human-readable name.
- `match_type` *(string)*: One of:
  - `"contains"`: Case-insensitive substring match.
  - `"startsWith"`: Case-insensitive prefix match.
  - `"endsWith"`: Case-insensitive suffix match.
  - `"regex"`: Case-insensitive regular expression.
- `pattern` *(string)*: Pattern to match against event titles.
- `calendars` *(array of strings)*: List of calendar source UIDs to match against. If empty, the rule applies to **all** calendars.
- `enable_offset_min` *(integer, default: `0`)*: Buffer offset in minutes before or after start (e.g. `-10` starts DND 10 minutes early).
- `disable_offset_min` *(integer, default: `0`)*: Buffer offset in minutes after event end.
- `enabled` *(boolean)*: Whether this rule is active.
