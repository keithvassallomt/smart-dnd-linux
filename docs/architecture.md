# Architecture & Design

Smart DND follows a decoupled, service-oriented architecture designed to separate desktop integration from business logic.

```
┌────────────────────────────────────────────────────────┐
│                   smart-dnd Core                       │
│  - Scheduler (midnight wrapping, DST awareness)        │
│  - Matcher (contains, starts/ends-with, regex, offsets)│
│  - Coordinator (ownership tracking & reconciliation)   │
│  - Sleep/Resume watcher (logind PrepareForSleep)       │
│  - Unix Domain Socket IPC (/run/user/1000/smart-dnd/…) │
│  - StatusNotifierItem (SNI / System Tray)              │
└───────────────────────────┬────────────────────────────┘
                            │
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Calendar    │     │ Notification │     │     GUI      │
│  Plugin SPI  │     │  Plugin SPI  │     │  Plugin SPI  │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
  ┌────┴────┐          ┌────┴────┐          ┌────┴────┐
  │evolution│          │caelestia│          │adwaita  │
  │(ECal2.0)│          │swaync   │          │(GTK 4 / │
  │         │          │dunst    │          │ Libadw) │
  └─────────┘          └─────────┘          └─────────┘
```

---

## 1. Core Daemon (`smart_dnd.daemon`)

The daemon runs continuously in your user session:
- **Event Loop**: Powered by `GLib.MainLoop`, coordinating timers, socket requests, and DBus signals.
- **Sleep & Resume**: Subscribes to `org.freedesktop.login1.Manager.PrepareForSleep` over system D-Bus. When your laptop or PC resumes from sleep, Smart DND immediately wakes up, flushes cached events, and recalculates DND state.
- **Unix Domain Socket IPC**: Listens on `$XDG_RUNTIME_DIR/smart-dnd/ipc.sock` using a lightweight line-delimited JSON-RPC protocol.
- **SNI System Tray**: Implements the freedesktop/KDE `org.kde.StatusNotifierItem` specification, registering with Caelestia, Waybar, or any StatusNotifierWatcher.

---

## 2. Coordinator & Ownership Tracking

A key design principle is **never stomping on manual user intent**:

| Desired State | Last Desired | Owned by Daemon | System DND State | Action Taken | Resulting Ownership |
|---------------|--------------|-----------------|------------------|--------------|---------------------|
| True          | False        | False           | Off              | Turn ON      | **True**            |
| True          | False        | False           | On (manually)    | None         | **True** (adopted)  |
| False         | True         | True            | On               | Turn OFF     | **False**           |
| False         | True         | False           | On (manually)    | **None**     | **False**           |
| True          | True         | True            | Off (manually)   | **None**     | **True**            |

- If Smart DND triggers an event, it takes ownership.
- If you turn DND on manually prior to an event, Smart DND adopts ownership and turns it off when the event ends.
- If you manually turn DND on outside of any event, Smart DND will **not** turn it off.
- If you manually turn DND off in the middle of a meeting, Smart DND respects your decision.

---

## 3. Plugin Architecture

Smart DND defines three Service Provider Interfaces (SPI):
1. **Calendar Backend**: Abstracts event sources (Evolution Data Server, Google Calendar, CalDAV, local ICS).
2. **Notification Backend**: Abstracts DND controllers (Caelestia, SwayNotificationCenter, Dunst, Mako, etc.).
3. **GUI Frontend**: Abstracts settings frontends (Libadwaita, Qt, Web, etc.).

See the [Plugin Guide](plugin-guide.md) to learn how to write custom plugins.
