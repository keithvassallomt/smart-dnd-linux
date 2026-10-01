Name:           smart-dnd
Version:        0.1.0
Release:        1%{?dist}
Summary:        Automated Do Not Disturb based on schedules and calendar events

License:        GPL-3.0-or-later
URL:            https://github.com/keithvassallomt/smart-dnd-linux
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-pip
BuildRequires:  python3-hatchling

Requires:       python3
Requires:       python3-gobject
Requires:       libadwaita
Requires:       evolution-data-server

%description
Smart DND automatically enables Do Not Disturb (DND) mode on Linux desktops
based on a schedule or during matching calendar events. Features an Adwaita
GUI, system tray integration, and pluggable backends.

%prep
%autosetup

%build
%pyproject_wheel

%install
%pyproject_install
# -l: LICENSE ships in the wheel's dist-info and is marked %%license
%pyproject_save_files -l smart_dnd

install -Dm644 data/com.keithvassallo.SmartDnd.desktop %{buildroot}%{_datadir}/applications/com.keithvassallo.SmartDnd.desktop
install -Dm644 data/com.keithvassallo.SmartDnd.metainfo.xml %{buildroot}%{_metainfodir}/com.keithvassallo.SmartDnd.metainfo.xml
# Start at login for every user; each user can switch it off in the GUI.
install -Dm644 data/smart-dnd-autostart.desktop %{buildroot}%{_sysconfdir}/xdg/autostart/com.keithvassallo.SmartDnd.desktop

install -Dm644 data/icons/hicolor/scalable/apps/com.keithvassallo.SmartDnd.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/com.keithvassallo.SmartDnd.svg
install -Dm644 data/icons/hicolor/symbolic/apps/com.keithvassallo.SmartDnd-symbolic.svg %{buildroot}%{_datadir}/icons/hicolor/symbolic/apps/com.keithvassallo.SmartDnd-symbolic.svg

for s in 16 32 48 64 128 256 512; do
    install -Dm644 data/icons/hicolor/${s}x${s}/apps/com.keithvassallo.SmartDnd.png %{buildroot}%{_datadir}/icons/hicolor/${s}x${s}/apps/com.keithvassallo.SmartDnd.png
done

%files -f %{pyproject_files}
%doc README.md
%{_bindir}/smart-dnd
%{_bindir}/smart-dnd-gui
%{_bindir}/smart-dnd-daemon
%{_datadir}/applications/com.keithvassallo.SmartDnd.desktop
%{_metainfodir}/com.keithvassallo.SmartDnd.metainfo.xml
%config(noreplace) %{_sysconfdir}/xdg/autostart/com.keithvassallo.SmartDnd.desktop
%{_datadir}/icons/hicolor/*/apps/com.keithvassallo.SmartDnd*

%changelog
* Thu Oct 01 2026 Keith Vassallo <keith@vassallo.cloud> - 0.1.0-1
- Initial release of Smart DND for Linux.
