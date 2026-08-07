#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PASS=0
FAIL=0
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT
mkdir -p "$TMPDIR_TEST/sprints"

ok() { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

SID="sprint-test-epic-child"
UPSTREAM="sprint-test-upstream"
STATUS_FILE="$TMPDIR_TEST/sprints/${SID}.status.json"
UPSTREAM_FILE="$TMPDIR_TEST/sprints/${UPSTREAM}.status.json"
TRANSITION_FILE="$TMPDIR_TEST/transition.json"

cat >"$STATUS_FILE" <<JSON
{
  "id": "$SID",
  "sprint_id": "$SID",
  "status": "queued",
  "phase": "epic_waiting_dependency",
  "dependency_policy": "activated_by_epic_dag",
  "blocked_by": "$UPSTREAM"
}
JSON

cat >"$UPSTREAM_FILE" <<JSON
{
  "id": "$UPSTREAM",
  "sprint_id": "$UPSTREAM",
  "status": "passed",
  "phase": "finalized"
}
JSON

export HARNESS_DIR="$TMPDIR_TEST"
export SPRINTS_DIR="$TMPDIR_TEST/sprints"
export COORD_NO_MAIN=1
source ./coordinator.sh

log() { :; }
rollback_state_cache() { :; }
runtime_status_transition() {
  printf '{"sid":"%s","status":"%s","reason":"%s","by":"%s"}\n' "$1" "$2" "$3" "$4" >"$TRANSITION_FILE"
}

handle_queued "$SID" "$STATUS_FILE"

python3 - "$TRANSITION_FILE" <<'PY' || fail "epic child unblock did not promote queued sprint"
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
if not p.exists():
    raise SystemExit(1)
payload = json.loads(p.read_text())
assert payload["sid"] == "sprint-test-epic-child"
assert payload["status"] == "drafting"
assert payload["reason"] == "queued_unblocked"
PY
ok "epic child queued sprint auto-promotes after dependency reaches terminal state"

bash -n ./coordinator.sh && ok "coordinator.sh syntax ok" || fail "coordinator.sh syntax failed"

echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -eq 0 ]]; then echo "PASS"; exit 0; else echo "FAIL"; exit 1; fi
