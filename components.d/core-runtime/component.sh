#!/usr/bin/env bash

COMPONENT_NAME="core-runtime"
COMPONENT_DESC="TypeScript core runtime, daemon, and web dashboard"
COMPONENT_DEFAULT="auto"
COMPONENT_REQUIRES_BINS="bun"
COMPONENT_REQUIRES_COMPONENTS="kernel"

component_install() {
    copy_payload "$SOURCE_DIR/core" "$SOLAR_HOME/core"
    dry_run_note "copy core package manifests" && return 0
    cp "$SOURCE_DIR/package.json" "$SOLAR_HOME/package.json"
    cp "$SOURCE_DIR/bun.lock" "$SOLAR_HOME/bun.lock"
    [ -f "$SOURCE_DIR/tsconfig.json" ] && cp "$SOURCE_DIR/tsconfig.json" "$SOLAR_HOME/tsconfig.json"
    # Keep bun's package cache inside SOLAR_HOME: the install must not
    # write to the user's ~/.bun, and uninstall removes it with ~/.solar.
    (cd "$SOLAR_HOME" && BUN_INSTALL_CACHE_DIR="$SOLAR_HOME/cache/bun" bun install --frozen-lockfile)
    return 0
}

component_verify() {
    [ -f "$SOLAR_HOME/core/daemon/server.ts" ] || die "core-runtime verify failed: daemon server missing"
    [ -f "$SOLAR_HOME/core/dashboard/server.ts" ] || die "core-runtime verify failed: dashboard server missing"
}
