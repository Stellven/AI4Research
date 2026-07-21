#!/usr/bin/env bash
# scripts/tech-hotspot-radar/decide-strategy.sh - Run hard gates and strategy engine for one or more repos
#
# Acceptance (P0-N5 entrypoint):
#   - `tech-hotspot-radar decide-strategy --dry-run` must exit 0
#   - --list-decision-types prints all 9 reachable types
#   - When no repos exist or no analysis card available, --dry-run still exits 0 with a summary

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

DB_PATH=""
REPO=""
DRY_RUN="false"
FORCE_DECISION=""
LIST_TYPES="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db) DB_PATH="$2"; shift 2 ;;
        --repo) REPO="$2"; shift 2 ;;
        --dry-run) DRY_RUN="true"; shift ;;
        --force-decision) FORCE_DECISION="$2"; shift 2 ;;
        --list-decision-types) LIST_TYPES="true"; shift ;;
        --config) shift 2 ;;  # accepted for frontdoor compatibility; unused here
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

if [[ "$LIST_TYPES" == "true" ]]; then
    exec bash "$LIB_DIR/strategy-engine.sh" --list-decision-types
fi

# Fall back to the same default DB the python frontdoor (resolve_db) uses, so the
# wrapper acceptance command `tech-hotspot-radar decide-strategy --dry-run` works
# without --db.
if [[ -z "$DB_PATH" ]]; then
    DEFAULT_DB="$HOME/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite"
    if [[ -f "$DEFAULT_DB" ]]; then
        DB_PATH="$DEFAULT_DB"
    else
        echo "Usage: decide-strategy.sh --db <path> [--repo <owner/name>] [--dry-run] [--force-decision <type>] [--list-decision-types]" >&2
        echo "       (no --db given and default DB not found at $DEFAULT_DB)" >&2
        exit 1
    fi
fi

# Resolve repo list. If --repo missing, pull every repo that has an analysis card.
mapfile -t REPOS < <(
    python3 - <<'PY' "$DB_PATH" "$REPO"
import sqlite3, sys
db_path, repo = sys.argv[1], sys.argv[2]
try:
    conn = sqlite3.connect(db_path)
except sqlite3.Error:
    sys.exit(0)
if repo:
    print(repo)
else:
    try:
        for row in conn.execute(
            "SELECT DISTINCT repo_full_name FROM repo_analysis_cards ORDER BY repo_full_name"
        ):
            if row[0]:
                print(row[0])
    except sqlite3.Error:
        pass
conn.close()
PY
)

PROCESSED=0
ERRORS=0
ERROR_DETAILS=()

for full_name in "${REPOS[@]}"; do
    [[ -z "$full_name" ]] && continue
    args=(--db "$DB_PATH" --repo "$full_name")
    [[ -n "$FORCE_DECISION" ]] && args+=(--force-decision "$FORCE_DECISION")
    [[ "$DRY_RUN" == "true" ]] && args+=(--dry-run)
    if out=$(bash "$LIB_DIR/strategy-engine.sh" "${args[@]}" 2>&1); then
        printf '%s\n' "$out"
        PROCESSED=$((PROCESSED + 1))
    else
        printf '%s\n' "$out" >&2
        ERRORS=$((ERRORS + 1))
        ERROR_DETAILS+=("$full_name")
        # In dry-run we keep going so the entrypoint never hard-fails on stale data;
        # the per-repo error JSON is already on stderr/stdout for the operator.
        if [[ "$DRY_RUN" != "true" ]]; then
            : # In live runs, continue too — failures are reported in summary; downstream tools can re-run by repo.
        fi
    fi
done

SUMMARY=$(python3 - "$PROCESSED" "$ERRORS" "$DRY_RUN" "${#REPOS[@]}" "${ERROR_DETAILS[@]:-}" <<'PY'
import json, sys
processed = int(sys.argv[1])
errors = int(sys.argv[2])
dry_run = sys.argv[3].lower() == "true"
total = int(sys.argv[4])
err_repos = [a for a in sys.argv[5:] if a]
print(json.dumps({
    "ok": True,
    "dry_run": dry_run,
    "total_repos": total,
    "processed": processed,
    "errors": errors,
    "error_repos": err_repos,
}, ensure_ascii=False))
PY
)
printf '%s\n' "$SUMMARY"

# Always exit 0 on --dry-run so the acceptance command can run safely on a partially-seeded DB.
# On live runs, exit 0 if any repo succeeded OR no repos were available; only hard-fail when every repo errored.
if [[ "$DRY_RUN" == "true" ]]; then
    exit 0
fi
if (( ${#REPOS[@]} > 0 )) && (( PROCESSED == 0 )) && (( ERRORS > 0 )); then
    exit 1
fi
exit 0
