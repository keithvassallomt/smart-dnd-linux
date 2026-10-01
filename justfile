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

# Install smart-dnd to ~/.local/bin and install user desktop + service files
install:
    pip install --break-system-packages -e . || uv tool install --editable .
    mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps ~/.config/systemd/user
    cp data/com.keithvassallo.SmartDnd.desktop ~/.local/share/applications/
    cp data/com.keithvassallo.SmartDnd.svg ~/.local/share/icons/hicolor/scalable/apps/
    cp data/smart-dnd.service ~/.config/systemd/user/
    systemctl --user daemon-reload
    @echo "Installed Smart DND! Enable with: systemctl --user enable --now smart-dnd"

# Uninstall user desktop and service files
uninstall:
    systemctl --user disable --now smart-dnd || true
    rm -f ~/.local/share/applications/com.keithvassallo.SmartDnd.desktop
    rm -f ~/.local/share/icons/hicolor/scalable/apps/com.keithvassallo.SmartDnd.svg
    rm -f ~/.config/systemd/user/smart-dnd.service
    systemctl --user daemon-reload
