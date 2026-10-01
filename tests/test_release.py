"""Tests for packaging/release.py: version bumps and changelog promotion."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("release", ROOT / "packaging" / "release.py")
release = importlib.util.module_from_spec(_spec)
sys.modules["release"] = release
_spec.loader.exec_module(release)

HEADER = "# Changelog\n\nIntro.\n\n"
METAINFO = """<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>com.keithvassallo.SmartDnd</id>
  <releases>
    <release version="0.1.0" date="2026-10-01">
      <description>
        <p>Initial release.</p>
      </description>
    </release>
  </releases>
</component>
"""


def make_repo(tmp_path, version, changelog_body):
    (tmp_path / "smart_dnd").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "x"\nversion = "{version}"\n')
    (tmp_path / "smart_dnd" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    (tmp_path / release.METAINFO).write_text(METAINFO)
    (tmp_path / "CHANGELOG.md").write_text(HEADER + changelog_body)
    return tmp_path


def read(repo, rel):
    return (repo / rel).read_text()


def test_first_release_keeps_the_version_and_fills_the_metainfo(tmp_path):
    repo = make_repo(tmp_path, "0.1.0", "## [Unreleased]\n\n## [0.1.0] - 2026-09-30\n\n### Added\n\n- **Tray**: a `tray` icon\n")
    version, why = release.prepare(repo, None, last=None, today="2026-10-01")
    assert (version, why) == ("0.1.0", "first release")
    assert "## [0.1.0] - 2026-10-01" in read(repo, "CHANGELOG.md")
    meta = read(repo, release.METAINFO)
    assert "<li>Tray: a <code>tray</code> icon</li>" in meta
    assert meta.count("<release ") == 1


def test_fixes_only_bump_patch(tmp_path):
    repo = make_repo(tmp_path, "0.1.0", "## [Unreleased]\n\n### Fixed\n\n- A crash\n\n## [0.1.0] - 2026-10-01\n\n### Added\n\n- Things\n")
    version, why = release.prepare(repo, None, last=(0, 1, 0), today="2026-11-02")
    assert version == "0.1.1"
    assert "patch" in why
    cl = read(repo, "CHANGELOG.md")
    assert "## [Unreleased]\n\n## [0.1.1] - 2026-11-02\n\n### Fixed\n\n- A crash" in cl
    assert "[Unreleased]: https://github.com/keithvassallomt/smart-dnd-linux/compare/v0.1.1...HEAD" in cl
    assert "[0.1.1]: https://github.com/keithvassallomt/smart-dnd-linux/compare/v0.1.0...v0.1.1" in cl
    assert '__version__ = "0.1.1"' in read(repo, "smart_dnd/__init__.py")
    assert 'version = "0.1.1"' in read(repo, "pyproject.toml")
    meta = read(repo, release.METAINFO)
    assert meta.index('version="0.1.1"') < meta.index('version="0.1.0"')  # newest first


def test_new_features_bump_minor(tmp_path):
    repo = make_repo(tmp_path, "0.1.0", "## [Unreleased]\n\n### Added\n\n- A thing\n\n### Fixed\n\n- A bug\n\n## [0.1.0] - 2026-10-01\n\n### Added\n\n- Things\n")
    assert release.prepare(repo, None, last=(0, 1, 0), today="2026-11-02")[0] == "0.2.0"


def test_removals_after_1_0_bump_major(tmp_path):
    repo = make_repo(tmp_path, "1.2.0", "## [Unreleased]\n\n### Removed\n\n- Old option\n\n## [1.2.0] - 2026-10-01\n\n### Added\n\n- Things\n")
    assert release.prepare(repo, None, last=(1, 2, 0), today="2026-11-02")[0] == "2.0.0"


def test_already_bumped_version_collects_later_entries(tmp_path):
    repo = make_repo(tmp_path, "0.2.0", (
        "## [Unreleased]\n\n### Fixed\n\n- Late fix\n\n"
        "## [0.2.0] - 2026-10-20\n\n### Added\n\n- Feature\n\n"
        "## [0.1.0] - 2026-10-01\n\n### Added\n\n- Things\n"))
    version, why = release.prepare(repo, None, last=(0, 1, 0), today="2026-11-02")
    assert version == "0.2.0" and "already bumped" in why
    cl = read(repo, "CHANGELOG.md")
    assert "## [0.2.0] - 2026-11-02\n\n### Added\n\n- Feature\n\n### Fixed\n\n- Late fix" in cl
    assert cl.count("- Late fix") == 1


def test_explicit_major_absorbs_an_untagged_section(tmp_path):
    repo = make_repo(tmp_path, "0.2.0", (
        "## [Unreleased]\n\n### Removed\n\n- Old CLI flag\n\n"
        "## [0.2.0] - 2026-10-20\n\n### Added\n\n- Feature\n\n"
        "## [0.1.0] - 2026-10-01\n\n### Added\n\n- Things\n"))
    assert release.prepare(repo, "major", last=(0, 1, 0), today="2026-11-02")[0] == "1.0.0"
    cl = read(repo, "CHANGELOG.md")
    assert "## [0.2.0]" not in cl
    assert "## [1.0.0] - 2026-11-02\n\n### Added\n\n- Feature\n\n### Removed\n\n- Old CLI flag" in cl


def test_nothing_to_release_is_an_error(tmp_path):
    repo = make_repo(tmp_path, "0.1.0", "## [Unreleased]\n\n## [0.1.0] - 2026-10-01\n\n### Added\n\n- Things\n")
    with pytest.raises(release.ReleaseError, match="Nothing to release"):
        release.prepare(repo, None, last=(0, 1, 0), today="2026-11-02")


def test_cannot_release_an_older_version(tmp_path):
    repo = make_repo(tmp_path, "0.1.0", "## [Unreleased]\n\n### Fixed\n\n- X\n\n## [0.1.0] - 2026-10-01\n\n### Added\n\n- Things\n")
    with pytest.raises(release.ReleaseError, match="not newer"):
        release.prepare(repo, "0.1.0", last=(0, 1, 0), today="2026-11-02")


def test_real_changelog_round_trips_unchanged():
    text = (ROOT / "CHANGELOG.md").read_text()
    assert release.render_changelog(release.parse_changelog(text)) == text


def test_notes_are_the_section_without_heading_or_links(tmp_path):
    repo = make_repo(tmp_path, "0.1.0", "## [Unreleased]\n\n## [0.1.0] - 2026-10-01\n\n### Added\n\n- Things\n")
    assert release.notes(repo, "0.1.0") == "### Added\n\n- Things\n"


def test_keep_metainfo_notes_keeps_the_description_but_syncs_the_date(tmp_path):
    repo = make_repo(tmp_path, "0.1.0", "## [Unreleased]\n\n## [0.1.0] - 2026-10-01\n\n### Added\n\n- Long technical list\n")
    before = read(repo, release.METAINFO)
    release.prepare(repo, None, last=None, today="2026-10-03", keep_metainfo_notes=True)
    meta = read(repo, release.METAINFO)
    assert "<p>Initial release.</p>" in meta
    assert "Long technical list" not in meta
    assert meta == before.replace('date="2026-10-01"', 'date="2026-10-03"')
    assert "## [0.1.0] - 2026-10-03" in read(repo, "CHANGELOG.md")


def test_keep_metainfo_notes_needs_an_entry_to_keep(tmp_path):
    repo = make_repo(tmp_path, "0.1.0", "## [Unreleased]\n\n### Fixed\n\n- A bug\n\n## [0.1.0] - 2026-10-01\n\n### Added\n\n- Things\n")
    changelog_before = read(repo, "CHANGELOG.md")
    with pytest.raises(release.ReleaseError, match="keep-metainfo-notes"):
        release.prepare(repo, None, last=(0, 1, 0), today="2026-11-02", keep_metainfo_notes=True)
    assert read(repo, "CHANGELOG.md") == changelog_before  # nothing half-written
