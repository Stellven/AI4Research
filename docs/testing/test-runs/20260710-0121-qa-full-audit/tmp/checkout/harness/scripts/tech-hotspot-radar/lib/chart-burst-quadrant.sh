#!/usr/bin/env bash
# scripts/tech-hotspot-radar/lib/chart-burst-quadrant.sh - ECharts spec for velocity x potential
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
[[ -z "$DB_PATH" ]] && { echo "Usage: chart-burst-quadrant.sh --db <path> [--output <file>]" >&2; exit 1; }

python3 - <<'PY' "$DB_PATH" "$OUTPUT"
import json, sqlite3, sys
db_path, output = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT v.repo_full_name, v.star_delta_7d, json_extract(c.scores_json, '$.potential_score') AS potential
    FROM repo_velocity_metrics v
    LEFT JOIN repo_analysis_cards c ON c.repo_full_name = v.repo_full_name
    ORDER BY v.star_delta_7d DESC
    LIMIT 60
    """
).fetchall()
spec = {
    "title": {"text": "Burst Quadrant"},
    "tooltip": {"trigger": "item"},
    "xAxis": {"name": "7d velocity", "type": "value"},
    "yAxis": {"name": "potential", "type": "value", "min": 0, "max": 1},
    "series": [{
        "type": "scatter",
        "symbolSize": 14,
        "data": [[int(r["star_delta_7d"] or 0), float(r["potential"] or 0), r["repo_full_name"]] for r in rows],
    }],
}
payload = json.dumps(spec, ensure_ascii=False, indent=2)
if output:
    open(output, "w", encoding="utf-8").write(payload + "\n")
else:
    print(payload)
conn.close()
PY
