# Changelog

All notable changes to Smart DND for Linux are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-01

### Added

- **Scheduled Do Not Disturb**: turn DND on between two times on the days of the week
  you choose, including windows that cross midnight. Schedules follow local time
  across daylight saving changes.
- **Calendar-based DND**: turn DND on during calendar events whose title matches a
  pattern (contains, starts with, ends with, or a regular expression), optionally
  limited to specific calendars. Events come from Evolution Data Server, so Google,
  Nextcloud, CalDAV, GNOME Online Accounts and local calendars all work.
- **Buffer offsets**: start DND up to two hours before an event and keep it on up to
  two hours after.
- **Respects manual changes**: Smart DND only acts at schedule and event boundaries,
  only turns off DND it turned on itself, and releases it when the daemon stops.
- **Notification systems**: Caelestia shell, SwayNotificationCenter and Dunst.
- **Preferences window**: a Libadwaita app with Schedules and Calendar Rules pages,
  the next activation shown for each schedule and rule, and General Settings for
  the master switch, ignoring all-day events, start at login, the notification and
  calendar backends, and the tray icon style.
- **Tray icon**: show or hide the window, toggle DND, and see when DND next turns on
  or off. Full colour by default, with an optional monochrome icon for desktops
  that recolour symbolic icons.
- **Start at login**: on by default for packaged installs, and for the Flatpak after
  its first launch. Turn it off in General Settings or with
  `smart-dnd autostart off`.
- **Command line**: `smart-dnd status`, `toggle`, `test` (a dry run of your rules
  against upcoming events), `eval`, `list-calendars`, `plugins`, `autostart`, `gui`
  and `daemon`.
- **Plugins**: add calendar sources, notification systems or frontends by dropping a
  Python file into `~/.config/smart-dnd/plugins/`, or by publishing a package with
  an entry point.
- Re-checks schedules and events after the system resumes from suspend.
- Packages for Debian and Ubuntu (`.deb`), Fedora (`.rpm`), Arch Linux (AUR:
  `smart-dnd` and `smart-dnd-git`) and Flatpak (via FriendlyHub), plus a Python wheel.

[Unreleased]: https://github.com/keithvassallomt/smart-dnd-linux/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/keithvassallomt/smart-dnd-linux/releases/tag/v0.1.0
