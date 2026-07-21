#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
COORD_TS="$HARNESS_DIR/coordinator.ts"

grep -q 'PM: `${SESSION_NAME}:0.0`' "$COORD_TS" || {
  echo "coordinator.ts missing current PM pane mapping" >&2
  exit 1
}

grep -q 'PLANNER: `${SESSION_NAME}:0.1`' "$COORD_TS" || {
  echo "coordinator.ts missing current Planner pane mapping" >&2
  exit 1
}

grep -q 'BUILDER: `${SESSION_NAME}:0.2`' "$COORD_TS" || {
  echo "coordinator.ts missing current Builder pane mapping" >&2
  exit 1
}

grep -q 'EVALUATOR: `${SESSION_NAME}:0.3`' "$COORD_TS" || {
  echo "coordinator.ts missing current Evaluator pane mapping" >&2
  exit 1
}

if grep -q 'PLANNER: `${SESSION_NAME}:0.0`\|BUILDER: `${SESSION_NAME}:0.1`\|EVALUATOR: `${SESSION_NAME}:0.2`' "$COORD_TS"; then
  echo "coordinator.ts still contains old pane mapping" >&2
  exit 1
fi

grep -q 'pane === PANE.BUILDER || pane === PANE.EVALUATOR' "$COORD_TS" || {
  echo "coordinator.ts pre-unlock is not role-based" >&2
  exit 1
}

echo "PASS coordinator.ts uses current Product Delivery pane map"
