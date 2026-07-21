#!/usr/bin/env bash
# Symphony Runner — dry-run (default) or guarded Codex app-server execution
#
# Usage:
#   runner.sh --dry-run --sprint-id <id>
#   runner.sh --dry-run --sprint <id>          (alias)
#   runner.sh --unsafe-run-codex --sprint-id <id>
#
# Dry-run sets SOLAR_SYMPHONY_DRY_RUN=1 (safe in Claude Code nested env).
# Real execution requires SOLAR_SYMPHONY_REAL=1 to bypass guard.
# P0 = dry-run only. Writes proof artifacts, does NOT launch external processes.
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
WS_MGR="$HARNESS_DIR/lib/symphony/workspace-manager.sh"
# sprint-20260507-symphony3 S3: structured events
[[ -f "$HARNESS_DIR/lib/events.sh" ]] && . "$HARNESS_DIR/lib/events.sh"

# Defaults
DRY_RUN=1
SPRINT_ID=""

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; export SOLAR_SYMPHONY_DRY_RUN=1; shift ;;
    --unsafe-run-codex) DRY_RUN=0; shift ;;
    --sprint-id|--sprint) SPRINT_ID="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; shift ;;
  esac
done

[[ -z "$SPRINT_ID" ]] && { echo "Error: --sprint-id required" >&2; exit 1; }

# Resolve workspace
WS_ROOT=$(bash "$WS_MGR" root)
WS_DIR="${WS_ROOT}/${SPRINT_ID}"

# Ensure workspace exists
if [[ ! -d "$WS_DIR" ]]; then
  bash "$WS_MGR" create "$SPRINT_ID" >/dev/null
fi

PROOF_DIR="${WS_DIR}/proof"
LOGS_DIR="${WS_DIR}/logs"
mkdir -p "$PROOF_DIR" "$LOGS_DIR"

# ─── Guard checks ───

# Guard 1: workspace must be in allowed roots
ALLOWED_ROOTS=("$WS_ROOT" "$HOME/.solar/workspaces")
ws_ok=0
for r in "${ALLOWED_ROOTS[@]}"; do
  if [[ "$WS_DIR" == "$r/"* ]]; then
    ws_ok=1
    break
  fi
done
if [[ $ws_ok -eq 0 ]]; then
  echo "Guard FAIL: workspace not in allowed roots: $WS_DIR" >&2
  exit 1
fi

# Guard 2: real execution requires explicit opt-in (dry-run is always safe)
# Replaced CLAUDECODE env check — that check blocked dry-run inside Claude Code nested env.
# Now: --dry-run sets SOLAR_SYMPHONY_DRY_RUN=1 and skips this guard entirely.
#      --unsafe-run-codex requires SOLAR_SYMPHONY_REAL=1 to proceed.
if [[ $DRY_RUN -eq 0 && -z "${SOLAR_SYMPHONY_REAL:-}" ]]; then
  echo "Guard FAIL: real execution requires SOLAR_SYMPHONY_REAL=1 env var" >&2
  exit 1
fi

# Guard 3: not inside solar-harness live pane (real execution only)
# Dry-run is safe inside any session — it only writes proof files, no pane mutation.
if [[ $DRY_RUN -eq 0 && -n "${TMUX_PANE:-}" ]]; then
  tmux_session=""
  tmux_session=$(tmux display-message -p -t "$TMUX_PANE" '#{session_name}' 2>/dev/null || true)
  case "$tmux_session" in
    solar-harness|solar-harness-lab)
      echo "Guard FAIL: running inside live tmux session: $tmux_session" >&2
      exit 1
      ;;
  esac
fi

# ─── Dry-run mode ───

if [[ $DRY_RUN -eq 1 ]]; then
  # S3: emit runner_started event
  events_emit "runner" "runner_started" "info" "$SPRINT_ID"     "{\"mode\":\"dry-run\",\"ws_dir\":\"${WS_DIR}\"}" 2>/dev/null || true

  # Write proof/run-request.md
  cat > "${PROOF_DIR}/run-request.md" << REQEOF
# Run Request (dry-run)

**Sprint**: ${SPRINT_ID}
**Mode**: dry-run
**Timestamp**: $(date -u +%Y-%m-%dT%H:%M:%SZ)

## Request

Execute sprint contract for ${SPRINT_ID}.

## Contract

See: ${SPRINTS_DIR}/${SPRINT_ID}.contract.md

## Workspace

${WS_DIR}

## Status

This is a dry-run. No external processes were launched.
REQEOF

  # Write proof/runner-env.json
  python3 << 'PYEOF' > "${PROOF_DIR}/runner-env.json"
import json, os, datetime
print(json.dumps({
    "mode": "dry-run",
    "sprint_id": os.environ.get("SPRINT_ID", ""),
    "workspace": os.environ.get("WS_DIR", ""),
    "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "tmux_pane": os.environ.get("TMUX_PANE", ""),
    "tmux_session": os.environ.get("TMUX", ""),
    "env_clean": not any(
        k.startswith("CLAUDECODE") or k.startswith("CLAUDE_CODE_")
        for k in os.environ
    ),
}, indent=2))
PYEOF

  # Write logs/runner.log
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] runner dry-run completed for ${SPRINT_ID}" \
    >> "${LOGS_DIR}/runner.log"

  # S3: emit runner_exited event
  events_emit "runner" "runner_exited" "info" "$SPRINT_ID"     "{\"mode\":\"dry-run\",\"exit_code\":0}" 2>/dev/null || true

  echo "dry-run completed: ${WS_DIR}"
  exit 0
fi

# ─── Unsafe: real Codex app-server (P1, NOT P0) ───

echo "Error: --unsafe-run-codex not implemented in P0" >&2
echo "P0 only supports dry-run mode." >&2
exit 1
