"""Tests for how --config flows from the CLI to the GUI and the daemon it starts."""

from pathlib import Path

import pytest

from smart_dnd import cli, config, host
from smart_dnd.models import Config


@pytest.fixture
def popen_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    calls = []
    monkeypatch.setattr(host.subprocess, "Popen", lambda argv, **kwargs: calls.append(argv))
    return calls


def test_started_daemon_gets_the_config_path(popen_calls, monkeypatch):
    monkeypatch.setattr(host, "IN_FLATPAK", False)
    host.start_daemon_detached(Path("/srv/dnd.json"))
    assert popen_calls[0][-4:] == ["smart_dnd.cli", "--config", "/srv/dnd.json", "daemon"]


def test_flatpak_daemon_instance_gets_the_config_path(popen_calls, monkeypatch):
    monkeypatch.setattr(host, "IN_FLATPAK", True)
    host.start_daemon_detached(Path("/srv/dnd.json"))
    assert popen_calls[0] == ["flatpak-spawn", "smart-dnd", "--config", "/srv/dnd.json", "daemon"]


def test_without_config_the_daemon_uses_its_default(popen_calls, monkeypatch):
    monkeypatch.setattr(host, "IN_FLATPAK", False)
    host.start_daemon_detached()
    assert "--config" not in popen_calls[0]


def test_config_flag_applies_to_every_save_in_the_process(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_config_path_override", None)
    target = tmp_path / "custom.json"
    config.set_default_config_path(target)
    config.save_config(Config(notification_backend="dunst"))
    assert config.load_config().notification_backend == "dunst"
    assert target.exists()


class FakeClient:
    def __init__(self, running, daemon_config=None):
        self.running = running
        self.daemon_config = daemon_config

    def is_daemon_running(self):
        return self.running

    def get_config(self):
        return self.daemon_config


def test_gui_edits_the_running_daemons_config(tmp_path):
    daemon_config = Config(notification_backend="swaync")
    cfg = cli._gui_config(FakeClient(True, daemon_config), str(tmp_path / "unused.json"))
    assert cfg is daemon_config


def test_gui_falls_back_to_the_file_when_the_daemon_is_down(tmp_path):
    path = tmp_path / "offline.json"
    config.save_config(Config(notification_backend="dunst"), custom_path=path)
    assert cli._gui_config(FakeClient(False), str(path)).notification_backend == "dunst"
