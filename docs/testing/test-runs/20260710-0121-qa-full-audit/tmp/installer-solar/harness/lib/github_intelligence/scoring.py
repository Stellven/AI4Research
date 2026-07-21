"""Heat scoring engine — 8-subscore weighted formula with percentile normalization.

Provides:
- ``compute_heat_score()``: compute composite heat score for a repo.
- ``compute_sub_scores()``: compute all 8 individual sub-scores.
- ``normalize_within_group()``: normalize scores to [0, 100] within percentile group.
- ``HEAT_WEIGHTS``: the 8 sub-score weights from design.md §A5.

Spec: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade
      design.md §A5 (heat score formula) + scoring-contract.md §2 (normalization)
Node: B9
"""
from __future__ import annotations

import sqlite3
from typing import Any


# Weights from design.md §A5 — must sum to 1.0
HEAT_WEIGHTS: dict[str, float] = {
    "star_velocity": 0.30,
    "star_acceleration": 0.15,
    "cross_source_signal": 0.15,
    "release_signal": 0.10,
    "community_activity": 0.10,
    "topic_relevance": 0.10,
    "maintainer_signal": 0.05,
    "novelty": 0.05,
}

# Clamp range
MIN_HEAT = 0.0
MAX_HEAT = 100.0


def compute_sub_scores(
    snapshot: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    percentile_data: dict[str, float] | None = None,
) -> dict[str, float]:
    """Compute 8 individual sub-scores for a repo.

    Parameters
    ----------
    snapshot : dict
        Snapshot data with keys: stars, forks, open_issues, watchers,
        stars_delta_24h, stars_delta_7d, star_acceleration,
        commit_count_7d, active_contributors_30d, latest_release_tag.
    evidence : list[dict]
        Evidence atoms for this repo.
    percentile_data : dict, optional
        Percentile values for normalization. Keys may include
        star_velocity_percentile, etc.

    Returns
    -------
    dict[str, float]
        All 8 sub-scores, each in [0, 100].
    """
    scores: dict[str, float] = {}

    # 1. star_velocity: based on stars_delta_24h, normalized by percentile
    delta_24h = float(snapshot.get("stars_delta_24h") or 0)
    velocity_raw = max(0, delta_24h)
    scores["star_velocity"] = _normalize_velocity(velocity_raw, percentile_data)

    # 2. star_acceleration: acceleration ratio → score
    accel = float(snapshot.get("star_acceleration") or 0)
    scores["star_acceleration"] = _normalize_acceleration(accel)

    # 3. cross_source_signal: count distinct source types in evidence
    source_types: set[str] = set()
    for atom in evidence:
        st = atom.get("raw_source_type") or atom.get("source_type") or ""
        if st:
            source_types.add(st)
    # Also check evidence types
    for atom in evidence:
        et = atom.get("evidence_type") or ""
        if "social" in et:
            source_types.add("social")
        if "youtube" in et:
            source_types.add("youtube")
    cross_count = len(source_types)
    scores["cross_source_signal"] = min(100.0, cross_count * 25.0)

    # 4. release_signal: has recent release + release evidence
    has_release = bool(snapshot.get("latest_release_tag"))
    release_evidence = [
        a for a in evidence
        if (a.get("evidence_type") or "") == "release_feature"
    ]
    release_score = 0.0
    if has_release:
        release_score += 30.0
    release_score += min(70.0, len(release_evidence) * 20.0)
    scores["release_signal"] = min(100.0, release_score)

    # 5. community_activity: commits + contributors
    commits_7d = int(snapshot.get("commit_count_7d") or 0)
    contributors = int(snapshot.get("active_contributors_30d") or 0)
    community_raw = min(50.0, commits_7d * 0.5) + min(50.0, contributors * 2.0)
    scores["community_activity"] = min(100.0, community_raw)

    # 6. topic_relevance: count evidence with topic tags
    topic_evidence = 0
    for atom in evidence:
        tags = atom.get("tags_json") or atom.get("topic_tags") or "[]"
        if isinstance(tags, str):
            import json
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []
        if tags:
            topic_evidence += 1
    scores["topic_relevance"] = min(100.0, topic_evidence * 15.0)

    # 7. maintainer_signal: evidence from issue_signal + pr_signal types
    maintainer_evidence = [
        a for a in evidence
        if (a.get("evidence_type") or "") in ("issue_signal", "pr_signal")
    ]
    scores["maintainer_signal"] = min(100.0, len(maintainer_evidence) * 25.0)

    # 8. novelty: average novelty_score from evidence
    novelty_scores = [
        float(a.get("novelty_score") or 0)
        for a in evidence
        if a.get("novelty_score") is not None
    ]
    if novelty_scores:
        scores["novelty"] = min(100.0, sum(novelty_scores) / len(novelty_scores))
    else:
        scores["novelty"] = 0.0

    return scores


def normalize_within_group(
    score: float,
    group_values: list[float],
) -> float:
    """Normalize a score to [0, 100] within its percentile group.

    Uses min-max normalization within the group.

    Parameters
    ----------
    score : float
    group_values : list[float]
        All scores in the same percentile group.

    Returns
    -------
    float in [0, 100]
    """
    if not group_values:
        return 50.0  # neutral default

    min_val = min(group_values)
    max_val = max(group_values)

    if max_val == min_val:
        return 50.0

    normalized = (score - min_val) / (max_val - min_val) * 100.0
    return max(MIN_HEAT, min(MAX_HEAT, normalized))


def compute_heat_score(
    sub_scores: dict[str, float],
) -> float:
    """Compute weighted composite heat score from 8 sub-scores.

    Parameters
    ----------
    sub_scores : dict[str, float]
        Must contain all 8 keys from HEAT_WEIGHTS.

    Returns
    -------
    float in [0, 100]
    """
    total = 0.0
    for key, weight in HEAT_WEIGHTS.items():
        score = sub_scores.get(key, 0.0)
        # Clamp individual score
        score = max(MIN_HEAT, min(MAX_HEAT, score))
        total += score * weight

    return max(MIN_HEAT, min(MAX_HEAT, round(total, 2)))


def compute_heat_score_for_repo(
    conn: sqlite3.Connection,
    full_name: str,
    *,
    snapshot_date: str | None = None,
) -> dict[str, Any]:
    """Compute heat score for a repo using DB data.

    Parameters
    ----------
    conn : sqlite3.Connection
    full_name : str
    snapshot_date : str, optional

    Returns
    -------
    dict with heat_score, sub_scores, normalization_group.
    """
    # Get latest snapshot
    row = conn.execute(
        """SELECT stars, forks, open_issues, watchers,
                  stars_delta_24h, stars_delta_7d, star_acceleration,
                  commit_count_7d, active_contributors_30d, latest_release_tag
           FROM github_star_snapshots
           WHERE full_name = ?
           ORDER BY snapshot_at DESC LIMIT 1""",
        (full_name,),
    ).fetchone()

    if row is None:
        return {
            "heat_score": 0.0,
            "sub_scores": {k: 0.0 for k in HEAT_WEIGHTS},
            "normalization_group": "unknown",
        }

    snapshot = {
        "stars": row[0], "forks": row[1], "open_issues": row[2],
        "watchers": row[3], "stars_delta_24h": row[4], "stars_delta_7d": row[5],
        "star_acceleration": row[6], "commit_count_7d": row[7],
        "active_contributors_30d": row[8], "latest_release_tag": row[9],
    }

    # Get evidence atoms
    evidence_rows = conn.execute(
        """SELECT evidence_type, raw_source_type, tags_json, novelty_score
           FROM repo_evidence_atoms
           WHERE repo_full_name = ?""",
        (full_name,),
    ).fetchall()

    evidence = [
        {
            "evidence_type": r[0],
            "raw_source_type": r[1],
            "tags_json": r[2],
            "novelty_score": r[3],
        }
        for r in evidence_rows
    ]

    # Get percentile data if available
    percentile_data = {}
    pct_row = conn.execute(
        """SELECT star_velocity_percentile
           FROM snapshot_percentiles
           WHERE repo_full_name = ?
           ORDER BY snapshot_date DESC LIMIT 1""",
        (full_name,),
    ).fetchone()
    if pct_row:
        percentile_data["star_velocity_percentile"] = pct_row[0]

    sub_scores = compute_sub_scores(snapshot, evidence, percentile_data=percentile_data)
    heat_score = compute_heat_score(sub_scores)

    # Determine normalization group
    stars = snapshot.get("stars") or 0
    if stars < 100:
        star_band = "<100"
    elif stars < 1000:
        star_band = "100-1k"
    elif stars < 10000:
        star_band = "1k-10k"
    else:
        star_band = "10k+"

    return {
        "heat_score": heat_score,
        "sub_scores": sub_scores,
        "normalization_group": star_band,
    }


# ---------------------------------------------------------------------------
# Internal normalization helpers
# ---------------------------------------------------------------------------

def _normalize_velocity(velocity: float, percentile_data: dict[str, float] | None) -> float:
    """Normalize star velocity using percentile data or global fallback."""
    if percentile_data and "star_velocity_percentile" in percentile_data:
        # Percentile is already 0-100
        return float(percentile_data["star_velocity_percentile"])

    # Global fallback: log-scale normalization
    if velocity <= 0:
        return 0.0
    import math
    # Map 0-500 stars/day to 0-100
    return min(100.0, math.log1p(velocity) / math.log1p(500) * 100.0)


def _normalize_acceleration(acceleration: float) -> float:
    """Map acceleration ratio to score using design thresholds.

    From design.md §A5:
    <1.5x → 0-25 (normal)
    1.5-3x → 25-50 (warming)
    3-8x → 50-75 (breakout)
    >8x → 75-100 (sudden_hot)
    """
    if acceleration < 1.5:
        return max(0.0, acceleration / 1.5 * 25.0)
    elif acceleration < 3.0:
        return 25.0 + (acceleration - 1.5) / 1.5 * 25.0
    elif acceleration < 8.0:
        return 50.0 + (acceleration - 3.0) / 5.0 * 25.0
    else:
        # >8x: cap at 100 at 20x
        return min(100.0, 75.0 + (acceleration - 8.0) / 12.0 * 25.0)
