"""Reasoning packet builder — Composes project reasoning packets from evidence atoms.

Provides:
- ``build_reasoning_packet()``: Composes a packet from database evidence atoms and metadata.

Spec: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s02-architecture
Node: B7
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from github_intelligence.scoring import compute_heat_score_for_repo


def get_acceleration_tier(acceleration: Optional[float]) -> Optional[str]:
    """Map acceleration ratio to tier according to design.md §A5."""
    if acceleration is None:
        return None
    try:
        accel = float(acceleration)
    except (ValueError, TypeError):
        return None

    if accel < 1.5:
        return "normal"
    elif accel < 3.0:
        return "warming"
    elif accel < 8.0:
        return "breakout"
    elif accel < 20.0:
        return "sudden_hot"
    else:
        return "needs_attribution"


def build_reasoning_packet(
    conn: sqlite3.Connection,
    repo_full_name: str,
) -> Dict[str, Any]:
    """Compose a project reasoning packet from evidence atoms and metadata.

    Parameters
    ----------
    conn : sqlite3.Connection
        Connection to tech-hotspot-radar database.
    repo_full_name : str
        The full name of the repository (e.g. 'owner/repo').

    Returns
    -------
    dict
        The compiled project reasoning packet dictionary.

    Raises
    ------
    ValueError
        If repository has fewer than 3 evidence atoms.
    """
    # 1. Fetch evidence atoms
    cursor = conn.execute(
        """SELECT atom_id, evidence_type, compressed_content, confidence, technical_depth, novelty_score
           FROM repo_evidence_atoms
           WHERE repo_full_name = ?
           ORDER BY created_at DESC""",
        (repo_full_name,),
    )
    rows = cursor.fetchall()

    if len(rows) < 3:
        raise ValueError(
            f"Cannot build reasoning packet for '{repo_full_name}': "
            f"only {len(rows)} evidence atoms found, minimum 3 required."
        )

    # 2. Group evidence atom IDs by type
    growth_ids: List[str] = []
    readme_ids: List[str] = []
    release_ids: List[str] = []
    social_ids: List[str] = []
    youtube_ids: List[str] = []
    issue_ids: List[str] = []
    pr_ids: List[str] = []
    all_atom_ids: List[str] = []

    brief_parts: List[str] = []

    for row in rows:
        atom_id = row[0]
        evidence_type = row[1]
        content = row[2]

        all_atom_ids.append(atom_id)
        if content:
            brief_parts.append(content)

        if evidence_type == "growth_fact":
            growth_ids.append(atom_id)
        elif evidence_type == "readme_claim":
            readme_ids.append(atom_id)
        elif evidence_type == "release_feature":
            release_ids.append(atom_id)
        elif evidence_type == "social_mention":
            social_ids.append(atom_id)
        elif evidence_type == "youtube_mention":
            youtube_ids.append(atom_id)
        elif evidence_type == "issue_signal":
            issue_ids.append(atom_id)
        elif evidence_type == "pr_signal":
            pr_ids.append(atom_id)

    # 3. Compose local project brief
    brief = "\n\n".join(brief_parts)
    if len(brief) > 1000:
        brief = brief[:997] + "..."

    # 4. Fetch metrics/snapshot stats
    snapshot_row = conn.execute(
        """SELECT stars, forks, open_issues, watchers,
                  stars_delta_24h, stars_delta_7d, star_acceleration,
                  commit_count_7d, active_contributors_30d
           FROM github_star_snapshots
           WHERE full_name = ?
           ORDER BY snapshot_at DESC LIMIT 1""",
        (repo_full_name,),
    ).fetchone()

    # 5. Fetch release tag and other repo info from github_repos
    repo_row = conn.execute(
        """SELECT stars, forks, watchers, open_issues, latest_release_tag, latest_release_at, pushed_at
           FROM github_repos
           WHERE full_name = ?""",
        (repo_full_name,),
    ).fetchone()

    latest_release_tag = repo_row[4] if repo_row else None
    latest_release_at = repo_row[5] if repo_row else None
    pushed_at = repo_row[6] if repo_row else None

    metrics: Dict[str, Any] = {}
    acceleration: Optional[float] = None
    if snapshot_row:
        metrics = {
            "stars": snapshot_row[0],
            "forks": snapshot_row[1],
            "open_issues": snapshot_row[2],
            "watchers": snapshot_row[3],
            "stars_delta_24h": snapshot_row[4],
            "stars_delta_7d": snapshot_row[5],
            "star_acceleration": snapshot_row[6],
            "commit_count_7d": snapshot_row[7],
            "active_contributors_30d": snapshot_row[8],
            "latest_release_tag": latest_release_tag,
            "latest_release_at": latest_release_at,
            "pushed_at": pushed_at,
        }
        acceleration = snapshot_row[6]
    elif repo_row:
        metrics = {
            "stars": repo_row[0],
            "forks": repo_row[1],
            "open_issues": repo_row[3],
            "watchers": repo_row[2],
            "stars_delta_24h": 0,
            "stars_delta_7d": 0,
            "star_acceleration": 1.0,
            "commit_count_7d": 0,
            "active_contributors_30d": 0,
            "latest_release_tag": latest_release_tag,
            "latest_release_at": latest_release_at,
            "pushed_at": repo_row[6],
        }
        acceleration = 1.0

    # 6. Fetch percentile rank
    pct_row = conn.execute(
        """SELECT star_velocity_percentile
           FROM snapshot_percentiles
           WHERE repo_full_name = ?
           ORDER BY snapshot_date DESC LIMIT 1""",
        (repo_full_name,),
    ).fetchone()
    star_velocity_percentile = float(pct_row[0]) if pct_row else None

    # 7. Map acceleration to tier
    acceleration_tier = get_acceleration_tier(acceleration)

    # 8. Generate packet ID
    h = hashlib.sha256(repo_full_name.encode("utf-8")).hexdigest()[:24]
    packet_id = f"pkt_{h}"

    # 9. Define questions for premium models
    questions = [
        "What is the core technical novelty of this project compared to existing alternatives?",
        "Is this repository a simple wrapper UI or does it contain custom engineering (e.g., custom kernels, libraries)?",
        "Based on the growth metrics, is the spike in stars organic or potentially manipulated?",
        "What are the primary use cases and target users for this repository?",
        "What planning suggestions or MVP ideas can be derived from this project's capabilities?",
    ]

    # 10. Compute scores safely using the imported functions
    from github_intelligence.scoring import compute_sub_scores, compute_heat_score

    # Prepare evidence dictionary for sub-scores calculation
    scoring_evidence = []
    for r in rows:
        scoring_evidence.append({
            "evidence_type": r[1],
            "raw_source_type": "", # or map if needed
            "tags_json": "[]",
            "novelty_score": r[5],
        })

    percentile_data = {}
    if star_velocity_percentile is not None:
        percentile_data["star_velocity_percentile"] = star_velocity_percentile

    sub_scores = compute_sub_scores(metrics, scoring_evidence, percentile_data=percentile_data)
    scores_json = json.dumps(sub_scores)

    # 11. Save to database (project_reasoning_packets table)
    created_at = datetime.now(timezone.utc).isoformat()
    total_tokens_estimate = len(brief) // 4

    conn.execute(
        """INSERT OR REPLACE INTO project_reasoning_packets (
            packet_id,
            repo_full_name,
            star_velocity_percentile,
            acceleration,
            acceleration_tier,
            evidence_atom_count,
            evidence_atom_ids_json,
            scores_json,
            detector_results_json,
            total_tokens,
            schema_version,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            packet_id,
            repo_full_name,
            star_velocity_percentile,
            acceleration,
            acceleration_tier,
            len(rows),
            json.dumps(all_atom_ids),
            scores_json,
            json.dumps([]),
            total_tokens_estimate,
            "v1",
            created_at,
        ),
    )
    conn.commit()

    # 12. Return the compiled reasoning packet dict
    return {
        "packet_id": packet_id,
        "repo_full_name": repo_full_name,
        "metrics": metrics,
        "brief": brief,
        "local_project_brief": brief,
        "growth_evidence": growth_ids,
        "readme_evidence": readme_ids,
        "release_evidence": release_ids,
        "social_evidence": social_ids,
        "youtube_evidence": youtube_ids,
        "issue_evidence": issue_ids,
        "pr_evidence": pr_ids,
        "questions": questions,
        "questions_for_reasoner": questions,
        "star_velocity_percentile": star_velocity_percentile,
        "acceleration": acceleration,
        "acceleration_tier": acceleration_tier,
        "created_at": created_at,
    }
