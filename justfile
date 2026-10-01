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

# Install smart-dnd to ~/.local/bin and install user desktop, icon, and service files
install:
    pip install --break-system-packages -e . || uv tool install --editable .
    mkdir -p ~/.local/share/applications ~/.local/share/metainfo ~/.config/systemd/user
    cp data/com.keithvassallo.SmartDnd.desktop ~/.local/share/applications/
    cp data/com.keithvassallo.SmartDnd.metainfo.xml ~/.local/share/metainfo/
    cp data/smart-dnd.service ~/.config/systemd/user/
    # Install icons
    mkdir -p ~/.local/share/icons/hicolor
    cp -r data/icons/hicolor/* ~/.local/share/icons/hicolor/
    gtk-update-icon-cache -q -t ~/.local/share/icons/hicolor 2>/dev/null || true
    systemctl --user daemon-reload
    @echo "Installed Smart DND! Enable with: systemctl --user enable --now smart-dnd"

# Uninstall user desktop and service files
uninstall:
    systemctl --user disable --now smart-dnd || true
    rm -f ~/.local/share/applications/com.keithvassallo.SmartDnd.desktop
    rm -f ~/.local/share/metainfo/com.keithvassallo.SmartDnd.metainfo.xml
    rm -f ~/.local/share/icons/hicolor/*/apps/com.keithvassallo.SmartDnd.*
    rm -f ~/.local/share/icons/hicolor/*/apps/smart-dnd.*
    rm -f ~/.local/share/icons/hicolor/*/actions/smart-dnd-symbolic.*
    rm -f ~/.local/share/icons/hicolor/*/actions/com.keithvassallo.SmartDnd-symbolic.*
    gtk-update-icon-cache -q -t ~/.local/share/icons/hicolor 2>/dev/null || true
    rm -f ~/.config/systemd/user/smart-dnd.service
    systemctl --user daemon-reload

# Build Flatpak bundle locally
build-flatpak:
    flatpak-builder --user --install --force-clean build-flatpak packaging/flatpak/com.keithvassallo.SmartDnd.yaml

# Test AUR PKGBUILD locally (Arch Linux)
build-aur:
    cd packaging/aur && makepkg -sfc
