#!/bin/bash
# test-degrade-real.sh — sprint-20260503-203232 D3
# 端到端: select_topology_with_degrade 真触发退化 + 恢复
set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
TELEMETRY_DIR="$HARNESS_DIR/telemetry"
TELEMETRY_FILE="$TELEMETRY_DIR/runs.jsonl"
PASS=0 FAIL=0

cleanup() {
  if [[ -f "${TELEMETRY_FILE}.bak.$$" ]]; then
    mv "${TELEMETRY_FILE}.bak.$$" "$TELEMETRY_FILE"
  fi
}
trap cleanup EXIT

pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

echo "=== test-degrade-real.sh ==="

# Source telemetry lib for _topology_degrade_check
# shellcheck source=/dev/null
HARNESS_DIR="$HARNESS_DIR" SPRINTS_DIR="$SPRINTS_DIR" source "$HARNESS_DIR/lib/telemetry.sh"

# select_topology_with_degrade is in coordinator.sh — extract the logic inline
# since sourcing coordinator.sh pulls in tmux dependencies.
# Instead, we directly call _topology_degrade_check (from telemetry.sh) + select_topology logic.

select_topology_test() {
  local topo="$1"
  if type _topology_degrade_check &>/dev/null; then
    local degraded
    degraded=$(_topology_degrade_check "$topo")
    [[ -n "$degraded" ]] && topo="$degraded"
  fi
  echo "$topo"
}

# ─── T1: Backup ───
echo ""
echo "--- T1: Backup runs.jsonl ---"

if [[ -f "$TELEMETRY_FILE" ]]; then
  cp "$TELEMETRY_FILE" "${TELEMETRY_FILE}.bak.$$"
  pass "T1a: backed up"
else
  _ensure_telemetry_dir
  touch "$TELEMETRY_FILE"
  pass "T1a: created fresh"
fi

# ─── T2: 6 mixture FAIL → degradation triggers ───
echo ""
echo "--- T2: 6 mixture FAIL → degrade to standard ---"

: > "$TELEMETRY_FILE"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for i in 1 2 3 4 5 6; do
  echo "{\"sid\":\"degrade-test-fail-$i\",\"topology\":\"mixture\",\"rounds\":3,\"start_ts\":\"$ts\",\"end_ts\":\"$ts\",\"duration_sec\":60.0,\"verdict\":\"failed\",\"fail_dones\":[\"D1\"],\"total_dones\":3,\"builder_persona\":\"\",\"evaluator_persona\":\"\",\"codex_reviewed\":false}" >> "$TELEMETRY_FILE"
done

lines=$(wc -l < "$TELEMETRY_FILE" | tr -d ' ')
if [[ "$lines" -eq 6 ]]; then
  pass "T2a: wrote 6 FAIL lines to runs.jsonl"
else
  fail "T2a: wrote $lines lines (expected 6)"
fi

result=$(select_topology_test "mixture")
if [[ "$result" == "standard" ]]; then
  pass "T2b: mixture degraded to standard (0/6 = 0% < 60%)"
else
  fail "T2b: got '$result' (expected 'standard')"
fi

# ─── T3: 6 mixture PASS → no degradation ───
echo ""
echo "--- T3: 6 mixture PASS → stays mixture ---"

: > "$TELEMETRY_FILE"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for i in 1 2 3 4 5 6; do
  echo "{\"sid\":\"degrade-test-pass-$i\",\"topology\":\"mixture\",\"rounds\":1,\"start_ts\":\"$ts\",\"end_ts\":\"$ts\",\"duration_sec\":30.0,\"verdict\":\"passed\",\"fail_dones\":[],\"total_dones\":3,\"builder_persona\":\"\",\"evaluator_persona\":\"\",\"codex_reviewed\":false}" >> "$TELEMETRY_FILE"
done

result=$(select_topology_test "mixture")
if [[ "$result" == "mixture" ]]; then
  pass "T3a: mixture stays mixture (6/6 = 100% > 60%)"
else
  fail "T3a: got '$result' (expected 'mixture')"
fi

# ─── T4: 5 mixture FAIL + 2 PASS = 28.6% → degrade ───
echo ""
echo "--- T4: 5 FAIL + 2 PASS = 28.6% → degrade ---"

: > "$TELEMETRY_FILE"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for i in 1 2 3 4 5; do
  echo "{\"sid\":\"degrade-mixed-f-$i\",\"topology\":\"mixture\",\"rounds\":3,\"start_ts\":\"$ts\",\"end_ts\":\"$ts\",\"duration_sec\":60.0,\"verdict\":\"failed\",\"fail_dones\":[\"D2\"],\"total_dones\":3,\"builder_persona\":\"\",\"evaluator_persona\":\"\",\"codex_reviewed\":false}" >> "$TELEMETRY_FILE"
done
for i in 1 2; do
  echo "{\"sid\":\"degrade-mixed-p-$i\",\"topology\":\"mixture\",\"rounds\":1,\"start_ts\":\"$ts\",\"end_ts\":\"$ts\",\"duration_sec\":30.0,\"verdict\":\"passed\",\"fail_dones\":[],\"total_dones\":3,\"builder_persona\":\"\",\"evaluator_persona\":\"\",\"codex_reviewed\":false}" >> "$TELEMETRY_FILE"
done

result=$(select_topology_test "mixture")
if [[ "$result" == "standard" ]]; then
  pass "T4a: mixture degraded to standard (2/7 = 28.6% < 60%)"
else
  fail "T4a: got '$result' (expected 'standard')"
fi

# ─── T5: standard never degrades ───
echo ""
echo "--- T5: standard never degrades ---"

: > "$TELEMETRY_FILE"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for i in 1 2 3 4 5 6; do
  echo "{\"sid\":\"std-fail-$i\",\"topology\":\"standard\",\"rounds\":3,\"start_ts\":\"$ts\",\"end_ts\":\"$ts\",\"duration_sec\":60.0,\"verdict\":\"failed\",\"fail_dones\":[\"D1\"],\"total_dones\":2,\"builder_persona\":\"\",\"evaluator_persona\":\"\",\"codex_reviewed\":false}" >> "$TELEMETRY_FILE"
done

result=$(select_topology_test "standard")
if [[ "$result" == "standard" ]]; then
  pass "T5a: standard never degrades (6/6 FAIL but immune)"
else
  fail "T5a: standard degraded to '$result'"
fi

# ─── T6: insufficient samples (< 5) → no degrade ───
echo ""
echo "--- T6: < 5 samples → no degrade ---"

: > "$TELEMETRY_FILE"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for i in 1 2 3 4; do
  echo "{\"sid\":\"few-fail-$i\",\"topology\":\"deliberation\",\"rounds\":3,\"start_ts\":\"$ts\",\"end_ts\":\"$ts\",\"duration_sec\":60.0,\"verdict\":\"failed\",\"fail_dones\":[],\"total_dones\":2,\"builder_persona\":\"\",\"evaluator_persona\":\"\",\"codex_reviewed\":false}" >> "$TELEMETRY_FILE"
done

result=$(select_topology_test "deliberation")
if [[ "$result" == "deliberation" ]]; then
  pass "T6a: deliberation not degraded with only 4 samples (< 5 min)"
else
  fail "T6a: deliberation degraded to '$result' with insufficient samples"
fi

# ─── Summary ───
echo ""
echo "=== Results: $PASS PASS / $FAIL FAIL ==="
if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL"
  exit 1
fi
echo "ALL_TESTS_PASS"
exit 0
