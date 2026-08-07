#!/usr/bin/env bash

. "$SOLAR_SOURCE_DIR/lib/installer/common.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/paths.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/system-deps.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/copy-engine.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/kernel-gen.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/render-template.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/config-vars.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/py-deps.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/settings-merge.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/mcp-register.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/db-init.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/migrate.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/receipt.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/doctor.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/components.sh"
. "$SOLAR_SOURCE_DIR/lib/installer/wizard.sh"

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
  --bootstrap-system-deps     Prompt/attempt OS package install for Python, tmux, jq, bash>=4
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
    BOOTSTRAP_SYSTEM_DEPS="${SOLAR_BOOTSTRAP_SYSTEM_DEPS:-false}"
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
            --bootstrap-system-deps) BOOTSTRAP_SYSTEM_DEPS=true; shift ;;
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
    export YES DRY_RUN FAKE_KEYS SKIP_LLM_CLI SKIP_PY_DEPS BOOTSTRAP_SYSTEM_DEPS NO_HOOKS NO_MCP REQUESTED_COMPONENTS SOLAR_SET_VARS
}

confirm_if_needed() {
    [ "$YES" = "true" ] && return 0
    if solar_can_prompt; then
        print_final_summary
        wizard_read "Confirm install? [y/N] "
        ans="$WIZARD_ANSWER"
        case "$ans" in
            y|Y|yes|YES) return 0 ;;
        esac
        cancel_install
    fi
    die "non-interactive input detected; rerun with --yes"
}

# Human-facing "what now" after a successful install. Replaces the raw
# doctor JSON that used to be dumped here -- that JSON was never consumed by
# anything (all gates run `solar doctor --json` separately), and a wall of
# JSON is not an onboarding step. Printed to stderr to match green()/the
# wizard and keep stdout clean.
installed_pane_runtime() {
    "${SOLAR_PYTHON:-python3}" - "$SOLAR_HOME/harness/config/solar-user-config.json" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        runtime = str(json.load(handle).get("runtime") or "claude").strip().lower()
except (OSError, ValueError, TypeError):
    runtime = "claude"
print(runtime if runtime in {"claude", "codex"} else "claude")
PY
}

print_get_started() {
    bindir="$SOLAR_HOME/bin"
    pane_runtime="$(installed_pane_runtime)"
    {
        printf '\n'
        if [ -x "$bindir/solar" ]; then
            printf 'Environment check\n'
        fi
    } >&2
    if [ -x "$bindir/solar" ]; then
        SOLAR_HOME="$SOLAR_HOME" CLAUDE_DIR="$CLAUDE_DIR" "$bindir/solar" doctor >&2 || true
        printf '\n' >&2
    fi
    {
        printf 'Get started\n'
        printf '  1. Put solar on your PATH (or call it by full path %s/solar):\n' "$bindir"
        printf '       export PATH="%s:$PATH"\n' "$bindir"
        printf '  2. Check the install:\n'
        printf '       solar doctor\n'
    } >&2
    case " $SELECTED_COMPONENTS " in
        *" harness "*)
            if [ "$pane_runtime" = "codex" ]; then
                {
                    printf '  3. Authenticate the selected runtime (Codex):\n'
                    printf '       codex login --device-auth\n'
                } >&2
            else
                {
                    printf '  3. Authenticate the selected runtime (Claude Code):\n'
                    printf '       claude\n'
                    printf '       (complete login/trust and approve the one-time @~/.claude/solar/SOLAR.md import)\n'
                } >&2
            fi
            {
                printf '       To switch between Codex and Claude Code before launch, start the dashboard\n'
                printf '       with `solar harness status-server start` and use Settings > Runtime.\n'
                printf '  4. Start the Product Delivery cockpit in your project:\n'
                printf '       solar harness start "$(pwd)"\n'
                printf '  5. Submit work in the dashboard or from the CLI:\n'
                printf '       solar harness intake "Describe the result you want"\n'
                printf '       Solar plans, delegates, gates, and publishes the result.\n'
            } >&2
            ;;
    esac
    printf '\nMore in INSTALL.md. Re-check health anytime with `solar doctor`.\n' >&2
}

main() {
    parse_args "$@"
    init_paths
    detect_os
    bootstrap_python_if_needed
    detect_python

    if [ "$LIST_COMPONENTS" = "true" ]; then
        list_components
        exit 0
    fi

    resolve_components
    run_component_wizard_if_needed
    resolve_config_vars
    confirm_if_needed
    bootstrap_system_deps
    ensure_base_dirs
    install_solar_bin
    config_init
    # Initialize the database BEFORE installing components so it exists before
    # the daemons component starts the service. Otherwise the daemon's first
    # boot races db-init and fails (recovered only by the restart policy).
    # db_init reads schema from SOURCE_DIR, so it has no dependency on the
    # component copy step.
    db_init
    # Apply pending schema migrations on top of the freshly-applied baseline.
    # On update this catches an older database up; on a fresh install it just
    # stamps the baseline schema_version (no migrations exist yet).
    db_migrate
    install_components
    settings_merge
    mcp_register
    write_receipt
    if [ "$DRY_RUN" = "true" ]; then
        green "OpenSolar dry-run complete: $SELECTED_COMPONENTS"
        return 0
    fi
    green "OpenSolar install complete: $SELECTED_COMPONENTS"
    print_get_started
}
