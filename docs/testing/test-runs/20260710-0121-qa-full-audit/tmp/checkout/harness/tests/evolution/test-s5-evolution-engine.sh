#!/usr/bin/env bash
# S5 Evolution Engine regression tests.
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
BIN="${BIN:-$HOME/.solar/bin/solar-harness}"
PASS=0
FAIL=0

ok() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }
check_contains() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == *"$expected"* ]]; then ok "$label"; else fail "$label (expected: $expected)"; fi
}

cd "$HARNESS_DIR"

echo "T1: modules compile"
python3 -m py_compile lib/failure_miner.py lib/eval_runner.py lib/evolution_engine.py lib/symphony/status-server.py \
  && ok "evolution modules compile" || fail "evolution modules compile"

echo "T2: failure mining produces clusters"
OUT=$("$BIN" evolution mine-failures --json)
check_contains "mine ok" "$OUT" '"ok": true'
check_contains "cluster_count present" "$OUT" '"cluster_count"'

echo "T3: eval runner executes pack"
OUT=$("$BIN" evolution eval-run --pack evals/packs/s5-basic/eval.json --json)
check_contains "eval runner ok" "$OUT" '"ok": true'
check_contains "eval pack id" "$OUT" '"pack": "s5-basic"'

echo "T4: scorecard persists capability rows"
OUT=$("$BIN" evolution scorecard --json)
check_contains "scorecard ok" "$OUT" '"ok": true'
check_contains "scorecards total" "$OUT" '"total"'
OUT=$("$BIN" evolution status --json)
check_contains "status has scorecards" "$OUT" '"scorecards"'

echo "T5: dual gate blocks unsafe promotion"
set +e
BAD=$("$BIN" evolution promote --capability vfs.search --eval-pass --json)
BAD_RC=$?
set -e
[[ $BAD_RC -ne 0 ]] && ok "single-gate promotion rejected" || fail "single-gate promotion rejected"
check_contains "promotion requires dual gate" "$BAD" 'promotion_requires_eval_pass_and_regression_pass'

echo "T6: run-loop creates experiment and promotes with dual gate"
OUT=$("$BIN" evolution run-loop --pack evals/packs/s5-basic/eval.json --json)
check_contains "run-loop ok" "$OUT" '"ok": true'
check_contains "experiment id" "$OUT" '"experiment_id"'
check_contains "promotion payload" "$OUT" '"promotion"'

echo "T7: demote-degraded is reachable"
OUT=$("$BIN" evolution demote-degraded --threshold 0 --json)
check_contains "demote ok" "$OUT" '"ok": true'
check_contains "demoted array" "$OUT" '"demoted"'

echo "T8: status API helper exposes evolution data"
python3 - <<'PY' && ok "status-server evolution helper works" || fail "status-server evolution helper works"
import importlib.util
from pathlib import Path
p = Path("lib/symphony/status-server.py")
spec = importlib.util.spec_from_file_location("status_server", p)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
d = mod._evolution_status()
assert "scorecards" in d and "experiments" in d
PY

echo "T9: experiment template has rollback"
grep -q "## Rollback" experiments/s5-vfs-search-promotion/hypothesis.md \
  && ok "experiment rollback documented" || fail "experiment rollback missing"

echo "T10: runtime-aware scorecard promotes Ruflo full runtime"
OUT=$("$BIN" evolution recommend --capability ruflo.swarm --json)
check_contains "recommend ok" "$OUT" '"ok": true'
check_contains "ruflo closed_loop" "$OUT" '"level": "closed_loop"'
check_contains "ruflo full runtime" "$OUT" '"runtime_level": "full_runtime_usable"'
check_contains "ruflo backend" "$OUT" '"runtime_backend": "official_claude_flow_cli"'

DISPATCH="$(mktemp /tmp/solar-evolution-ranked-dispatch.XXXXXX.md)"
cat >"$DISPATCH" <<'EOF'
# Runtime Ranked Dispatch

Need Ruflo swarm and Claude Flow MCP for multi-agent orchestration.
EOF
"$BIN" skills inject "$DISPATCH" >/dev/null
grep -q "Score: " "$DISPATCH" && ok "dispatch includes score" || fail "dispatch missing score"
grep -q "runtime=full_runtime_usable" "$DISPATCH" && ok "dispatch includes runtime level" || fail "dispatch missing runtime level"
rm -f "$DISPATCH"

echo ""
echo "=== S5 Evolution Engine: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]
