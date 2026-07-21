#!/usr/bin/env bash
set -euo pipefail

REAL_HARNESS="${HOME}/.solar/harness"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/sprints" "$TMP/events"
ln -s "$REAL_HARNESS/lib" "$TMP/lib"

export HARNESS_DIR="$TMP"
source "$REAL_HARNESS/lib/events.sh"

sid="sprint-test-events-runtime-bridge"
emit_event "coordinator" "dispatch_queued" "info" "$sid" '{"target":"0.1","round":1}'

legacy="$TMP/sprints/${sid}.events.jsonl"
session="$TMP/sessions/${sid}/events.jsonl"

[[ -s "$legacy" ]] || { echo "FAIL legacy event missing"; exit 1; }
[[ -s "$session" ]] || { echo "FAIL session event missing"; exit 1; }

python3 - "$session" <<'PY'
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
types = {e.get("type") for e in events}
assert "log_message" in types, types
assert "command_issued" in types, types
cmd = next(e for e in events if e.get("type") == "command_issued")
assert cmd.get("payload", {}).get("target") == "0.1", cmd
assert cmd.get("payload", {}).get("round") == 1, cmd
print("PASS events.sh dual-writes legacy events to session log")
PY

