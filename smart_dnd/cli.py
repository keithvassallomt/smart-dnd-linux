"""CLI interface for Smart DND."""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import sys
import time
from typing import Optional

from smart_dnd.config import load_config
from smart_dnd.daemon import SmartDndDaemon
from smart_dnd.ipc import SmartDndClient
from smart_dnd.models import Config, Status
from smart_dnd.plugins.manager import PluginManager


def get_client() -> SmartDndClient:
    return SmartDndClient()


def format_ms(ts_ms: Optional[float]) -> str:
    if not ts_ms:
        return "None"
    dt = datetime.datetime.fromtimestamp(ts_ms / 1000.0)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def cmd_status(args: argparse.Namespace) -> int:
    client = get_client()
    if not client.is_daemon_running():
        print("Smart DND daemon is NOT running.")
        print("Run 'smart-dnd daemon' or enable the systemd service with:")
        print("  systemctl --user enable --now smart-dnd")
        return 1

    try:
        status: Status = client.get_status()
        print("=== Smart DND Status ===")
        print(f"DND Active:           {'YES' if status.active else 'NO'}")
        print(f"Reason:               {status.reason}")
        print(f"Owned by Smart DND:   {'YES' if status.owned else 'NO'}")
        print(f"Next Activation:      {format_ms(status.next_on_ms)}")
        print(f"Next Deactivation:    {format_ms(status.next_off_ms)}")
        print(f"Notification Backend: {status.notification_backend}")
        print(f"Calendar Backend:     {status.calendar_backend}")
        return 0
    except Exception as e:
        print(f"Error querying daemon: {e}", file=sys.stderr)
        return 1


def cmd_toggle(args: argparse.Namespace) -> int:
    client = get_client()
    if client.is_daemon_running():
        res = client.toggle_dnd()
        status = client.get_status()
        print(f"DND toggled. Now: {'ACTIVE' if status.active else 'INACTIVE'}")
        return 0

    # If daemon is not running, toggle directly via active notification plugin
    config = load_config()
    pm = PluginManager()
    try:
        notif = pm.get_notification_plugin(config.notification_backend)
        cur = notif.is_dnd_enabled()
        notif.set_dnd(not cur)
        print(f"DND toggled directly via {config.notification_backend}. Now: {'ACTIVE' if not cur else 'INACTIVE'}")
        return 0
    except Exception as e:
        print(f"Failed to toggle DND: {e}", file=sys.stderr)
        return 1


def cmd_eval(args: argparse.Namespace) -> int:
    client = get_client()
    if not client.is_daemon_running():
        print("Daemon is not running. Launching single in-process evaluation...")
        daemon = SmartDndDaemon(config_path=args.config)
        status = daemon.evaluate()
    else:
        status = client.evaluate()

    print("=== Evaluation Result ===")
    print(f"DND Active:        {'YES' if status.active else 'NO'}")
    print(f"Reason:            {status.reason}")
    print(f"Next Activation:   {format_ms(status.next_on_ms)}")
    print(f"Next Deactivation: {format_ms(status.next_off_ms)}")
    return 0


def cmd_list_calendars(args: argparse.Namespace) -> int:
    client = get_client()
    if client.is_daemon_running():
        calendars = client.list_calendars()
    else:
        config = load_config(args.config)
        pm = PluginManager()
        cal_plugin = pm.get_calendar_plugin(config.calendar_backend)
        calendars = cal_plugin.list_calendars()

    print(f"Found {len(calendars)} calendar sources:")
    for c in calendars:
        print(f" • {c.name} (uid: {c.uid})")
    return 0


def cmd_plugins(args: argparse.Namespace) -> int:
    pm = PluginManager()
    print("=== Discovered Plugins ===")
    print("Calendar Backends:")
    for pid, cls in pm.calendar_plugins.items():
        print(f"  • {pid}: {cls.name} - {cls.description}")
    print("\nNotification Systems:")
    for pid, cls in pm.notification_plugins.items():
        print(f"  • {pid}: {cls.name} - {cls.description}")
    print("\nGUI Frontends:")
    for pid, cls in pm.gui_plugins.items():
        print(f"  • {pid}: {cls.name} - {cls.description}")
    return 0


def cmd_test_rules(args: argparse.Namespace) -> int:
    """Dry-run test: check current schedules and events against rules without changing state."""
    config = load_config(args.config)
    pm = PluginManager()
    cal_plugin = pm.get_calendar_plugin(config.calendar_backend)

    now_sec = time.time()
    now_ms = now_sec * 1000.0
    now_dt = datetime.datetime.fromtimestamp(now_sec)

    from smart_dnd.matcher import matching_windows, title_matches
    from smart_dnd.scheduler import py_to_js_dow, schedule_active_at, to_minutes

    dow = py_to_js_dow(now_dt.weekday())
    minutes = now_dt.hour * 60 + now_dt.minute

    print(f"Current local time: {now_dt.strftime('%Y-%m-%d %H:%M:%S')} (Day of week: {dow}, Minute: {minutes})")
    print(f"Master Enabled: {config.master_enabled}")

    print("\n-- Schedule Evaluation --")
    if not config.schedules:
        print("  No schedules defined.")
    for s in config.schedules:
        active = schedule_active_at(s, dow, minutes)
        print(f"  Schedule '{s.name}' ({s.start} - {s.end}): {'ACTIVE' if active else 'Inactive'} (Enabled: {s.enabled})")

    print("\n-- Calendar Event Evaluation --")
    events = cal_plugin.get_events(now_sec - 3600, now_sec + 86400 * 2)
    print(f"  Fetched {len(events)} events in the window [-1h .. +48h].")

    for ev in events:
        s_dt = datetime.datetime.fromtimestamp(ev.start).strftime("%a %H:%M")
        e_dt = datetime.datetime.fromtimestamp(ev.end).strftime("%H:%M")
        all_day_str = " [ALL DAY]" if ev.all_day else ""
        matches: list[str] = []
        for r in config.calendar_rules:
            if not r.enabled:
                continue
            if config.ignore_all_day and ev.all_day:
                continue
            if r.calendars and ev.source_uid not in r.calendars:
                continue
            if title_matches(r, ev.summary):
                matches.append(r.name)

        status_str = f"--> MATCHES: {', '.join(matches)}" if matches else "no match"
        print(f"  Event: '{ev.summary}' ({s_dt} - {e_dt}){all_day_str} [{status_str}]")

    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    daemon = SmartDndDaemon(config_path=args.config)
    try:
        daemon.start()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logger = logging.getLogger("smart-dnd")
        logger.exception("Daemon error: %s", e)
        return 1


def cmd_gui(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    client = get_client()
    pm = PluginManager()

    gui_backend = config.gui_backend or "adwaita"
    try:
        gui_plugin = pm.get_gui_plugin(gui_backend)
        gui_plugin.launch(client, config)
        return 0
    except Exception as e:
        print(f"Failed to launch GUI plugin '{gui_backend}': {e}", file=sys.stderr)
        return 1


def daemon_main() -> None:
    parser = argparse.ArgumentParser(description="Smart DND background daemon")
    parser.add_argument("--config", "-c", help="Path to config file", default=None)
    parser.add_argument("--debug", "-d", help="Enable debug logging", action="store_true")
    args = parser.parse_args()
    sys.exit(cmd_daemon(args))


def gui_main() -> None:
    parser = argparse.ArgumentParser(description="Smart DND Preferences GUI")
    parser.add_argument("--config", "-c", help="Path to config file", default=None)
    args = parser.parse_args()
    sys.exit(cmd_gui(args))


def main() -> None:
    parser = argparse.ArgumentParser(prog="smart-dnd", description="Smart Do Not Disturb for Linux Desktops")
    parser.add_argument("--config", "-c", help="Path to config file", default=None)

    subparsers = parser.add_subparsers(dest="command")

    # daemon
    p_daemon = subparsers.add_parser("daemon", help="Run background daemon")
    p_daemon.add_argument("--debug", "-d", help="Enable debug logging", action="store_true")

    # gui
    subparsers.add_parser("gui", help="Open preferences GUI (Libadwaita)")

    # status
    subparsers.add_parser("status", help="Show current DND and automation status")

    # toggle
    subparsers.add_parser("toggle", help="Toggle Do Not Disturb")

    # eval
    subparsers.add_parser("eval", help="Trigger evaluation of rules")

    # list-calendars
    subparsers.add_parser("list-calendars", help="List available calendars")

    # plugins
    subparsers.add_parser("plugins", help="List all discovered plugins")

    # test
    subparsers.add_parser("test", help="Dry-run evaluation of rules against upcoming events")

    args = parser.parse_args()
    if not args.command:
        # Default action when run with no arguments: open GUI if in graphical session, else show status
        if sys.stdout.isatty() and not any(env in os.environ for env in ("WAYLAND_DISPLAY", "DISPLAY")):
            sys.exit(cmd_status(args))
        else:
            sys.exit(cmd_gui(args))

    commands = {
        "daemon": cmd_daemon,
        "gui": cmd_gui,
        "status": cmd_status,
        "toggle": cmd_toggle,
        "eval": cmd_eval,
        "list-calendars": cmd_list_calendars,
        "plugins": cmd_plugins,
        "test": cmd_test_rules,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        sys.exit(cmd_fn(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
