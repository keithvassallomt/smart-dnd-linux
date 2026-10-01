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
