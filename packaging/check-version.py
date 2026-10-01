#!/usr/bin/env python3
"""Check that the hand-maintained version strings agree, and print the version.

Usage: packaging/check-version.py [EXPECTED]

EXPECTED (e.g. a git tag like v0.2.0) must match too when given. The deb, rpm and
AUR versions are set from this one at release time, so they are not checked.
FriendlyHub reads the version from the newest metainfo <release>, so it must be
first in the list.
"""

import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    init = (ROOT / "smart_dnd" / "__init__.py").read_text()
    metainfo = ET.parse(ROOT / "data" / "com.keithvassallo.SmartDnd.metainfo.xml")
    newest_release = metainfo.find("releases/release")

    found = {
        "pyproject.toml": tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
        "smart_dnd/__init__.py": re.search(r'__version__ = "([^"]+)"', init).group(1),
        "metainfo newest <release>": newest_release.get("version") if newest_release is not None else None,
    }
    if len(sys.argv) > 1:
        found["expected"] = sys.argv[1].removeprefix("v")

    if len(set(found.values())) != 1:
        print("Version strings disagree:", file=sys.stderr)
        for where, version in found.items():
            print(f"  {where}: {version}", file=sys.stderr)
        sys.exit(1)
    print(found["pyproject.toml"])


if __name__ == "__main__":
    main()
