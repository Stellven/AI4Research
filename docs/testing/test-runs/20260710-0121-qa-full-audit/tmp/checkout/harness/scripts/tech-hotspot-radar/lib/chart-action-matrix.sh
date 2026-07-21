#!/usr/bin/env bash
# scripts/tech-hotspot-radar/lib/chart-action-matrix.sh - ECharts bar chart for strategy decisions
set -euo pipefail

DB_PATH=""
OUTPUT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --db) DB_PATH="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done
[[ -z "$DB_PATH" ]] && { echo "Usage: chart-action-matrix.sh --db <path> [--output <file>]" >&2; exit 1; }

python3 - <<'PY' "$DB_PATH" "$OUTPUT"
import json, sqlite3, sys
db_path, output = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(db_path)
rows = conn.execute(
    "SELECT decision, COUNT(*) FROM task_candidates GROUP BY decision ORDER BY COUNT(*) DESC, decision ASC"
).fetchall()
labels = [r[0] for r in rows]
values = [int(r[1]) for r in rows]
spec = {
    "title": {"text": "Action Matrix"},
    "tooltip": {"trigger": "axis"},
    "xAxis": {"type": "category", "data": labels},
    "yAxis": {"type": "value", "name": "candidate_count"},
    "series": [{"type": "bar", "data": values}],
}
payload = json.dumps(spec, ensure_ascii=False, indent=2)
if output:
    open(output, "w", encoding="utf-8").write(payload + "\n")
else:
    print(payload)
conn.close()
PY
