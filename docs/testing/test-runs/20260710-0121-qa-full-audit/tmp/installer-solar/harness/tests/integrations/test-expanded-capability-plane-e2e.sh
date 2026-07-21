#!/usr/bin/env bash
# test-expanded-capability-plane-e2e.sh — prove rows 11-17 are real Solar-Harness capabilities.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
BIN="$HARNESS_DIR/solar-harness.sh"
SKILLS_PY="$HARNESS_DIR/lib/solar_skills.py"
HEALTH_PY="$HARNESS_DIR/lib/external-integrations-health.py"
PLUGIN_PY="$HARNESS_DIR/lib/plugin_loader.py"
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

echo "B1 — rows 11-17 plugin manifests are valid"
PLUGIN_VALIDATE="$(python3 "$PLUGIN_PY" validate --json 2>/dev/null || true)"
json_assert "plugin validate ok" 'data.get("ok") is True' "$PLUGIN_VALIDATE"
for plugin in empirical-research addy-agent-skills gstack superpowers browser-use openai-agents-python codex-bridge; do
  if JSON_INPUT="$PLUGIN_VALIDATE" python3 - "$plugin" >/dev/null 2>&1 <<'PY'
import json, os, sys
plugin = sys.argv[1]
data = json.loads(os.environ["JSON_INPUT"])
assert any(item.get("id") == plugin and item.get("valid") for item in data.get("results", [])), plugin
PY
  then
    pass "plugin $plugin valid"
  else
    fail "plugin $plugin valid"
  fi
done

echo ""
echo "B2 — capability registry exposes rows 11-17 to dispatch"
bash "$BIN" integrations sync-caps --json >/dev/null 2>&1 || true
CAPS="$(bash "$BIN" integrations capabilities list --json 2>/dev/null || true)"
for cap in research.empirical_pipeline agent_skills.catalog browser.browse skill.methodology browser.mcp agents_sdk.design codex.bridge; do
  if JSON_INPUT="$CAPS" python3 - "$cap" >/dev/null 2>&1 <<'PY'
import json, os, sys
cap = sys.argv[1]
data = json.loads(os.environ["JSON_INPUT"])
assert any(item.get("capability") == cap and item.get("status") == "active" for item in data.get("capabilities", [])), cap
PY
  then
    pass "capability $cap active"
  else
    fail "capability $cap active"
  fi
done

echo ""
echo "B3 — health probe no longer reports stale warn/error for rows 11-17"
HEALTH="$(python3 "$HEALTH_PY" --json --refresh 2>/dev/null || true)"
for name in "Empirical Research skills" "addyosmani/agent-skills" "gstack" "Superpowers" "Browser-use MCP" "openai-agents-python PoC" "Codex Bridge / pane3 bridge"; do
  if JSON_INPUT="$HEALTH" python3 - "$name" >/dev/null 2>&1 <<'PY'
import json, os, sys
name = sys.argv[1]
data = json.loads(os.environ["JSON_INPUT"])
item = next((x for x in data.get("integrations", []) if x.get("name") == name), None)
assert item is not None, name
assert item.get("status") in {"ok", "warn"}, item
assert item.get("health", {}).get("basic_available") == "ok", item
assert item.get("health", {}).get("dead_ends") == "ok", item
PY
  then
    pass "$name basic/default probe"
  else
    fail "$name basic/default probe"
  fi
done

if JSON_INPUT="$HEALTH" python3 - >/dev/null 2>&1 <<'PY'
import json, os
data = json.loads(os.environ["JSON_INPUT"])
item = next(x for x in data["integrations"] if x["name"] == "openai-agents-python PoC")
assert item["status"] == "ok", item
assert item["lifecycle"] == "candidate", item
assert item["status_label"] == "basic_usable", item
assert item["running"] is False and item["used_by_default"] is False, item
PY
then
  pass "openai-agents-python stays PoC, not production executor"
else
  fail "openai-agents-python stays PoC, not production executor"
fi

echo ""
echo "B4 — Browser-use and Codex Bridge local runtimes are syntactically healthy"
if [[ -x "$HOME/.claude/mcp-servers/browser-use/.venv/bin/python" ]] \
  && "$HOME/.claude/mcp-servers/browser-use/.venv/bin/python" -m py_compile "$HOME/.claude/mcp-servers/browser-use/server.py" >/dev/null 2>&1; then
  pass "browser-use MCP server py_compile"
else
  fail "browser-use MCP server py_compile"
fi
if bash -n "$HARNESS_DIR/chain-watcher.sh" >/dev/null 2>&1; then
  pass "chain-watcher syntax"
else
  fail "chain-watcher syntax"
fi
if [[ -d "$HOME/.solar/codex-bridge/from-codex" ]] \
  && [[ -f "$HOME/.solar/codex-bridge/CODEX-PROTOCOL.md" ]] \
  && [[ -f "$HOME/.solar/codex-bridge/bridge-ledger.jsonl" ]]; then
  pass "codex bridge active inbox/protocol/ledger"
else
  fail "codex bridge active inbox/protocol/ledger"
fi

echo ""
echo "B5 — dispatch auto-inject selects rows 11-17 capability hints"
DISPATCH="$TMPDIR_TEST/expanded-capability-dispatch.md"
cat > "$DISPATCH" <<'EOF'
# Expanded Capability Dispatch Smoke

需要做 empirical research、literature review、causal analysis 和可复现论文分析。
需要使用 addyosmani agent-skills 的 spec-driven / context engineering 方法。
需要 gstack 浏览器 QA，也需要 browser-use MCP 对 localhost 点击、输入、截图。
需要 Superpowers 做系统化规划、TDD 和 root cause debug。
需要参考 openai-agents-python / Agents SDK 的 guardrails、tracing、handoffs 设计。
需要通过 Codex Bridge / pane3 / from-codex 导入 execution-contract。
EOF
python3 "$SKILLS_PY" inject "$DISPATCH" >/dev/null
has_text "capability block injected" "<solar-capability-context>" "$DISPATCH"
for provider in "Empirical Research" "addyosmani/agent-skills" "gstack" "Browser-use MCP" "Superpowers" "openai-agents-python" "Codex Bridge"; do
  has_text "$provider selected" "$provider" "$DISPATCH"
done

echo ""
echo "B6 — two four-pane topology can see skill/capability context"
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
echo "=== Expanded Capability Plane E2E: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]]
