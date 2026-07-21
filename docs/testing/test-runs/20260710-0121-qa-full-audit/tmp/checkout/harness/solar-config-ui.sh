#!/bin/bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
SERVER="$HARNESS_DIR/integrations/solar-config-server.py"

if [[ ! -f "$SERVER" ]]; then
  echo "solar-config-server.py not found: $SERVER" >&2
  exit 1
fi

exec python3 "$SERVER" "${@:-status}"

