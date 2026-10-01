# Smart DND (Linux)

**Smart DND** is an automated Do Not Disturb daemon and Libadwaita control application for Linux desktops (Hyprland, Caelestia, Sway, GNOME, etc.).

Smart DND monitors your schedule and calendar events, automatically turning Do Not Disturb on and off so you can focus when it matters without missing important alerts when you're free.

---

## Key Features

- **Recurring Schedules**: Define custom time windows with multi-day selection, midnight-wrapping, and timezone/DST support.
- **Calendar Event Automation**: Match events across all your calendars (Google Calendar, Nextcloud, CalDAV, local) using pattern matchers (`contains`, `startsWith`, `endsWith`, `regex`).
- **Buffer Offsets**: Turn on DND *N* minutes before an event starts, or keep it on *M* minutes after an event concludes.
- **Respectful Ownership**: If you manually enable or disable DND, Smart DND honors your decision and avoids clobbering your state.
- **Native Libadwaita Interface**: A clean GTK 4 interface matching modern Linux desktop design guidelines.
- **System Tray (SNI)**: Lightweight `StatusNotifierItem` tray icon for Hyprland, Caelestia, Waybar, and other desktop shells.
- **100% Pluggable**: Modular architecture allowing custom Calendar providers, Notification backends, and GUI frontends.

---

## Quick Start

### 1. Installation

Clone and install editable mode with `just`:
```bash
git clone https://github.com/keithvassallomt/smart-dnd-linux.git
cd smart-dnd-linux
just install
```

### 2. Enable User Daemon

```bash
systemctl --user enable --now smart-dnd.service
```

### 3. Open Preferences GUI

Launch **Smart DND** from your application launcher or run:
```bash
smart-dnd gui
```

---

## Table of Contents

- [Architecture & Design](architecture.md)
- [Plugin Development Guide](plugin-guide.md)
- [Configuration Reference](configuration.md)
- [CLI Reference](cli.md)
- [Systemd & Desktop Integration](systemd.md)
