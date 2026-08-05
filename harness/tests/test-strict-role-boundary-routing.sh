#!/usr/bin/env bash
# Governed workflows must queue same-role work instead of borrowing another persona.

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:?HARNESS_DIR is required}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

export COORD_NO_MAIN=1
export SPRINTS_DIR="$TMP_DIR/sprints"
mkdir -p "$SPRINTS_DIR"

# shellcheck disable=SC1091
. "$HARNESS_DIR/coordinator.sh"

STRICT_SID="sprint-strict-autosci"
LEGACY_SID="sprint-legacy"
printf '%s\n' '{"sprint_id":"sprint-strict-autosci","strict_role_boundaries":true}' \
  > "$SPRINTS_DIR/${STRICT_SID}.task_graph.json"
printf '%s\n' '{"sprint_id":"sprint-legacy"}' \
  > "$SPRINTS_DIR/${LEGACY_SID}.task_graph.json"

role_pool_candidates_via_python() {
  local role="$1" strict="${2:-0}"
  [[ "$role" == "planner" ]] || return 1
  printf '%s\n' 'solar-harness:0.1'
  [[ "$strict" == "1" ]] || printf '%s\n' 'solar-harness:0.2'
}
choose_planner_pane() { printf '%s\n' 'solar-harness:0.1'; }
choose_architect_pane() { printf '%s\n' 'solar-harness-lab:0.4'; }
list_lab_persona_panes() {
  [[ "${1:-}" == "lab-builder" ]] && printf '%s\n' 'solar-harness-lab:0.0'
}

strict_panes="$(role_candidate_panes planner "$STRICT_SID")"
legacy_panes="$(role_candidate_panes planner "$LEGACY_SID")"

[[ "$strict_panes" == 'solar-harness:0.1' ]] || {
  printf 'strict planner pool leaked another role:\n%s\n' "$strict_panes" >&2
  exit 1
}
[[ "$legacy_panes" == *'solar-harness:0.2'* ]] || {
  printf 'legacy planner pool unexpectedly lost configured spillover:\n%s\n' "$legacy_panes" >&2
  exit 1
}
[[ "$legacy_panes" == *'solar-harness-lab:0.0'* ]] || {
  printf 'legacy manual lab-builder fallback missing:\n%s\n' "$legacy_panes" >&2
  exit 1
}

printf 'PASS strict workflow planner routing excludes builder panes\n'
