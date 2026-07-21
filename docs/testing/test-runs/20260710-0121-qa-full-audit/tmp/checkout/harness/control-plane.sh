#!/usr/bin/env bash
# control-plane.sh — Solar Harness 控制面入口 (Phase A — read-only)
set -euo pipefail
HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
# lib/run-state.sh 使用 SPRINTS_DIR
SPRINTS_DIR="${SPRINTS_DIR:-$HARNESS_DIR/sprints}"
. "$HARNESS_DIR/lib/run-state.sh"

show_help() {
  cat <<EOF
Solar Harness Control Plane (Phase A — read-only)

Usage:
  control-plane.sh help                       Show this help
  control-plane.sh --help                     Same as 'help'
  control-plane.sh status                     List recent 20 sprints
  control-plane.sh status <sid>               Show one sprint summary

Examples:
  control-plane.sh status sprint-20260503-094659
  control-plane.sh status

Note: state-write commands (transition/promote/...) intentionally NOT exposed
in Phase A. Use solar-harness.sh subcommands (plan-verdict, eval-verdict, etc).

See also: solar-harness.sh (sprint CRUD), coordinator.sh (auto dispatch)
EOF
}

cmd="${1:---help}"
case "$cmd" in
  -h|--help|help) show_help ;;
  status)
    sid="${2:-}"
    if [[ -z "$sid" ]]; then
      for s in $(rs_list_recent 20); do
        st=$(rs_read_status "$s" 2>/dev/null || echo "?")
        printf "%-40s %s\n" "$s" "$st"
      done
    else
      rs_summary "$sid"
    fi
    ;;
  *) echo "Unknown command: $cmd" >&2; show_help; exit 1 ;;
esac
