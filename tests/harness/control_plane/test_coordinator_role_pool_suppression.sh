#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../harness" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export COORD_NO_MAIN=1
export HARNESS_DIR="$TMP/harness"
export SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH=1
mkdir -p "$HARNESS_DIR/run/operator-status" "$HARNESS_DIR/run/pm-inbox" "$HARNESS_DIR/run/operator-results/op" "$HARNESS_DIR/sprints"

# Keep sourced coordinator dependencies quiet/minimal.
touch "$HARNESS_DIR/PLANNER-INBOX.md"

# shellcheck source=/dev/null
. "$ROOT/coordinator.sh"

sid="sprint-role-pool-planner"

if pm_operator_role_pool_task_seen "$sid" "planner"; then
  echo "FAIL: role-pool task falsely detected before any records exist" >&2
  exit 1
fi

cat > "$HARNESS_DIR/run/operator-status/mini-codex-planner.json" <<JSON
{"operator_id":"mini-codex-planner","runtime_state":"running","current_task_id":"pm-${sid}-N0-abc123","requested_role":"planner"}
JSON

if ! pm_operator_role_pool_task_seen "$sid" "planner"; then
  echo "FAIL: active planner operator task was not detected" >&2
  exit 1
fi

rm "$HARNESS_DIR/run/operator-status/mini-codex-planner.json"
cat > "$HARNESS_DIR/run/pm-inbox/pm-${sid}-N0-abc123.json" <<JSON
{"task_id":"pm-${sid}-N0-abc123","requested_role":"planner","status":"submitted"}
JSON

if ! pm_operator_role_pool_task_seen "$sid" "planner"; then
  echo "FAIL: planner pm-inbox task was not detected" >&2
  exit 1
fi

rm "$HARNESS_DIR/run/pm-inbox/pm-${sid}-N0-abc123.json"
mkdir -p "$HARNESS_DIR/run/operator-results/op/pm-${sid}-N0-abc123"

if ! pm_operator_role_pool_task_seen "$sid" "planner"; then
  echo "FAIL: planner operator-result directory was not detected" >&2
  exit 1
fi

echo "PASS coordinator role-pool planner detection"
