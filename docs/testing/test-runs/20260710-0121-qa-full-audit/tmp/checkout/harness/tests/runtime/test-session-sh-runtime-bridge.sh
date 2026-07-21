#!/usr/bin/env bash
set -euo pipefail

REAL_HARNESS="${HOME}/.solar/harness"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/sprints"
ln -s "$REAL_HARNESS/lib" "$TMP/lib"

sid="sprint-test-session-sh-runtime-bridge"
HARNESS_DIR="$TMP" "$REAL_HARNESS/session.sh" append "$sid" '{"event":"planner_notified","by":"coordinator","data":{"status":"drafting"}}' >/dev/null

legacy="$TMP/sprints/${sid}.events.jsonl"
session="$TMP/sessions/${sid}/events.jsonl"

[[ -s "$legacy" ]] || { echo "FAIL session.sh legacy event missing"; exit 1; }
[[ -s "$session" ]] || { echo "FAIL session.sh runtime event missing"; exit 1; }

python3 - "$session" <<'PY'
import json
import sys
from pathlib import Path

events = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
assert any(e.get("type") == "log_message" and e.get("payload", {}).get("legacy_event") == "planner_notified" for e in events), events
assert any(e.get("type") == "command_issued" for e in events), events
print("PASS session.sh append dual-writes to session log")
PY

