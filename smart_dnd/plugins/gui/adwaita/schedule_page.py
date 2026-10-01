"""Schedule management page in Libadwaita."""

from __future__ import annotations

import uuid
from typing import Callable, List

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from smart_dnd.models import Config, Schedule

DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


class ScheduleRow(Adw.ExpanderRow):
    """Row representing a single time schedule."""

    def __init__(
        self,
        schedule: Schedule,
        on_change: Callable[[], None],
        on_delete: Callable[[Schedule], None],
    ) -> None:
        super().__init__()
        self.schedule = schedule
        self.on_change = on_change
        self.on_delete = on_delete

        # Enable switch as suffix
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.set_active(schedule.enabled)
        self.switch.connect("notify::active", self._on_switch_toggled)
        self.add_suffix(self.switch)

        self._build_content()
        self._update_headers()

    def _update_headers(self) -> None:
        self.set_title(self.schedule.name or "Untitled Schedule")
        days_str = ", ".join(DAY_LABELS[d] for d in sorted(self.schedule.days)) if self.schedule.days else "No days"
        self.set_subtitle(f"{days_str} • {self.schedule.start} – {self.schedule.end}")

    def _on_switch_toggled(self, *args) -> None:
        self.schedule.enabled = self.switch.get_active()
        self.on_change()

    def _build_content(self) -> None:
        # Name entry
        self.name_entry = Adw.EntryRow(title="Name", text=self.schedule.name)
        self.name_entry.connect("changed", self._on_name_changed)
        self.add_row(self.name_entry)

        # Days selector
        days_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_top=8, margin_bottom=8)
        self.day_buttons: List[Gtk.ToggleButton] = []
        for i, label in enumerate(DAY_LABELS):
            btn = Gtk.ToggleButton(label=label)
            btn.set_active(i in self.schedule.days)
            btn.connect("toggled", self._on_day_toggled, i)
            self.day_buttons.append(btn)
            days_box.append(btn)

        days_action_row = Adw.ActionRow(title="Active Days")
        days_action_row.add_suffix(days_box)
        self.add_row(days_action_row)

        # Time range
        time_row = Adw.ActionRow(title="Time Range")
        time_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        start_lbl = Gtk.Label(label="Start:")
        time_box.append(start_lbl)
        self.start_entry = Gtk.Entry(text=self.schedule.start, max_length=5, width_chars=5)
        self.start_entry.connect("changed", self._on_time_changed)
        time_box.append(self.start_entry)

        end_lbl = Gtk.Label(label="End:")
        time_box.append(end_lbl)
        self.end_entry = Gtk.Entry(text=self.schedule.end, max_length=5, width_chars=5)
        self.end_entry.connect("changed", self._on_time_changed)
        time_box.append(self.end_entry)

        time_row.add_suffix(time_box)
        self.add_row(time_row)

        # Delete button
        del_row = Adw.ActionRow()
        del_btn = Gtk.Button(label="Delete Schedule", css_classes=["destructive-action"], valign=Gtk.Align.CENTER)
        del_btn.connect("clicked", lambda *_: self.on_delete(self.schedule))
        del_row.add_suffix(del_btn)
        self.add_row(del_row)

    def _on_name_changed(self, entry: Adw.EntryRow) -> None:
        self.schedule.name = entry.get_text()
        self._update_headers()
        self.on_change()

    def _on_day_toggled(self, btn: Gtk.ToggleButton, day_idx: int) -> None:
        if btn.get_active():
            if day_idx not in self.schedule.days:
                self.schedule.days.append(day_idx)
                self.schedule.days.sort()
        else:
            if day_idx in self.schedule.days:
                self.schedule.days.remove(day_idx)
        self._update_headers()
        self.on_change()

    def _on_time_changed(self, *args) -> None:
        s_txt = self.start_entry.get_text()
        e_txt = self.end_entry.get_text()
        if len(s_txt) == 5 and ":" in s_txt:
            self.schedule.start = s_txt
        if len(e_txt) == 5 and ":" in e_txt:
            self.schedule.end = e_txt
        self._update_headers()
        self.on_change()


class SchedulePage(Adw.PreferencesPage):
    """Preferences page displaying all schedules."""

    def __init__(self, config: Config, on_save: Callable[[Config], None]) -> None:
        super().__init__()
        self.config = config
        self.on_save = on_save

        self.group = Adw.PreferencesGroup(title="Active Schedules")

        add_btn = Gtk.Button(
            icon_name="list-add-symbolic",
            tooltip_text="Add Schedule",
            css_classes=["flat"],
            valign=Gtk.Align.CENTER,
        )
        add_btn.connect("clicked", self._on_add_schedule)
        self.group.set_header_suffix(add_btn)
        self.add(self.group)

        self._rebuild()

    def _rebuild(self) -> None:
        # Clear existing rows
        for child in list(self.group.observe_children()):
            self.group.remove(child)

        for sched in self.config.schedules:
            row = ScheduleRow(
                sched,
                on_change=lambda: self.on_save(self.config),
                on_delete=self._on_delete_schedule,
            )
            self.group.add(row)

    def _on_add_schedule(self, *args) -> None:
        new_sched = Schedule(
            id=str(uuid.uuid4())[:8],
            name="New Schedule",
            days=[1, 2, 3, 4, 5],
            start="22:00",
            end="07:00",
            enabled=True,
        )
        self.config.schedules.append(new_sched)
        self.on_save(self.config)
        self._rebuild()

    def _on_delete_schedule(self, sched: Schedule) -> None:
        self.config.schedules = [s for s in self.config.schedules if s.id != sched.id]
        self.on_save(self.config)
        self._rebuild()
