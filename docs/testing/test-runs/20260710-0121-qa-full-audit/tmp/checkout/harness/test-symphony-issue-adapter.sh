#!/usr/bin/env bash
# Test: issue-adapter --list returns valid JSON list; --one returns single object
set -eu

HARNESS_DIR="$HOME/.solar/harness"
ADAPTER="$HARNESS_DIR/lib/symphony/issue-adapter.py"

echo "=== Test: Symphony Issue Adapter ==="

# Test 1: --list returns valid JSON list
echo -n "Test 1: --list returns JSON list... "
output=$(python3 "$ADAPTER" --list 2>&1)
count=$(echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d))' 2>/dev/null)
if [[ -n "$count" ]] && [[ "$count" -ge 0 ]]; then
  echo "PASS ($count issues)"
else
  echo "FAIL"
  exit 1
fi

# Test 2: --list with --states filter
echo -n "Test 2: --list --states active... "
output=$(python3 "$ADAPTER" --list --states active 2>&1)
is_list=$(echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("yes" if isinstance(d,list) else "no")' 2>/dev/null)
if [[ "$is_list" == "yes" ]]; then
  echo "PASS"
else
  echo "FAIL"
  exit 1
fi

# Test 3: --one with a known sprint
echo -n "Test 3: --one with known sprint... "
known_sid=$(ls "$HARNESS_DIR/sprints/"*.status.json 2>/dev/null | head -1 | xargs -I{} python3 -c "import json; print(json.load(open('{}'))['id'])" 2>/dev/null)
if [[ -n "$known_sid" ]]; then
  output=$(python3 "$ADAPTER" --one "$known_sid" 2>&1)
  has_id=$(echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("yes" if d.get("id") else "no")' 2>/dev/null)
  has_fields=$(echo "$output" | python3 -c '
import json,sys
d=json.load(sys.stdin)
required = ["id","identifier","title","priority","state","labels","blocked_by","created_at","updated_at","contract_path"]
missing = [f for f in required if f not in d]
print("yes" if not missing else "missing: " + ",".join(missing))
' 2>/dev/null)
  if [[ "$has_id" == "yes" && "$has_fields" == "yes" ]]; then
    echo "PASS ($known_sid)"
  else
    echo "FAIL (fields: $has_fields)"
    exit 1
  fi
else
  echo "SKIP (no sprints found)"
fi

echo ""
echo "=== All issue-adapter tests PASSED ==="
