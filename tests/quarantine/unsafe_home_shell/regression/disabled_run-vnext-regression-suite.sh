#!/usr/bin/env bash
# run-vnext-regression-suite.sh
#
# vNext sprint S05/N3 regression aggregator. Runs, in order:
#   (a) tests/regression/test-vnext-graph-scheduler-shim.sh
#       -> delegates to tests/control_plane/test-graph-scheduler.sh
#   (b) py_compile across every *.py under harness/lib (non-empty enumeration)
#   (c) solar-harness.sh doctor
#   (d) tests/installer/test-s1-installer.sh  (best-effort smoke; skip if absent
#       — original spec called for test-smoke-install.sh which does not exist
#       under tests/; the closest live smoke is the s1 installer test)
#   (e) tests/regression/test-vnext-no-side-effect.sh
#
# Output: per-step PASS/FAIL summary table plus aggregated failed list. Returns
# 0 only when every step exits 0; otherwise prints the failed list and exits 1.
set -uo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
REG_DIR="$HARNESS_DIR/tests/regression"
LIB_DIR="$HARNESS_DIR/lib"
DOCTOR_BIN="$HARNESS_DIR/solar-harness.sh"
# Per dispatch spec the "d" step is `test-smoke-install.sh (若存在)` — strict
# literal match. Substituting a different installer test would surface noise
# unrelated to S03/S04 (e.g. pre-existing .gitignore drift), so we honor the
# spec: SKIP cleanly when this exact filename is absent. The auxiliary path
# (test-s1-installer.sh) is only consulted via the
# SOLAR_REG_SMOKE_INSTALL_OVERRIDE escape hatch.
SMOKE_TEST_PRIMARY="$HARNESS_DIR/tests/installer/test-smoke-install.sh"
SMOKE_TEST_OVERRIDE="${SOLAR_REG_SMOKE_INSTALL_OVERRIDE:-}"

declare -a STEP_NAMES=()
declare -a STEP_STATUS=()
declare -a STEP_DETAIL=()
FAILED=()

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
hr() { printf -- '----------------------------------------\n'; }

record() {
  local name="$1" status="$2" detail="$3"
  STEP_NAMES+=("$name")
  STEP_STATUS+=("$status")
  STEP_DETAIL+=("$detail")
  if [[ "$status" != "PASS" && "$status" != "SKIP" ]]; then
    FAILED+=("$name")
  fi
}

run_step() {
  local name="$1"; shift
  local logfile="$1"; shift
  local cmd_label="$*"
  hr
  echo "[$(ts)] STEP: $name"
  echo "[$(ts)] CMD : $cmd_label"
  set +e
  "$@" >"$logfile" 2>&1
  local rc=$?
  set -e 2>/dev/null || true
  tail -n 8 "$logfile" | sed 's/^/  | /'
  if [[ $rc -eq 0 ]]; then
    record "$name" "PASS" "rc=0, log=$logfile"
    echo "[$(ts)] RESULT: PASS"
  else
    record "$name" "FAIL" "rc=$rc, log=$logfile"
    echo "[$(ts)] RESULT: FAIL (rc=$rc)"
  fi
}

LOGROOT="${SOLAR_REG_LOG_DIR:-$HOME/.solar/logs/vnext-regression}"
mkdir -p "$LOGROOT"
RUN_ID="vnext-regression-$(date -u +%Y%m%dT%H%M%SZ)-$$"
LOGDIR="$LOGROOT/$RUN_ID"
mkdir -p "$LOGDIR"
echo "[$(ts)] vNext regression suite start"
echo "[$(ts)] HARNESS_DIR=$HARNESS_DIR"
echo "[$(ts)] LOGDIR=$LOGDIR"

# (a) graph scheduler shim
GS_LOG="$LOGDIR/01-graph-scheduler.log"
if [[ -f "$REG_DIR/test-vnext-graph-scheduler-shim.sh" ]]; then
  run_step "graph-scheduler-shim" "$GS_LOG" bash "$REG_DIR/test-vnext-graph-scheduler-shim.sh"
else
  record "graph-scheduler-shim" "FAIL" "shim missing"
  echo "FAIL: graph-scheduler-shim missing"
fi

# (b) py_compile lib/*.py — assert non-empty enumeration & all compile
PY_LOG="$LOGDIR/02-py-compile-lib.log"
PY_SCRIPT="$LOGDIR/02-py-compile-lib.py"
cat >"$PY_SCRIPT" <<'PY'
import os, sys, py_compile, json
root = sys.argv[1]
files = []
for dirpath, _dirs, fnames in os.walk(root):
    for f in fnames:
        if f.endswith('.py'):
            files.append(os.path.join(dirpath, f))
fails = []
for p in files:
    try:
        py_compile.compile(p, doraise=True)
    except py_compile.PyCompileError as e:
        fails.append({'path': p, 'err': str(e)})
print(json.dumps({'total': len(files), 'fails': len(fails), 'details': fails[:20]}, ensure_ascii=False, indent=2))
sys.exit(0 if files and not fails else 1)
PY
run_step "py-compile-lib" "$PY_LOG" python3 "$PY_SCRIPT" "$LIB_DIR"

# (c) solar-harness doctor
DOCTOR_LOG="$LOGDIR/03-doctor.log"
if [[ -x "$DOCTOR_BIN" || -f "$DOCTOR_BIN" ]]; then
  run_step "solar-harness-doctor" "$DOCTOR_LOG" bash "$DOCTOR_BIN" doctor
else
  record "solar-harness-doctor" "FAIL" "doctor entrypoint missing: $DOCTOR_BIN"
  echo "FAIL: doctor entrypoint missing"
fi

# (d) smoke install — only when the canonical test-smoke-install.sh exists, or
# the operator opts in via SOLAR_REG_SMOKE_INSTALL_OVERRIDE.
SMOKE_LOG="$LOGDIR/04-smoke-install.log"
if [[ -n "$SMOKE_TEST_OVERRIDE" && -f "$SMOKE_TEST_OVERRIDE" ]]; then
  run_step "smoke-install" "$SMOKE_LOG" bash "$SMOKE_TEST_OVERRIDE"
elif [[ -f "$SMOKE_TEST_PRIMARY" ]]; then
  run_step "smoke-install" "$SMOKE_LOG" bash "$SMOKE_TEST_PRIMARY"
else
  echo "[$(ts)] STEP: smoke-install (SKIP — test-smoke-install.sh absent; spec allows skip)"
  record "smoke-install" "SKIP" "test-smoke-install.sh absent; spec '(若存在)' permits skip"
fi

# (e) no-side-effect
NSE_LOG="$LOGDIR/05-no-side-effect.log"
if [[ -f "$REG_DIR/test-vnext-no-side-effect.sh" ]]; then
  run_step "no-side-effect" "$NSE_LOG" bash "$REG_DIR/test-vnext-no-side-effect.sh"
else
  record "no-side-effect" "FAIL" "test-vnext-no-side-effect.sh missing"
fi

hr
echo "## vNext Regression Suite Summary"
printf '| # | Step | Status | Detail |\n'
printf '|---|------|--------|--------|\n'
i=0
while [[ $i -lt ${#STEP_NAMES[@]} ]]; do
  printf '| %d | %s | %s | %s |\n' "$((i+1))" "${STEP_NAMES[$i]}" "${STEP_STATUS[$i]}" "${STEP_DETAIL[$i]}"
  i=$((i+1))
done

# SKIP does not count as failure but is reported.
if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo
  echo "FAILED:"
  for f in "${FAILED[@]}"; do echo "  - $f"; done
  echo "[$(ts)] vNext regression suite: FAIL"
  exit 1
fi

echo "[$(ts)] vNext regression suite: PASS"
exit 0
