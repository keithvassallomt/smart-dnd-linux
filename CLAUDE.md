# smart-dnd-linux

Python daemon + Libadwaita GUI that turns notification Do Not Disturb on and off from recurring
schedules and calendar events, on any Linux desktop. It is the desktop-agnostic sibling of the
GNOME Shell extension in `~/LocalCode/keithvassallomt/smart-dnd` (GitHub `keithvassallomt/smart-dnd`).
The pure logic (scheduler, matcher, coordinator, format) was ported from that extension's JS, and
the tests mirror its suite. When behaviour is in doubt, the extension is the reference.

## Dev environment

- `.venv` is a `uv` venv with `include-system-site-packages = true`. PyGObject (`gi`) comes from
  the system package (`python-gobject` on Arch), not pip. The project is installed editable.
- `just test` runs pytest. `just run-daemon` runs the daemon in the foreground with `--debug`.
  `just run-gui`, `just status`, `just test-rules` (dry run against real events), `just plugins`.
- `just install` does an editable install and copies the desktop file, metainfo, systemd unit and
  icons into `~/.local`.
- Only one daemon can run at a time (it owns the IPC socket). Check `pgrep -af "smart-dnd daemon"`
  before starting another.

## Process model

Three processes, all from the `smart-dnd` entry point (`smart_dnd/cli.py`):

- **Daemon** (`smart-dnd daemon`): one `GLib.MainLoop`. Owns config, plugins, the IPC server, the
  SNI tray, a logind `PrepareForSleep` subscription and one re-armed timer. All state lives on the
  main loop; the only other thread is the calendar fetch, which hands results back via `GLib.idle_add`.
- **GUI** (`smart-dnd gui`): separate `Adw.Application` (`com.keithvassallo.SmartDnd`). Starts the
  daemon detached if it isn't running (`host.start_daemon_detached`, passing `--config` on), then
  takes its config from the daemon (`get_config`) so it always edits the file the daemon uses.
  `--config` is applied process-wide by `config.set_default_config_path`. Talks to
  the daemon over IPC from a single background worker (`MainWindow._run_in_background`), never
  from the GTK thread. If the daemon is down it writes `config.json` directly and calls plugins
  in-process.
- **CLI** one-shots (`status`, `toggle`, `eval`, `list-calendars`, `plugins`, `test`): IPC first,
  most fall back to in-process work when the daemon is down.

## The evaluate loop (`daemon.py: SmartDndDaemon.evaluate`)

1. Take cached events. If older than 60s, start a background refresh and carry on with the stale
   cache (event times are absolute, so stale data is still correct for timing). When the refresh
   lands, `_on_events_fetched` re-runs evaluate. A result from a replaced calendar plugin is
   dropped via `_calendar_generation`.
2. `scheduler.first_active_at` + `matcher.active_match_at` give the active schedule/event, which
   also becomes `Status.trigger_name`.
3. `coordinator.compute_desired` then `coordinator.reconcile` against current DND state and ownership.
   DND state is queried once per evaluate (each Caelestia query is a ~170ms subprocess).
4. Apply `set_dnd` if reconcile says so.
5. Compute `next_on_ms` / `next_off_ms`, arm the timer at the earliest boundary (capped at 900s).
6. Push the new `Status` to the tray.

Triggers: the timer, IPC `save_config` / `evaluate` / `toggle_dnd`, resume from sleep, tray clicks.

## Module map

| Module | Role |
|---|---|
| `models.py` | Dataclasses. `Config` and `CalendarRule.from_dict` also accept camelCase keys (interop with the extension). |
| `config.py` | `$XDG_CONFIG_HOME/smart-dnd/config.json`, atomic write via `.tmp`. Missing file: writes defaults. Parse error: returns defaults without saving. |
| `scheduler.py` | Pure. Wrap-midnight windows, end-exclusive, `start == end` means never active. |
| `matcher.py` | Pure. Case-insensitive `contains` / `startsWith` / `endsWith` / `regex`; bad regex means no match. |
| `coordinator.py` | Pure. Edge-triggered ownership (see invariants). |
| `format.py` | Relative times: `Today, 22:00`, `Tomorrow, 07:00`, `Wednesday, 09:00`, `Wed 14 Oct, 18:00`. |
| `ipc.py` | Unix socket `$XDG_RUNTIME_DIR/smart-dnd/ipc.sock`. One newline-terminated JSON request per connection, `{"method", "params"}` in, `{"result", "error"}` out. Methods: `get_status`, `get_config`, `save_config`, `evaluate`, `toggle_dnd`, `list_calendars`, `get_events`, `list_plugins`. Dispatch lives in `SmartDndDaemon._dispatch_ipc`. |
| `sni.py` | Hand-rolled `org.kde.StatusNotifierItem` at `/StatusNotifierItem` and `com.canonical.dbusmenu` at `/MenuBar` via Gio. Left click toggles the GUI window (D-Bus `ActivateAction "toggle"` on the GUI app, else spawns `smart-dnd gui`). Middle click toggles DND. Menu item ids are fixed: 1 show/hide, 3 toggle DND, 4 next-transition label, 6 quit. |
| `plugins/manager.py` | Discovery order: entry points, then `_register_builtins()` fallback, then user drop-ins in `~/.config/smart-dnd/plugins/{calendar,notifications,gui}/*.py` (a drop-in with the same `plugin_id` overrides). |
| `plugins/calendar/evolution.py` | Evolution Data Server via ECal 2.0. One cached `ECal.Client` per source. Instance times resolved with `as_timet_with_zone`. |
| `plugins/notifications/` | `caelestia` (`caelestia shell notifs isDndEnabled/enableDnd/disableDnd`), `swaync` (`swaync-client -D`, `-d` only toggles so `set_dnd` reads first), `dunst` (`dunstctl is-paused/set-paused`). All shell out via `host.host_argv` with a 5s timeout; a missing binary means "DND off" and `set_dnd` is a no-op. |
| `host.py` | Flatpak helpers. `IN_FLATPAK`; `host_argv`/`which_host` run and find host CLIs through `flatpak-spawn --host`; `start_daemon_detached` starts the daemon so it outlives the GUI (a portal-spawned instance inside the Flatpak). |
| `autostart.py` | Start at login via XDG autostart entries: system entry from packages, per-user `Hidden=true` override, user entry with an absolute `Exec` when there's no package entry. In the Flatpak: Background portal on GNOME/KDE, direct write elsewhere, plus a once-only default-on at first launch. Backs the GUI switch and `smart-dnd autostart`. |
| `plugins/gui/adwaita/` | `window.py` (header status button, schedules and calendar-rule pages, 3s status poll), `schedule_page.py`, `calendar_page.py`, `general_dialog.py` (master switch, all-day, backend pickers, monochrome tray). |

## Invariants and gotchas

- **Never stomp manual DND.** Act only on edges of `desired`. On the rising edge take ownership
  (adopt it if DND is already on). On the falling edge turn off only what we own. A manual change
  mid-window is left alone. `reconcile` stays pure and fully tested; the table is in
  `docs/architecture.md`.
- **Day numbering is JS-style, 0 = Sunday.** Convert with `py_to_js_dow`, never use Python's
  `weekday()` directly. Config `days` uses the same numbering.
- **Units:** `CalendarEvent.start/end` are epoch seconds. Matcher windows, scheduler results and
  `Status.next_*_ms` are epoch milliseconds.
- **Keep slow work off both main loops.** The daemon serves IPC, the tray and timers on one
  thread, so any blocking plugin call stalls all of them; calendar fetches already run in a thread.
  A cold Evolution Data Server takes about 8s to return events for 20 sources. In the GUI, never
  call the daemon from the GTK thread: use `_run_in_background` (`serial=True` for IPC, `False` for
  slow one-offs so saves don't queue behind them).
- **GUI saves are debounced (400ms) and collapsed.** Only the newest config snapshot is written;
  a close request flushes a pending save, and the worker drains before the process exits.
- **GTK is main-thread only.** Background threads hand results back with `GLib.idle_add`.
- **`smart-dnd eval` runs the daemon class without a main loop,** so it calls
  `refresh_events_blocking()` first. Any new one-shot use of `SmartDndDaemon` needs the same.
- **Icons:** the wheel ships only `smart_dnd/`, not `data/`. `sni.find_icon_file` looks in the
  source tree first, then `$XDG_DATA_HOME` / `$XDG_DATA_DIRS` `icons/hicolor` (where the packages
  and Flatpak install them). `ensure_icons_installed` copies source-tree icons into `~/.local` for
  dev installs and does nothing otherwise.
- **Tray registration:** the daemon owns `org.kde.StatusNotifierItem-<pid>-1` and watches
  `org.kde.StatusNotifierWatcher`, re-registering whenever the watcher (re)appears, e.g. when
  Caelestia reloads. Tray-launched GUIs start via `sys.executable -m smart_dnd.cli gui` because
  the systemd PATH may not contain the `smart-dnd` binary.
- **Start at login is XDG autostart, not systemd.** Packages install
  `/etc/xdg/autostart/com.keithvassallo.SmartDnd.desktop` (on for everyone); a user switches it off
  with a `Hidden=true` override of the same name in `~/.config/autostart` (`autostart.py`). There is
  deliberately no systemd user unit: a globally enabled user unit can't be switched off per user
  without masking it. Verify changes with `/usr/lib/systemd/user-generators/systemd-xdg-autostart-generator`
  run against temp `XDG_CONFIG_HOME`/`XDG_CONFIG_DIRS`, which is what UWSM/GNOME/KDE sessions use.
- **Tray icon:** full-colour `com.keithvassallo.SmartDnd` by default; symbolic is opt-in
  (`monochrome_tray_icon`) because Caelestia does not recolour symbolic icons, which leaves a black
  icon on a dark panel.
- **Versions:** `pyproject.toml`, `smart_dnd/__init__.py` and the newest metainfo `<release>` must
  agree (`just check-version`, also a test). `CHANGELOG.md` follows Keep a Changelog and SemVer: add
  user-facing changes under `[Unreleased]` as you make them. `just release` (with
  `packaging/release.py`) settles the version, commits, tags and pushes; never run it yourself,
  since it publishes to GitHub and the AUR. Test it in a scratch clone whose `origin` is a local
  bare repo. The About dialog reads `__version__`; deb/rpm/AUR
  versions are set from the tag by the release workflow.
- **Flatpak sandbox rules:**
  - Any subprocess call to a host tool must go through `host.host_argv` / `which_host`.
  - The daemon must be started as its own instance (`flatpak-spawn smart-dnd daemon`): when a
    Flatpak's main process exits, everything else in its sandbox is killed.
  - Config lives in `~/.var/app/com.keithvassallo.SmartDnd/config`; only the IPC socket dir is
    shared with the host (`--filesystem=xdg-run/smart-dnd:create`).
  - Image loading goes through glycin, which needs an installed app: `flatpak-builder --run` can't
    load the tray pixmap, so test that in an installed build.
  - Flatpak export rejects non-square icons; the SVGs use a square `viewBox` for that reason.

## Adding a built-in plugin

1. Module under `smart_dnd/plugins/<calendar|notifications|gui>/`, subclassing the kind's `base.py` ABC.
2. Entry point in `pyproject.toml`.
3. Fallback import in `PluginManager._register_builtins()`.
4. The GUI's hardcoded offline fallback list in `window.py` (`_available_plugins` / `_fetch_plugins`).
5. Discovery/instantiation test in `tests/test_plugins.py`, mocking the external binary or D-Bus.
6. If it shells out, use `host_argv`/`which_host`, and add any new D-Bus name it talks to to the
   Flatpak manifest's `finish-args`.

## Code style

`from __future__ import annotations` at the top of every module; `typing.List/Dict/Optional`;
dataclasses for data; `logger = logging.getLogger(__name__)` per module. Desktop integrations are
wrapped in broad `try/except` that logs and degrades rather than crashing the daemon.

## Tests

pytest covers the pure logic (scheduler, matcher, coordinator), plugin discovery, the SNI menu
model and icon lookup, and the daemon's evaluate loop and background fetch (`tests/test_daemon.py`,
with fake plugins and a temp `XDG_RUNTIME_DIR`). There are no IPC or GUI tests. Tests import `gi`,
so any test environment needs PyGObject and the typelibs.

For GUI responsiveness, measure rather than eyeball: build `MainWindow` without presenting it
against a throwaway daemon (`smart-dnd --config <tmp> daemon`, automation off), drive the pages,
and record the largest gap between 20ms main-loop ticks. Before the 2026-10-01 fix, adding 5
schedules and typing names stalled 19 times over 250ms; after, the worst stall was ~28ms.

## CI and release

- `.github/workflows/ci.yml`: ubuntu-latest, distro `python3-gi` + typelibs, a
  `--system-site-packages` venv, pytest. Deliberately not `actions/setup-python` + pip PyGObject:
  PyGObject publishes no wheels, so that path compiles it and pycairo from source.
- `.github/workflows/release.yml` on `v*` tags (or `just release-dry-run`, which publishes nothing):
  version check, wheel + sdist, `.deb` and `.rpm` (each installed and smoke-tested), a Flatpak
  bundle, FriendlyHub submission files, the GitHub release, then the AUR push. Full description and
  one-time AUR key setup in `docs/releasing.md`.
- Packaging lives in `packaging/`: `debian/` (copied to `debian/` at build time), `rpm/`,
  `aur/smart-dnd` (published by CI from the release tarball), `aur/smart-dnd-git` (manual),
  `flatpak/` (manifest builds the working tree; `friendlyhub-manifest.py` swaps in the git tag).
- The Flatpak bundles libical + EDS client libraries (with introspection) and build-only
  `hatchling` wheels, pinned with `sha256`. Distribution is FriendlyHub, not Flathub.
- To test the Flatpak locally without touching the repo, copy the manifest with an absolute source
  `path` (and an installed `runtime-version`), build with `--state-dir`/build dir in scratch, and
  use `--repo=<scratch>` to run export validation without installing.
- Keep every Action on its latest major version. Check with
  `gh api repos/<owner>/<repo>/releases/latest --jq .tag_name`.
- After pushing, check the run with `gh run list` / `gh run view <id> --log-failed`.
