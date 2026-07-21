#!/usr/bin/env bash
# test-model-call-runtime.sh — observable model-call boundary events
set -euo pipefail

HARNESS_DIR="${HOME}/.solar/harness"
LIB_DIR="${HARNESS_DIR}/lib"
SESSION_ID="test-model-call-$$"
DISPATCH_FILE="${HARNESS_DIR}/run/test-model-call-${SESSION_ID}.md"
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
# Model Call Runtime Test

Read and execute this dispatch.
EOF
cat > "${HARNESS_DIR}/run/pane-env/_test-model-pane.json" <<'JSON'
{
  "pane": "%test-model-pane",
  "persona": "builder",
  "auth_source": "anthropic",
  "model_flag": "--model sonnet",
  "claude_bin": "/tmp/claude"
}
JSON

echo "T1: record request/succeeded events"
python3 "${LIB_DIR}/model_call_runtime.py" request --session-id "$SESSION_ID" --pane "%test-model-pane" --dispatch-id "dispatch-1" --instruction-file "$DISPATCH_FILE" --json >/tmp/model-call-request.$$.json
python3 "${LIB_DIR}/model_call_runtime.py" succeeded --session-id "$SESSION_ID" --pane "%test-model-pane" --dispatch-id "dispatch-1" --instruction-file "$DISPATCH_FILE" --status "tmux_submit_accepted" --tries 1 --json >/tmp/model-call-success.$$.json
OUT=$(python3 - "$SESSION_ID" <<'PY'
import sys
sys.path.insert(0, "~/.solar/harness/lib")
from session_log import SessionLog
events = SessionLog(sys.argv[1]).all_events()
types = [e["type"] for e in events]
payload = events[0]["payload"]
print(types)
print(payload["private_reasoning_visible"])
print(payload["model"]["model_flag"])
print(bool(payload.get("instruction_sha256")))
PY
)
assert_contains "request event" "$OUT" "model_call_requested"
assert_contains "succeeded event" "$OUT" "model_call_succeeded"
assert_contains "private reasoning false" "$OUT" "False"
assert_contains "model flag captured" "$OUT" "--model sonnet"
assert_contains "instruction digest captured" "$OUT" "True"

echo "T2: doctor sees no pending model call"
DOCTOR=$(python3 "${LIB_DIR}/runtime_doctor.py" "$SESSION_ID" --json || true)
assert_contains "doctor model runtime ok" "$DOCTOR" '"model_call_runtime"'
assert_contains "doctor pending zero" "$DOCTOR" '"pending_dispatch_ids": []'

echo "T3: failed call is terminal"
python3 "${LIB_DIR}/model_call_runtime.py" request --session-id "$SESSION_ID" --pane "%test-model-pane" --dispatch-id "dispatch-2" --instruction-file "$DISPATCH_FILE" >/dev/null
python3 "${LIB_DIR}/model_call_runtime.py" failed --session-id "$SESSION_ID" --pane "%test-model-pane" --dispatch-id "dispatch-2" --instruction-file "$DISPATCH_FILE" --error "capture_verify_failed" >/dev/null
DOCTOR2=$(python3 "${LIB_DIR}/runtime_doctor.py" "$SESSION_ID" --json || true)
assert_contains "doctor failed count" "$DOCTOR2" '"failed": 1'
assert_contains "doctor still no pending" "$DOCTOR2" '"pending_dispatch_ids": []'

rm -f /tmp/model-call-request.$$.json /tmp/model-call-success.$$.json
echo ""
echo "=== Model Call Runtime: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]]
