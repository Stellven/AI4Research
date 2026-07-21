#!/usr/bin/env bash
set -u
TASK_DIR='/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0080/pytest/test_runner_script_auto_closes0/task'
STATUS_FILE='/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0080/pytest/test_runner_script_auto_closes0/task/status.json'
DISPATCH_FILE='/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0080/pytest/test_runner_script_auto_closes0/task/dispatch.md'
OUTPUT_LOG="$TASK_DIR/output.log"
RUN_STARTED_MARKER="$TASK_DIR/run.started"
HARNESS_DIR='/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-checkout/harness'
HARNESS_BIN="$HARNESS_DIR/bin"
SPRINTS_DIR='/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-checkout/harness/sprints'
GRAPH='/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0080/pytest/test_runner_script_auto_closes0/graph.json'
NODE_ID=N1
SID=sprint-demo
ROLE=builder
PROFILE=builder
BACKEND=claude-cli
MODEL=sonnet
PROVIDER=anthropic
CAPABILITY_STATUS=ok
HANDOFF='/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0080/pytest/test_runner_script_auto_closes0/handoff.md'
HARNESS='/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-checkout/harness/solar-harness.sh'
WORK_DIR='/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-checkout'
export TASK_DIR STATUS_FILE DISPATCH_FILE OUTPUT_LOG RUN_STARTED_MARKER HARNESS_DIR HARNESS_BIN SPRINTS_DIR GRAPH NODE_ID SID ROLE PROFILE BACKEND MODEL PROVIDER CAPABILITY_STATUS HANDOFF HARNESS WORK_DIR
export PATH="$HARNESS_BIN:$PATH"
export SOLAR_SAFE_FIND_ROOT="$WORK_DIR"

pane_title() {
  local title="$1"
  if [[ -n "${TMUX:-}" ]]; then
    tmux select-pane -T "$title" >/dev/null 2>&1 || true
  fi
}

write_status() {
  local status="$1" exit_code="${2:-}"
  python3 - "$STATUS_FILE" "$status" "$exit_code" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
data = {}
if p.exists():
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {}
data["status"] = sys.argv[2]
data["exit_code"] = None if sys.argv[3] == "" else int(sys.argv[3])
data["updated_at"] = sys.argv[4]
data.setdefault("created_at", sys.argv[4])
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

mkdir -p "$TASK_DIR"
: > "$RUN_STARTED_MARKER"
write_status running
pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:running"

if [[ "${SOLAR_MULTI_TASK_SANITIZE_ENV:-1}" != "0" ]]; then
  unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_EXECPATH
  unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY
fi

{
  echo "[solar-harness multi-task] sid=$SID node=$NODE_ID backend=$BACKEND model=$MODEL start=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[solar-harness multi-task] sid=$SID node=$NODE_ID agent_launch backend=$BACKEND profile=$PROFILE dispatch=$DISPATCH_FILE"
  (
    if [[ "$BACKEND" == "command" && -z '' ]]; then
      echo "ERROR: backend=command requires SOLAR_MULTI_TASK_AGENT_CMD"
      exit 127
    elif [[ -n '' && "$BACKEND" != "command" ]]; then
      SOLAR_MULTI_TASK_DISPATCH_FILE="$DISPATCH_FILE" bash -lc ''
    else
      if [[ "$BACKEND" == "claude-cli" ]] && ! command -v claude >/dev/null 2>&1; then
        echo "ERROR: claude command not found; set SOLAR_MULTI_TASK_AGENT_CMD"
        exit 127
      fi
      claude --dangerously-skip-permissions --permission-mode bypassPermissions --model sonnet --tools default --strict-mcp-config --mcp-config '/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-checkout/harness/config/empty-mcp.json' -p "$(cat "$DISPATCH_FILE")"
    fi
  ) &
  agent_pid=$!
  echo "$agent_pid" > "$TASK_DIR/agent.pid"
  echo "[solar-harness multi-task] sid=$SID node=$NODE_ID agent_pid=$agent_pid"
  sleep "${SOLAR_MULTI_TASK_AGENT_START_GRACE_SEC:-2}"
  if kill -0 "$agent_pid" >/dev/null 2>&1; then
    echo "[solar-harness multi-task] sid=$SID node=$NODE_ID agent_alive_after_grace=true"
  else
    echo "[solar-harness multi-task] sid=$SID node=$NODE_ID agent_alive_after_grace=false"
  fi
  wait "$agent_pid"
  agent_rc=$?
  echo "[solar-harness multi-task] sid=$SID node=$NODE_ID agent_exit=$agent_rc at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > >(tee -a "$OUTPUT_LOG") 2>&1
rc=${agent_rc:-$?}

graph_node_status() {
  python3 - "$GRAPH" "$NODE_ID" <<PY 2>/dev/null || true
import json, sys
from pathlib import Path
try:
    graph = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    node_id = sys.argv[2]
    for node in graph.get("nodes", []):
        if str(node.get("id") or "") == node_id:
            print(str(node.get("status") or ""))
            break
except Exception:
    pass
PY
}

mark_graph_failed_unless_passed() {
  local current
  current="$(graph_node_status | tail -n 1)"
  if [[ "$current" == "passed" ]]; then
    echo "[solar-harness multi-task] sid=$SID node=$NODE_ID late_failure_ignored_graph_already_passed=true" | tee -a "$OUTPUT_LOG"
    return 2
  fi
  "$HARNESS" graph-scheduler mark --graph "$GRAPH" --node "$NODE_ID" --status failed --in-place >> "$OUTPUT_LOG" 2>&1 || true
  return 0
}

if [[ "$rc" -eq 0 && -s "$HANDOFF" && "$HANDOFF" -nt "$RUN_STARTED_MARKER" ]]; then
  "$HARNESS" graph-scheduler mark --graph "$GRAPH" --node "$NODE_ID" --status reviewing --in-place >> "$OUTPUT_LOG" 2>&1 || true
  write_status completed "$rc"
  pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:completed"
elif [[ "$rc" -eq 0 && -s "$HANDOFF" ]]; then
  echo "ERROR: stale handoff predates current run: $HANDOFF" | tee -a "$OUTPUT_LOG"
  if mark_graph_failed_unless_passed; then
    write_status failed_stale_handoff 66
  else
    write_status failed_aligned 66
  fi
  pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:failed_stale_handoff"
  rc=66
elif [[ "$rc" -eq 0 ]]; then
  echo "ERROR: missing handoff: $HANDOFF" | tee -a "$OUTPUT_LOG"
  if mark_graph_failed_unless_passed; then
    write_status failed_missing_handoff 65
  else
    write_status failed_aligned 65
  fi
  pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:failed_missing_handoff"
  rc=65
else
  if mark_graph_failed_unless_passed; then
    write_status failed "$rc"
  else
    write_status failed_aligned "$rc"
  fi
  pane_title "MT $ROLE/$PROFILE | 模型:$MODEL | provider:$PROVIDER | 状态:failed"
fi
echo "[solar-harness multi-task] sid=$SID node=$NODE_ID exit=$rc end=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$OUTPUT_LOG"
exit "$rc"
