#!/usr/bin/env bash
# tests/test-status-identity-repair.sh — coordinator repairs readable status files missing id/sprint_id

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
export COORD_NO_MAIN=1

# shellcheck disable=SC1091
. "$HARNESS_DIR/coordinator.sh"

PASS=0
FAIL=0
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

check() {
  local label="$1" got="$2" want="$3"
  if [[ "$got" == "$want" ]]; then
    echo "  ✅ $label"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $label"
    echo "       want: $want"
    echo "        got: $got"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== test-status-identity-repair.sh ==="

sf="$TMP_DIR/sprint-identity-repair.status.json"
cat > "$sf" <<'JSON'
{
  "status": "queued",
  "phase": "contract_ready",
  "handoff_to": "planner"
}
JSON

result="$(repair_status_identity "$sf")"
id="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("id",""))' "$sf")"
sprint_id="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("sprint_id",""))' "$sf")"
event="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("history", [{}])[-1].get("event",""))' "$sf")"

check "missing identity is repaired" "$result" "repaired"
check "id recovered from filename" "$id" "sprint-identity-repair"
check "sprint_id recovered from filename" "$sprint_id" "sprint-identity-repair"
check "history records repair" "$event" "status_identity_repaired"

result2="$(repair_status_identity "$sf")"
check "second repair is idempotent" "$result2" "ok"

bad="$TMP_DIR/sprint-bad.status.json"
printf '{not-json' > "$bad"
if repair_status_identity "$bad" >/dev/null 2>&1; then
  got=0
else
  got=1
fi
check "unreadable JSON is not rewritten" "$got" "1"

echo ""
echo "=== RESULT: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]
