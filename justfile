# Justfile for Smart DND (Linux)

default:
    @just --list

# Run test suite
test:
    . .venv/bin/activate && pytest -v

# Run the daemon in foreground with debug output
run-daemon:
    . .venv/bin/activate && smart-dnd daemon --debug

# Run the Libadwaita Preferences GUI
run-gui:
    . .venv/bin/activate && smart-dnd gui

# Query current daemon status
status:
    . .venv/bin/activate && smart-dnd status

# Dry-run test calendar rules against upcoming events
test-rules:
    . .venv/bin/activate && smart-dnd test

# List discovered plugins
plugins:
    . .venv/bin/activate && smart-dnd plugins

# Install smart-dnd editable, plus user desktop, icon and autostart files
install:
    pip install --break-system-packages -e . || uv tool install --editable .
    mkdir -p ~/.local/share/applications ~/.local/share/metainfo
    cp data/com.keithvassallo.SmartDnd.desktop ~/.local/share/applications/
    cp data/com.keithvassallo.SmartDnd.metainfo.xml ~/.local/share/metainfo/
    # Install icons
    mkdir -p ~/.local/share/icons/hicolor
    cp -r data/icons/hicolor/* ~/.local/share/icons/hicolor/
    gtk-update-icon-cache -q -t ~/.local/share/icons/hicolor 2>/dev/null || true
    # Start at login, pointing at the smart-dnd just installed
    smart-dnd autostart on
    @echo "Installed Smart DND. Open it from your launcher, or run: smart-dnd gui"

# Uninstall user desktop, icon and autostart files
uninstall:
    rm -f ~/.config/autostart/com.keithvassallo.SmartDnd.desktop
    rm -f ~/.local/share/applications/com.keithvassallo.SmartDnd.desktop
    rm -f ~/.local/share/metainfo/com.keithvassallo.SmartDnd.metainfo.xml
    rm -f ~/.local/share/icons/hicolor/*/apps/com.keithvassallo.SmartDnd.*
    rm -f ~/.local/share/icons/hicolor/*/apps/smart-dnd.*
    rm -f ~/.local/share/icons/hicolor/*/actions/smart-dnd-symbolic.*
    rm -f ~/.local/share/icons/hicolor/*/actions/com.keithvassallo.SmartDnd-symbolic.*
    gtk-update-icon-cache -q -t ~/.local/share/icons/hicolor 2>/dev/null || true

# Build and install the Flatpak locally (needs the GNOME SDK named in the manifest)
build-flatpak:
    flatpak-builder --user --install --force-clean build-flatpak packaging/flatpak/com.keithvassallo.SmartDnd.yaml

# Build the -git AUR package from main (Arch Linux)
build-aur:
    cd packaging/aur/smart-dnd-git && makepkg -sfc

# Check the version strings agree; pass the tag you're about to push to check it too
check-version tag="":
    python3 packaging/check-version.py {{tag}}

# Run the release workflow as a dry run on GitHub: builds every package, publishes nothing
release-dry-run ref="main":
    gh workflow run release.yml --ref {{ref}}

# Moves [Unreleased] into a dated CHANGELOG.md section and syncs the version strings.
# Without part, bumps from the last tag by what changed (see packaging/release.py).
# --keep-metainfo-notes keeps a hand-written metainfo <release> description.
# Settle the next version (part: major, minor, patch or X.Y.Z; default inferred)
[arg("keep_notes", long="keep-metainfo-notes", value="true")]
bump-version part="" keep_notes="false":
    python3 packaging/release.py prepare {{part}} {{ if keep_notes == "true" { "--keep-metainfo-notes" } else { "" } }}

# Settles the version and changelog, commits, tags and pushes. CI then builds the packages
# and publishes the GitHub release and the AUR package. See docs/releasing.md.
# Options: --keep-metainfo-notes, --friendlyhub-dir DIR (default ~/Downloads).
# Cut a release and save the FriendlyHub files
[arg("keep_notes", long="keep-metainfo-notes", value="true")]
[arg("friendlyhub_dir", long="friendlyhub-dir")]
release keep_notes="false" friendlyhub_dir="~/Downloads":
    #!/usr/bin/env bash
    set -euo pipefail
    export GH_REPO=keithvassallomt/smart-dnd-linux
    die() { echo "error: $*" >&2; exit 1; }
    dest="{{friendlyhub_dir}}"
    dest="${dest/#\~/$HOME}"

    # Preflight: nothing is changed until all of these pass.
    [ "$(git branch --show-current)" = main ] || die "release from main"
    [ -z "$(git status --porcelain)" ] || die "commit or stash your changes first"
    git fetch -q --tags origin
    git merge-base --is-ancestor origin/main HEAD || die "main is behind origin/main; pull first"
    GIT_TERMINAL_PROMPT=0 git push --dry-run -q origin HEAD:main 2>/dev/null \
        || die "can't push to origin; switch it to SSH: git remote set-url origin git@github.com-keith:$GH_REPO.git"
    gh secret list | grep -q '^AUR_SSH_PRIVATE_KEY' || die "AUR_SSH_PRIVATE_KEY secret is missing; see docs/releasing.md"
    .venv/bin/pytest -q

    # 1-2. Changelog and version: bumps unless the current version is still untagged.
    bump_flags=()
    [ "{{keep_notes}}" = true ] && bump_flags+=(--keep-metainfo-notes)
    version=$({{just_executable()}} bump-version "${bump_flags[@]}")
    git rev-parse -q --verify "refs/tags/v$version" >/dev/null && die "v$version is already tagged"
    python3 packaging/check-version.py "v$version" >/dev/null

    echo
    echo "=== Release notes for v$version ==="
    python3 packaging/release.py notes "$version"
    git --no-pager diff --stat
    read -r -p "Release v$version? [y/N] " answer
    if [ "$answer" != y ]; then
        git checkout -q -- .
        die "cancelled; files restored"
    fi

    # 3. Commit, tag and push; the tag starts the release workflow.
    git add -A
    git diff --cached --quiet || git commit -q -m "Release v$version"
    git tag -a "v$version" -m "Smart DND $version"
    git push -q --atomic origin main "v$version"

    echo "Pushed v$version. Waiting for the release workflow (the Flatpak build takes a while)..."
    run=""
    for _ in $(seq 1 30); do
        run=$(gh run list --workflow release.yml --branch "v$version" --event push --limit 1 --json databaseId --jq '.[0].databaseId // empty')
        [ -n "$run" ] && break
        sleep 5
    done
    [ -n "$run" ] || die "the release workflow didn't start; check: gh run list --workflow release.yml"
    echo "https://github.com/$GH_REPO/actions/runs/$run"
    gh run watch "$run" --exit-status --interval 30 > /dev/null \
        || die "the release workflow failed: gh run view $run --log-failed (see docs/releasing.md)"

    # 4. FriendlyHub submission files.
    mkdir -p "$dest"
    gh release download "v$version" --pattern 'com.keithvassallo.SmartDnd.*' --dir "$dest" --clobber
    echo
    echo "Released v$version: $(gh release view "v$version" --json url --jq .url)"
    echo "AUR: https://aur.archlinux.org/packages/smart-dnd"
    echo "FriendlyHub files: $dest/com.keithvassallo.SmartDnd.yaml and .metainfo.xml"
