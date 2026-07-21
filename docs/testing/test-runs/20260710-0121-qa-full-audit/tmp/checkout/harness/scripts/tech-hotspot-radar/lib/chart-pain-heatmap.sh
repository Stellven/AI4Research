#!/usr/bin/env bash
# scripts/tech-hotspot-radar/lib/chart-pain-heatmap.sh - ECharts heatmap for risk x tier
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
[[ -z "$DB_PATH" ]] && { echo "Usage: chart-pain-heatmap.sh --db <path> [--output <file>]" >&2; exit 1; }

python3 - <<'PY' "$DB_PATH" "$OUTPUT"
import json, sqlite3, sys
db_path, output = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
tiers = ["S", "A", "B", "C"]
risks = ["none", "unverified", "license_issue", "security_watch"]
matrix = {(risk, tier): 0 for risk in risks for tier in tiers}
rows = conn.execute("SELECT risk_classification, tier FROM repo_analysis_cards").fetchall()
for r in rows:
    risk = r["risk_classification"] or "none"
    tier = r["tier"] or "B"
    if (risk, tier) in matrix:
        matrix[(risk, tier)] += 1
data = [[tiers.index(tier), risks.index(risk), count] for (risk, tier), count in matrix.items()]
spec = {
    "title": {"text": "Pain Point Heatmap"},
    "tooltip": {"position": "top"},
    "xAxis": {"type": "category", "data": tiers, "name": "tier"},
    "yAxis": {"type": "category", "data": risks, "name": "risk"},
    "visualMap": {"min": 0, "max": max([d[2] for d in data] or [1]), "calculable": True, "orient": "horizontal"},
    "series": [{"type": "heatmap", "data": data}],
}
payload = json.dumps(spec, ensure_ascii=False, indent=2)
if output:
    open(output, "w", encoding="utf-8").write(payload + "\n")
else:
    print(payload)
conn.close()
PY
