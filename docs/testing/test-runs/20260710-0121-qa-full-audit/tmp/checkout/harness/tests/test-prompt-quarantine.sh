#!/usr/bin/env bash
# tests/test-prompt-quarantine.sh — Prompt Quarantine Lifecycle regression tests
# sprint-20260508-coordinator-control-plane-v2 S4

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
. "$HARNESS_DIR/lib/dispatch-ledger.sh"
. "$HARNESS_DIR/lib/pane-lease.sh"
. "$HARNESS_DIR/lib/prompt-quarantine.sh"

PASS=0
FAIL=0

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# Override state dirs to temp
_QUARANTINE_DIR="$TMP_DIR/quarantine"
_PANE_LEASE_DIR="$TMP_DIR/pane-leases"
DISPATCH_LEDGER_FILE="$TMP_DIR/dispatch-ledger.jsonl"
mkdir -p "$_QUARANTINE_DIR" "$_PANE_LEASE_DIR"

check() {
    local label="$1" got="$2" want="$3"
    if [[ "$got" == "$want" ]]; then
        echo "  ✅ $label"
        PASS=$((PASS+1))
    else
        echo "  ❌ $label"
        echo "       want: $want"
        echo "        got: $got"
        FAIL=$((FAIL+1))
    fi
}

check_contains() {
    local label="$1" haystack="$2" needle="$3"
    if echo "$haystack" | grep -q "$needle" 2>/dev/null; then
        echo "  ✅ $label"
        PASS=$((PASS+1))
    else
        echo "  ❌ $label — '$needle' not found"
        FAIL=$((FAIL+1))
    fi
}

PANE="solar-harness:0.2"
SID="sprint-pq-test-01"
DID1="d-20260508T200000Z-aa0001"

echo "=== test-prompt-quarantine.sh ==="
echo ""
echo "--- clean pane (no residue) ---"

# T1: clean pane → returns 0
export _QUARANTINE_CAPTURE_OVERRIDE="  ❯  "   # idle prompt, whitespace only after ❯
rc=0
prompt_quarantine_check "$PANE" "$SID" "$DID1" || rc=$?
check "clean pane → exit 0" "$rc" "0"
unset _QUARANTINE_CAPTURE_OVERRIDE

# T2: no prompt at all → also clean
export _QUARANTINE_CAPTURE_OVERRIDE="some output line"
rc=0
prompt_quarantine_check "$PANE" "$SID" "$DID1" || rc=$?
check "no prompt → exit 0" "$rc" "0"
unset _QUARANTINE_CAPTURE_OVERRIDE

# T2b: historical prompt text above footer is not editable residue
export _QUARANTINE_CAPTURE_OVERRIDE="old output
────────────────────────────────────────
❯ 把 4 项 low-severity 注脚开个新 sprint 修了
────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)"
rc=0
prompt_quarantine_check "$PANE" "$SID" "$DID1" || rc=$?
check "historical prompt line near footer → exit 0" "$rc" "0"
unset _QUARANTINE_CAPTURE_OVERRIDE

echo ""
echo "--- residue detection + fix keys (≤3 attempts) ---"

SID2="sprint-pq-test-02"
DID2="d-20260508T200001Z-bb0001"

# T3: first residue → exit 1 (fix keys sent), counter = 1
export _QUARANTINE_CAPTURE_OVERRIDE="  ❯ some residual text here
  ⏵⏵ bypass permissions on (shift+tab to cycle)"
rc=0
prompt_quarantine_check "$PANE" "$SID2" "$DID2" || rc=$?
check "1st residue → exit 1" "$rc" "1"
cnt_file="$_QUARANTINE_DIR/$(_pane_safe_q "$PANE").${DID2}.cnt"
cnt=$(cat "$cnt_file" 2>/dev/null || echo -1)
check "1st residue → counter=1" "$cnt" "1"
unset _QUARANTINE_CAPTURE_OVERRIDE

# T4: second residue (same pane+did) → exit 1, counter = 2
export _QUARANTINE_CAPTURE_OVERRIDE="  ❯ still some text
  ⏵⏵ bypass permissions on (shift+tab to cycle)"
rc=0
prompt_quarantine_check "$PANE" "$SID2" "$DID2" || rc=$?
check "2nd residue → exit 1" "$rc" "1"
cnt=$(cat "$cnt_file" 2>/dev/null || echo -1)
check "2nd residue → counter=2" "$cnt" "2"
unset _QUARANTINE_CAPTURE_OVERRIDE

# T5: third residue → exit 1, counter = 3
export _QUARANTINE_CAPTURE_OVERRIDE="  ❯ more text
  ⏵⏵ bypass permissions on (shift+tab to cycle)"
rc=0
prompt_quarantine_check "$PANE" "$SID2" "$DID2" || rc=$?
check "3rd residue → exit 1" "$rc" "1"
cnt=$(cat "$cnt_file" 2>/dev/null || echo -1)
check "3rd residue → counter=3" "$cnt" "3"
unset _QUARANTINE_CAPTURE_OVERRIDE

# T6: inbox.jsonl has 3 fixkeys_sent entries
inbox=$(cat "$_QUARANTINE_DIR/inbox.jsonl" 2>/dev/null || echo "")
fixkeys_count=$(echo "$inbox" | grep -c "fixkeys_sent" 2>/dev/null || echo 0)
check "inbox has 3 fixkeys_sent entries" "$fixkeys_count" "3"

echo ""
echo "--- quarantine on 4th attempt ---"

# T7: fourth residue → exit 2 (quarantined), cooldown file created
export _QUARANTINE_CAPTURE_OVERRIDE="  ❯ still stuck
  ⏵⏵ bypass permissions on (shift+tab to cycle)"
rc=0
prompt_quarantine_check "$PANE" "$SID2" "$DID2" || rc=$?
check "4th attempt → exit 2 (quarantined)" "$rc" "2"
unset _QUARANTINE_CAPTURE_OVERRIDE

cooldown_file="$_QUARANTINE_DIR/$(_pane_safe_q "$PANE").cooldown"
check "cooldown file created" "$(test -f "$cooldown_file" && echo yes)" "yes"

# T8: inbox has quarantined entry
inbox=$(cat "$_QUARANTINE_DIR/inbox.jsonl" 2>/dev/null || echo "")
check_contains "inbox has quarantined entry" "$inbox" '"action": "quarantined"'

# T9: subsequent check (even clean) → exit 3 (cooldown)
export _QUARANTINE_CAPTURE_OVERRIDE="  ❯  "   # clean, but pane in cooldown
rc=0
prompt_quarantine_check "$PANE" "$SID2" "$DID2" || rc=$?
check "pane in cooldown → exit 3" "$rc" "3"
unset _QUARANTINE_CAPTURE_OVERRIDE

echo ""
echo "--- cooldown expiry ---"

SID3="sprint-pq-test-03"
DID3="d-20260508T200002Z-cc0001"
PANE3="solar-harness:0.5"

# T10: write expired cooldown → check returns 0 (clean)
pane3_safe=$(_pane_safe_q "$PANE3")
echo "2020-01-01T00:00:00Z" > "$_QUARANTINE_DIR/${pane3_safe}.cooldown"
export _QUARANTINE_CAPTURE_OVERRIDE="  ❯  "
rc=0
prompt_quarantine_check "$PANE3" "$SID3" "$DID3" || rc=$?
check "expired cooldown → exit 0 (clean)" "$rc" "0"
check "expired cooldown file removed" "$(test ! -f "$_QUARANTINE_DIR/${pane3_safe}.cooldown" && echo yes)" "yes"
unset _QUARANTINE_CAPTURE_OVERRIDE

echo ""
echo "--- prompt_quarantine_resolve ---"

SID4="sprint-pq-test-04"
DID4="d-20260508T200003Z-dd0001"
PANE4="solar-harness:0.6"
pane4_safe=$(_pane_safe_q "$PANE4")

# Create synthetic cooldown + counter
echo "2099-01-01T00:00:00Z" > "$_QUARANTINE_DIR/${pane4_safe}.cooldown"
echo "2" > "$_QUARANTINE_DIR/${pane4_safe}.${DID4}.cnt"

# T11: resolve clears cooldown and counter
prompt_quarantine_resolve "$PANE4" "$DID4" "manual_test"
check "resolve: cooldown file removed" "$(test ! -f "$_QUARANTINE_DIR/${pane4_safe}.cooldown" && echo yes)" "yes"
check "resolve: counter file removed"  "$(test ! -f "$_QUARANTINE_DIR/${pane4_safe}.${DID4}.cnt" && echo yes)" "yes"

# T12: resolve writes resolved entry to inbox
inbox=$(cat "$_QUARANTINE_DIR/inbox.jsonl" 2>/dev/null || echo "")
check_contains "resolve: inbox has resolved entry" "$inbox" '"action": "resolved_manual_test"'

echo ""
echo "--- coordinator.sh has no direct send-keys Escape/C-u ---"

# T13: verify coordinator.sh no longer has raw Escape/C-u send-keys
direct_cu=$(grep -cE "tmux send-keys.*C-u|tmux send-keys.*Escape" "$HARNESS_DIR/coordinator.sh" 2>/dev/null || true)
direct_cu="$(printf '%s\n' "$direct_cu" | tail -1)"
check "coordinator.sh: 0 direct C-u/Escape send-keys" "$direct_cu" "0"

echo ""
echo "=== RESULT: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]
