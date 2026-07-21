"""Alert dispatcher — evaluate alert rules, write to alerts table, suppress duplicates.

Spec: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s02-architecture
Node: B11
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("github_intelligence.alerts")

_DEFAULT_CONFIG_PATH = "~/Solar/harness/config/github_intelligence_config.yaml"

VALID_DETECTORS = {
    "sudden_hot",
    "early_potential",
    "foundation_infra_candidate",
    "hype_or_noise",
    "star_manipulation_suspicion",
    "major_release_signal",
    "cross_source_resonance"
}

VALID_SEVERITIES = {
    "critical",
    "high",
    "medium",
    "low",
    "info"
}

SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4
}


def parse_iso_timestamp(ts_str: str) -> datetime:
    """Parse ISO-8601 UTC timestamp to timezone-aware datetime."""
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    return datetime.fromisoformat(ts_str)


def generate_alert_id(repo_full_name: str, detector: str, triggered_at: str) -> str:
    """Generate a reproducible alert ID."""
    raw = f"{repo_full_name}\0{detector}\0{triggered_at}"
    return "alert_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def load_tracked_repos(config_path: str = _DEFAULT_CONFIG_PATH) -> set[str]:
    """Load tracked repos full names from the config file."""
    tracked = set()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                import yaml
                config = yaml.safe_load(f)
            repos = config.get("discovery", {}).get("tracked_repos", [])
            for r in repos:
                full_name = r.get("full_name")
                if full_name:
                    tracked.add(full_name.strip().lower())
        except Exception as e:
            logger.warning("Failed to load config for tracked repos from %s: %s", config_path, e)
    return tracked


def check_duplicate_alert(
    conn: sqlite3.Connection,
    repo_full_name: str,
    detector: str,
    triggered_at: str,
    window_hours: int = 24
) -> bool:
    """Check if an alert for the same repo and detector exists within last 24h."""
    try:
        cursor = conn.execute(
            """SELECT triggered_at FROM alerts
               WHERE repo_full_name = ? AND detector = ?
               ORDER BY triggered_at DESC LIMIT 1""",
            (repo_full_name, detector)
        )
        row = cursor.fetchone()
        if not row:
            return False
            
        last_triggered = row[0]
        dt_last = parse_iso_timestamp(last_triggered)
        dt_curr = parse_iso_timestamp(triggered_at)
        
        diff = dt_curr - dt_last
        return diff.total_seconds() < window_hours * 3600
    except Exception as e:
        logger.error("Failed to check duplicate alerts for %s (%s): %s", repo_full_name, detector, e)
        return False


def dispatch_alerts(
    conn: sqlite3.Connection,
    repo_full_name: str,
    detections: list[Any],
    snapshot: dict[str, Any] | None = None,
    evidence_atoms: list[dict[str, Any]] | None = None,
    config_path: str | None = None,
) -> list[str]:
    """Evaluate alert rules against detector outputs, write to alerts table.

    Applies duplicate suppression within 24 hours.
    Returns a list of successfully inserted alert_ids.
    """
    if config_path is None:
        config_path = _DEFAULT_CONFIG_PATH

    # 1. Query snapshot and evidence if not provided
    if snapshot is None:
        snapshot = {}
        try:
            snapshot_row = conn.execute(
                """SELECT stars, forks, open_issues, watchers,
                          stars_delta_1h, stars_delta_6h, stars_delta_24h, stars_delta_7d, stars_delta_30d,
                          forks_delta_24h, issues_delta_24h, prs_delta_24h,
                          commit_count_7d, active_contributors_30d,
                          star_acceleration
                   FROM github_star_snapshots
                   WHERE full_name = ?
                   ORDER BY snapshot_at DESC LIMIT 1""",
                (repo_full_name,),
            ).fetchone()
            if snapshot_row:
                snapshot = {
                    "stars": snapshot_row[0],
                    "forks": snapshot_row[1],
                    "open_issues": snapshot_row[2],
                    "watchers": snapshot_row[3],
                    "stars_delta_1h": snapshot_row[4],
                    "stars_delta_6h": snapshot_row[5],
                    "stars_delta_24h": snapshot_row[6],
                    "stars_delta_7d": snapshot_row[7],
                    "stars_delta_30d": snapshot_row[8],
                    "forks_delta_24h": snapshot_row[9],
                    "issues_delta_24h": snapshot_row[10],
                    "prs_delta_24h": snapshot_row[11],
                    "commit_count_7d": snapshot_row[12],
                    "active_contributors_30d": snapshot_row[13],
                    "star_acceleration": snapshot_row[14],
                }
        except Exception as e:
            logger.error("Failed to query snapshot for %s: %s", repo_full_name, e)

    if evidence_atoms is None:
        evidence_atoms = []
        try:
            cursor = conn.execute(
                """SELECT atom_id, evidence_type, compressed_content, confidence, technical_depth, novelty_score, raw_source_type, tags_json
                   FROM repo_evidence_atoms
                   WHERE repo_full_name = ?""",
                (repo_full_name,),
            )
            for r in cursor.fetchall():
                evidence_atoms.append({
                    "atom_id": r[0],
                    "evidence_type": r[1],
                    "compressed_content": r[2],
                    "confidence": r[3],
                    "technical_depth": r[4],
                    "novelty_score": r[5],
                    "raw_source_type": r[6],
                    "tags_json": r[7],
                })
        except Exception as e:
            logger.error("Failed to query evidence atoms for %s: %s", repo_full_name, e)

    # 2. Evaluate alert rules & conditions
    # Check if tracked repo
    tracked_repos = load_tracked_repos(config_path)
    is_tracked = repo_full_name.lower() in tracked_repos

    # Rule A: tracked repo 24h growth >10% → high severity alert
    growth_alert_triggered = False
    stars = snapshot.get("stars") or 0
    stars_delta_24h = snapshot.get("stars_delta_24h") or 0
    base_stars = stars - stars_delta_24h
    if is_tracked:
        if base_stars > 0:
            growth_ratio = stars_delta_24h / base_stars
            if growth_ratio > 0.10:
                growth_alert_triggered = True
        elif stars_delta_24h > 0:
            growth_alert_triggered = True

    # Rule B: X+YouTube+Trending all hit → high severity alert
    has_social = any(a.get("evidence_type") == "social_mention" for a in evidence_atoms)
    has_youtube = any(a.get("evidence_type") == "youtube_mention" for a in evidence_atoms)
    has_growth = any(a.get("evidence_type") == "growth_fact" for a in evidence_atoms)
    is_trending = has_growth or stars_delta_24h > 0 or (snapshot.get("star_acceleration") or 1.0) > 1.0
    resonance_alert_triggered = has_social and has_youtube and is_trending

    # 3. Map detections and construct candidates
    candidate_alerts: list[dict[str, Any]] = []
    triggered_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    has_sudden_hot = False
    has_cross_resonance = False

    for d in detections:
        # Support both object and dict
        d_name = d.detector_name if hasattr(d, "detector_name") else d.get("detector_name")
        d_sev = d.severity if hasattr(d, "severity") else d.get("severity", "info")
        d_ev_ids = d.evidence_ids if hasattr(d, "evidence_ids") else d.get("evidence_ids", [])
        d_cond = d.trigger_condition if hasattr(d, "trigger_condition") else d.get("trigger_condition", "")
        d_cond_json = d.conditions_met_json if hasattr(d, "conditions_met_json") else d.get("conditions_met_json", {})
        d_rec = d.recommended_action if hasattr(d, "recommended_action") else d.get("recommended_action", "")

        if d_name not in VALID_DETECTORS:
            logger.warning("Ignoring detection with invalid detector name: %s", d_name)
            continue

        if d_name == "sudden_hot":
            has_sudden_hot = True
            if growth_alert_triggered:
                # Escalate to high
                d_sev = "critical" if d_sev == "critical" else "high"
                d_cond = f"{d_cond} | Tracked growth: {stars_delta_24h} stars delta / {base_stars} base (>10%)"
        
        if d_name == "cross_source_resonance":
            has_cross_resonance = True
            if resonance_alert_triggered:
                # Escalate to high
                d_sev = "critical" if d_sev == "critical" else "high"
                d_cond = f"{d_cond} | X+YouTube+Trending resonance hit"

        severity = d_sev if d_sev in VALID_SEVERITIES else "info"

        candidate_alerts.append({
            "detector": d_name,
            "repo_full_name": repo_full_name,
            "triggered_at": triggered_at,
            "trigger_condition": d_cond,
            "conditions_met_json": d_cond_json,
            "supporting_evidence_ids_json": d_ev_ids,
            "severity": severity,
            "recommended_action": d_rec,
        })

    # 4. Inject alerts if rules matched but detector did not run or trigger
    if growth_alert_triggered and not has_sudden_hot:
        evidence_ids = [a["atom_id"] for a in evidence_atoms if a.get("evidence_type") == "growth_fact"]
        if not evidence_ids and evidence_atoms:
            evidence_ids = [evidence_atoms[0]["atom_id"]]
        candidate_alerts.append({
            "detector": "sudden_hot",
            "repo_full_name": repo_full_name,
            "triggered_at": triggered_at,
            "trigger_condition": f"Tracked repo 24h growth >10% (delta: {stars_delta_24h}, base: {base_stars})",
            "conditions_met_json": {"stars_delta_24h": stars_delta_24h, "base_stars": base_stars, "is_tracked": True},
            "supporting_evidence_ids_json": evidence_ids,
            "severity": "high",
            "recommended_action": "Create project intelligence card and run why-hot attribution for high growth tracked repo.",
        })

    if resonance_alert_triggered and not has_cross_resonance:
        evidence_ids = [a["atom_id"] for a in evidence_atoms if a.get("evidence_type") in ("social_mention", "youtube_mention")]
        if not evidence_ids and evidence_atoms:
            evidence_ids = [evidence_atoms[0]["atom_id"]]
        candidate_alerts.append({
            "detector": "cross_source_resonance",
            "repo_full_name": repo_full_name,
            "triggered_at": triggered_at,
            "trigger_condition": "X+YouTube+Trending all hit resonance",
            "conditions_met_json": {"has_social": has_social, "has_youtube": has_youtube, "is_trending": is_trending},
            "supporting_evidence_ids_json": evidence_ids,
            "severity": "high",
            "recommended_action": "Compile cross-source mention highlights and check community velocity.",
        })

    # 5. Write to alerts table with duplicate suppression
    inserted_ids: list[str] = []
    for alert in candidate_alerts:
        try:
            detector = alert["detector"]
            # Check duplicate within 24h
            if check_duplicate_alert(conn, repo_full_name, detector, triggered_at, window_hours=24):
                logger.info("Alert suppressed: duplicate within 24h for %s (%s)", repo_full_name, detector)
                continue

            alert_id = generate_alert_id(repo_full_name, detector, triggered_at)
            
            evidence_ids = alert["supporting_evidence_ids_json"]
            if isinstance(evidence_ids, str):
                try:
                    evidence_ids = json.loads(evidence_ids)
                except json.JSONDecodeError:
                    evidence_ids = [evidence_ids] if evidence_ids else []

            conn.execute(
                """INSERT INTO alerts (alert_id, detector, repo_full_name, triggered_at, trigger_condition,
                                      conditions_met_json, supporting_evidence_ids_json, severity, recommended_action, acknowledged)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    alert_id,
                    detector,
                    repo_full_name,
                    triggered_at,
                    alert["trigger_condition"],
                    json.dumps(alert["conditions_met_json"]),
                    json.dumps(evidence_ids),
                    alert["severity"],
                    alert["recommended_action"],
                )
            )
            inserted_ids.append(alert_id)
        except Exception as e:
            logger.error("Failed to insert alert for %s: %s", repo_full_name, e)

    if inserted_ids:
        conn.commit()

    return inserted_ids
