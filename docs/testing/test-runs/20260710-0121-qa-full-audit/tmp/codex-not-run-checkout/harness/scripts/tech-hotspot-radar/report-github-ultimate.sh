#!/usr/bin/env bash
# scripts/tech-hotspot-radar/report-github-ultimate.sh - Internal daily markdown report for GitHub ultimate analyzer
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

DB_PATH=""
DATE_STR="$(date -u +%Y-%m-%d)"
OUTPUT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db) DB_PATH="$2"; shift 2 ;;
        --date) DATE_STR="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        --daily) shift ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done
[[ -z "$DB_PATH" ]] && { echo "Usage: report-github-ultimate.sh --db <path> [--date YYYY-MM-DD] [--output file]" >&2; exit 1; }

if [[ -n "$OUTPUT" ]]; then
    TMP_DIR="$(cd "$(dirname "$OUTPUT")" && pwd)"
else
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT
fi
BURST_PATH="$TMP_DIR/github-ultimate-burst.json"
PAIN_PATH="$TMP_DIR/github-ultimate-pain.json"
ACTION_PATH="$TMP_DIR/github-ultimate-action.json"
bash "$LIB_DIR/chart-burst-quadrant.sh" --db "$DB_PATH" --output "$BURST_PATH"
bash "$LIB_DIR/chart-pain-heatmap.sh" --db "$DB_PATH" --output "$PAIN_PATH"
bash "$LIB_DIR/chart-action-matrix.sh" --db "$DB_PATH" --output "$ACTION_PATH"

python3 - <<'PY' "$DB_PATH" "$DATE_STR" "$BURST_PATH" "$PAIN_PATH" "$ACTION_PATH" "$OUTPUT"
import json, sqlite3, sys
from pathlib import Path

db_path, date_str = sys.argv[1], sys.argv[2]
burst_path, pain_path, action_path = Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
output = sys.argv[6]
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
top_movers = conn.execute(
    "SELECT repo_full_name, star_delta_24h, star_delta_7d, acceleration FROM repo_velocity_metrics ORDER BY star_delta_7d DESC, star_delta_24h DESC LIMIT 8"
).fetchall()
detectors = conn.execute(
    "SELECT repo_full_name, detector_name, score FROM detector_results WHERE matched=1 ORDER BY score DESC, repo_full_name ASC LIMIT 12"
).fetchall()
decisions = conn.execute(
    "SELECT repo_full_name, decision, confidence, recommended_action FROM repo_strategy_decisions ORDER BY updated_at DESC LIMIT 12"
).fetchall()
lines = [
    f"# AI Influence GitHub Ultimate — {date_str}",
    "",
    "## Top Movers",
    "",
]
for row in top_movers:
    lines.append(f"- **{row['repo_full_name']}** 24h={int(row['star_delta_24h'] or 0)} 7d={int(row['star_delta_7d'] or 0)} accel={float(row['acceleration'] or 0):.2f}")
lines.extend(["", "## Detector Results", ""])
for row in detectors:
    lines.append(f"- **{row['repo_full_name']}** {row['detector_name']} score={float(row['score'] or 0):.3f}")
lines.extend(["", "## Strategy Decisions", ""])
for row in decisions:
    lines.append(f"- **{row['repo_full_name']}** -> `{row['decision']}` confidence={float(row['confidence'] or 0):.3f} — {row['recommended_action']}")
lines.extend([
    "",
    "## Chart Embeds",
    "",
    f"- burst_quadrant: `{burst_path}`",
    f"- pain_heatmap: `{pain_path}`",
    f"- action_matrix: `{action_path}`",
    "",
    "## Provenance",
    "",
    "- source: tech-hotspot-radar/github-ultimate",
    "- charts: ECharts JSON specs",
    "- decisions: repo_strategy_decisions",
    "- detectors: detector_results",
])
text = "\n".join(lines).rstrip() + "\n"
if output:
    Path(output).write_text(text, encoding="utf-8")
else:
    print(text, end="")
conn.close()
PY
