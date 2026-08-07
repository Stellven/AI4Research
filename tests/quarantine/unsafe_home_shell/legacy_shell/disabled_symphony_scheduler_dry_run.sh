#!/usr/bin/env bash
# Test: scheduler dry-run produces state files + JSONL events, no codex process
set -eu

HARNESS_DIR="$HOME/.solar/harness"
SCHEDULER="$HARNESS_DIR/lib/symphony/scheduler.py"
STATE_DIR="$HARNESS_DIR/state/symphony"
LOG_FILE="$HARNESS_DIR/logs/symphony-events.jsonl"

echo "=== Test: Symphony Scheduler Dry-Run ==="

# Clean previous state
rm -f "$STATE_DIR"/{claimed,running,retry,completed}/*.json 2>/dev/null || true

# Test 1: --status returns valid JSON
echo -n "Test 1: --status returns valid JSON... "
output=$(python3 "$SCHEDULER" --status 2>&1)
has_fields=$(echo "$output" | python3 -c '
import json,sys
d=json.load(sys.stdin)
ok = all(k in d for k in ["claimed","running","retry","completed"])
print("yes" if ok else "no")
' 2>/dev/null)
if [[ "$has_fields" == "yes" ]]; then
  echo "PASS"
else
  echo "FAIL"
  exit 1
fi

# Test 2: --dry-run does not crash
echo -n "Test 2: --dry-run completes... "
python3 "$SCHEDULER" --dry-run 2>&1
echo "PASS"

# Test 3: state directory has correct subdirs
echo -n "Test 3: State dirs exist... "
for subdir in claimed running retry completed; do
  if [[ ! -d "$STATE_DIR/$subdir" ]]; then
    echo "FAIL (missing $subdir)"
    exit 1
  fi
done
echo "PASS"

# Test 4: Event log exists and has valid JSONL
echo -n "Test 4: Event log has valid JSONL... "
if [[ -f "$LOG_FILE" ]]; then
  line_count=$(wc -l < "$LOG_FILE" | tr -d ' ')
  if [[ "$line_count" -gt 0 ]]; then
    # Check first line is valid JSON
    first_line=$(head -1 "$LOG_FILE")
    is_json=$(echo "$first_line" | python3 -c 'import json,sys; json.load(sys.stdin); print("yes")' 2>/dev/null)
    if [[ "$is_json" == "yes" ]]; then
      echo "PASS ($line_count events)"
    else
      echo "FAIL (invalid JSON in log)"
      exit 1
    fi
  else
    echo "PASS (empty log, may be no candidates)"
  fi
else
  echo "FAIL (log file missing)"
  exit 1
fi

# Test 5: No codex process spawned
echo -n "Test 5: No codex app-server process... "
codex_count=$(pgrep -fc 'codex app-server' 2>/dev/null || echo "0")
if [[ "$codex_count" -eq 0 ]]; then
  echo "PASS"
else
  echo "FAIL ($codex_count codex processes found)"
  exit 1
fi

echo ""
echo "=== All scheduler tests PASSED ==="
