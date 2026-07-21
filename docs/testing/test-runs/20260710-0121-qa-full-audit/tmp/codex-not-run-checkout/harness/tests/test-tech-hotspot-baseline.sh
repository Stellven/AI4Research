#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/tech-hotspot-baseline-test-$$"
DB="$TMP_DIR/tech-hotspot-baseline.sqlite"
mkdir -p "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

python3 "$ROOT/scripts/tech_hotspot_radar.py" --db "$DB" build-baseline --days 180 --limit 3 >/tmp/thr-baseline-build.json
python3 "$ROOT/scripts/tech_hotspot_radar.py" --db "$DB" analyze-baseline --write-report >/tmp/thr-baseline-analysis.json

python3 - "$DB" <<'PY'
import json
import os
import sqlite3
import sys

build = json.load(open("/tmp/thr-baseline-build.json"))
analysis = json.load(open("/tmp/thr-baseline-analysis.json"))
assert build["ok"] is True
assert analysis["ok"] is True
assert {"1d", "7d", "30d", "180d"} <= set(analysis["analysis"]["windows"])
conn = sqlite3.connect(sys.argv[1])
assert conn.execute("SELECT COUNT(*) FROM baseline_signals").fetchone()[0] > 0
assert os.path.exists(analysis["files"]["markdown"])
PY

echo "tech_hotspot_baseline ok"
