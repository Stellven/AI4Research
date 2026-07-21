#!/usr/bin/env bash

init_paths() {
    SOURCE_DIR="${SOLAR_SOURCE_DIR:-$(cd "$(dirname "$0")" && pwd)}"
    SOLAR_HOME="${SOLAR_HOME:-$HOME/.solar}"
    CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
    RECEIPT_PATH="$SOLAR_HOME/install-receipt.json"
    SOLAR_DB="$SOLAR_HOME/db/solar.db"
    export SOURCE_DIR SOLAR_HOME CLAUDE_DIR RECEIPT_PATH SOLAR_DB
}

ensure_base_dirs() {
    dry_run_note "create $SOLAR_HOME, $SOLAR_HOME/bin, $CLAUDE_DIR" && return 0
    mkdir -p "$SOLAR_HOME/bin" "$SOLAR_HOME/db" "$CLAUDE_DIR"
}

install_solar_bin() {
    [ -f "$SOURCE_DIR/bin/solar" ] || return 0
    dry_run_note "install lifecycle commands to $SOLAR_HOME/bin" && return 0
    mkdir -p "$SOLAR_HOME/bin"
    cp "$SOURCE_DIR/bin/solar" "$SOLAR_HOME/bin/solar"
    chmod +x "$SOLAR_HOME/bin/solar"
    if [ -f "$SOURCE_DIR/bin/solar-daemon" ]; then
        cp "$SOURCE_DIR/bin/solar-daemon" "$SOLAR_HOME/bin/solar-daemon"
        chmod +x "$SOLAR_HOME/bin/solar-daemon"
    fi
}
