#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-${HOME}/Solar/harness}"
CONFIG="${GITHUB_TRENDS_CONFIG:-$HARNESS_DIR/config/github-trends.yaml}"
PYTHON="${PYTHON:-python3}"

echo "[github-trends-digest] retired: raw digest report/email generation is disabled; use tech_hotspot_radar.py github-trend-report" >&2
exec "$PYTHON" "$HARNESS_DIR/scripts/github_trends_digest.py" collect --config "$CONFIG" "$@"
