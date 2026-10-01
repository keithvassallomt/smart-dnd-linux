#!/usr/bin/env python3
"""Settle a release's version and changelog. Driven by `just bump-version` and `just release`.

Usage:
  packaging/release.py prepare [major|minor|patch|X.Y.Z] [--keep-metainfo-notes]
      Decide the release version, move every change since the last tag into its
      CHANGELOG.md section dated today, and update pyproject.toml,
      smart_dnd/__init__.py and the metainfo <release> to match. Prints the version.
      Without an argument it keeps an already-bumped version, or bumps from the last
      tag by what [Unreleased] contains (see infer_part).
      --keep-metainfo-notes keeps a hand-written <release> description (only its
      date is updated) instead of generating it from the changelog.
  packaging/release.py notes VERSION
      Print that version's CHANGELOG.md section as markdown (the GitHub release body).
"""

from __future__ import annotations

import datetime
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/keithvassallomt/smart-dnd-linux"
METAINFO = Path("data/com.keithvassallo.SmartDnd.metainfo.xml")
CATEGORY_ORDER = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]
PARTS = ("major", "minor", "patch")

Version = Tuple[int, int, int]


class ReleaseError(Exception):
    pass


def parse_version(text: str) -> Version:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    if not m:
        raise ReleaseError(f"Not a MAJOR.MINOR.PATCH version: {text!r}")
    return int(m[1]), int(m[2]), int(m[3])


def fmt(v: Version) -> str:
    return "%d.%d.%d" % v


def bump(v: Version, part: str) -> Version:
    if part == "major":
        return v[0] + 1, 0, 0
    if part == "minor":
        return v[0], v[1] + 1, 0
    return v[0], v[1], v[2] + 1


# -- CHANGELOG.md (Keep a Changelog) ------------------------------------------

@dataclass
class Section:
    name: str  # "Unreleased" or a version
    date: Optional[str] = None
    # category -> bullet items, each kept as its raw lines (continuations included)
    categories: Dict[str, List[List[str]]] = field(default_factory=dict)

    def has_entries(self) -> bool:
        return any(self.categories.values())

    def absorb(self, other: "Section") -> None:
        for cat, items in other.categories.items():
            self.categories.setdefault(cat, []).extend(items)
        other.categories = {}


@dataclass
class Changelog:
    header: List[str]
    sections: List[Section]

    def get(self, name: str) -> Optional[Section]:
        return next((s for s in self.sections if s.name == name), None)


SECTION_RE = re.compile(r"^## \[([^\]]+)\](?: - (\d{4}-\d{2}-\d{2}))?\s*$")
LINK_RE = re.compile(r"^\[[^\]]+\]: \S+")


def parse_changelog(text: str) -> Changelog:
    lines = text.splitlines()
    header: List[str] = []
    sections: List[Section] = []
    current: Optional[Section] = None
    category: Optional[str] = None
    for line in lines:
        m = SECTION_RE.match(line)
        if m:
            current = Section(m[1], m[2])
            sections.append(current)
            category = None
            continue
        if current is None:
            header.append(line)
            continue
        if LINK_RE.match(line):
            continue  # link references are regenerated
        if line.startswith("### "):
            category = line[4:].strip()
            current.categories.setdefault(category, [])
        elif re.match(r"^[-*] ", line):
            if category is None:
                raise ReleaseError(f"Changelog entry outside a ### category in [{current.name}]: {line}")
            current.categories[category].append([line])
        elif line.strip() and category and current.categories[category]:
            current.categories[category][-1].append(line)  # continuation of the last item
    while header and not header[-1].strip():
        header.pop()
    return Changelog(header, sections)


def render_changelog(cl: Changelog) -> str:
    out = list(cl.header) + [""]
    for s in cl.sections:
        out.append(f"## [{s.name}]" + (f" - {s.date}" if s.date else ""))
        out.append("")
        for cat in sorted(s.categories, key=lambda c: CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 99):
            items = s.categories[cat]
            if not items:
                continue
            out += [f"### {cat}", ""]
            for item in items:
                out += item
            out.append("")
    versions = [s.name for s in cl.sections if s.name != "Unreleased"]
    if versions:
        out.append(f"[Unreleased]: {REPO_URL}/compare/v{versions[0]}...HEAD")
    for i, v in enumerate(versions):
        if i + 1 < len(versions):
            out.append(f"[{v}]: {REPO_URL}/compare/v{versions[i + 1]}...v{v}")
        else:
            out.append(f"[{v}]: {REPO_URL}/releases/tag/v{v}")
    return "\n".join(out).rstrip("\n") + "\n"


def infer_part(section: Section, last: Version) -> str:
    """SemVer bump implied by the kinds of change (Keep a Changelog categories).

    Removals after 1.0 are breaking, so major; new or changed behaviour is minor; fixes
    and security are patch. Pre-1.0, breaking changes bump minor. Pass `major`
    explicitly for any other breaking change.
    """
    cats = {c for c, items in section.categories.items() if items}
    if last[0] >= 1 and "Removed" in cats:
        return "major"
    if cats & {"Added", "Changed", "Deprecated", "Removed"}:
        return "minor"
    return "patch"


# -- version strings and metainfo --------------------------------------------

def read_version(root: Path) -> Version:
    m = re.search(r'^version\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text(), re.M)
    return parse_version(m[1])


def write_versions(root: Path, version: str) -> None:
    for rel, pattern in (("pyproject.toml", r'^(version\s*=\s*")[^"]+(")'),
                         ("smart_dnd/__init__.py", r'^(__version__\s*=\s*")[^"]+(")')):
        path = root / rel
        text, n = re.subn(pattern, rf"\g<1>{version}\g<2>", path.read_text(), count=1, flags=re.M)
        if n != 1:
            raise ReleaseError(f"No version string found in {rel}")
        path.write_text(text)


def _inline_xml(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links: keep the text
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", text)


def release_xml(section: Section) -> str:
    lines = [f'    <release version="{section.name}" date="{section.date}">', "      <description>"]
    for cat in CATEGORY_ORDER + [c for c in section.categories if c not in CATEGORY_ORDER]:
        items = section.categories.get(cat)
        if not items:
            continue
        lines += [f"        <p>{cat}:</p>", "        <ul>"]
        for item in items:
            joined = " ".join(l.strip() for l in item)
            lines.append(f"          <li>{_inline_xml(re.sub(r'^[-*] ', '', joined))}</li>")
        lines.append("        </ul>")
    lines += ["      </description>", "    </release>"]
    return "\n".join(lines)


def update_metainfo_release_date(root: Path, section: Section) -> None:
    path = root / METAINFO
    text, n = re.subn(
        rf'(<release version="{re.escape(section.name)}" date=")[^"]*(")',
        rf"\g<1>{section.date}\g<2>",
        path.read_text(),
        count=1,
    )
    if n != 1:
        raise ReleaseError(
            f"--keep-metainfo-notes needs an existing <release version=\"{section.name}\" date=...> "
            f"in {METAINFO} to keep"
        )
    path.write_text(text)


def write_metainfo_release(root: Path, section: Section) -> None:
    path = root / METAINFO
    text = path.read_text()
    new = release_xml(section)
    existing = re.compile(
        rf'^[ \t]*<release version="{re.escape(section.name)}"[^>]*?(?:/>|>.*?</release>)', re.S | re.M
    )
    if existing.search(text):
        text = existing.sub(lambda _m: new, text, count=1)
    else:
        text, n = re.subn(r"(<releases>\n)", lambda m: m[1] + new + "\n", text, count=1)
        if n != 1:
            raise ReleaseError(f"No <releases> element in {METAINFO}")
    path.write_text(text)


# -- prepare -----------------------------------------------------------------

def prepare(
    root: Path,
    arg: Optional[str],
    last: Optional[Version],
    today: str,
    keep_metainfo_notes: bool = False,
) -> Tuple[str, str]:
    """Settle the release version and files. Returns (version, explanation)."""
    current = read_version(root)
    cl_path = root / "CHANGELOG.md"
    cl = parse_changelog(cl_path.read_text())
    unreleased = cl.get("Unreleased")
    if unreleased is None:
        unreleased = Section("Unreleased")
        cl.sections.insert(0, unreleased)

    if arg in PARTS:
        target = bump(last or current, arg)
        why = f"{arg} bump from {fmt(last or current)} (requested)"
    elif arg:
        target = parse_version(arg)
        why = "requested"
    elif last is None:
        target, why = current, "first release"
    elif current > last:
        target, why = current, f"already bumped from v{fmt(last)}"
    else:
        if not unreleased.has_entries():
            raise ReleaseError(f"Nothing to release: [Unreleased] in CHANGELOG.md is empty and v{fmt(last)} is already tagged")
        part = infer_part(unreleased, last)
        target = bump(last, part)
        kinds = ", ".join(c for c, items in unreleased.categories.items() if items)
        why = f"{part} bump from v{fmt(last)} ({kinds})"
    if last is not None and target <= last:
        raise ReleaseError(f"{fmt(target)} is not newer than the last release, v{fmt(last)}")

    name = fmt(target)
    section = cl.get(name)
    if section is None:
        section = Section(name)
        cl.sections.insert(cl.sections.index(unreleased) + 1, section)
    # Everything since the last tag ships in this release: [Unreleased] plus any
    # section for a version that was bumped to but never tagged.
    for other in list(cl.sections):
        if other is section or other is unreleased:
            continue
        v = parse_version(other.name)
        if last is None or v > last:
            section.absorb(other)
            cl.sections.remove(other)
    section.absorb(unreleased)
    if not section.has_entries():
        raise ReleaseError(f"CHANGELOG.md has no entries for {name}; add them under [Unreleased]")
    section.date = today

    if keep_metainfo_notes:
        update_metainfo_release_date(root, section)  # checked first: fails before writing anything
    cl_path.write_text(render_changelog(cl))
    write_versions(root, name)
    if not keep_metainfo_notes:
        write_metainfo_release(root, section)
    return name, why


def last_tag(root: Path) -> Optional[Version]:
    out = subprocess.run(["git", "tag", "--list", "v*"], cwd=root, capture_output=True, text=True, check=True).stdout
    versions = []
    for tag in out.split():
        try:
            versions.append(parse_version(tag))
        except ReleaseError:
            pass
    return max(versions) if versions else None


def notes(root: Path, version: str) -> str:
    section = parse_changelog((root / "CHANGELOG.md").read_text()).get(version)
    if section is None or not section.has_entries():
        raise ReleaseError(f"CHANGELOG.md has no section for {version}")
    body = render_changelog(Changelog([], [section]))
    # Drop the "## [x] - date" heading and the link reference the renderer appends.
    lines = [l for l in body.splitlines() if not SECTION_RE.match(l) and not LINK_RE.match(l)]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    args = sys.argv[1:]
    keep_notes = "--keep-metainfo-notes" in args
    args = [a for a in args if a != "--keep-metainfo-notes"]
    try:
        if args[:1] == ["prepare"] and len(args) <= 2:
            version, why = prepare(ROOT, args[1] if len(args) == 2 else None, last_tag(ROOT),
                                   datetime.date.today().isoformat(), keep_metainfo_notes=keep_notes)
            print(f"Release version {version}: {why}", file=sys.stderr)
            print(version)
        elif args[:1] == ["notes"] and len(args) == 2:
            sys.stdout.write(notes(ROOT, args[1]))
        else:
            sys.exit(__doc__.strip())
    except ReleaseError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
