# CLI Reference

The `smart-dnd` command-line utility controls the background daemon, queries status, and allows dry-run testing.

---

## Commands

### `smart-dnd status`
Query the running daemon and print the active DND state, active trigger, and next transition time.

```bash
$ smart-dnd status
=== Smart DND Status ===
DND Active:           YES
Reason:               calendar
Owned by Smart DND:   YES
Next Activation:      None
Next Deactivation:    2026-10-01 15:00:00
Notification Backend: caelestia
Calendar Backend:     evolution
```

### `smart-dnd toggle`
Toggle Do Not Disturb immediately. If the daemon is running, this notifies the daemon and adopts/releases ownership properly.

```bash
$ smart-dnd toggle
DND toggled. Now: ACTIVE
```

### `smart-dnd test`
Performs a dry-run rule evaluation against your upcoming calendar events without altering any DND state.

```bash
$ smart-dnd test
Current local time: 2026-10-01 14:37:24 (Day of week: 4, Minute: 877)
Master Enabled: True

-- Schedule Evaluation --
  Schedule 'Work' (09:00 - 17:00): ACTIVE (Enabled: True)

-- Calendar Event Evaluation --
  Fetched 12 events in the window [-1h .. +48h].
  Event: 'CCF Proposal Check In' (Thu 14:00 - 15:00) [--> MATCHES: Meetings]
```

### `smart-dnd list-calendars`
List all calendar sources discovered by the active calendar backend.

```bash
$ smart-dnd list-calendars
Found 20 calendar sources:
 • Family (uid: f78e7a4362a400fc73fb18b40c2aabb8dd66215d)
 • ICE (uid: e79a4d40bcd7201b427bd009f60d6a7e9b7f7431)
 • Keith (uid: 330e31b33d9ebbe8a4059b6e056bca52f4e4045e)
```

### `smart-dnd plugins`
Display all available and loaded plugins across Calendar, Notification, and GUI categories.

```bash
$ smart-dnd plugins
=== Discovered Plugins ===
Calendar Backends:
  • evolution: Evolution Data Server

Notification Systems:
  • caelestia: Caelestia Shell
  • dunst: Dunst
  • swaync: SwayNotificationCenter

GUI Frontends:
  • adwaita: Libadwaita (GNOME HIG)
```

### `smart-dnd gui`
Open the Libadwaita Preferences Window.

### `smart-dnd daemon [--debug]`
Run the background daemon in the foreground.
