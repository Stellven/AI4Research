#!/usr/bin/env bash
# test-symphony-d6-guard.sh — 2 test cases for D6 CLAUDECODE guard fix
# Usage: bash test-symphony-d6-guard.sh
set -eu

RUNNER="$HOME/.solar/harness/lib/symphony/runner.sh"
SID="sprint-20260507-symphony2"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

# ─── Case 1: --dry-run exits 0 inside Claude Code env ───
# Even with CLAUDECODE set (Claude Code nested env), --dry-run must exit 0.
case_dryrun_exits_zero() {
  export CLAUDECODE=1  # simulate Claude Code nested env
  local exit_code=0
  bash "$RUNNER" --dry-run --sprint "$SID" >/dev/null 2>&1 || exit_code=$?
  unset CLAUDECODE 2>/dev/null || true

  if [[ $exit_code -eq 0 ]]; then
    pass "dryrun_exits_zero: --dry-run exits 0 even with CLAUDECODE=1"
  else
    fail "dryrun_exits_zero: --dry-run exited ${exit_code} (expected 0) with CLAUDECODE=1"
  fi
}

# ─── Case 2: --unsafe-run-codex blocked without SOLAR_SYMPHONY_REAL=1 ───
case_realexec_blocked_without_flag() {
  unset SOLAR_SYMPHONY_REAL 2>/dev/null || true
  local exit_code=0
  bash "$RUNNER" --unsafe-run-codex --sprint "$SID" 2>/dev/null || exit_code=$?

  if [[ $exit_code -ne 0 ]]; then
    pass "realexec_blocked: --unsafe-run-codex blocked without SOLAR_SYMPHONY_REAL=1 (exit=${exit_code})"
  else
    fail "realexec_blocked: --unsafe-run-codex should be blocked but exited 0"
  fi
}

case_dryrun_exits_zero
case_realexec_blocked_without_flag

echo ""
echo "Results: PASS=${PASS} FAIL=${FAIL}"
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
echo "ALL_PASS"
