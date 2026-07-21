#!/usr/bin/env bash
# scripts/tech-hotspot-radar/lib/anomaly-detectors.sh - Apply anomaly detectors to velocity metrics
set -euo pipefail

run_anomaly_detectors() {
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
metric = conn.execute(
    "SELECT * FROM repo_velocity_metrics WHERE repo_full_name=?",
    (repo,),
).fetchone()
if not metric:
    print(json.dumps({"ok": False, "repo": repo, "error": "missing repo_velocity_metrics"}, ensure_ascii=False))
    sys.exit(1)

repo_row = conn.execute(
    "SELECT description, topics, language, stars FROM github_repos WHERE full_name=?",
    (repo,),
).fetchone()
desc = (repo_row["description"] if repo_row else "") or ""
topics = (repo_row["topics"] if repo_row else "") or ""
lang = (repo_row["language"] if repo_row else "") or ""
stars = int(metric["stars_latest"] or (repo_row["stars"] if repo_row else 0) or 0)
delta24 = int(metric["star_delta_24h"] or 0)
delta7 = int(metric["star_delta_7d"] or 0)
delta30 = int(metric["star_delta_30d"] or 0)
accel = float(metric["acceleration"] or 0.0)
avg7 = delta7 / 7.0 if delta7 else 0.0
blob = " ".join([repo.lower(), desc.lower(), topics.lower(), lang.lower()])
infra_keywords = {"infra", "kernel", "runtime", "compiler", "database", "mcp", "agent", "orchestrator"}
is_infra = any(kw in blob for kw in infra_keywords)
potential = min(1.0, 0.45 * min(1.0, max(accel, 0) / 25.0) + 0.35 * min(1.0, stars / 5000.0) + 0.2 * (1.0 if is_infra else 0.0))

detectors = [
    ("sudden_hot", delta24 > max(10, 3 * avg7), round(delta24 / max(1.0, avg7 or 1.0), 4), {"delta24": delta24, "avg7": avg7}),
    ("early_potential", accel > 3 and stars < 5000, round(potential, 4), {"acceleration": accel, "stars": stars}),
    ("foundation_infra_candidate", is_infra and stars >= 100, round(min(1.0, stars / 50000.0), 4), {"stars": stars, "infra": is_infra}),
    ("hype_zombie", stars >= 1000 and delta24 < max(1.0, avg7 * 0.2) and accel < 0, round(abs(accel), 4), {"delta24": delta24, "avg7": avg7, "acceleration": accel}),
    ("steady_compounder", delta30 > 0 and delta7 > 0 and abs(accel) <= max(2.0, avg7 * 0.5), round(delta30 / 30.0, 4), {"delta30": delta30, "acceleration": accel}),
]
evidence_map = json.loads(metric["evidence_map_json"] or "[]")
updated_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

if not dry_run:
    for name, matched, score, details in detectors:
        conn.execute(
            """
            INSERT INTO detector_results
            (repo_full_name, detector_name, matched, score, evidence_map_json, details_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_full_name, detector_name) DO UPDATE SET
              matched=excluded.matched,
              score=excluded.score,
              evidence_map_json=excluded.evidence_map_json,
              details_json=excluded.details_json,
              updated_at=excluded.updated_at
            """,
            (repo, name, 1 if matched else 0, float(score), json.dumps(evidence_map, ensure_ascii=False), json.dumps(details, ensure_ascii=False), updated_at),
        )
    try:
        packet = conn.execute(
            "SELECT detector_results_json FROM project_reasoning_packets WHERE repo_full_name=? ORDER BY created_at DESC LIMIT 1",
            (repo,),
        ).fetchone()
        if packet:
            payload = [
                {"name": name, "matched": bool(matched), "value": score, "details": details}
                for name, matched, score, details in detectors
            ]
            conn.execute(
                """
                UPDATE project_reasoning_packets
                SET detector_results_json=?
                WHERE repo_full_name=? AND created_at=(
                    SELECT MAX(created_at) FROM project_reasoning_packets WHERE repo_full_name=?
                )
                """,
                (json.dumps(payload, ensure_ascii=False), repo, repo),
            )
    except Exception:
        pass
    conn.commit()

print(json.dumps({
    "ok": True,
    "repo": repo,
    "detectors": [
        {"name": name, "matched": bool(matched), "score": score, "details": details}
        for name, matched, score, details in detectors
    ],
}, ensure_ascii=False))
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
        echo "Usage: anomaly-detectors.sh --db <path> --repo <owner/name> [--dry-run]" >&2
        exit 1
    fi
    run_anomaly_detectors "$DB_PATH" "$REPO" "$DRY_RUN"
fi
