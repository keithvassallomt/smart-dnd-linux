"""Guards for the release plumbing, so drift shows up in CI rather than on a tag push."""

import subprocess
import sys
from pathlib import Path

from smart_dnd import host

ROOT = Path(__file__).resolve().parents[1]


def run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)


def test_version_strings_agree():
    res = run_script("packaging/check-version.py")
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip()


def test_version_check_rejects_a_different_tag():
    assert run_script("packaging/check-version.py", "v999.0.0").returncode == 1


def test_friendlyhub_manifest_builds_from_the_tag():
    res = run_script("packaging/flatpak/friendlyhub-manifest.py", "v1.2.3", "abc1234")
    assert res.returncode == 0, res.stderr
    assert "type: dir" not in res.stdout
    assert "tag: v1.2.3" in res.stdout
    assert "commit: abc1234" in res.stdout


def test_host_argv_wraps_only_inside_flatpak(monkeypatch):
    monkeypatch.setattr(host, "IN_FLATPAK", False)
    assert host.host_argv(["dunstctl", "is-paused"]) == ["dunstctl", "is-paused"]
    monkeypatch.setattr(host, "IN_FLATPAK", True)
    assert host.host_argv(["dunstctl", "is-paused"]) == ["flatpak-spawn", "--host", "dunstctl", "is-paused"]
