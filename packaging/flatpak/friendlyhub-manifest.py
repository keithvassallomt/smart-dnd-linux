#!/usr/bin/env python3
"""Print the FriendlyHub version of the Flatpak manifest.

FriendlyHub builds from a git tag rather than a working tree, so the app module's
`type: dir` source is swapped for the release tag and its commit.

Usage: packaging/flatpak/friendlyhub-manifest.py TAG COMMIT > com.keithvassallo.SmartDnd.yaml
"""

import sys
from pathlib import Path

MANIFEST = Path(__file__).with_name("com.keithvassallo.SmartDnd.yaml")
REPO_URL = "https://github.com/keithvassallomt/smart-dnd-linux.git"

DIR_SOURCE = """      # Local and CI builds use the working tree. packaging/flatpak/friendlyhub-manifest.py
      # swaps this for the release's git tag when preparing the FriendlyHub submission.
      - type: dir
        path: ../..
        skip:
          - .git
          - .venv
          - .flatpak-builder
          - build-flatpak
"""

GIT_SOURCE = """      - type: git
        url: {url}
        tag: {tag}
        commit: {commit}
"""


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__.strip().splitlines()[-1])
    tag, commit = sys.argv[1], sys.argv[2]
    manifest = MANIFEST.read_text()
    if manifest.count(DIR_SOURCE) != 1:
        sys.exit(f"{MANIFEST.name}: the smart-dnd module's dir source changed; update DIR_SOURCE here to match")
    sys.stdout.write(manifest.replace(DIR_SOURCE, GIT_SOURCE.format(url=REPO_URL, tag=tag, commit=commit)))


if __name__ == "__main__":
    main()
