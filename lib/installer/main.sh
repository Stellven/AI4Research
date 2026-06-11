#!/usr/bin/env bash

. "$SOLAR_SOURCE_DIR/lib/installer/common.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/paths.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/copy-engine.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/kernel-gen.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/render-template.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/config-vars.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/py-deps.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/settings-merge.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/mcp-register.sh"
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
  --set KEY=VALUE             Set a config var (repeatable; highest precedence)
  --no-hooks                  Skip settings.json hook registration
  --no-mcp                    Skip MCP server registration
  --list-components           Show component manifests
  --solar-home PATH           Runtime root (default: ~/.solar)
  --claude-dir PATH           Claude user dir (default: ~/.claude)
  --dry-run                   Print actions without writing
  --fake-keys                 Write test-only placeholder env files
  --skip-llm-cli              Skip LLM CLI checks for CI
  --skip-py-deps              Validate Python requirements only (deps-light CI)
  --help                      Show this help
EOF
}

parse_args() {
    YES="${SOLAR_YES:-false}"
    DRY_RUN="${SOLAR_DRY_RUN:-false}"
    FAKE_KEYS="${SOLAR_FAKE_KEYS:-false}"
    SKIP_LLM_CLI="${SOLAR_SKIP_LLM_CLI:-false}"
    SKIP_PY_DEPS="${SOLAR_SKIP_PY_DEPS:-false}"
    NO_HOOKS="${SOLAR_NO_HOOKS:-false}"
    NO_MCP="${SOLAR_NO_MCP:-false}"
    LIST_COMPONENTS=false
    REQUESTED_COMPONENTS="${SOLAR_COMPONENTS:-}"
    SOLAR_SET_VARS=""

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --yes|--non-interactive) YES=true; shift ;;
            --components) REQUESTED_COMPONENTS="$2"; shift 2 ;;
            --set)
                case "$2" in
                    *=*) SOLAR_SET_VARS="$SOLAR_SET_VARS$2
" ;;
                    *) die "--set expects KEY=VALUE, got: $2" ;;
                esac
                shift 2 ;;
            --list-components) LIST_COMPONENTS=true; shift ;;
            --solar-home) SOLAR_HOME="$2"; shift 2 ;;
            --claude-dir) CLAUDE_DIR="$2"; shift 2 ;;
            --dry-run) DRY_RUN=true; shift ;;
            --fake-keys) FAKE_KEYS=true; shift ;;
            --skip-llm-cli) SKIP_LLM_CLI=true; shift ;;
            --skip-py-deps) SKIP_PY_DEPS=true; shift ;;
            --no-hooks) NO_HOOKS=true; shift ;;
            --no-mcp) NO_MCP=true; shift ;;
            --no-modify-path|--quiet|--verbose) shift ;;
            --help|-h) usage; exit 0 ;;
            *) die "unknown option: $1" ;;
        esac
    done
    export YES DRY_RUN FAKE_KEYS SKIP_LLM_CLI SKIP_PY_DEPS NO_HOOKS NO_MCP REQUESTED_COMPONENTS SOLAR_SET_VARS
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
    resolve_config_vars
    confirm_if_needed
    ensure_base_dirs
    install_solar_bin
    config_init
    install_components
    db_init
    settings_merge
    mcp_register
    write_receipt
    if [ "$DRY_RUN" = "true" ]; then
        green "OpenSolar dry-run complete: $SELECTED_COMPONENTS"
        return 0
    fi
    doctor_json
    green "OpenSolar install complete: $SELECTED_COMPONENTS"
}
