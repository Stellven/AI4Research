#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR_REAL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HARNESS_DIR_REAL/solar-harness.sh"
TMPDIR_TEST="${TMPDIR:-/tmp}/solar-autosci-harness-entrypoint-$$"
mkdir -p "$TMPDIR_TEST"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

bash -n "$BIN"

HARNESS_DIR="$HARNESS_DIR_REAL" bash "$BIN" autosci '$skills' > "$TMPDIR_TEST/autosci-skills.json"
python3 - "$TMPDIR_TEST/autosci-skills.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["ok"] is True
assert payload["count"] == 28
skills = {item["skill"] for item in payload["skills"]}
assert {"ingest", "review", "research"}.issubset(skills)
PY

HARNESS_DIR="$HARNESS_DIR_REAL" bash "$BIN" '$skills' > "$TMPDIR_TEST/dollar-skills.json"
python3 - "$TMPDIR_TEST/dollar-skills.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["ok"] is True
assert payload["count"] == 28
PY

HARNESS_DIR="$HARNESS_DIR_REAL" bash "$BIN" autosci '$review --help' > "$TMPDIR_TEST/review-help.txt"
grep -q -- "--review-llm-evidence" "$TMPDIR_TEST/review-help.txt"
grep -q -- "--scheduler-run" "$TMPDIR_TEST/review-help.txt"

echo "PASS autosci harness entrypoint"
