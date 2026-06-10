#!/usr/bin/env bash

COMPONENT_NAME="codex-bridge"
COMPONENT_DESC="Optional file-based handoff bridge for external coding agents"
COMPONENT_DEFAULT="off"
COMPONENT_REQUIRES_BINS=""

component_install() {
    copy_payload "$SOURCE_DIR/codex-bridge" "$SOLAR_HOME/codex-bridge"
    return 0
}

component_verify() {
    [ -f "$SOLAR_HOME/codex-bridge/CODEX-PROTOCOL.md" ] || die "codex-bridge verify failed: protocol missing"
}
