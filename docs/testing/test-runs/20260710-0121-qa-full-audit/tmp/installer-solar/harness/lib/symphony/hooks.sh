#!/usr/bin/env bash
# Symphony Hook Runner — sandboxed lifecycle hook execution
#
# Usage (source this file, then call run_hook):
#   source hooks.sh
#   run_hook <hook_name> <sprint_id> <command> <timeout_ms> <on_failure> [env_allow_var...]
#
# Isolation model:
#   - env -i starts a completely clean environment
#   - Only whitelisted vars are injected (SPRINT_ID, WORKSPACE_DIR, WORKSPACE_ROOT,
#     SOLAR_SYMPHONY_HOOK_NAME, PATH, plus any env_allow extras)
#   - All *_TOKEN and *_KEY vars are explicitly excluded (never in the clean env)
#   - timeout: gtimeout (coreutils) if available, else perl alarm fallback
#   - Logs: ~/.solar/harness/sprints/<sprint_id>.hook-<hook_name>.log

set -eu

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
# sprint-20260507-symphony3 S3: structured events
[[ -f "$HARNESS_DIR/lib/events.sh" ]] && . "$HARNESS_DIR/lib/events.sh"
SPRINTS_DIR="${SPRINTS_DIR:-$HARNESS_DIR/sprints}"

# Default whitelist (always injected if non-empty in host env)
_HOOK_ENV_WHITELIST=(SPRINT_ID WORKSPACE_DIR WORKSPACE_ROOT SOLAR_SYMPHONY_HOOK_NAME PATH)

# ─── run_hook ───
# Args:
#   $1  hook_name      e.g. pre_claim_workspace
#   $2  sprint_id
#   $3  command        shell command string
#   $4  timeout_ms     integer milliseconds (default: 60000)
#   $5  on_failure     "fail" or "continue" (default: fail)
#   $6+ env_allow      additional host env var names to pass through
run_hook() {
  local hook_name="$1"
  local sprint_id="$2"
  local command="$3"
  local timeout_ms="${4:-60000}"
  local on_failure="${5:-fail}"
  shift 5 || true
  local env_allow=("$@")

  local log_file="${SPRINTS_DIR}/${sprint_id}.hook-${hook_name}.log"
  local timeout_sec=$(( timeout_ms / 1000 ))
  [[ $timeout_sec -lt 1 ]] && timeout_sec=1

  # Timestamp log entry
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [hook:${hook_name}] starting (timeout=${timeout_sec}s on_failure=${on_failure})" >> "$log_file"

  # Build sanitized env array (env -i friendly: KEY=VALUE strings)
  local safe_env=()
  for var in "${_HOOK_ENV_WHITELIST[@]}"; do
    local val="${!var:-}"
    if [[ -n "$val" ]]; then
      safe_env+=("${var}=${val}")
    fi
  done

  # Inject env_allow extras (only if non-empty in host env)
  for var in "${env_allow[@]}"; do
    local val="${!var:-}"
    [[ -n "$val" ]] && safe_env+=("${var}=${val}")
  done

  # Execute with timeout in sanitized env
  local exit_code=0
  if command -v gtimeout &>/dev/null; then
    # gtimeout: SIGTERM, then SIGKILL after 5s
    env -i "${safe_env[@]}" \
      gtimeout --signal=TERM --kill-after=5 "${timeout_sec}" \
      bash -c "$command" >> "$log_file" 2>&1 || exit_code=$?
  else
    # perl alarm fallback: macOS-compatible, handles SIGTERM
    # Use getpgrp() to send signal to the entire process group (not just perl's PID)
    env -i "${safe_env[@]}" \
      bash -c "
        perl -e '
          alarm $timeout_sec;
          \$SIG{ALRM} = sub { kill q(TERM), -getpgrp(); sleep 5; kill 9, -getpgrp() };
          exec @ARGV
        ' -- bash -c $(printf '%q' "$command")
      " >> "$log_file" 2>&1 || exit_code=$?
  fi

  if [[ $exit_code -eq 124 ]]; then
    # gtimeout exit code for timeout
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [hook:${hook_name}] timeout after ${timeout_sec}s (exit=124)" >> "$log_file"
  elif [[ $exit_code -eq 142 ]]; then
    # SIGALRM signal exit (perl alarm path: 128 + 14)
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [hook:${hook_name}] timeout after ${timeout_sec}s (SIGALRM)" >> "$log_file"
  fi

  if [[ $exit_code -ne 0 ]]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [hook:${hook_name}] FAILED exit=${exit_code} on_failure=${on_failure}" >> "$log_file"
    # S3: emit hook_failed event
    events_emit "hooks" "hook_failed" "warn" "$sprint_id"       "{\"hook\":\"${hook_name}\",\"exit_code\":${exit_code},\"on_failure\":\"${on_failure}\"}" 2>/dev/null || true
    if [[ "$on_failure" == "fail" ]]; then
      echo "[run_hook] ${hook_name} failed (exit=${exit_code}), on_failure=fail — aborting" >&2
      return 1
    fi
    echo "[run_hook] ${hook_name} failed (exit=${exit_code}), on_failure=continue — proceeding" >&2
    return 0
  fi

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [hook:${hook_name}] OK" >> "$log_file"
  # S3: emit hook_executed event
  events_emit "hooks" "hook_executed" "info" "$sprint_id"     "{\"hook\":\"${hook_name}\",\"timeout_sec\":${timeout_sec}}" 2>/dev/null || true
  return 0
}

# ─── load_workflow_hooks ───
# Parse hooks config from a WORKFLOW.md file.
# Outputs KEY=VALUE lines that can be eval'd or read line-by-line.
# Returns 0 always (no hooks = empty output).
load_workflow_hooks() {
  local workflow_path="$1"
  local loader="$HARNESS_DIR/lib/symphony/workflow-loader.py"
  [[ -f "$workflow_path" ]] || return 0
  [[ -f "$loader" ]] || return 0
  python3 "$loader" "$workflow_path" 2>/dev/null || true
}

# ─── get_hook_field ───
# Extract a single field from flat workflow-loader output.
# Args: <loader_output_file_or_string> <dotted.key>
# Usage: val=$(get_hook_field <output> "hooks.pre_claim_workspace.command")
get_hook_field() {
  local output="$1"
  local dotted_key="$2"
  echo "$output" | grep "^  ${dotted_key}:" | sed 's/^  [^:]*: //' | head -1
}
