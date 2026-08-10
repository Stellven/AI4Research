#!/usr/bin/env bash
# test-events-emit.sh — Unit tests for lib/events.sh emit_event()
# Sprint: sprint-20260507-symphony3 / S1

set -eu

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"

# ── Safety guards ──
[[ "${SESSION_NAME:-}" == "solar-harness" ]] && {
  echo "REFUSE: cannot run tests on live solar-harness session"; exit 1
}

# ── Test isolation: use a temp dir ──
TEST_TMP=$(mktemp -d)
trap 'rm -rf "$TEST_TMP"' EXIT

export HARNESS_DIR="$TEST_TMP"
export _SPRINTS_DIR="$TEST_TMP/sprints"
mkdir -p "$TEST_TMP/events" "$TEST_TMP/sprints" "$TEST_TMP/lib"

# Source the library
source "$HOME/.solar/harness/lib/events.sh"

# ── Test framework ──
PASS=0
FAIL=0

assert() {
  local desc="$1" expr="$2"
  if eval "$expr" 2>/dev/null; then
    echo "  ✅ PASS: $desc"
    (( PASS++ )) || true
  else
    echo "  ❌ FAIL: $desc"
    (( FAIL++ )) || true
  fi
}

echo "=== test-events-emit.sh ==="
echo ""

# ── TC1: Normal event emitted correctly ──
echo "TC1: Normal emit_event writes valid JSON to all.jsonl"
emit_event "coordinator" "state_change" "info" "sprint-test-001" '{"from":"active","to":"reviewing"}'
assert "all.jsonl exists" '[[ -f "$TEST_TMP/events/all.jsonl" ]]'
assert "all.jsonl has 1 line" '[[ "$(wc -l < "$TEST_TMP/events/all.jsonl")" -eq 1 ]]'
assert "per-sprint jsonl exists" '[[ -f "$TEST_TMP/sprints/sprint-test-001.events.jsonl" ]]'
assert "JSON is valid" 'python3 -c "import json; json.loads(open(\"$TEST_TMP/events/all.jsonl\").read())"'
assert "ts field present" 'python3 -c "import json; d=json.loads(open(\"$TEST_TMP/events/all.jsonl\").read()); assert \"ts\" in d"'
assert "actor field = coordinator" 'python3 -c "import json; d=json.loads(open(\"$TEST_TMP/events/all.jsonl\").read()); assert d[\"actor\"]==\"coordinator\""'
assert "event field = state_change" 'python3 -c "import json; d=json.loads(open(\"$TEST_TMP/events/all.jsonl\").read()); assert d[\"event\"]==\"state_change\""'
assert "severity = info" 'python3 -c "import json; d=json.loads(open(\"$TEST_TMP/events/all.jsonl\").read()); assert d[\"severity\"]==\"info\""'
assert "sprint_id = sprint-test-001" 'python3 -c "import json; d=json.loads(open(\"$TEST_TMP/events/all.jsonl\").read()); assert d[\"sprint_id\"]==\"sprint-test-001\""'
assert "payload.from = active" 'python3 -c "import json; d=json.loads(open(\"$TEST_TMP/events/all.jsonl\").read()); assert d[\"payload\"][\"from\"]==\"active\""'
echo ""

# ── TC2: Empty sprint_id → sprint_id null in JSON ──
echo "TC2: Empty sprint_id → sprint_id:null, no per-sprint file"
emit_event "solar-harness" "server_started" "info" "" '{"port":8765}'
assert "sprint_id is null in JSON" 'python3 -c "
import json
lines = open(\"$TEST_TMP/events/all.jsonl\").readlines()
d = json.loads(lines[-1])
assert d[\"sprint_id\"] is None
"'
assert "no per-sprint file for empty sid" '[[ ! -f "$TEST_TMP/sprints/.events.jsonl" ]]'
echo ""

# ── TC3: Invalid severity → defaults to info ──
echo "TC3: Invalid severity defaults to info"
emit_event "hooks" "hook_executed" "INVALID_SEV" "sprint-test-002" '{}'
assert "severity coerced to info" 'python3 -c "
import json
lines = open(\"$TEST_TMP/events/all.jsonl\").readlines()
d = json.loads(lines[-1])
assert d[\"severity\"] == \"info\"
"'
echo ""

# ── TC4: Invalid JSON payload → wrapped in raw field ──
echo "TC4: Invalid JSON payload → wrapped in raw field"
emit_event "runner" "runner_exited" "warn" "sprint-test-003" 'not-valid-json'
assert "event still written" 'python3 -c "
import json
lines = open(\"$TEST_TMP/events/all.jsonl\").readlines()
d = json.loads(lines[-1])
assert d[\"actor\"] == \"runner\"
"'
assert "payload has raw field fallback" 'python3 -c "
import json
lines = open(\"$TEST_TMP/events/all.jsonl\").readlines()
d = json.loads(lines[-1])
assert \"raw\" in d[\"payload\"]
"'
echo ""

# ── TC5: Concurrent writes — 20 parallel emit_event calls ──
echo "TC5: Concurrent writes — 20 parallel emit_event (no torn JSON lines)"
for i in $(seq 1 20); do
  emit_event "coordinator" "dispatch_sent" "info" "sprint-concurrent" "{\"i\":$i}" &
done
wait
COUNT=$(wc -l < "$TEST_TMP/sprints/sprint-concurrent.events.jsonl" || echo 0)
assert "20 lines written" '[[ "$COUNT" -eq 20 ]]'
VALID=$(python3 -c "
import json
bad=0
for line in open('$TEST_TMP/sprints/sprint-concurrent.events.jsonl'):
    try: json.loads(line)
    except: bad+=1
print(bad)
")
assert "all 20 JSON lines are valid" '[[ "$VALID" -eq 0 ]]'
echo ""

# ── query_events test ──
echo "TC6: query_events returns correct count"
RESULT=$(query_events "sprint-test-001" 5 | wc -l | tr -d ' ')
assert "query returns ≤5 lines" '[[ "$RESULT" -le 5 ]]'
echo ""

# ── list_event_types test ──
echo "TC7: list_event_types returns unique event names"
TYPES=$(list_event_types)
assert "state_change in types" 'echo "$TYPES" | grep -q "state_change"'
assert "dispatch_sent in types" 'echo "$TYPES" | grep -q "dispatch_sent"'
echo ""

# ── TC8: events_emit remains stable if a caller wraps emit_event ──
echo "TC8: events_emit does not recurse when emit_event is overridden"
emit_event() {
  events_emit "$@"
}
events_emit "coordinator" "shim_state_changed" "info" "sprint-shim" '{"ok":true}'
assert "shim event written once" '[[ "$(grep -c "\"event\":\"shim_state_changed\"" "$TEST_TMP/events/all.jsonl")" -eq 1 ]]'
assert "shim per-sprint event written" '[[ -f "$TEST_TMP/sprints/sprint-shim.events.jsonl" ]]'
echo ""

# ── Summary ──
echo "=== Results: PASS=$PASS FAIL=$FAIL ==="
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
