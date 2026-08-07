#!/usr/bin/env bash
# tests/test-dispatch-ledger.sh — Dispatch Ledger + Queue regression tests
# sprint-20260508-coordinator-control-plane-v2 S2

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
. "$HARNESS_DIR/lib/dispatch-ledger.sh"
. "$HARNESS_DIR/lib/queue.sh"

PASS=0
FAIL=0

# override ledger and queue paths to temp dirs
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

DISPATCH_LEDGER_FILE="$TMP_DIR/dispatch-ledger.jsonl"
_QUEUE_DIR="$TMP_DIR/queue"
mkdir -p "$_QUEUE_DIR"

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

echo "=== test-dispatch-ledger.sh ==="
echo ""
echo "--- dispatch_id format ---"

# T1: dispatch_id format matches d-<compact>-<6hex>
did=$(new_dispatch_id)
if echo "$did" | grep -qE '^d-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}$'; then
    echo "  ✅ dispatch_id format: $did"
    PASS=$((PASS+1))
else
    echo "  ❌ dispatch_id format unexpected: $did"
    FAIL=$((FAIL+1))
fi

# T2: 1000 dispatch_ids are unique
echo -n "  ⏳ generating 1000 dispatch_ids..."
ids_file="$TMP_DIR/ids.txt"
for _ in $(seq 1 1000); do
    new_dispatch_id
done > "$ids_file"
unique_count=$(sort -u "$ids_file" | wc -l | tr -d ' ')
check "1000 dispatch_ids unique" "$unique_count" "1000"

echo ""
echo "--- dispatch_ledger_append + query ---"

# T3: append an 'attempted' record
DID1=$(new_dispatch_id)
dispatch_ledger_append "attempted" "sprint-test-01" "session:0.2" "$DID1" '{"file":"test.dispatch.md"}'
count=$(wc -l < "$DISPATCH_LEDGER_FILE" | tr -d ' ')
check "ledger has 1 record after append" "$count" "1"

# T4: record contains dispatch_id
line=$(cat "$DISPATCH_LEDGER_FILE")
check_contains "record contains dispatch_id" "$line" "$DID1"

# T5: record contains 'attempted' kind
check_contains "record contains kind=attempted" "$line" '"kind": "attempted"'

# T6: append acked + nacked
DID2=$(new_dispatch_id)
dispatch_ledger_append "acked" "sprint-test-01" "session:0.2" "$DID1" '{}'
dispatch_ledger_append "nacked" "sprint-test-02" "session:0.3" "$DID2" '{"retries":3}'
count=$(wc -l < "$DISPATCH_LEDGER_FILE" | tr -d ' ')
check "ledger has 3 records after 3 appends" "$count" "3"

# T7: query by sid filters correctly
result=$(dispatch_ledger_query --sid "sprint-test-02")
lines=$(echo "$result" | grep -c '"sprint-test-02"' 2>/dev/null || true)
check "query --sid sprint-test-02 returns 1 line" "$lines" "1"

# T8: query by dispatch_id returns only that record
result=$(dispatch_ledger_query --did "$DID1")
lines=$(echo "$result" | wc -l | tr -d ' ')
check "query --did returns 2 lines (attempted+acked for DID1)" "$lines" "2"

# T9: query --tail 1 returns last record
last=$(dispatch_ledger_query --tail 1)
check_contains "query --tail 1 contains nacked" "$last" '"nacked"'

echo ""
echo "--- queue FIFO + dedup ---"

# T10: enqueue returns "ok"
result=$(queue_enqueue "sprint-q1" "build feature A")
check "queue_enqueue returns ok" "$result" "ok"

# T11: enqueue same intent within 24h returns "duplicate"
result=$(queue_enqueue "sprint-q1" "build feature A")
check "queue_enqueue same intent returns duplicate" "$result" "duplicate"

# T12: enqueue different intent returns "ok"
result=$(queue_enqueue "sprint-q1" "review code B")
check "queue_enqueue different intent returns ok" "$result" "ok"

# T13: peek returns first item (build feature A)
peeked=$(queue_peek "sprint-q1")
check_contains "queue_peek returns first intent" "$peeked" "build feature A"

# T14: peek does not consume item (depth still 2)
depth=$(queue_depth "sprint-q1")
check "queue_depth is 2 after peek" "$depth" "2"

# T15: pop removes first item
popped=$(queue_pop "sprint-q1")
check_contains "queue_pop returns first item" "$popped" "build feature A"

# T16: depth decreases to 1 after pop
depth=$(queue_depth "sprint-q1")
check "queue_depth is 1 after pop" "$depth" "1"

# T17: peek now returns second item
peeked=$(queue_peek "sprint-q1")
check_contains "queue_peek returns second item after pop" "$peeked" "review code B"

# T18: pop on empty queue returns nothing (no error)
queue_pop "sprint-q1" >/dev/null
result=$(queue_pop "sprint-q1")
check "queue_pop on empty returns empty" "$result" ""

# T19: crash recovery — file survives, items visible after re-source
queue_enqueue "sprint-q2" "crash-test intent" >/dev/null
# Re-source (simulates restart) and verify peek works
. "$HARNESS_DIR/lib/queue.sh"
_QUEUE_DIR="$TMP_DIR/queue"
recovered=$(queue_peek "sprint-q2")
check_contains "crash recovery: item visible after re-source" "$recovered" "crash-test intent"

# T20: priority queue picks higher priority before older low-priority item
queue_enqueue "sprint-priority" "low priority item" 10 >/dev/null
queue_enqueue "sprint-priority" "high priority item" 100 >/dev/null
priority_peek=$(queue_peek "sprint-priority")
check_contains "queue_peek returns highest priority item" "$priority_peek" "high priority item"

# T21: priority pop consumes highest priority item first
priority_pop=$(queue_pop "sprint-priority")
check_contains "queue_pop returns highest priority item" "$priority_pop" "high priority item"

# T22: terminal queue cleanup consumes all pending entries
queue_enqueue "sprint-terminal" "review stale A" 10 >/dev/null
queue_enqueue "sprint-terminal" "review stale B" 20 >/dev/null
consumed_all=$(queue_consume_all "sprint-terminal" "test_terminal_passed")
check "queue_consume_all returns number consumed" "$consumed_all" "2"
terminal_depth=$(queue_depth "sprint-terminal")
check "queue_consume_all leaves depth 0" "$terminal_depth" "0"
terminal_line=$(grep -m1 'test_terminal_passed' "$_QUEUE_DIR/sprint-terminal.jsonl" || true)
check_contains "queue_consume_all records reason" "$terminal_line" "test_terminal_passed"
if [[ ! -e "$_QUEUE_DIR/sprint-terminal.jsonl.lock" ]]; then
    echo "  ✅ queue_consume_all removes empty terminal lock"
    PASS=$((PASS+1))
else
    echo "  ❌ queue_consume_all removes empty terminal lock"
    FAIL=$((FAIL+1))
fi

# T23: intent-prefix consume only marks matching pending items
queue_enqueue "sprint-prefix" "pm_prd_fix|role=pm|file=x.dispatch.md" 80 >/dev/null
queue_enqueue "sprint-prefix" "graph_node|node_id=N1|pane=lab:0.0" 80 >/dev/null
prefix_consumed=$(queue_consume_intent_prefix "sprint-prefix" "pm_prd_fix|" "superseded_by_graph_dispatch")
check "queue_consume_intent_prefix returns matching count" "$prefix_consumed" "1"
prefix_depth=$(queue_depth "sprint-prefix")
check "queue_consume_intent_prefix leaves non-matching pending" "$prefix_depth" "1"
prefix_line=$(grep -m1 'superseded_by_graph_dispatch' "$_QUEUE_DIR/sprint-prefix.jsonl" || true)
check_contains "queue_consume_intent_prefix records reason" "$prefix_line" "superseded_by_graph_dispatch"

# T24: concurrent appends don't corrupt ledger (10 background writes)
for i in $(seq 1 10); do
    dispatch_ledger_append "attempted" "sprint-concurrent" "pane:0.$i" "$(new_dispatch_id)" '{}' &
done
wait
lines_after=$(wc -l < "$DISPATCH_LEDGER_FILE" | tr -d ' ')
# We had 3 before + 10 new = 13
check "concurrent 10 appends all recorded (total=13)" "$lines_after" "13"

echo ""
echo "=== RESULT: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]
