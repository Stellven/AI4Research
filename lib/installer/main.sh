#!/usr/bin/env bash

. "$SOLAR_SOURCE_DIR/lib/installer/common.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/paths.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/copy-engine.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/db-init.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/receipt.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/doctor.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/components.sh"

usage() {
    cat <<'EOF'
OpenSolar installer

Usage: ./install.sh [options]

Options:
  --yes, --non-interactive    Accept resolved defaults
  --components LIST           Comma-separated component list
  --list-components           Show component manifests
  --solar-home PATH           Runtime root (default: ~/.solar)
  --claude-dir PATH           Claude user dir (default: ~/.claude)
  --dry-run                   Print actions without writing
  --fake-keys                 Write test-only placeholder env files
  --skip-llm-cli              Skip LLM CLI checks for CI
  --help                      Show this help
EOF
}

parse_args() {
    YES="${SOLAR_YES:-false}"
    DRY_RUN="${SOLAR_DRY_RUN:-false}"
    FAKE_KEYS="${SOLAR_FAKE_KEYS:-false}"
    SKIP_LLM_CLI="${SOLAR_SKIP_LLM_CLI:-false}"
    LIST_COMPONENTS=false
    REQUESTED_COMPONENTS="${SOLAR_COMPONENTS:-}"

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --yes|--non-interactive) YES=true; shift ;;
            --components) REQUESTED_COMPONENTS="$2"; shift 2 ;;
            --list-components) LIST_COMPONENTS=true; shift ;;
            --solar-home) SOLAR_HOME="$2"; shift 2 ;;
            --claude-dir) CLAUDE_DIR="$2"; shift 2 ;;
            --dry-run) DRY_RUN=true; shift ;;
            --fake-keys) FAKE_KEYS=true; shift ;;
            --skip-llm-cli) SKIP_LLM_CLI=true; shift ;;
            --no-hooks|--no-mcp|--no-modify-path|--quiet|--verbose) shift ;;
            --help|-h) usage; exit 0 ;;
            *) die "unknown option: $1" ;;
        esac
    done
    export YES DRY_RUN FAKE_KEYS SKIP_LLM_CLI REQUESTED_COMPONENTS
}

confirm_if_needed() {
    [ "$YES" = "true" ] && return 0
    if [ -t 0 ]; then
        echo "Components: $SELECTED_COMPONENTS"
        echo "Solar home: $SOLAR_HOME"
        echo "Claude dir: $CLAUDE_DIR"
        printf 'Proceed? [y/N] '
        read ans
        case "$ans" in
            y|Y|yes|YES) return 0 ;;
        esac
        die "cancelled"
    fi
    die "non-interactive input detected; rerun with --yes"
}

main() {
    parse_args "$@"
    init_paths
    detect_os
    require_bin python3 "Install Python 3."

    if [ "$LIST_COMPONENTS" = "true" ]; then
        list_components
        exit 0
    fi

    resolve_components
    confirm_if_needed
    ensure_base_dirs
    install_solar_bin
    install_components
    db_init
    write_receipt
    if [ "$DRY_RUN" = "true" ]; then
        green "OpenSolar dry-run complete: $SELECTED_COMPONENTS"
        return 0
    fi
    doctor_json
    green "OpenSolar install complete: $SELECTED_COMPONENTS"
}
