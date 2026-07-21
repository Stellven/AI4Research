#!/usr/bin/env bash
# Shim: invoke existing graph scheduler regression suite from the regression dir
# so run-vnext-regression-suite.sh can locate it under tests/regression/.
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
UPSTREAM="$HARNESS_DIR/tests/control_plane/test-graph-scheduler.sh"

if [[ ! -x "$UPSTREAM" && ! -f "$UPSTREAM" ]]; then
  echo "FAIL: upstream test missing: $UPSTREAM" >&2
  exit 2
fi

echo "[shim] delegating to $UPSTREAM"
exec bash "$UPSTREAM" "$@"
