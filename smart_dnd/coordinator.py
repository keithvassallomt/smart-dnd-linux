"""Reconciliation and ownership tracking logic ported from smart-dnd."""

from __future__ import annotations

from typing import NamedTuple, Optional


class ReconcileResult(NamedTuple):
    owned: bool
    action: Optional[str]  # "on", "off", or None


def compute_desired(
    master_enabled: bool,
    schedule_active: bool,
    calendar_active: bool,
) -> bool:
    """Determine whether DND should ideally be active."""
    return master_enabled and (schedule_active or calendar_active)


def reconcile(
    desired: bool,
    last_desired: bool,
    owned: bool,
    dnd_on: bool,
) -> ReconcileResult:
    """Reconcile desired state with current system DND state.

    Ensures that manual toggles by the user are not trampled:
    - On rising edge: turns DND on (or adopts ownership if already on manually).
    - On falling edge: releases DND only if smart-dnd owned it and it is still on.
    - Mid-window manual overrides (e.g. user toggles DND off during an event)
      are preserved because there is no edge.
    """
    if desired and not last_desired:
        return ReconcileResult(owned=True, action=None if dnd_on else "on")
    if not desired and last_desired:
        if owned and dnd_on:
            return ReconcileResult(owned=False, action="off")
        return ReconcileResult(owned=False, action=None)
    return ReconcileResult(owned=owned, action=None)
