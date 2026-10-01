# Systemd & Desktop Integration

Smart DND provides both a systemd user service unit and an XDG desktop entry for seamless desktop integration.

---

## 1. Systemd User Service

The service file is located at `data/smart-dnd.service`.

### Enabling the Service
```bash
# Reload user daemon
systemctl --user daemon-reload

# Enable and start immediately
systemctl --user enable --now smart-dnd.service
```

### Checking Service Logs
```bash
journalctl --user -u smart-dnd -f
```

---

## 2. Desktop Launcher & Tray

### Desktop Entry
- Path: `~/.local/share/applications/com.keithvassallo.SmartDnd.desktop`
- Launches: `smart-dnd gui`
- Appears in your desktop launcher (Caelestia, Fuzzel, Rofi, GNOME Dash).

### StatusNotifierItem (SNI) Tray
When the daemon starts, it automatically registers a StatusNotifierItem with your system tray (Caelestia Quickshell, Waybar, etc.):
- **Left click**: Shows / focuses the Smart DND GUI.
- **Middle click**: Toggles DND immediately.
- **Hover**: Displays current DND status and when the next schedule or event transition is due.
