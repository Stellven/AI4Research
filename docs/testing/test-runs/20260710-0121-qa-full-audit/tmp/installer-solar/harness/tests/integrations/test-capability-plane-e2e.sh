#!/usr/bin/env bash
# test-capability-plane-e2e.sh — prove external capabilities are usable by Solar-Harness dispatch.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
BIN="$HARNESS_DIR/solar-harness.sh"
SKILLS_PY="$HARNESS_DIR/lib/solar_skills.py"
HEALTH_PY="$HARNESS_DIR/lib/external-integrations-health.py"
PLUGIN_PY="$HARNESS_DIR/lib/plugin_loader.py"
MIRAGE_PY="$HARNESS_DIR/lib/solar_mirage.py"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

json_assert() {
  local label="$1" expr="$2" input="$3"
  if JSON_INPUT="$input" python3 - "$expr" >/dev/null 2>&1 <<'PY'
import json
import os
import sys
expr = sys.argv[1]
data = json.loads(os.environ["JSON_INPUT"])
assert eval(expr, {}, {"data": data})
PY
  then
    pass "$label"
  else
    fail "$label"
  fi
}

has_text() {
  local label="$1" needle="$2" file="$3"
  if grep -qF "$needle" "$file" 2>/dev/null; then
    pass "$label"
  else
    fail "$label"
  fi
}

echo "A1 — plugin manifests and capability registry"
PLUGIN_VALIDATE="$(python3 "$PLUGIN_PY" validate --json 2>/dev/null || true)"
json_assert "plugin validate ok" 'data.get("ok") is True' "$PLUGIN_VALIDATE"
for plugin in owl markitdown agency-agents; do
  if JSON_INPUT="$PLUGIN_VALIDATE" python3 - "$plugin" >/dev/null 2>&1 <<'PY'
import json, os, sys
plugin = sys.argv[1]
data = json.loads(os.environ["JSON_INPUT"])
assert any(item.get("id") == plugin and item.get("valid") for item in data.get("results", []))
PY
  then
    pass "plugin $plugin valid"
  else
    fail "plugin $plugin valid"
  fi
done

bash "$BIN" integrations sync-caps --json >/dev/null 2>&1 || true
CAPS="$(bash "$BIN" integrations capabilities list --json 2>/dev/null || true)"
for cap in multi_agent.research document.convert persona.agent; do
  if JSON_INPUT="$CAPS" python3 - "$cap" >/dev/null 2>&1 <<'PY'
import json, os, sys
cap = sys.argv[1]
data = json.loads(os.environ["JSON_INPUT"])
assert any(item.get("capability") == cap and item.get("status") == "active" for item in data.get("capabilities", []))
PY
  then
    pass "capability $cap registered"
  else
    fail "capability $cap registered"
  fi
done

echo ""
echo "A2 — external integration health is not stale warn table"
HEALTH="$(python3 "$HEALTH_PY" --json --refresh 2>/dev/null || true)"
for name in "Google Drive mount" "camel-ai/owl" "Microsoft MarkItDown MCP" "agency-agents persona"; do
  if JSON_INPUT="$HEALTH" python3 - "$name" >/dev/null 2>&1 <<'PY'
import json, os, sys
name = sys.argv[1]
data = json.loads(os.environ["JSON_INPUT"])
item = next((x for x in data.get("integrations", []) if x.get("name") == name), None)
assert item is not None, name
assert item.get("status") in {"ok", "warn"}, item
assert item.get("health", {}).get("basic_available") == "ok", item
PY
  then
    pass "$name basic_available"
  else
    fail "$name basic_available"
  fi
done

if JSON_INPUT="$HEALTH" python3 - >/dev/null 2>&1 <<'PY'
import json, os
data = json.loads(os.environ["JSON_INPUT"])
drive = next(x for x in data["integrations"] if x["name"] == "Google Drive mount")
assert drive["evidence"].get("state") == "local_mount", drive
assert drive["configured"] and drive["running"], drive
PY
then
  pass "Google Drive uses local macOS mount"
else
  fail "Google Drive uses local macOS mount"
fi

echo ""
echo "A3 — Mirage /drive is reachable through Solar VFS"
if python3 "$MIRAGE_PY" doctor --json >/tmp/solar-mirage-doctor-$$.json 2>/dev/null; then
  pass "mirage doctor exits 0"
else
  fail "mirage doctor exits 0"
fi
if python3 "$MIRAGE_PY" exec -- 'ls /drive' >/tmp/solar-drive-ls-$$.txt 2>/dev/null; then
  pass "mirage exec ls /drive"
else
  fail "mirage exec ls /drive"
fi
rm -f /tmp/solar-mirage-doctor-$$.json /tmp/solar-drive-ls-$$.txt

echo ""
echo "A4 — dispatch auto-inject selects all requested capabilities"
DISPATCH="$TMPDIR_TEST/capability-dispatch.md"
cat > "$DISPATCH" <<'EOF'
# Capability Dispatch Smoke

需要浏览 localhost 页面并截图做 browser QA。
需要系统化 debug 一个 hook_failed 超时，并用 repair 方式修复。
需要 OWL / camel-ai 做 multi-agent research。
需要把 PDF/DOCX 转成 Markdown，再进 Obsidian/QMD。
需要选择 specialist persona / agency agent 辅助拆解。
EOF
python3 "$SKILLS_PY" inject "$DISPATCH" >/dev/null
has_text "capability block injected" "<solar-capability-context>" "$DISPATCH"
has_text "gstack selected" "gstack" "$DISPATCH"
has_text "Superpowers selected" "Superpowers" "$DISPATCH"
has_text "ATLAS selected" "ATLAS" "$DISPATCH"
has_text "OWL selected" "OWL" "$DISPATCH"
has_text "MarkItDown selected" "MarkItDown" "$DISPATCH"
has_text "agency-agents selected" "agency-agents" "$DISPATCH"

echo ""
echo "A5 — two four-pane topology can receive capability context"
DOCTOR="$(bash "$BIN" skills doctor --json 2>/dev/null || true)"
json_assert "skills doctor has builder config" 'any(p.get("pane") == "builder" for p in data.get("panes", []))' "$DOCTOR"
json_assert "skills doctor has lab-builder config" 'any(p.get("pane") == "lab-builder" for p in data.get("panes", []))' "$DOCTOR"

if command -v tmux >/dev/null 2>&1 && tmux has-session -t solar-harness 2>/dev/null && tmux has-session -t solar-harness-lab 2>/dev/null; then
  MAIN_COUNT="$(tmux list-panes -t solar-harness:0 2>/dev/null | wc -l | tr -d ' ')"
  LAB_COUNT="$(tmux list-panes -t solar-harness-lab:0 2>/dev/null | wc -l | tr -d ' ')"
  [[ "$MAIN_COUNT" -ge 4 ]] && pass "main four-pane session live" || fail "main four-pane session live"
  [[ "$LAB_COUNT" -ge 4 ]] && pass "lab four-pane session live" || fail "lab four-pane session live"
else
  pass "tmux live topology skipped: sessions not running in this test context"
fi

echo ""
echo "=== Capability Plane E2E: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]]
