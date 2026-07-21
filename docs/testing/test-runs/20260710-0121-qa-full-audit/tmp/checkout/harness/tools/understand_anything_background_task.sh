#!/usr/bin/env bash
set -euo pipefail

HOME_DIR="${HOME}"
HARNESS_DIR="${HARNESS_DIR:-$HOME_DIR/.solar/harness}"
SPRINT_ID="${SPRINT_ID:-sprint-20260527-understand-anything-background-knowledge-graph}"
TARGET_REPO="${1:-${HOME}/Solar}"
OUTPUT_DIR="$TARGET_REPO/.understand-anything"
RUN_ROOT="$HARNESS_DIR/run/understand-anything-background/$SPRINT_ID"
STATUS_JSON="$RUN_ROOT/status.json"
OUTPUT_LOG="$RUN_ROOT/output.log"
PREFLIGHT_JSON="$RUN_ROOT/preflight.json"
VERIFY_JSON="$RUN_ROOT/verify.json"
RECOVERY_JSON="$RUN_ROOT/recovery.json"
HANDOFF_MD="$HARNESS_DIR/sprints/$SPRINT_ID.handoff.md"
TASK_GRAPH="$HARNESS_DIR/sprints/$SPRINT_ID.task_graph.json"
SPRINT_STATUS="$HARNESS_DIR/sprints/$SPRINT_ID.status.json"
PLUGIN_ROOT="$HOME_DIR/.claude/plugins/cache/understand-anything/understand-anything/2.7.5"
LOCAL_PIPELINE="${LOCAL_PIPELINE:-$PWD/harness/tools/understand_anything_local_pipeline.py}"
if [[ ! -f "$LOCAL_PIPELINE" ]]; then
  LOCAL_PIPELINE="$(cd "$(dirname "$0")" && pwd)/understand_anything_local_pipeline.py"
fi
PIPELINE_TIMEOUT_SECONDS="${PIPELINE_TIMEOUT_SECONDS:-${CLAUDE_TIMEOUT_SECONDS:-1800}}"

export SPRINT_ID

mkdir -p "$RUN_ROOT"
rm -f "$RECOVERY_JSON"

write_status() {
  local phase="$1"
  local state="$2"
  local message="$3"
  STATUS_JSON="$STATUS_JSON" phase="$phase" state="$state" message="$message" target_repo="$TARGET_REPO" output_dir="$OUTPUT_DIR" python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["STATUS_JSON"])
payload = {
    "schema_version": "solar.understand_anything_background.status.v1",
    "sprint_id": os.environ.get("SPRINT_ID", "unknown"),
    "phase": os.environ["phase"],
    "status": os.environ["state"],
    "message": os.environ["message"],
    "target_repo": os.environ["target_repo"],
    "output_dir": os.environ["output_dir"],
    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

update_sprint_status() {
  local phase="$1"
  local state="$2"
  local blocker="$3"
  SPRINT_STATUS="$SPRINT_STATUS" phase="$phase" state="$state" blocker="$blocker" python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["SPRINT_STATUS"])
payload = {}
if path.exists():
    payload = json.loads(path.read_text(encoding="utf-8"))
payload.update({
    "sprint_id": payload.get("sprint_id", os.environ.get("SPRINT_ID", "sprint-20260527-understand-anything-background-knowledge-graph")),
    "id": payload.get("id", os.environ.get("SPRINT_ID", "sprint-20260527-understand-anything-background-knowledge-graph")),
    "title": payload.get("title", "Understand Anything 全仓知识图后台生成（分阶段、非阻塞）"),
    "status": os.environ["state"],
    "phase": os.environ["phase"],
    "current_node": payload.get("current_node", "U1_preflight_runtime"),
    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "blocker": os.environ["blocker"],
})
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

write_handoff() {
  local result="$1"
  cat > "$HANDOFF_MD" <<EOF
# Handoff — $SPRINT_ID

- target_repo: \`$TARGET_REPO\`
- output_dir: \`$OUTPUT_DIR\`
- result: \`$result\`
- status_json: \`$STATUS_JSON\`
- output_log: \`$OUTPUT_LOG\`
- preflight_json: \`$PREFLIGHT_JSON\`
- verify_json: \`$VERIFY_JSON\`

## Notes
- This run is isolated in a dedicated background tmux session to avoid blocking the main Solar Harness panes.
- Check \`$STATUS_JSON\` for the latest phase and \`$OUTPUT_LOG\` for raw command output.
EOF
}

write_recovery() {
  local recovery_state="$1"
  local reason="$2"
  local resume_hint="$3"
  RECOVERY_JSON="$RECOVERY_JSON" recovery_state="$recovery_state" reason="$reason" resume_hint="$resume_hint" python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["RECOVERY_JSON"])
payload = {
    "schema_version": "solar.understand_anything_background.recovery.v1",
    "sprint_id": os.environ.get("SPRINT_ID", "unknown"),
    "recovery_state": os.environ["recovery_state"],
    "reason": os.environ["reason"],
    "resume_hint": os.environ["resume_hint"],
    "resume_command": "solar-harness understand-anything background resume",
    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

run_local_pipeline_with_timeout() {
  PIPELINE_TIMEOUT_SECONDS="$PIPELINE_TIMEOUT_SECONDS" TARGET_REPO="$TARGET_REPO" OUTPUT_DIR="$OUTPUT_DIR" LOCAL_PIPELINE="$LOCAL_PIPELINE" python3 - <<'PY'
import os
import subprocess
import sys

timeout = int(os.environ.get("PIPELINE_TIMEOUT_SECONDS", "1800"))
cmd = [
    "python3",
    os.environ["LOCAL_PIPELINE"],
    "--repo",
    os.environ["TARGET_REPO"],
    "--output-dir",
    os.environ["OUTPUT_DIR"],
    "--language",
    "zh",
    "--objective",
    "background repository understanding for Solar",
]
try:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
except subprocess.TimeoutExpired as exc:
    sys.stdout.write(exc.stdout or "")
    sys.stderr.write(exc.stderr or "")
    print(f"pipeline_timeout_after_seconds={timeout}", file=sys.stderr)
    raise SystemExit(124)

sys.stdout.write(proc.stdout or "")
sys.stderr.write(proc.stderr or "")
raise SystemExit(proc.returncode)
PY
}

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] understand-anything background task start" > "$OUTPUT_LOG"
echo "sprint=$SPRINT_ID target=$TARGET_REPO" >> "$OUTPUT_LOG"

write_status "U1_preflight_runtime" "running" "Checking ThunderOMLX local pipeline prerequisites."
update_sprint_status "background_preflight" "active" ""

NODE_VERSION="$(node -v)"
PNPM_VERSION="$(pnpm -v)"
LOCAL_PIPELINE_EXISTS="0"
if [[ -f "$LOCAL_PIPELINE" ]]; then
  LOCAL_PIPELINE_EXISTS="1"
fi

python3 - <<PY > "$PREFLIGHT_JSON"
import json
import os
from pathlib import Path
claude_config = Path.home() / ".claude.json"
oauth = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
auth_status = "cli_oauth_token" if oauth else ("claude_config_json" if claude_config.exists() else "missing")
payload = {
  "node_version": "$NODE_VERSION",
  "pnpm_version": "$PNPM_VERSION",
  "plugin_root_exists": Path("$PLUGIN_ROOT").exists(),
  "plugin_root": "$PLUGIN_ROOT",
  "plugin_root_readable": Path("$PLUGIN_ROOT").exists() and os.access("$PLUGIN_ROOT", os.R_OK),
  "local_pipeline_exists": bool(int("$LOCAL_PIPELINE_EXISTS")),
  "claude_cli_auth_status": auth_status,
  "claude_cli_auth_evidence": "CLAUDE_CODE_OAUTH_TOKEN" if oauth else ("claude_config_json" if claude_config.exists() else "missing"),
  "target_repo": "$TARGET_REPO",
  "output_dir_exists": Path("$OUTPUT_DIR").exists(),
}
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

write_status "U2_run_understand_zh_background" "running" "Launching deterministic scan + ThunderOMLX semantic phase in the dedicated background runner."
update_sprint_status "background_understand_running" "active" ""

PIPELINE_EXIT=0
{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] phase=U2_run_understand_zh_background"
  set +e
  run_local_pipeline_with_timeout
  cmd_status=$?
  set -e
  if [[ "$cmd_status" -ne 0 ]]; then
    PIPELINE_EXIT=$cmd_status
  fi
} >> "$OUTPUT_LOG" 2>&1

if [[ "$PIPELINE_EXIT" -ne 0 ]]; then
  if [[ "$PIPELINE_EXIT" -eq 124 ]]; then
    write_recovery "deferred_timeout" "thunderomlx_command_timeout" "ThunderOMLX semantic phase exceeded PIPELINE_TIMEOUT_SECONDS=$PIPELINE_TIMEOUT_SECONDS; retry later or raise the timeout for long runs."
    write_handoff "deferred_timeout"
    write_status "U2_run_understand_zh_background" "blocked" "ThunderOMLX semantic phase timed out before verification; run deferred for later resume."
    update_sprint_status "background_waiting_for_runtime_timeout_recovery" "blocked" "thunderomlx_command_timeout"
    exit 0
  fi
  write_recovery "failed_runtime" "thunderomlx_pipeline_failed" "Check output.log for the exact local pipeline failure and retry after fixing it."
  write_handoff "failed_runtime"
  write_status "U2_run_understand_zh_background" "failed" "Local deterministic scan + ThunderOMLX semantic phase failed before knowledge graph verification."
  update_sprint_status "background_runtime_failed" "active" "thunderomlx_pipeline_failed"
  exit "$PIPELINE_EXIT"
fi

write_status "U3_verify_graph_artifacts" "running" "Verifying knowledge graph artifacts and metadata."

python3 - <<PY > "$VERIFY_JSON"
import json
from pathlib import Path
root = Path("$OUTPUT_DIR")
graph = root / "knowledge-graph.json"
meta = root / "meta.json"
config = root / "config.json"
manifest = root / "chunk-manifest.json"
resume = root / "resume-state.json"
payload = {
  "output_dir_exists": root.exists(),
  "config_exists": config.exists(),
  "chunk_manifest_exists": manifest.exists(),
  "resume_state_exists": resume.exists(),
  "knowledge_graph_exists": graph.exists(),
  "knowledge_graph_size": graph.stat().st_size if graph.exists() else 0,
  "meta_exists": meta.exists(),
}
if graph.exists():
  try:
    json.loads(graph.read_text(encoding="utf-8"))
    payload["knowledge_graph_json_valid"] = True
  except Exception as exc:
    payload["knowledge_graph_json_valid"] = False
    payload["knowledge_graph_error"] = str(exc)
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

if python3 - <<PY
import json
from pathlib import Path
payload = json.loads(Path("$VERIFY_JSON").read_text(encoding="utf-8"))
assert payload.get("knowledge_graph_exists")
assert payload.get("knowledge_graph_json_valid")
assert payload.get("chunk_manifest_exists")
assert payload.get("resume_state_exists")
assert payload.get("meta_exists")
PY
then
  rm -f "$RECOVERY_JSON"
  write_status "U4_handoff_resume_contract" "running" "Knowledge graph verified; writing handoff."
  write_handoff "success"
  write_status "U4_handoff_resume_contract" "completed" "Background understand-anything run completed successfully."
  update_sprint_status "background_completed" "reviewing" ""
  if ! python3 "$(cd "$(dirname "$0")" && pwd)/generate_understand_anything_background_closeout.py" --runtime-root "$HARNESS_DIR" --target-repo "$TARGET_REPO" >> "$OUTPUT_LOG" 2>&1; then
    update_sprint_status "background_closeout_reviewing" "reviewing" "understand_anything_background_auto_closeout_failed"
  fi
else
  write_handoff "partial_or_failed"
  write_status "U3_verify_graph_artifacts" "failed" "Background run finished without a valid knowledge-graph.json."
  update_sprint_status "background_verification_failed" "active" "knowledge-graph.json missing or invalid after background run"
  exit 1
fi
