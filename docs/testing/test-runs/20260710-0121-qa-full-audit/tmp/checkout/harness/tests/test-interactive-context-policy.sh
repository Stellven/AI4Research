#!/usr/bin/env bash
# Verify interactive panes receive mandatory unified knowledge-context policy.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

ok() { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*" >&2; FAIL=$((FAIL+1)); }
check() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == *"$expected"* ]]; then ok "$label"; else fail "$label"; fi
}

bash -n "$HARNESS_DIR/lib/persona-config.sh" && ok "persona-config syntax" || fail "persona-config syntax"
bash -n "$HARNESS_DIR/pane-launcher.sh" && ok "pane-launcher syntax" || fail "pane-launcher syntax"

POLICY=$(bash -lc "source '$HARNESS_DIR/lib/persona-config.sh'; inject_runtime_policy builder")
check "policy includes context inject command" "$POLICY" "solar-harness context inject --query"
check "policy names Mirage" "$POLICY" "Mirage VFS"
check "policy names QMD" "$POLICY" "QMD solar-wiki"
check "policy forbids sqlite-first" "$POLICY" "不得把 \`sqlite3 ~/.solar/solar.db"
check "policy requires visibility line" "$POLICY" "Knowledge Context: solar-harness context inject used"
check "policy includes Definition of Done gate" "$POLICY" "Definition of Done · Mandatory Completion Gate"
check "policy requires evidence before success" "$POLICY" "没有证据，不许报喜"
check "policy requires structured closeout" "$POLICY" "已完成 · 已验证 · 未验证 · 风险 · 后续待办"

if grep -q '_runtime_policy=$(inject_runtime_policy "$PERSONA")' "$HARNESS_DIR/pane-launcher.sh" \
  && grep -q '"${CLAUDE_CMD\[@\]}" --append-system-prompt "\$_runtime_policy' "$HARNESS_DIR/pane-launcher.sh"; then
  ok "pane-launcher prepends runtime policy in append-system-prompt"
else
  fail "pane-launcher does not append runtime policy"
fi

if grep -q 'CLAUDE_CMD+=(--setting-sources "$SOLAR_CLAUDE_SETTING_SOURCES" --settings "$CLAUDE_SETTINGS_FILE")' "$HARNESS_DIR/pane-launcher.sh"; then
  ok "pane-launcher passes Claude settings path as one argv"
else
  fail "pane-launcher may split Claude settings path"
fi

if grep -q 'check_for_update_on_startup=false' "$HARNESS_DIR/pane-launcher.sh" \
  && grep -q 'SOLAR_CODEX_CHECK_FOR_UPDATE_ON_STARTUP' "$HARNESS_DIR/pane-launcher.sh"; then
  ok "Codex panes disable startup update prompts by default"
else
  fail "Codex pane launcher can still show startup update prompts"
fi

if grep -q '_runtime_policy=$(inject_runtime_policy "$PERSONA")' "$HARNESS_DIR/start-incarnation.sh" \
  && grep -q '"${CLAUDE_CMD\[@\]}" --append-system-prompt "\$_runtime_policy' "$HARNESS_DIR/start-incarnation.sh"; then
  ok "start-incarnation prepends runtime policy in append-system-prompt"
else
  fail "start-incarnation does not append runtime policy"
fi

if grep -q 'CLAUDE_CMD+=(--setting-sources "$SOLAR_CLAUDE_SETTING_SOURCES" --settings "$CLAUDE_SETTINGS_FILE")' "$HARNESS_DIR/start-incarnation.sh"; then
  ok "start-incarnation passes Claude settings path as one argv"
else
  fail "start-incarnation may split Claude settings path"
fi

check "PM persona has zero-law context rule" "$(sed -n '1,40p' "$HARNESS_DIR/personas/pm.md")" "第零铁律：先查 Solar Unified Context"
check "Planner persona has zero-law context rule" "$(sed -n '1,40p' "$HARNESS_DIR/personas/planner.md")" "第零铁律：先查 Solar Unified Context"

echo "PROBES_PASSED=$PASS PROBES_FAILED=$FAIL"
[[ "$FAIL" -eq 0 ]]
