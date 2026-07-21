#!/usr/bin/env bash
# test-lab-routing.sh — verify second quadrant is routable, not just visible.
set -uo pipefail

HARNESS_DIR="$HOME/.solar/harness"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }

echo "=== test-lab-routing.sh ==="

backup_state() {
  cp "$HARNESS_DIR/.pane-assignments" /tmp/lab-pa.bak.$$ 2>/dev/null || true
}

restore_state() {
  mv /tmp/lab-pa.bak.$$ "$HARNESS_DIR/.pane-assignments" 2>/dev/null || rm -f "$HARNESS_DIR/.pane-assignments"
}

trap restore_state EXIT
backup_state

COORD_NO_MAIN=1 source "$HARNESS_DIR/coordinator.sh" 2>/dev/null

main_key="$(pane_key "solar-harness:0.1")"
lab_key="$(pane_key "solar-harness-lab:0.1")"
MAIN_TARGET="solar-harness:0.1"
LAB_TARGET="solar-harness-lab:0.1"
rm -rf "$HARNESS_DIR/.dispatch-pane-${main_key}.lock" "$HARNESS_DIR/.dispatch-pane-${lab_key}.lock"
if [[ "$main_key" != "$lab_key" ]]; then
  pass "pane_key keeps main and lab locks distinct"
else
  fail "pane_key collision: $main_key"
fi

PANE_CURRENT_SPRINT=()
PANE_ASSIGN_TS=()
SID_A="sprint-test-lab-routing-a-$$"
SID_B="sprint-test-lab-routing-b-$$"

DISPATCH_MOCK=1 dispatch_to_pane "$MAIN_TARGET" "" "$SID_A"
rc_main=$?
DISPATCH_MOCK=1 dispatch_to_pane "$LAB_TARGET" "" "$SID_B"
rc_lab=$?

if [[ "$rc_main" -eq 0 && "$rc_lab" -eq 0 ]]; then
  pass "mock dispatch can assign main builder and lab-builder independently"
else
  fail "mock dispatch rc_main=$rc_main rc_lab=$rc_lab"
fi

if [[ "${PANE_CURRENT_SPRINT[$MAIN_TARGET]:-}" == "$SID_A" ]]; then
  pass "main assignment stored by full target"
else
  fail "main assignment missing"
fi

if [[ "${PANE_CURRENT_SPRINT[$LAB_TARGET]:-}" == "$SID_B" ]]; then
  pass "lab assignment stored by full target"
else
  fail "lab assignment missing"
fi

if grep -q 'choose_lab_builder_pane' "$HARNESS_DIR/coordinator.sh" \
  && grep -q 'choose_lab_evaluator_pane' "$HARNESS_DIR/coordinator.sh" \
  && grep -q 'choose_architect_pane' "$HARNESS_DIR/coordinator.sh"; then
  pass "coordinator exposes lab routing helpers"
else
  fail "coordinator missing lab routing helpers"
fi

if grep -q 'LAB_SESSION_NAME="solar-harness-lab"' "$HARNESS_DIR/coordinator-watchdog.sh" \
  && grep -q 'lab-builder' "$HARNESS_DIR/coordinator-watchdog.sh"; then
  pass "watchdog tracks lab session panes"
else
  fail "watchdog does not track lab session panes"
fi

if tmux has-session -t solar-harness-lab 2>/dev/null; then
  arch_pane="$(choose_architect_pane)"
  lab_builder_pane="$(choose_lab_builder_pane)"
  lab_eval_pane="$(choose_lab_evaluator_pane)"
  case "$arch_pane:$lab_builder_pane:$lab_eval_pane" in
    solar-harness-lab:0.*:solar-harness-lab:0.*:solar-harness-lab:0.*)
      pass "live lab personas resolve to solar-harness-lab"
      ;;
    *)
      fail "live lab persona resolution unexpected: $arch_pane / $lab_builder_pane / $lab_eval_pane"
      ;;
  esac
else
  pass "live lab resolution skipped (solar-harness-lab not running)"
fi

if tmux has-session -t solar-harness 2>/dev/null; then
  main_builder_pane="$(choose_builder_pane)"
  main_eval_pane="$(choose_evaluator_pane)"
  builder_persona="$(pane_process_persona "$main_builder_pane" 2>/dev/null || true)"
  eval_persona="$(pane_process_persona "$main_eval_pane" 2>/dev/null || true)"
  if [[ "$builder_persona" == "builder" && "$eval_persona" == "evaluator" ]]; then
    pass "live main routes resolve to actual builder/evaluator personas"
  else
    fail "live main route mismatch: $main_builder_pane=$builder_persona / $main_eval_pane=$eval_persona"
  fi
else
  pass "live main resolution skipped (solar-harness not running)"
fi

rm -rf "$HARNESS_DIR/.dispatch-pane-${main_key}.lock" "$HARNESS_DIR/.dispatch-pane-${lab_key}.lock"

echo ""
echo "=== Results: PASS=$PASS FAIL=$FAIL ==="
if (( FAIL == 0 )); then
  echo "PASS"
  exit 0
fi
echo "FAIL"
exit 1
