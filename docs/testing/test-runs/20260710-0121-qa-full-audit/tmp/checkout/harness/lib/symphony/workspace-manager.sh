#!/usr/bin/env bash
# Workspace Manager — creates deterministic isolated workspaces per sprint
#
# Usage:
#   workspace-manager.sh create <sprint-id>
#   workspace-manager.sh info   <sprint-id>
#   workspace-manager.sh show   <sprint-id>
#   workspace-manager.sh clean  <sprint-id>
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"

# Source hook runner (optional — no-op if hooks.sh missing)
_HOOKS_SH="$HARNESS_DIR/lib/symphony/hooks.sh"
if [[ -f "$_HOOKS_SH" ]]; then
  # shellcheck source=hooks.sh
  source "$_HOOKS_SH"
fi
# sprint-20260507-symphony3 S3: structured events
[[ -f "$HARNESS_DIR/lib/events.sh" ]] && . "$HARNESS_DIR/lib/events.sh"

# ─── _run_ws_hook ───
# Run a lifecycle hook for a sprint workspace, reading config from WORKFLOW.md.
# Args: <hook_name> <sprint_id> <ws_dir>
# Returns: 0 if hook succeeded or no hook configured; 1 if hook failed (on_failure=fail)
_run_ws_hook() {
  local hook_name="$1"
  local sprint_id="$2"
  local ws_dir="$3"

  # hooks.sh must be sourced for run_hook to be available
  if ! declare -f run_hook >/dev/null 2>&1; then
    return 0
  fi

  local workflow_path="$ws_dir/WORKFLOW.md"
  [[ -f "$workflow_path" ]] || return 0

  local loader_output
  loader_output=$(python3 "$HARNESS_DIR/lib/symphony/workflow-loader.py" "$workflow_path" 2>/dev/null || true)
  [[ -z "$loader_output" ]] && return 0

  local cmd
  cmd=$(echo "$loader_output" | grep "^  hooks\.${hook_name}\.command:" | sed 's/^  [^:]*: //' | head -1)
  [[ -z "$cmd" ]] && return 0

  local timeout_ms
  timeout_ms=$(echo "$loader_output" | grep "^  hooks\.${hook_name}\.timeout_ms:" | sed 's/^  [^:]*: //' | head -1)
  timeout_ms="${timeout_ms:-60000}"

  local on_failure
  on_failure=$(echo "$loader_output" | grep "^  hooks\.${hook_name}\.on_failure:" | sed 's/^  [^:]*: //' | head -1)
  on_failure="${on_failure:-fail}"

  # Parse env_allow list (stored as Python list repr: ['FOO', 'BAR'])
  local env_allow_str
  env_allow_str=$(echo "$loader_output" | grep "^  hooks\.${hook_name}\.env_allow:" | sed "s/^  [^:]*: //" | head -1)
  local env_allow=()
  if [[ -n "$env_allow_str" ]]; then
    # Strip brackets and quotes, split by comma
    local cleaned
    cleaned=$(echo "$env_allow_str" | tr -d "[]'" | tr ',' ' ')
    for var in $cleaned; do
      var=$(echo "$var" | tr -d ' "')
      [[ -n "$var" ]] && env_allow+=("$var")
    done
  fi

  # Export workspace vars so run_hook can inject them
  export SPRINT_ID="$sprint_id"
  export WORKSPACE_DIR="$ws_dir"
  export WORKSPACE_ROOT
  WORKSPACE_ROOT=$(resolve_root)

  run_hook "$hook_name" "$sprint_id" "$cmd" "$timeout_ms" "$on_failure" "${env_allow[@]+"${env_allow[@]}"}"
}

resolve_root() {
  # Check env var first
  if [[ -n "${SOLAR_SYMPHONY_WORKSPACE_ROOT:-}" ]]; then
    echo "$SOLAR_SYMPHONY_WORKSPACE_ROOT"
    return 0
  fi
  # Check Toshiba
  if [[ -d "/Volumes/toshiba/SolarWorkspaces" ]]; then
    echo "/Volumes/toshiba/SolarWorkspaces"
    return 0
  fi
  # Fallback
  echo "$HOME/.solar/workspaces"
}

sanitize_key() {
  local key="$1"
  # Only allow [A-Za-z0-9._-]
  local cleaned
  cleaned=$(echo "$key" | tr -cs 'A-Za-z0-9._-' '_')
  # Remove leading/trailing underscores
  cleaned="${cleaned#_}"
  cleaned="${cleaned%_}"
  echo "$cleaned"
}

validate_key() {
  local key="$1"
  if [[ ! "$key" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "Error: invalid workspace key: $key (only [A-Za-z0-9._-] allowed)" >&2
    return 1
  fi
  # Must not be empty
  [[ -n "$key" ]] || { echo "Error: empty workspace key" >&2; return 1; }
  # Must not traverse paths
  [[ "$key" != *"..*"* ]] || { echo "Error: path traversal in key" >&2; return 1; }
  return 0
}

do_create() {
  local sprint_id="$1"
  local ws_key
  ws_key=$(sanitize_key "$sprint_id")
  validate_key "$ws_key" || return 1

  local root
  root=$(resolve_root)
  local ws_dir="${root}/${ws_key}"

  # Copy WORKFLOW template first so hook runner can read it for pre_claim
  # Only copy if WORKFLOW.md not already present (test can inject custom one)
  mkdir -p "${ws_dir}/proof" "${ws_dir}/logs"
  local workflow_src="$HARNESS_DIR/templates/WORKFLOW.solar.md"
  if [[ -f "$workflow_src" && ! -f "${ws_dir}/WORKFLOW.md" ]]; then
    cp "$workflow_src" "${ws_dir}/WORKFLOW.md"
  fi

  # pre_claim_workspace hook (before workspace is marked ready)
  _run_ws_hook "pre_claim_workspace" "$sprint_id" "$ws_dir" || return 1

  # Atomic claim: use O_EXCL via bash noclobber — fails if file already exists.
  # This eliminates the TOCTOU race between a separate check and write.
  local claim_file="${ws_dir}/.solar-sprint-id"
  if ! ( set -o noclobber && echo "$sprint_id" > "$claim_file" ) 2>/dev/null; then
    # Another concurrent create already claimed this workspace — idempotent return
    echo "$ws_dir"
    return 0
  fi

  # Copy or symlink contract
  local contract_src="${SPRINTS_DIR}/${sprint_id}.contract.md"
  if [[ -f "$contract_src" ]]; then
    ln -sf "$contract_src" "${ws_dir}/contract.md" 2>/dev/null || \
      cp "$contract_src" "${ws_dir}/contract.md"
  fi

  # post_claim_workspace hook (workspace fully set up)
  _run_ws_hook "post_claim_workspace" "$sprint_id" "$ws_dir" || true

  # S3: emit workspace_created event
  events_emit "workspace-manager" "workspace_created" "info" "$sprint_id"     "{\"ws_dir\":\"${ws_dir}\"}" 2>/dev/null || true

  echo "$ws_dir"
}

do_info() {
  local sprint_id="$1"
  local ws_key
  ws_key=$(sanitize_key "$sprint_id")
  local root
  root=$(resolve_root)
  local ws_dir="${root}/${ws_key}"

  if [[ ! -d "$ws_dir" ]]; then
    echo "Workspace not found: $ws_dir" >&2
    return 1
  fi

  echo "workspace: $ws_dir"
  echo "sprint_id: $(cat "${ws_dir}/.solar-sprint-id" 2>/dev/null || echo 'unknown')"
  echo "contract:  $(ls -la "${ws_dir}/contract.md" 2>/dev/null || echo 'missing')"
  echo "workflow:  $([ -f "${ws_dir}/WORKFLOW.md" ] && echo 'present' || echo 'missing')"
  echo "proof/:    $([ -d "${ws_dir}/proof" ] && echo 'present' || echo 'missing')"
  echo "logs/:     $([ -d "${ws_dir}/logs" ] && echo 'present' || echo 'missing')"

  # Check workspace is NOT in project root
  local project_root="$HOME/.solar/harness"
  if [[ "$ws_dir" == "$project_root"* ]]; then
    echo "WARNING: workspace is inside project root!" >&2
  fi
}

do_show() {
  do_info "$1"
}

do_clean() {
  local sprint_id="$1"
  local ws_key
  ws_key=$(sanitize_key "$sprint_id")
  local root
  root=$(resolve_root)
  local ws_dir="${root}/${ws_key}"

  if [[ ! -d "$ws_dir" ]]; then
    echo "Workspace not found: $ws_dir" >&2
    return 1
  fi

  # Read post_release hook config BEFORE deletion (WORKFLOW.md will be gone after rm -rf)
  local post_release_cmd="" post_release_timeout="30000" post_release_on_fail="continue"
  if declare -f run_hook >/dev/null 2>&1; then
    local workflow_path="$ws_dir/WORKFLOW.md"
    if [[ -f "$workflow_path" ]]; then
      local loader_output
      loader_output=$(python3 "$HARNESS_DIR/lib/symphony/workflow-loader.py" "$workflow_path" 2>/dev/null || true)
      post_release_cmd=$(echo "$loader_output" | grep "^  hooks\.post_release_workspace\.command:" | sed 's/^  [^:]*: //' | head -1)
      local t
      t=$(echo "$loader_output" | grep "^  hooks\.post_release_workspace\.timeout_ms:" | sed 's/^  [^:]*: //' | head -1)
      [[ -n "$t" ]] && post_release_timeout="$t"
      local f
      f=$(echo "$loader_output" | grep "^  hooks\.post_release_workspace\.on_failure:" | sed 's/^  [^:]*: //' | head -1)
      [[ -n "$f" ]] && post_release_on_fail="$f"
    fi
  fi

  # pre_release_workspace hook (before cleanup)
  _run_ws_hook "pre_release_workspace" "$sprint_id" "$ws_dir" || true

  rm -rf "$ws_dir"

  # post_release_workspace hook (after cleanup, using config read before deletion)
  if [[ -n "$post_release_cmd" ]] && declare -f run_hook >/dev/null 2>&1; then
    export SPRINT_ID="$sprint_id"
    export WORKSPACE_DIR="$ws_dir"
    export WORKSPACE_ROOT="$root"
    run_hook "post_release_workspace" "$sprint_id" "$post_release_cmd" \
      "$post_release_timeout" "$post_release_on_fail" || true
  fi

  # S3: emit workspace_cleanup event
  events_emit "workspace-manager" "workspace_cleanup" "info" "$sprint_id"     "{\"ws_dir\":\"${ws_dir}\"}" 2>/dev/null || true

  echo "Cleaned: $ws_dir"
}

# Main
cmd="${1:-}"
sid="${2:-}"

case "$cmd" in
  create) [[ -z "$sid" ]] && { echo "Usage: $0 create <sprint-id>" >&2; exit 1; }; do_create "$sid" ;;
  info|show) [[ -z "$sid" ]] && { echo "Usage: $0 $cmd <sprint-id>" >&2; exit 1; }; do_info "$sid" ;;
  clean) [[ -z "$sid" ]] && { echo "Usage: $0 clean <sprint-id>" >&2; exit 1; }; do_clean "$sid" ;;
  root) resolve_root ;;
  *) echo "Usage: $0 {create|info|show|clean|root} <sprint-id>" >&2; exit 1 ;;
esac
