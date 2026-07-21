#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CHAIN_WATCHER="$HARNESS_DIR/chain-watcher.sh"

fail() {
  echo "FAIL $*" >&2
  exit 1
}

bash -n "$CHAIN_WATCHER" || fail "chain-watcher syntax failed"

grep -q 'resolve_planner_pane_target()' "$CHAIN_WATCHER" \
  || fail "missing runtime Planner pane resolver"

grep -q 'Planner|规划者' "$CHAIN_WATCHER" \
  || fail "resolver does not match Planner pane title"

if grep -q '^PANE0_TARGET="solar-harness:0.0"' "$CHAIN_WATCHER"; then
  fail "chain-watcher still hardcodes pane0 as Planner"
fi

grep -q 'PANE_PLANNER_FALLBACK_TARGET="solar-harness:0.1"' "$CHAIN_WATCHER" \
  || fail "fallback target should match current Product Delivery Planner pane"

echo "PASS chain-watcher resolves Planner pane dynamically"
