#!/usr/bin/env bash
set -euo pipefail

REAL_HARNESS="${HOME}/.solar/harness"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/sprints"
ln -s "$REAL_HARNESS/lib" "$TMP/lib"

sid="sprint-test-phase-runtime-bridge"
cat > "$TMP/sprints/${sid}.status.json" <<JSON
{
  "id": "$sid",
  "sprint_id": "$sid",
  "status": "drafting",
  "phase": "spec",
  "round": 0,
  "history": []
}
JSON
cat > "$TMP/sprints/${sid}.contract.md" <<'MD'
# Contract

## Done
- Runtime phase transition writes session-log evidence.
MD

HARNESS_DIR="$TMP" "$REAL_HARNESS/lib/phase-state-machine.sh" transition "$sid" spec plan >/dev/null

python3 - "$TMP" "$sid" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
sid = sys.argv[2]
status = json.loads((root / "sprints" / f"{sid}.status.json").read_text())
assert status["phase"] == "plan", status
session = root / "sessions" / sid / "events.jsonl"
events = [json.loads(line) for line in session.read_text().splitlines() if line.strip()]
types = [e.get("type") for e in events]
assert "log_message" in types, types
assert "state_transition" in types, types
print("PASS phase-state-machine dual-writes phase transitions to session log")
PY
