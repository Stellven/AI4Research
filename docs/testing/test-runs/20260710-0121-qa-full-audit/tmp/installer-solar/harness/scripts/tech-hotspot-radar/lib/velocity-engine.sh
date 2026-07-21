#!/usr/bin/env bash
# scripts/tech-hotspot-radar/lib/velocity-engine.sh - Compute repo velocity metrics from star snapshots
set -euo pipefail

compute_repo_velocity() {
    local db_path="$1"
    local repo_full_name="$2"
    local dry_run="${3:-false}"

    python3 - <<'PY' "$db_path" "$repo_full_name" "$dry_run"
import datetime as dt
import json
import sqlite3
import sys

db_path, repo, dry_run = sys.argv[1], sys.argv[2], sys.argv[3].lower() == "true"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS repo_velocity_metrics (
        repo_full_name TEXT PRIMARY KEY,
        latest_snapshot_at TEXT NOT NULL,
        stars_latest INTEGER NOT NULL DEFAULT 0,
        star_delta_24h INTEGER NOT NULL DEFAULT 0,
        star_delta_7d INTEGER NOT NULL DEFAULT 0,
        star_delta_30d INTEGER NOT NULL DEFAULT 0,
        acceleration REAL NOT NULL DEFAULT 0,
        evidence_map_json TEXT NOT NULL DEFAULT '[]',
        updated_at TEXT NOT NULL
    )
    """
)
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS detector_results (
        repo_full_name TEXT NOT NULL,
        detector_name TEXT NOT NULL,
        matched INTEGER NOT NULL DEFAULT 0,
        score REAL NOT NULL DEFAULT 0,
        evidence_map_json TEXT NOT NULL DEFAULT '[]',
        details_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL,
        PRIMARY KEY (repo_full_name, detector_name)
    )
    """
)

rows = conn.execute(
    "SELECT snapshot_at, stars FROM github_star_snapshots WHERE full_name=? ORDER BY snapshot_at ASC",
    (repo,),
).fetchall()
if not rows:
    print(json.dumps({"ok": False, "repo": repo, "error": "no github_star_snapshots"}, ensure_ascii=False))
    sys.exit(1)

def parse_ts(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")

snapshots = [(parse_ts(r["snapshot_at"]), int(r["stars"] or 0), r["snapshot_at"]) for r in rows]
latest_dt, latest_stars, latest_at = snapshots[-1]

def delta_for(days: int) -> tuple[int, str]:
    target = latest_dt - dt.timedelta(days=days)
    candidate = snapshots[0]
    for item in snapshots:
        if item[0] <= target:
            candidate = item
        else:
            break
    base_dt, base_stars, base_raw = candidate
    return max(0, latest_stars - base_stars), base_raw

delta_24h, base_24h = delta_for(1)
delta_7d, base_7d = delta_for(7)
delta_30d, base_30d = delta_for(30)
avg_7d = delta_7d / 7.0 if delta_7d else 0.0
acceleration = round(delta_24h - avg_7d, 4)
updated_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
evidence_map = [
    {"kind": "latest_snapshot", "snapshot_at": latest_at, "stars": latest_stars},
    {"kind": "baseline_24h", "snapshot_at": base_24h},
    {"kind": "baseline_7d", "snapshot_at": base_7d},
    {"kind": "baseline_30d", "snapshot_at": base_30d},
]
payload = {
    "ok": True,
    "repo": repo,
    "latest_snapshot_at": latest_at,
    "stars_latest": latest_stars,
    "star_delta_24h": delta_24h,
    "star_delta_7d": delta_7d,
    "star_delta_30d": delta_30d,
    "acceleration": acceleration,
    "evidence_map": evidence_map,
}

if not dry_run:
    conn.execute(
        """
        INSERT INTO repo_velocity_metrics
        (repo_full_name, latest_snapshot_at, stars_latest, star_delta_24h, star_delta_7d,
         star_delta_30d, acceleration, evidence_map_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(repo_full_name) DO UPDATE SET
          latest_snapshot_at=excluded.latest_snapshot_at,
          stars_latest=excluded.stars_latest,
          star_delta_24h=excluded.star_delta_24h,
          star_delta_7d=excluded.star_delta_7d,
          star_delta_30d=excluded.star_delta_30d,
          acceleration=excluded.acceleration,
          evidence_map_json=excluded.evidence_map_json,
          updated_at=excluded.updated_at
        """,
        (repo, latest_at, latest_stars, delta_24h, delta_7d, delta_30d, acceleration, json.dumps(evidence_map, ensure_ascii=False), updated_at),
    )
    try:
        pkt = conn.execute(
            "SELECT scores_json FROM project_reasoning_packets WHERE repo_full_name=? ORDER BY created_at DESC LIMIT 1",
            (repo,),
        ).fetchone()
        if pkt:
            scores = json.loads(pkt["scores_json"] or "{}")
            scores.update({
                "star_delta_24h": delta_24h,
                "star_delta_7d": delta_7d,
                "star_delta_30d": delta_30d,
                "acceleration": acceleration,
                "heat_score": round(min(1.0, max(delta_24h, delta_7d / 7.0) / 100.0), 4),
            })
            conn.execute(
                """
                UPDATE project_reasoning_packets
                SET scores_json=?
                WHERE repo_full_name=? AND created_at=(
                    SELECT MAX(created_at) FROM project_reasoning_packets WHERE repo_full_name=?
                )
                """,
                (json.dumps(scores, ensure_ascii=False), repo, repo),
            )
    except Exception:
        pass
    conn.commit()

print(json.dumps(payload, ensure_ascii=False))
conn.close()
PY
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    DB_PATH=""
    REPO=""
    DRY_RUN="false"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --db) DB_PATH="$2"; shift 2 ;;
            --repo) REPO="$2"; shift 2 ;;
            --dry-run) DRY_RUN="true"; shift ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done
    if [[ -z "$DB_PATH" || -z "$REPO" ]]; then
        echo "Usage: velocity-engine.sh --db <path> --repo <owner/name> [--dry-run]" >&2
        exit 1
    fi
    compute_repo_velocity "$DB_PATH" "$REPO" "$DRY_RUN"
fi
