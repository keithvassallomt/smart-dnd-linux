"""Calendar rules page in Libadwaita."""

from __future__ import annotations

import time
import uuid
from typing import Callable, List

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from smart_dnd.format import format_when
from smart_dnd.matcher import (
    calendar_next_transition,
    next_enable,
    rules_active_at,
)
from smart_dnd.models import CalendarEvent, CalendarRule, CalendarSource, Config

MATCH_TYPES = [
    ("contains", "Contains"),
    ("startsWith", "Starts with"),
    ("endsWith", "Ends with"),
    ("regex", "Matches regex"),
]


class CalendarRuleRow(Adw.ExpanderRow):
    """Row representing a single calendar rule."""

    def __init__(
        self,
        rule: CalendarRule,
        calendars: List[CalendarSource],
        events: List[CalendarEvent],
        config: Config,
        on_change: Callable[[], None],
        on_delete: Callable[[CalendarRule], None],
    ) -> None:
        super().__init__()
        self.rule = rule
        self.calendars = calendars
        self.events = events
        self.config = config
        self.on_change = on_change
        self.on_delete = on_delete

        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.set_active(rule.enabled)
        self.switch.connect("notify::active", self._on_switch_toggled)
        self.add_suffix(self.switch)

        self._build_content()
        self._update_headers()

    def _update_headers(self) -> None:
        now_sec = time.time()
        now_ms = now_sec * 1000.0

        self.set_title(self.rule.name or "Untitled Rule")
        m_label = next((label for k, label in MATCH_TYPES if k == self.rule.match_type), self.rule.match_type)
        cal_str = f"{len(self.rule.calendars)} calendars" if self.rule.calendars else "All calendars"
        pat_str = f'"{self.rule.pattern}"' if self.rule.pattern else "Any event"

        if not self.rule.enabled:
            status_text = "Disabled"
        elif rules_active_at([self.rule], self.events, now_ms, ignore_all_day=self.config.ignore_all_day):
            ends_ms = calendar_next_transition([self.rule], self.events, now_ms, ignore_all_day=self.config.ignore_all_day)
            status_text = f"Active now (ends {format_when(now_ms, ends_ms)})"
        else:
            nxt_on_ms = next_enable([self.rule], self.events, now_ms, ignore_all_day=self.config.ignore_all_day)
            if nxt_on_ms:
                status_text = f"Next: {format_when(now_ms, nxt_on_ms)}"
            else:
                status_text = "No upcoming events"

        self.set_subtitle(f"{status_text} • {m_label} {pat_str} • {cal_str}")

    def _on_switch_toggled(self, *args) -> None:
        self.rule.enabled = self.switch.get_active()
        self.on_change()

    def _build_content(self) -> None:
        # Name
        self.name_entry = Adw.EntryRow(title="Rule Name", text=self.rule.name)
        self.name_entry.connect("changed", self._on_name_changed)
        self.add_row(self.name_entry)

        # Match Type
        type_labels = [label for _, label in MATCH_TYPES]
        self.type_combo = Adw.ComboRow(
            title="Match Criteria",
            model=Gtk.StringList.new(type_labels),
        )
        current_idx = next((i for i, (k, _) in enumerate(MATCH_TYPES) if k == self.rule.match_type), 0)
        self.type_combo.set_selected(current_idx)
        self.type_combo.connect("notify::selected", self._on_type_changed)
        self.add_row(self.type_combo)

        # Pattern
        self.pattern_entry = Adw.EntryRow(title="Pattern / Keyword", text=self.rule.pattern)
        self.pattern_entry.connect("changed", self._on_pattern_changed)
        self.add_row(self.pattern_entry)

        # Buffer Offsets
        offset_row = Adw.ActionRow(title="Buffer Offsets")
        offset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        start_lbl = Gtk.Label(label="Start offset (min):")
        offset_box.append(start_lbl)
        self.start_spin = Gtk.SpinButton.new_with_range(-120, 120, 5)
        self.start_spin.set_value(self.rule.enable_offset_min)
        self.start_spin.connect("value-changed", self._on_offset_changed)
        offset_box.append(self.start_spin)

        end_lbl = Gtk.Label(label="End offset (min):")
        offset_box.append(end_lbl)
        self.end_spin = Gtk.SpinButton.new_with_range(-120, 120, 5)
        self.end_spin.set_value(self.rule.disable_offset_min)
        self.end_spin.connect("value-changed", self._on_offset_changed)
        offset_box.append(self.end_spin)

        offset_row.add_suffix(offset_box)
        self.add_row(offset_row)

        # Calendars multi-select expander
        if self.calendars:
            cal_expander = Adw.ExpanderRow(title="Target Calendars", subtitle="Leave unselected to apply to all")
            for c in self.calendars:
                check = Gtk.CheckButton(label=c.name)
                check.set_active(c.uid in self.rule.calendars)
                check.connect("toggled", self._on_calendar_toggled, c.uid)
                row = Adw.ActionRow()
                row.add_prefix(check)
                cal_expander.add_row(row)
            self.add_row(cal_expander)

        # Delete
        del_row = Adw.ActionRow()
        del_btn = Gtk.Button(label="Delete Rule", css_classes=["destructive-action"], valign=Gtk.Align.CENTER)
        del_btn.connect("clicked", lambda *_: self.on_delete(self.rule))
        del_row.add_suffix(del_btn)
        self.add_row(del_row)

    def _on_name_changed(self, entry: Adw.EntryRow) -> None:
        self.rule.name = entry.get_text()
        self._update_headers()
        self.on_change()

    def _on_type_changed(self, combo: Adw.ComboRow, *args) -> None:
        idx = combo.get_selected()
        if idx < len(MATCH_TYPES):
            self.rule.match_type = MATCH_TYPES[idx][0]
            self._update_headers()
            self.on_change()

    def _on_pattern_changed(self, entry: Adw.EntryRow) -> None:
        self.rule.pattern = entry.get_text()
        self._update_headers()
        self.on_change()

    def _on_offset_changed(self, *args) -> None:
        self.rule.enable_offset_min = int(self.start_spin.get_value())
        self.rule.disable_offset_min = int(self.end_spin.get_value())
        self.on_change()

    def _on_calendar_toggled(self, btn: Gtk.CheckButton, uid: str) -> None:
        if btn.get_active():
            if uid not in self.rule.calendars:
                self.rule.calendars.append(uid)
        else:
            if uid in self.rule.calendars:
                self.rule.calendars.remove(uid)
        self._update_headers()
        self.on_change()


class CalendarPage(Adw.PreferencesPage):
    """Preferences page for Calendar event rules."""

    def __init__(
        self,
        config: Config,
        calendars: List[CalendarSource],
        events: List[CalendarEvent],
        on_save: Callable[[Config], None],
    ) -> None:
        super().__init__()
        self.config = config
        self.calendars = calendars
        self.events = events
        self.on_save = on_save
        self._rows: List[CalendarRuleRow] = []

        self.group = Adw.PreferencesGroup(title="Calendar Matching Rules")

        add_btn = Gtk.Button(
            icon_name="list-add-symbolic",
            tooltip_text="Add Rule",
            css_classes=["flat"],
            valign=Gtk.Align.CENTER,
        )
        add_btn.connect("clicked", self._on_add_rule)
        self.group.set_header_suffix(add_btn)
        self.add(self.group)

        self._rebuild()

    def set_calendar_data(self, calendars: List[CalendarSource], events: List[CalendarEvent]) -> None:
        self.calendars = calendars
        self.events = events
        self._rebuild()

    def _rebuild(self) -> None:
        for row in list(self._rows):
            self.group.remove(row)
        self._rows.clear()

        for rule in self.config.calendar_rules:
            self._add_row_for_rule(rule)

    def _add_row_for_rule(self, rule: CalendarRule) -> CalendarRuleRow:
        row = CalendarRuleRow(
            rule,
            self.calendars,
            self.events,
            self.config,
            on_change=lambda: self.on_save(self.config),
            on_delete=self._on_delete_rule,
        )
        self._rows.append(row)
        self.group.add(row)
        return row

    def _on_add_rule(self, *args) -> None:
        new_rule = CalendarRule(
            id=str(uuid.uuid4())[:8],
            name="New Rule",
            match_type="contains",
            pattern="",
            calendars=[],
            enable_offset_min=0,
            disable_offset_min=0,
            enabled=True,
        )
        self.config.calendar_rules.append(new_rule)
        row = self._add_row_for_rule(new_rule)
        row.set_expanded(True)
        self.on_save(self.config)

    def _on_delete_rule(self, rule: CalendarRule) -> None:
        self.config.calendar_rules = [r for r in self.config.calendar_rules if r.id != rule.id]
        for row in list(self._rows):
            if row.rule.id == rule.id:
                self.group.remove(row)
                self._rows.remove(row)
                break
        self.on_save(self.config)
