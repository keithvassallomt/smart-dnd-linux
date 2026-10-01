"""Tests for start-at-login via XDG autostart entries."""

import pytest

from smart_dnd import autostart


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """Point the user and system autostart directories at temp dirs, outside a Flatpak."""
    monkeypatch.setattr(autostart, "IN_FLATPAK", False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home-config"))
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(tmp_path / "etc-xdg"))
    user = tmp_path / "home-config" / "autostart" / autostart.ENTRY_NAME
    system = tmp_path / "etc-xdg" / "autostart" / autostart.ENTRY_NAME
    return user, system


def install_system_entry(system):
    system.parent.mkdir(parents=True)
    system.write_text("[Desktop Entry]\nType=Application\nName=Smart DND\nExec=smart-dnd daemon\n")


def test_off_without_any_entry(dirs):
    assert autostart.is_enabled() is False


def test_package_entry_turns_it_on_for_everyone(dirs):
    _, system = dirs
    install_system_entry(system)
    assert autostart.is_enabled() is True


def test_user_can_switch_off_the_package_entry_and_back(dirs):
    user, system = dirs
    install_system_entry(system)

    autostart.set_enabled(False)
    assert "Hidden=true" in user.read_text()
    assert autostart.is_enabled() is False
    assert system.exists()  # never touches the package's file

    autostart.set_enabled(True)
    assert not user.exists()
    assert autostart.is_enabled() is True


def test_without_package_entry_a_user_entry_is_written(dirs, monkeypatch):
    user, _ = dirs
    monkeypatch.setattr(autostart.shutil, "which", lambda name: "/opt/my env/bin/smart-dnd")

    autostart.set_enabled(True)
    assert 'Exec="/opt/my env/bin/smart-dnd" daemon' in user.read_text()
    assert autostart.is_enabled() is True

    autostart.set_enabled(False)
    assert not user.exists()
    assert autostart.is_enabled() is False


def test_gnome_disabled_key_counts_as_off(dirs):
    user, system = dirs
    install_system_entry(system)
    user.parent.mkdir(parents=True)
    user.write_text("[Desktop Entry]\nType=Application\nX-GNOME-Autostart-enabled=false\n")
    assert autostart.is_enabled() is False


def test_override_replaces_a_symlink_instead_of_writing_through_it(dirs, tmp_path):
    user, system = dirs
    install_system_entry(system)
    dotfile = tmp_path / "dotfiles" / autostart.ENTRY_NAME
    dotfile.parent.mkdir()
    dotfile.write_text("[Desktop Entry]\nType=Application\nExec=smart-dnd daemon\n")
    user.parent.mkdir(parents=True)
    user.symlink_to(dotfile)

    autostart.set_enabled(False)
    assert not user.is_symlink()
    assert "Hidden" not in dotfile.read_text()


def test_flatpak_without_portal_writes_the_entry_itself(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "IN_FLATPAK", True)
    monkeypatch.setenv("HOST_XDG_CONFIG_HOME", str(tmp_path / "host-config"))
    monkeypatch.setattr(autostart, "_request_background", lambda enabled: False)
    user = tmp_path / "host-config" / "autostart" / autostart.ENTRY_NAME

    autostart.set_enabled(True)
    assert f"Exec={autostart.FLATPAK_DAEMON_COMMAND}" in user.read_text()
    assert autostart.is_enabled() is True

    autostart.set_enabled(False)
    assert not user.exists()


def test_flatpak_with_portal_leaves_the_entry_to_the_portal(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "IN_FLATPAK", True)
    monkeypatch.setenv("HOST_XDG_CONFIG_HOME", str(tmp_path / "host-config"))
    requests = []
    monkeypatch.setattr(autostart, "_request_background", lambda enabled: requests.append(enabled) or True)

    autostart.set_enabled(True)
    assert requests == [True]
    assert not (tmp_path / "host-config" / "autostart").exists()


def test_flatpak_default_applies_once(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    calls = []
    monkeypatch.setattr(autostart, "set_enabled", calls.append)
    autostart.enable_by_default_once()
    autostart.enable_by_default_once()
    assert calls == [True]
