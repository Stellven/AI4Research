#!/usr/bin/env bash
# Static regression: PM/Planner prompts require HTML artifacts without replacing canonical gates.
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
COORD="$HARNESS_DIR_REAL/coordinator.sh"
PM="$HARNESS_DIR_REAL/personas/pm.md"
PLANNER="$HARNESS_DIR_REAL/personas/planner.md"
GUARD="$HARNESS_DIR_REAL/lib/workflow_guard.py"
HELPER="$HARNESS_DIR_REAL/lib/html_artifact.py"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "PASS: $*"; }

bash -n "$COORD" || fail "coordinator syntax"
python3 -m py_compile "$HELPER" "$GUARD" || fail "python helper/guard syntax"
ok "syntax checks pass"

grep -Fq '${sid}.prd.html' "$COORD" || fail "coordinator PM dispatch missing prd.html"
grep -Fq '${sid}.design.html' "$COORD" || fail "coordinator Planner dispatch missing design.html"
grep -Fq '${sid}.planning.html' "$COORD" || fail "coordinator Planner dispatch missing planning.html"
grep -Fq 'html_artifact.py register --sid ${sid} --kind prd_html' "$COORD" || fail "coordinator missing prd_html helper call"
grep -Fq 'html_artifact.py register --sid ${sid} --kind design_html' "$COORD" || fail "coordinator missing design_html helper call"
grep -Fq 'html_artifact.py register --sid ${sid} --kind planning_html' "$COORD" || fail "coordinator missing planning_html helper call"
ok "coordinator prompts require HTML helper registration"

grep -Fq "<sprint-id>.prd.html" "$PM" || fail "PM persona missing prd.html"
grep -Fq "<sprint-id>.design.html" "$PLANNER" || fail "Planner persona missing design.html"
grep -Fq "<sprint-id>.planning.html" "$PLANNER" || fail "Planner persona missing planning.html"
grep -Fq "不能替代 PRD" "$PM" || fail "PM persona must preserve PRD gate"
grep -Fq "不替代 plan/task_graph" "$PLANNER" || fail "Planner persona must preserve plan/task_graph gate"
ok "personas document HTML as human artifact"

python3 - "$GUARD" <<'PY' || fail "workflow_guard must expose HTML artifacts but not gate on them"
from pathlib import Path
s = Path(__import__("sys").argv[1]).read_text(encoding="utf-8")
assert "prd_html" in s
assert "design_html" in s
assert "planning_html" in s
planner_ready = s.index('planner_ready = artifacts["prd"] and artifacts["design"] and artifacts["plan"] and artifacts["task_graph"]')
assert "prd_html" not in s[planner_ready:planner_ready + 160]
assert "design_html" not in s[planner_ready:planner_ready + 160]
assert "planning_html" not in s[planner_ready:planner_ready + 160]
PY
ok "workflow_guard leaves HTML out of route gate"

echo "PASS"
