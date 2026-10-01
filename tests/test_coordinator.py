"""Tests for coordinator logic mirroring smart-dnd test suite."""

from smart_dnd.coordinator import ReconcileResult, compute_desired, reconcile


def test_compute_desired_requires_master_and_source():
    assert compute_desired(master_enabled=True, schedule_active=True, calendar_active=False) is True
    assert compute_desired(master_enabled=True, schedule_active=False, calendar_active=True) is True
    assert compute_desired(master_enabled=False, schedule_active=True, calendar_active=True) is False
    assert compute_desired(master_enabled=True, schedule_active=False, calendar_active=False) is False


def test_rising_edge_turns_dnd_on_and_takes_ownership():
    res = reconcile(desired=True, last_desired=False, owned=False, dnd_on=False)
    assert res == ReconcileResult(owned=True, action="on")


def test_rising_edge_adopts_ownership_if_already_on_manually():
    res = reconcile(desired=True, last_desired=False, owned=False, dnd_on=True)
    assert res == ReconcileResult(owned=True, action=None)


def test_falling_edge_releases_only_what_we_own():
    res = reconcile(desired=False, last_desired=True, owned=True, dnd_on=True)
    assert res == ReconcileResult(owned=False, action="off")


def test_falling_edge_does_not_turn_off_manual_dnd():
    res = reconcile(desired=False, last_desired=True, owned=False, dnd_on=True)
    assert res == ReconcileResult(owned=False, action=None)


def test_manual_off_mid_window_is_respected():
    res = reconcile(desired=True, last_desired=True, owned=True, dnd_on=False)
    assert res == ReconcileResult(owned=True, action=None)


def test_no_edge_never_acts():
    res = reconcile(desired=False, last_desired=False, owned=False, dnd_on=True)
    assert res == ReconcileResult(owned=False, action=None)


def test_falling_edge_owned_but_already_off():
    res = reconcile(desired=False, last_desired=True, owned=True, dnd_on=False)
    assert res == ReconcileResult(owned=False, action=None)
