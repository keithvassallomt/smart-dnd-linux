# Desktop Integration

How Smart DND starts at login, appears in your launcher and tray, and works as a Flatpak.

---

## 1. Start at Login

The daemon starts at login through an XDG autostart entry named `com.keithvassallo.SmartDnd.desktop`.

| Install | Default |
|---|---|
| `.deb`, `.rpm`, AUR | **On** for every user: the package installs `/etc/xdg/autostart/com.keithvassallo.SmartDnd.desktop` |
| Flatpak | **On** after you first open Smart DND (a Flatpak can't add anything at install time) |
| `just install` | **On**: it runs `smart-dnd autostart on` |
| `pip install` | Off until you turn it on |

Each user can change it in **General Settings → Start at login**, or from a terminal:

```bash
smart-dnd autostart        # show
smart-dnd autostart on
smart-dnd autostart off
```

Switching it off writes an override with `Hidden=true` to `~/.config/autostart/`, which takes
precedence over the package's entry; switching it back on removes the override. Nothing outside your
home directory changes, so no root access is needed.

Opening Smart DND also starts the daemon if it isn't running, so you don't have to log out after
installing.

### Which sessions run autostart entries

GNOME, KDE Plasma, Xfce and other full desktops run them, and so do Hyprland, Sway and other
compositors when the session is started through [UWSM](https://github.com/Vladimir-csp/uwsm). A
compositor started without UWSM ignores them; there, start the daemon from your compositor's config
instead, with `smart-dnd daemon` (or `flatpak run --command=smart-dnd com.keithvassallo.SmartDnd daemon`
for the Flatpak).

### Checking Logs

Under systemd-managed sessions the autostarted daemon logs to the journal:

```bash
journalctl --user -u 'app-com.keithvassallo.SmartDnd@autostart.service' -f
```

When the GUI starts the daemon, it logs to `~/.local/state/smart-dnd/daemon.log` instead.

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

---

## 3. Flatpak

- **Opening Smart DND starts the daemon** if it isn't running. The daemon runs as its own sandbox
  instance, so it keeps running after you close the window.
- **Start at login** goes through the Background portal on GNOME and KDE, which may ask you to allow
  it once. Desktops without that portal (Hyprland's, for example) get the autostart entry written
  directly, which is what the `xdg-config/autostart` permission is for.
- **Inside the sandbox**, Smart DND reaches the host in three ways: notification daemons are
  controlled by running their CLI on the host (`flatpak-spawn --host`), calendars come from the
  host's Evolution Data Server over D-Bus, and the IPC socket in `$XDG_RUNTIME_DIR/smart-dnd/` is
  shared with the host, so a host `smart-dnd` CLI can talk to the Flatpak daemon and vice versa.
- **Config and plugins** live in `~/.var/app/com.keithvassallo.SmartDnd/config/smart-dnd/`, and the
  daemon's log in `~/.var/app/com.keithvassallo.SmartDnd/.local/state/smart-dnd/daemon.log`.
