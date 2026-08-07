#!/usr/bin/env bash
# test-long-running-observability.sh — long-running runtime observability coverage
set -euo pipefail

HARNESS_DIR="${HOME}/.solar/harness"
LIB_DIR="${HARNESS_DIR}/lib"
SID="test-long-running-observability-$$"
DISPATCH="${HARNESS_DIR}/run/${SID}.dispatch.md"
PASS=0
FAIL=0

cleanup() {
  rm -rf "${HARNESS_DIR}/sessions/${SID}"
  rm -f "$DISPATCH" "$DISPATCH.runtime-context.json"
}
trap cleanup EXIT

ok() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  if [[ "$haystack" == *"$needle"* ]]; then ok "$label"; else fail "$label"; fi
}

mkdir -p "${HARNESS_DIR}/run"
cat > "$DISPATCH" <<'EOF'
# Long-running Dispatch

Implement a tiny safe task and report evidence.
EOF

echo "T1: runtime context projection is injected and recorded"
python3 "${LIB_DIR}/runtime_context_inject.py" "$DISPATCH" --session-id "$SID" --pane "solar-harness:0.2" --dispatch-id "dispatch-obs-1" --json >/tmp/ctx-inject.$$.json
OUT=$(cat "$DISPATCH")
assert_contains "context block injected" "$OUT" "<solar-runtime-context>"
EVENTS=$(python3 "${LIB_DIR}/session_tools.py" replay "$SID" --json)
assert_contains "context event recorded" "$EVENTS" '"context_injected": 1'

echo "T2: Claude hook tool events enter session log"
printf '{"tool_name":"Bash","tool_input":{"command":"echo token=supersecret123456789"}}' \
  | SOLAR_RUNTIME_SESSION_ID="$SID" TMUX_PANE="%test" SOLAR_PERSONA="builder" \
    python3 "${LIB_DIR}/claude_hook_event_bridge.py" pre-tool --json >/tmp/hook-pre.$$.json
printf '{"tool_name":"Bash","status":"ok","tool_response":"token=supersecret123456789"}' \
  | SOLAR_RUNTIME_SESSION_ID="$SID" TMUX_PANE="%test" SOLAR_PERSONA="builder" \
    python3 "${LIB_DIR}/claude_hook_event_bridge.py" post-tool --json >/tmp/hook-post.$$.json
EVAL=$(python3 "${LIB_DIR}/session_tools.py" evaluate "$SID" --json || true)
assert_contains "process audit exists" "$EVAL" '"process_audit"'
assert_contains "tool requested counted" "$EVAL" '"requested": 1'
assert_contains "tool terminal counted" "$EVAL" '"terminal": 1'
assert_contains "tool observable true" "$EVAL" '"observable": true'
if [[ "$EVAL" == *"supersecret"* ]]; then
  fail "hook payload redacted"
else
  ok "hook payload redacted"
fi

echo "T3: pane launcher sanitized settings include harness hook bridge"
SANITIZED="${HARNESS_DIR}/run/claude-settings/test-observability-builder.json"
python3 - "${HOME}/.claude/settings.json" "$SANITIZED" "$HARNESS_DIR" <<'PY'
import json, sys
from pathlib import Path
src = Path(sys.argv[1])
out = Path(sys.argv[2])
harness_dir = Path(sys.argv[3])
data = json.loads(src.read_text(encoding="utf-8")) if src.exists() else {}
data.pop("env", None)
hooks = data.setdefault("hooks", {})
for event_name, phase in (("PreToolUse", "pre-tool"), ("PostToolUse", "post-tool")):
    entries = hooks.setdefault(event_name, [])
    command = f"python3 {harness_dir}/lib/claude_hook_event_bridge.py {phase}"
    if not any(hook.get("command") == command for entry in entries for hook in (entry.get("hooks") or [])):
        entries.append({"matcher": "", "hooks": [{"type": "command", "command": command}]})
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
SETTINGS=$(cat "$SANITIZED")
assert_contains "pre hook bridge configured" "$SETTINGS" "claude_hook_event_bridge.py pre-tool"
assert_contains "post hook bridge configured" "$SETTINGS" "claude_hook_event_bridge.py post-tool"
if [[ "$SETTINGS" == *"ANTHROPIC_BASE_URL"* ]]; then
  fail "settings env stripped"
else
  ok "settings env stripped"
fi

rm -f /tmp/ctx-inject.$$.json /tmp/hook-pre.$$.json /tmp/hook-post.$$.json "$SANITIZED"
echo ""
echo "=== Long-running Observability: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]]
