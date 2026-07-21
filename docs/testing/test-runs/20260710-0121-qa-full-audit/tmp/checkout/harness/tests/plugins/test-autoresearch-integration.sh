#!/usr/bin/env bash
# test-autoresearch-integration.sh — smallnest/autoresearch safe local-issue integration.
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
PASS=0
FAIL=0

ok() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "A1 — modules compile"
python3 -m py_compile \
  "$HARNESS_DIR/lib/autoresearch_adapter.py" \
  "$HARNESS_DIR/lib/autoresearch_pane_optimizer.py" \
  "$HARNESS_DIR/lib/external-integrations-health.py" \
  "$HARNESS_DIR/lib/intent_engine_adapter.py" \
  "$HARNESS_DIR/lib/capability_inference.py" \
  "$HARNESS_DIR/lib/solar_skills.py" \
  && ok "autoresearch modules compile" || fail "autoresearch modules compile"
bash -n "$HARNESS_DIR/coordinator.sh" \
  && grep -q "build_autoresearch_optimizer_context" "$HARNESS_DIR/coordinator.sh" \
  && ok "coordinator injects autoresearch optimizer" \
  || fail "coordinator injects autoresearch optimizer"

echo "A2 — status is readable even before vendor"
OUT=$("$HARNESS_DIR/solar-harness.sh" integrations autoresearch-status --json)
python3 - "$OUT" <<'PY' && ok "autoresearch status schema" || fail "autoresearch status schema"
import json, sys
d=json.loads(sys.argv[1])
assert d["source"]["repo"] == "https://github.com/smallnest/autoresearch.git"
assert d["mode"] == "pane_optimizer_advisor_and_explicit_local_issue_runner"
assert d["safety"]["default_execution"] == "dry_run"
assert d["safety"]["execute_requires_flag"] == "--execute"
assert d["safety"]["replaces_builder"] is False
assert d["safety"]["pane_optimizer_advisor"] is True
PY

echo "A3 — dry-run local issue creates controlled issue file and does not execute"
TMP_PROJECT=$(mktemp -d /tmp/solar-autoresearch-project.XXXXXX)
git -C "$TMP_PROJECT" init -q
OUT=$("$HARNESS_DIR/solar-harness.sh" integrations autoresearch-run-local \
  --project "$TMP_PROJECT" \
  --issue-title "Improve test harness" \
  --issue-body "Add a tiny deterministic check." \
  --max-iterations 2 \
  --json || true)
python3 - "$OUT" "$TMP_PROJECT" <<'PY' && ok "autoresearch dry-run issue plan" || fail "autoresearch dry-run issue plan"
import json, sys
from pathlib import Path
d=json.loads(sys.argv[1])
project=str(Path(sys.argv[2]).resolve())
if d.get("reason") == "autoresearch_run_sh_missing":
    assert d["autoresearch_dir"].endswith("vendor/autoresearch")
else:
    assert d["ok"] is True
    assert d["executed"] is False
    assert d["mode"] == "dry_run"
    assert str(Path(d["created_issue"]).resolve()).startswith(project)
    assert d["command"][-2] == str(d["issue_number"])
    assert d["command"][-1] == "2"
    assert any(str(item).startswith("--issues-dir=") for item in d["command"])
    assert d["environment"]["PASSING_SCORE"] == "80"
PY
rm -rf "$TMP_PROJECT"

echo "A4 — plugin manifest validates and capability sync sees provider"
OUT=$("$HARNESS_DIR/solar-harness.sh" integrations validate --id autoresearch --json)
python3 - "$OUT" <<'PY' && ok "autoresearch manifest valid" || fail "autoresearch manifest valid"
import json, sys
d=json.loads(sys.argv[1])
assert d["ok"] is True
assert d["results"][0]["valid"] is True
PY
"$HARNESS_DIR/solar-harness.sh" integrations sync-caps --json >/tmp/solar-autoresearch-sync.json
OUT=$("$HARNESS_DIR/solar-harness.sh" integrations capabilities query autoresearch.issue_loop --json)
python3 - "$OUT" <<'PY' && ok "autoresearch capability found" || fail "autoresearch capability found"
import json, sys
d=json.loads(sys.argv[1])
assert d["found"] is True
assert d["providers"][0]["provider"] == "autoresearch"
PY

echo "A5 — planner/builder dispatch can see autoresearch but does not auto-execute"
intent="$("$HARNESS_DIR/solar-harness.sh" intent match "Use autoresearch issue loop for this local issue with score gate" 2>/dev/null)"
grep -q "autoresearch" <<<"$intent" && ok "autoresearch intent route" || fail "autoresearch intent route"
plain_intent="$("$HARNESS_DIR/solar-harness.sh" intent match "请写一段普通总结，不要运行本地问题循环" 2>/dev/null)"
if grep -q "autoresearch" <<<"$plain_intent"; then
  fail "negative intent should not route to autoresearch"
else
  ok "negative intent avoids autoresearch"
fi

TMP_DISPATCH="$(mktemp -t solar-autoresearch-dispatch).md"
cat > "$TMP_DISPATCH" <<'EOF'
# Planner Handoff

Implement the local issue through an explicit autoresearch issue-loop.
Use score-gated iterations, but do not execute without user approval.
EOF
"$HARNESS_DIR/solar-harness.sh" skills inject "$TMP_DISPATCH" >/dev/null
grep -q "Autoresearch (autoresearch.pane_optimizer" "$TMP_DISPATCH" \
  && grep -q "不得自动运行" "$TMP_DISPATCH" \
  && ok "Autoresearch capability injected with stop rules" \
  || fail "Autoresearch capability injected with stop rules"
python3 - "$TMP_DISPATCH.intent.json" <<'PY' && ok "autoresearch telemetry visible" || fail "autoresearch telemetry visible"
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
assert any(m.get("source") == "autoresearch" for m in d["intent"]["matches"]), d["intent"]
assert any(c.get("provider") == "Autoresearch" for c in d["capabilities"]), d["capabilities"]
assert d["worker_visible"]["solar_intent_context"] is True, d["worker_visible"]
assert d["worker_visible"]["solar_capability_context"] is True, d["worker_visible"]
PY
OUT=$(python3 "$HARNESS_DIR/lib/capability_inference.py" infer --text "Create a local issue and run an autoresearch score gate implementation loop")
python3 - "$OUT" <<'PY' && ok "capability inference routes autoresearch" || fail "capability inference routes autoresearch"
import json, sys
d=json.loads(sys.argv[1])
matches=d.get("matches", [])
assert any(m.get("provider") == "Autoresearch" and "autoresearch.issue_loop" in m.get("capabilities", []) for m in matches), matches
PY

echo "A6 — pane optimizer renders role-specific advisor blocks"
for role in "产品经理" "规划者" "建设者" "审判官"; do
  OUT=$(python3 "$HARNESS_DIR/lib/autoresearch_pane_optimizer.py" --sid sprint-test --role "$role" --task "需要提升 pane 执行质量、验收和 score gate" --format json)
  python3 - "$OUT" <<'PY' || fail "pane optimizer json for role"
import json, sys
d=json.loads(sys.argv[1])
assert d["recommended"] is True, d
assert d["execution_policy"]["replaces_builder"] is False, d
assert "autoresearch.pane_optimizer" in d["capabilities"], d
PY
done
ok "pane optimizer recommends for all main panes"
OUT=$(python3 "$HARNESS_DIR/lib/autoresearch_pane_optimizer.py" --sid sprint-test --role "规划者" --task "基于 PRD 产出 DAG 和 write_scope" --format markdown)
grep -q "Autoresearch Pane Optimizer" <<<"$OUT" \
  && grep -q "不替代" <<<"$OUT" \
  && ok "pane optimizer markdown is advisor-only" \
  || fail "pane optimizer markdown is advisor-only"

TMP_TELEMETRY=$(mktemp -d /tmp/solar-autoresearch-telemetry.XXXXXX)
cat > "$TMP_TELEMETRY/status.json" <<'EOF'
{
  "status": "failed_review",
  "phase": "eval_failed",
  "round": 2,
  "target_role": "builder"
}
EOF
cat > "$TMP_TELEMETRY/eval.json" <<'EOF'
{
  "verdict": "FAIL",
  "failed_conditions": [
    {"id": "missing_evidence", "fix_hint": "Bind each claim to source evidence."},
    {"id": "weak_stop_rule", "fix_hint": "Add measurable stop rules."}
  ],
  "errors": [
    {"cond": "regression", "message": "Quality gate failed after review."}
  ]
}
EOF
OUT=$(python3 "$HARNESS_DIR/lib/autoresearch_pane_optimizer.py" \
  --sid sprint-test \
  --role "建设者" \
  --task "Round N+1 修复/继续实现" \
  --status-file "$TMP_TELEMETRY/status.json" \
  --eval-json "$TMP_TELEMETRY/eval.json" \
  --format json)
python3 - "$OUT" <<'PY' && ok "pane optimizer uses eval/status telemetry" || fail "pane optimizer uses eval/status telemetry"
import json, sys
d=json.loads(sys.argv[1])
assert d["recommended"] is True, d
assert d["trigger_level"] == "strong", d
assert d["telemetry"]["status"] == "failed_review", d
assert d["telemetry"]["phase"] == "eval_failed", d
assert d["telemetry"]["round"] == 2, d
assert d["telemetry"]["eval_verdict"] == "FAIL", d
assert "missing_evidence" in d["telemetry"]["failed_conditions"], d
assert d["execution_policy"]["replaces_builder"] is False, d
assert "repair_round_delta" in d["quality_metrics"]["must_measure"], d
PY
OUT=$(python3 "$HARNESS_DIR/lib/autoresearch_pane_optimizer.py" \
  --sid sprint-test \
  --role "建设者" \
  --task "Round N+1 修复/继续实现" \
  --status-file "$TMP_TELEMETRY/status.json" \
  --eval-json "$TMP_TELEMETRY/eval.json" \
  --record-status \
  --format json)
python3 - "$OUT" "$TMP_TELEMETRY/status.json" <<'PY' && ok "pane optimizer records status artifact" || fail "pane optimizer records status artifact"
import json, sys
payload=json.loads(sys.argv[1])
status=json.load(open(sys.argv[2], encoding="utf-8"))
assert payload["record_status"]["ok"] is True, payload
artifact=status["artifacts"]["autoresearch_optimizer"]
assert artifact["trigger_level"] == "strong", artifact
assert artifact["telemetry"]["eval_verdict"] == "FAIL", artifact
assert "missing_evidence" in artifact["telemetry"]["failed_conditions"], artifact
assert artifact["execution_policy"]["replaces_builder"] is False, artifact
assert any(h.get("event") == "autoresearch_optimizer_recorded" for h in status["history"]), status
PY
OUT=$(python3 "$HARNESS_DIR/lib/autoresearch_pane_optimizer.py" \
  --sid sprint-test \
  --role "建设者" \
  --task "Round N+1 修复/继续实现" \
  --status-file "$TMP_TELEMETRY/status.json" \
  --eval-json "$TMP_TELEMETRY/eval.json" \
  --format markdown)
grep -q "Telemetry trigger" <<<"$OUT" \
  && grep -q "missing_evidence" <<<"$OUT" \
  && grep -q "repair_round_delta" <<<"$OUT" \
  && ok "pane optimizer markdown exposes telemetry trigger" \
  || fail "pane optimizer markdown exposes telemetry trigger"
rm -rf "$TMP_TELEMETRY"

echo "A7 — unified health exposes autoresearch"
OUT=$("$HARNESS_DIR/solar-harness.sh" integrations status --json --refresh)
python3 - "$OUT" <<'PY' && ok "autoresearch unified health present" || fail "autoresearch unified health present"
import json, sys
d=json.loads(sys.argv[1])
items=[x for x in d.get("integrations", []) if "autoresearch" in x.get("name", "").lower()]
assert items, "autoresearch integration missing"
ev=items[0].get("evidence", {})
assert ev.get("dispatch_capability") == "autoresearch.pane_optimizer"
assert ev.get("issue_loop_capability") == "autoresearch.issue_loop"
assert ev.get("execute_requires") == "--execute"
PY

echo ""
echo "=== Autoresearch Integration Test: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]]
