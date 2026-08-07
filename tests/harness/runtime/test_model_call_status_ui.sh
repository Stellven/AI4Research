#!/usr/bin/env bash
# test-model-call-status-ui.sh — model-call events are visible in status UI projection
set -euo pipefail

HARNESS_DIR="${HOME}/.solar/harness"
SESSION_ID="test-model-call-status-ui-$$"
DISPATCH_FILE="${HARNESS_DIR}/run/${SESSION_ID}.md"
PASS=0
FAIL=0

cleanup() {
  rm -rf "${HARNESS_DIR}/sessions/${SESSION_ID}"
  rm -f "$DISPATCH_FILE"
}
trap cleanup EXIT

ok() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  if [[ "$haystack" == *"$needle"* ]]; then ok "$label"; else fail "$label"; fi
}

mkdir -p "${HARNESS_DIR}/run" "${HARNESS_DIR}/run/pane-env"
cat > "$DISPATCH_FILE" <<'EOF'
# Status UI Model Call Test

This dispatch should be projected into the status dashboard.
EOF
cat > "${HARNESS_DIR}/run/pane-env/solar-harness_0.2.json" <<'JSON'
{
  "pane": "solar-harness:0.2",
  "persona": "builder",
  "auth_source": "anthropic",
  "model_flag": "--model opus",
  "claude_bin": "/tmp/claude"
}
JSON

python3 "${HARNESS_DIR}/lib/model_call_runtime.py" request \
  --session-id "$SESSION_ID" \
  --pane "solar-harness:0.2" \
  --dispatch-id "dispatch-status-ui" \
  --instruction-file "$DISPATCH_FILE" \
  --status "queued" \
  --json >/tmp/model-call-status-request.$$.json
python3 "${HARNESS_DIR}/lib/model_call_runtime.py" succeeded \
  --session-id "$SESSION_ID" \
  --pane "solar-harness:0.2" \
  --dispatch-id "dispatch-status-ui" \
  --instruction-file "$DISPATCH_FILE" \
  --status "accepted" \
  --json >/tmp/model-call-status-success.$$.json

OUT=$(python3 - <<'PY'
import importlib.util
import json
from pathlib import Path

path = Path.home() / ".solar" / "harness" / "lib" / "symphony" / "status-server.py"
spec = importlib.util.spec_from_file_location("solar_status_server_test", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
projection = mod._latest_model_call_for_pane("solar-harness:0.2", "")
html = path.read_text(encoding="utf-8", errors="replace")
print(json.dumps(projection, ensure_ascii=False, sort_keys=True))
print("HAS_MODEL_COLUMN", "模型调用" in html)
print("HAS_MODEL_CELL", "modelCallCell" in html)
PY
)

assert_contains "projects latest succeeded status" "$OUT" '"status": "ok"'
assert_contains "projects dispatch id" "$OUT" '"dispatch_id": "dispatch-status-ui"'
assert_contains "projects model flag" "$OUT" 'opus'
assert_contains "dashboard has model column" "$OUT" 'HAS_MODEL_COLUMN True'
assert_contains "dashboard has model call renderer" "$OUT" 'HAS_MODEL_CELL True'

rm -f /tmp/model-call-status-request.$$.json /tmp/model-call-status-success.$$.json
echo ""
echo "=== Model Call Status UI: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]]
