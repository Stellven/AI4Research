#!/usr/bin/env bash
# livework_heartbeat_hook.sh — Fail-open wrapper for heartbeat runner.
#
# Called by autopilot or coordinator. Runs the Python heartbeat runner.
# If runner fails (exception, missing module, etc), hook exits 0 anyway
# so the caller is never blocked.

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
RUNNER="$HARNESS_DIR/autopilot/hooks/livework_heartbeat_runner.py"

if [[ ! -f "$RUNNER" ]]; then
    exit 0
fi

python3 "$RUNNER" 2>/dev/null || exit 0
