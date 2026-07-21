#!/usr/bin/env bash
# test-capsule-ledger.sh — D6: Capsule + Ledger 端到端 fixture 测试
set -euo pipefail
HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
SPRINTS_DIR="$HARNESS_DIR/sprints"
LEDGER_FILE="$HOME/.solar/codex-bridge/bridge-ledger.jsonl"
. "$HARNESS_DIR/lib/run-state.sh"
. "$HARNESS_DIR/lib/bridge-ledger.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); }
fail() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

FIXTURE_SID="sprint-fixture-cl-$$"
FIXTURE_FILE="$SPRINTS_DIR/${FIXTURE_SID}.status.json"
cleanup() { rm -f "$SPRINTS_DIR/${FIXTURE_SID}".* 2>/dev/null; }
trap cleanup EXIT

# Create fixture sprint
create_fixture() {
  cat > "$FIXTURE_FILE" <<EOF
{"id":"${FIXTURE_SID}","status":"active","round":1,"created_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","updated_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","history":[]}
EOF
}

# ── T1: capsule-schema.yaml exists + 8 fields ──
test -f "$HARNESS_DIR/schemas/capsule-schema.yaml" && pass || fail "T1a: capsule-schema.yaml missing"
field_count=$(grep -cE '^(goal|facts_established|changes_made|risks|open_questions|required_next_action|recursion_round|topology):' "$HARNESS_DIR/schemas/capsule-schema.yaml")
[[ "$field_count" -ge 8 ]] && pass || fail "T1b: expected 8 fields, got $field_count"

# ── T2: capsule.template.md exists ──
test -f "$HARNESS_DIR/schemas/capsule.template.md" && pass || fail "T2: capsule.template.md missing"

# ── T3: validate.sh capsule_plan on valid capsule ──
create_fixture
cat > "$SPRINTS_DIR/${FIXTURE_SID}.plan.md" <<EOF2
# Plan for ${FIXTURE_SID}

## Goal
Test goal

## Facts Established
- Fact 1

## Changes Made
- (none)

## Risks
- Risk 1

## Open Questions
- Q1

## Required Next Action
Do the thing

## Recursion Round
0

## Topology
standard

## 变更文件
- test: fixture

## 技术方案
fixture test

## 风险点
- fixture
EOF2
bash "$HARNESS_DIR/schemas/validate.sh" capsule_plan "$SPRINTS_DIR/${FIXTURE_SID}.plan.md" >/dev/null 2>&1 && pass || fail "T3: capsule_plan validation failed"

# ── T4: validate.sh capsule_handoff on valid capsule ──
cat > "$SPRINTS_DIR/${FIXTURE_SID}.handoff.md" <<EOF2
# Handoff for ${FIXTURE_SID}

## Goal
Test goal

## Facts Established
- Fact 1

## Changes Made
- Changed code

## Risks
- Risk 1

## Open Questions
- Q1

## Required Next Action
Verify

## Recursion Round
1

## Topology
standard

## 变更文件
- test: fixture

## Done 达成
1. D1: test

## 验证方法
echo test
EOF2
bash "$HARNESS_DIR/schemas/validate.sh" capsule_handoff "$SPRINTS_DIR/${FIXTURE_SID}.handoff.md" >/dev/null 2>&1 && pass || fail "T4: capsule_handoff validation failed"

# ── T5: validate.sh capsule_eval on valid capsule ──
cat > "$SPRINTS_DIR/${FIXTURE_SID}.eval.md" <<EOF2
# Eval for ${FIXTURE_SID}

## Goal
Test goal

## Facts Established
- Fact 1

## Changes Made
- Eval changes

## Risks
- Risk 1

## Open Questions
- Q1

## Required Next Action
Close

## Recursion Round
1

## Topology
standard

## 总判定: PASS
All good

## Done 条件
1. D1: PASS

PASS
EOF2
bash "$HARNESS_DIR/schemas/validate.sh" capsule_eval "$SPRINTS_DIR/${FIXTURE_SID}.eval.md" >/dev/null 2>&1 && pass || fail "T5: capsule_eval validation failed"

# ── T6: validate.sh capsule_handoff fails on missing capsule fields ──
cat > /tmp/test-no-capsule-$$.md <<EOF2
# Handoff without capsule fields

## 变更文件
- test

## Done 达成
1. D1: test

## 验证方法
echo test
EOF2
bash "$HARNESS_DIR/schemas/validate.sh" capsule_handoff /tmp/test-no-capsule-$$.md >/dev/null 2>&1 && fail "T6: should FAIL on missing capsule fields" || pass
rm -f /tmp/test-no-capsule-$$.md

# ── T7: validate.sh old format plan still PASS ──
cat > /tmp/test-old-plan-$$.md <<EOF2
# Plan old format

## 变更文件
- test

## 技术方案
fixture

## 风险点
- fixture
EOF2
bash "$HARNESS_DIR/schemas/validate.sh" plan /tmp/test-old-plan-$$.md >/dev/null 2>&1 && pass || fail "T7: old format plan should PASS"
rm -f /tmp/test-old-plan-$$.md

# ── T8: bridge ledger events ──
ledger_emit "produced" "${FIXTURE_SID}.handoff.md" "{\"by\":\"builder\"}" && pass || fail "T8a: ledger_emit produced failed"
ledger_emit "consumed" "${FIXTURE_SID}.handoff.md" "{\"by\":\"chain-watcher\"}" && pass || fail "T8b: ledger_emit consumed failed"
ledger_emit "reviewed" "${FIXTURE_SID}" "{\"by\":\"coordinator\"}" && pass || fail "T8c: ledger_emit reviewed failed"
ledger_emit "accepted" "${FIXTURE_SID}.handoff.md" "{\"verdict\":\"PASS\",\"by\":\"evaluator\"}" && pass || fail "T8d: ledger_emit accepted failed"
ledger_emit "closed" "${FIXTURE_SID}" "{}" && pass || fail "T8e: ledger_emit closed failed"

# Verify all 5 event types in ledger
events=$(ledger_events_for_sid "$FIXTURE_SID")
produced_n=$(echo "$events" | grep -c '"produced"' || true)
consumed_n=$(echo "$events" | grep -c '"consumed"' || true)
reviewed_n=$(echo "$events" | grep -c '"reviewed"' || true)
accepted_n=$(echo "$events" | grep -c '"accepted"' || true)
closed_n=$(echo "$events" | grep -c '"closed"' || true)
[[ "$produced_n" -ge 1 ]] && [[ "$consumed_n" -ge 1 ]] && [[ "$reviewed_n" -ge 1 ]] && [[ "$accepted_n" -ge 1 ]] && [[ "$closed_n" -ge 1 ]] && pass || fail "T8f: ledger events incomplete (p=$produced_n c=$consumed_n r=$reviewed_n a=$accepted_n cl=$closed_n)"

# ── T9: ledger_emit rejects invalid event ──
ledger_emit "invalid_event" "test" 2>/dev/null && fail "T9: should reject invalid event" || pass

# ── T10: rs_set_topology / rs_set_mode ──
rs_set_topology "$FIXTURE_SID" "deliberation" && pass || fail "T10a: rs_set_topology failed"
top_val=$(rs_read_field "$FIXTURE_SID" "topology")
[[ "$top_val" == "deliberation" ]] && pass || fail "T10b: topology expected deliberation, got $top_val"

rs_set_mode "$FIXTURE_SID" "fast" && pass || fail "T10c: rs_set_mode failed"
mode_val=$(rs_read_field "$FIXTURE_SID" "mode")
[[ "$mode_val" == "fast" ]] && pass || fail "T10d: mode expected fast, got $mode_val"

# T10e: default topology/mode for old sprint without these fields
old_sid="sprint-20260503-090450"
if rs_exists "$old_sid"; then
  old_top=$(rs_read_field "$old_sid" "topology")
  [[ "$old_top" == "standard" || -z "$old_top" ]] && pass || fail "T10e: old sprint topology should default to standard, got $old_top"
else
  pass
fi

# T10f: invalid topology rejected
rs_set_topology "$FIXTURE_SID" "invalid" 2>/dev/null && fail "T10f: should reject invalid topology" || pass

# ── T11: capsule show command ──
output=$(bash "$HARNESS_DIR/solar-harness.sh" capsule show "$FIXTURE_SID" 2>&1)
echo "$output" | grep -qi "goal" && pass || fail "T11a: capsule show missing goal"
echo "$output" | grep -qi "topology" && pass || fail "T11b: capsule show missing topology"

# ── T12: ledger show command ──
output=$(bash "$HARNESS_DIR/solar-harness.sh" ledger show "$FIXTURE_SID" 2>&1)
echo "$output" | grep -qi "produced" && pass || fail "T12a: ledger show missing produced"
echo "$output" | grep -qi "accepted" && pass || fail "T12b: ledger show missing accepted"

# ── Cleanup: remove fixture events from ledger ──
if [[ -f "$LEDGER_FILE" ]]; then
  grep -v "$FIXTURE_SID" "$LEDGER_FILE" > "${LEDGER_FILE}.tmp" 2>/dev/null || true
  mv "${LEDGER_FILE}.tmp" "$LEDGER_FILE" 2>/dev/null || true
fi

echo ""
echo "=== Results: PASS=$PASS FAIL=$FAIL ==="
if (( FAIL == 0 )); then
  echo "ALL_TESTS_PASS"
  exit 0
fi
echo "SOME_TESTS_FAILED"
exit 1
