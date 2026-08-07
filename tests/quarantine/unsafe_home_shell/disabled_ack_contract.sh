#!/usr/bin/env bash
# tests/test-ack-contract.sh — Ack Contract regression tests
# sprint-20260508-coordinator-control-plane-v2 S3

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
. "$HARNESS_DIR/lib/dispatch-ledger.sh"
. "$HARNESS_DIR/lib/ack-watcher.sh"

PASS=0
FAIL=0

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# Override paths to temp dirs
DISPATCH_LEDGER_FILE="$TMP_DIR/dispatch-ledger.jsonl"
SPRINTS_DIR="$TMP_DIR/sprints"
mkdir -p "$SPRINTS_DIR"

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

echo "=== test-ack-contract.sh ==="
echo ""
echo "--- write_ack_file schema ---"

SID="sprint-ack-test-01"
DID="d-20260508T120000Z-abcdef"

# T1: write_ack_file creates the file
write_ack_file "$SID" "$DID" "builder" "success" "0" "handoff submitted"
ACK_FILE="$SPRINTS_DIR/${SID}.ack-${DID}.json"
check "ack file created" "$(test -f "$ACK_FILE" && echo yes)" "yes"

# T2: ack file contains dispatch_id
ack_content=$(cat "$ACK_FILE")
check_contains "ack contains dispatch_id" "$ack_content" "$DID"

# T3: ack file contains sid
check_contains "ack contains sid" "$ack_content" "$SID"

# T4: ack file contains role=builder
check_contains "ack contains role=builder" "$ack_content" '"role": "builder"'

# T5: ack file contains status=success
check_contains "ack contains status=success" "$ack_content" '"status": "success"'

# T6: ack file contains exit_code=0
check_contains "ack contains exit_code" "$ack_content" '"exit_code": 0'

# T7: ack file contains artifacts array
check_contains "ack contains artifacts" "$ack_content" '"artifacts"'

# T8: read_ack_file returns content
read_result=$(read_ack_file "$SID" "$DID")
check_contains "read_ack_file returns content" "$read_result" "$DID"

# T9: read_ack_file on missing returns empty
missing_result=$(read_ack_file "$SID" "d-nonexistent-000000")
check "read_ack_file missing → empty" "$missing_result" ""

echo ""
echo "--- ack-watcher (fast path: ack appears quickly) ---"

SID2="sprint-ack-watcher-01"
DID2="d-20260508T130000Z-111111"

# T10: start ack-watcher, write ack after 1s, verify ledger gets acked_by_ack_file
ack_watcher_bg "$SID2" "$DID2" 10
sleep 1
write_ack_file "$SID2" "$DID2" "builder" "success" "0" "done"
sleep 3  # give watcher time to detect and write ledger

ledger_content=$(cat "$DISPATCH_LEDGER_FILE" 2>/dev/null || echo "")
check_contains "ack-watcher writes acked_by_ack_file to ledger" "$ledger_content" "acked_by_ack_file"
check_contains "ack-watcher ledger entry has correct did" "$ledger_content" "$DID2"

echo ""
echo "--- ack-watcher (timeout path) ---"

SID3="sprint-ack-timeout-01"
DID3="d-20260508T140000Z-222222"

# T11: start watcher with 3s timeout, no ack file → ledger gets ack_timeout
ack_watcher_bg "$SID3" "$DID3" 3
sleep 5  # wait for timeout

ledger_content2=$(cat "$DISPATCH_LEDGER_FILE" 2>/dev/null || echo "")
check_contains "ack-watcher timeout writes ack_timeout to ledger" "$ledger_content2" "ack_timeout"
check_contains "ack_timeout entry has correct sid" "$ledger_content2" "$SID3"

echo ""
echo "--- failed ack ---"

SID4="sprint-ack-failed-01"
DID4="d-20260508T150000Z-333333"

# T12: write failed ack → correct schema
write_ack_file "$SID4" "$DID4" "builder" "failed" "1" "implementation error"
ack4=$(cat "$SPRINTS_DIR/${SID4}.ack-${DID4}.json")
check_contains "failed ack has status=failed" "$ack4" '"status": "failed"'
check_contains "failed ack has exit_code=1" "$ack4" '"exit_code": 1'

echo ""
echo "=== RESULT: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]
