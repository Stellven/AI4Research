#!/bin/bash
# Code Signal Plane — daily pipeline wrapper
# Per S1-plan: launchd/crontab changes deferred to S5.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HARNESS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

python3 "$HARNESS_ROOT/scripts/code_signal_plane.py" \
    --knowledge-root "${KNOWLEDGE_ROOT:-$HOME/Knowledge}" \
    --db-path "${CODE_SIGNAL_DB:-$HOME/.solar/harness/state/code-signal-plane.sqlite}" \
    --dry-run
