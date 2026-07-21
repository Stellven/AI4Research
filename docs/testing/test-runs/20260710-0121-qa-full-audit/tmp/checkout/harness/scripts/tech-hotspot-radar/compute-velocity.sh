#!/usr/bin/env bash
# scripts/tech-hotspot-radar/compute-velocity.sh - Compute velocity and detector outputs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

DB_PATH=""
REPO=""
DRY_RUN="false"
WORK_DB_PATH=""
TEMP_DB_PATH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db) DB_PATH="$2"; shift 2 ;;
        --repo) REPO="$2"; shift 2 ;;
        --dry-run) DRY_RUN="true"; shift ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$DB_PATH" ]]; then
    echo "Usage: compute-velocity.sh --db <path> [--repo <owner/name>] [--dry-run]" >&2
    exit 1
fi

WORK_DB_PATH="$DB_PATH"
cleanup() {
    if [[ -n "$TEMP_DB_PATH" && -f "$TEMP_DB_PATH" ]]; then
        rm -f "$TEMP_DB_PATH"
    fi
}
trap cleanup EXIT

if [[ "$DRY_RUN" == "true" ]]; then
    TEMP_DB_PATH="$(mktemp "${TMPDIR:-/tmp}/compute-velocity-dryrun.XXXXXX.sqlite")"
    cp "$DB_PATH" "$TEMP_DB_PATH"
    WORK_DB_PATH="$TEMP_DB_PATH"
fi

mapfile -t REPOS < <(
    python3 - <<'PY' "$WORK_DB_PATH" "$REPO"
import sqlite3, sys
db_path, repo = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(db_path)
if repo:
    print(repo)
else:
    for row in conn.execute(
        "SELECT DISTINCT full_name FROM github_star_snapshots ORDER BY full_name"
    ):
        print(row[0])
conn.close()
PY
)

if [[ "${#REPOS[@]}" -eq 0 ]]; then
    echo '{"ok": true, "processed": 0, "message": "no repositories found"}'
    exit 0
fi

processed=0
for full_name in "${REPOS[@]}"; do
    [[ -z "$full_name" ]] && continue
    args=(--db "$WORK_DB_PATH" --repo "$full_name")
    bash "$LIB_DIR/velocity-engine.sh" "${args[@]}" >/dev/null
    bash "$LIB_DIR/anomaly-detectors.sh" "${args[@]}" >/dev/null
    processed=$((processed + 1))
done

echo "{\"ok\": true, \"processed\": $processed, \"dry_run\": $( [[ \"$DRY_RUN\" == \"true\" ]] && echo true || echo false )}"
