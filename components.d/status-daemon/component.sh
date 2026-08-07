#!/usr/bin/env bash

COMPONENT_NAME="status-daemon"
COMPONENT_DESC="Auto-start the Solar status-server (dashboard + API) at login (off by default)"
COMPONENT_DEFAULT="off"
COMPONENT_PLATFORMS="darwin linux wsl"
COMPONENT_REQUIRES_BINS="python3"
COMPONENT_REQUIRES_COMPONENTS="harness"

# Installs the status-server (the dashboard + API the desktop app attaches to) as a per-user
# login service. Renders the unit always; load/enable is best-effort and never fails the install
# (CI runners and headless boxes have no user session). The desktop app also detect-or-starts the
# runtime on launch, so this is the "running before the app opens / survives" path.
component_install() {
    dry_run_note "install solar-status-server service for $OS_KIND" && return 0
    mkdir -p "$SOLAR_HOME/logs"

    # systemd/launchd have no PATH, so the unit needs an absolute interpreter. Resolve the python3
    # the installer sees (not a hardcoded /usr/bin/python3 — wrong on some WSL distros / mac brew).
    export SOLAR_STATUS_PYTHON
    SOLAR_STATUS_PYTHON="${SOLAR_PYTHON:-$(command -v python3 2>/dev/null || true)}"
    [ -n "$SOLAR_STATUS_PYTHON" ] || { yellow "python3 not found; skipping status-daemon install"; return 0; }
    if ! "$SOLAR_STATUS_PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 8) else 1)' 2>/dev/null; then
        yellow "python3 ($SOLAR_STATUS_PYTHON) is < 3.8; skipping status-daemon install"
        return 0
    fi

    case "$OS_KIND" in
        darwin)
            la="$HOME/Library/LaunchAgents"
            mkdir -p "$la"
            # Set HOME in the plist so the LaunchAgent's Python resolves ~ (SOLAR_DB, secrets, state)
            # correctly even if launchd doesn't propagate HOME. SOLAR_USER_HOME (a SOLAR_* var) is
            # substituted into the template by render_template.
            export SOLAR_USER_HOME="$HOME"
            render_template "$SOURCE_DIR/templates/status-daemon/com.solar.status-server.plist.template" \
                "$la/com.solar.status-server.plist"
            printf 'launchd\tcom.solar.status-server\t%s\n' "$la/com.solar.status-server.plist" >> "$SOLAR_HOME/registered-daemons.txt"
            if launchctl load "$la/com.solar.status-server.plist" >/dev/null 2>&1; then
                info "loaded LaunchAgent com.solar.status-server"
            else
                yellow "rendered plist; load it with: launchctl load $la/com.solar.status-server.plist"
            fi
            ;;
        linux|wsl)
            if command -v systemctl >/dev/null 2>&1; then
                ud="$HOME/.config/systemd/user"
                mkdir -p "$ud"
                render_template "$SOURCE_DIR/templates/status-daemon/solar-status-server.service.template" \
                    "$ud/solar-status-server.service"
                printf 'systemd\tsolar-status-server.service\t%s\n' "$ud/solar-status-server.service" >> "$SOLAR_HOME/registered-daemons.txt"
                # enable-linger so the service runs without an active login (required under WSL,
                # where there's no graphical session to hold the user manager open).
                loginctl enable-linger "$USER" >/dev/null 2>&1 || true
                if systemctl --user enable --now solar-status-server.service >/dev/null 2>&1; then
                    info "enabled systemd --user service solar-status-server (+ enable-linger)"
                else
                    yellow "rendered unit; enable with: systemctl --user enable --now solar-status-server.service"
                fi
            else
                yellow "no systemd detected; skipping status-daemon install (the desktop app still starts the runtime on launch)"
            fi
            ;;
        *)
            yellow "status-daemon component unsupported on $OS_KIND; skipping"
            ;;
    esac
    return 0
}

component_verify() {
    case "$OS_KIND" in
        darwin)
            [ -f "$HOME/Library/LaunchAgents/com.solar.status-server.plist" ] \
                || die "status-daemon verify failed: plist not rendered"
            ;;
        linux|wsl)
            if command -v systemctl >/dev/null 2>&1; then
                [ -f "$HOME/.config/systemd/user/solar-status-server.service" ] \
                    || die "status-daemon verify failed: systemd unit not rendered"
            fi
            ;;
    esac
}
