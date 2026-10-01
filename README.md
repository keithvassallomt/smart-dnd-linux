# Smart DND (Linux)

<p align="center">
  <img src="data/smart-dnd.svg" width="120" alt="Smart DND logo">
</p>

Smart Do Not Disturb (DND) automation for Linux desktops (Hyprland, Caelestia, Sway, GNOME, etc.).

Automatically toggles Do Not Disturb:
- **On a schedule**: Recurring time windows with day-of-week selection, midnight-crossing, and DST support.
- **From calendar events**: Pattern matching (contains, starts-with, ends-with, regex), calendar filtering, buffer offsets, and all-day event exclusion.
- **Respectful ownership**: Manual user toggles are never stomped.

> [!NOTE]
> <img width="200" height="auto" alt="friendly-manifesto-badge" src="https://github.com/user-attachments/assets/cb91210b-0f66-46fe-93a8-a3a67857593c" /> <br>
> This project voluntarily adheres to The Friendly Manifesto. Read more [here](https://friendlymanifesto.org)

## Architecture & Plugins

Smart DND is built with a pluggable architecture:
- **Calendar Providers**:
  - `evolution`: Evolution Data Server (`ECal 2.0`) — connects directly to Google Calendar, GNOME Online Accounts, Nextcloud, CalDAV, and local calendars.
  - Drop-in custom plugins via `~/.config/smart-dnd/plugins/calendar/`.
- **Notification Systems**:
  - `caelestia`: Direct IPC to Caelestia Quickshell desktop.
  - `swaync`: SwayNotificationCenter (`swaync-client`).
  - `dunst`: Dunst (`dunstctl`).
  - Drop-in custom plugins via `~/.config/smart-dnd/plugins/notifications/`.
- **GUI Frontends**:
  - `adwaita`: Native Libadwaita (GTK 4) preferences window matching GNOME HIG.
  - Drop-in custom frontends via `~/.config/smart-dnd/plugins/gui/`.

> Built a plugin for your desktop or notification setup? We'd love to have it officially included! See the [Plugin Development Guide](docs/plugin-guide.md#5-contributing-your-plugin-upstream) for details on submitting a Pull Request.

## Installation & Usage

```bash
# Run the daemon
smart-dnd daemon

# Open the Libadwaita Preferences GUI
smart-dnd gui

# Check live status
smart-dnd status

# Dry-run test against upcoming calendar events
smart-dnd test

# List discovered plugins
smart-dnd plugins
```

## Systemd Service

Enable the user service:
```bash
systemctl --user enable --now smart-dnd.service
```
