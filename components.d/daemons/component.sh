#!/usr/bin/env bash

COMPONENT_NAME="daemons"
COMPONENT_DESC="User-level daemon for the Solar runtime (off by default)"
COMPONENT_DEFAULT="off"
COMPONENT_PLATFORMS="darwin linux wsl"
COMPONENT_REQUIRES_BINS="bun"
COMPONENT_REQUIRES_COMPONENTS="core-runtime"

# Renders the real service file always; load/enable is best-effort and never
# fails the install (CI runners and headless boxes have no user session).
component_install() {
    dry_run_note "install solar-daemon service for $OS_KIND" && return 0
    mkdir -p "$SOLAR_HOME/logs"
    export SOLAR_DAEMON_HOME="$HOME"
    export SOLAR_DAEMON_BUN
    SOLAR_DAEMON_BUN="$(command -v bun 2>/dev/null || printf '%s/.bun/bin/bun' "$HOME")"

    case "$OS_KIND" in
        darwin)
            la="$HOME/Library/LaunchAgents"
            mkdir -p "$la"
            render_template "$SOURCE_DIR/templates/daemons/solar-daemon.plist.template" \
                "$la/com.solar.daemon.plist"
            printf 'launchd\tcom.solar.daemon\t%s\n' "$la/com.solar.daemon.plist" >> "$SOLAR_HOME/registered-daemons.txt"
            if launchctl load "$la/com.solar.daemon.plist" >/dev/null 2>&1; then
                info "loaded LaunchAgent com.solar.daemon"
            else
                yellow "rendered plist; load it with: launchctl load $la/com.solar.daemon.plist"
            fi
            ;;
        linux|wsl)
            if command -v systemctl >/dev/null 2>&1; then
                ud="$HOME/.config/systemd/user"
                mkdir -p "$ud"
                render_template "$SOURCE_DIR/templates/daemons/solar-daemon.service.template" \
                    "$ud/solar-daemon.service"
                printf 'systemd\tsolar-daemon.service\t%s\n' "$ud/solar-daemon.service" >> "$SOLAR_HOME/registered-daemons.txt"
                if systemctl --user enable --now solar-daemon.service >/dev/null 2>&1; then
                    info "enabled systemd --user service solar-daemon"
                    info "note: run 'loginctl enable-linger $USER' so it survives logout"
                else
                    yellow "rendered unit; enable with: systemctl --user enable --now solar-daemon.service"
                    yellow "and (for boot persistence): loginctl enable-linger $USER"
                fi
            else
                yellow "no systemd detected; skipping daemon service install (run bin/solar-daemon manually)"
            fi
            ;;
        *)
            yellow "daemons component unsupported on $OS_KIND; skipping"
            ;;
    esac
    return 0
}

component_verify() {
    case "$OS_KIND" in
        darwin)
            [ -f "$HOME/Library/LaunchAgents/com.solar.daemon.plist" ] \
                || die "daemons verify failed: plist not rendered"
            ;;
        linux|wsl)
            if command -v systemctl >/dev/null 2>&1; then
                [ -f "$HOME/.config/systemd/user/solar-daemon.service" ] \
                    || die "daemons verify failed: systemd unit not rendered"
            fi
            ;;
    esac
}
