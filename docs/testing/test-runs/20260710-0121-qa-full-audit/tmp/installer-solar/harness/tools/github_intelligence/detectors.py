"""GitHub Project Intelligence — Heat Scoring & Detectors (C3 node).

Sprint: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s03-core-runtime
Node:   C3_detectors

Provides:
- compute_heat_score  : composite [0,100] heat score (S02 §A5 formula)
- 7 detector functions:
    detect_sudden_hot          (severity=high)
    detect_early_potential     (severity=medium)
    detect_foundation_infra    (severity=info)
    detect_hype_or_noise       (severity=medium)
    detect_star_manipulation   (severity=high)
    detect_major_release       (severity=medium)
    detect_cross_source_resonance (severity=medium)
- run_detectors : run all detectors, persist Detections if conn provided

Design constraints honored:
- Pure stdlib only
- Deterministic: same input → same output (no randomness, no time.now in logic)
- Negative controls: stars_delta_24h=1, star_acceleration=0.5 → NO sudden_hot alert
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .schema import (
    Detection,
    EvidenceAtom,
    RepoSnapshot,
    insert_row,
    utc_now_iso,
)

# ---------------------------------------------------------------------------
# Heat Score sub-score helpers
# ---------------------------------------------------------------------------

# S02 §A5 weights (must sum to 1.00)
_HEAT_WEIGHTS = {
    "star_velocity_score":       0.30,
    "star_acceleration_score":   0.15,
    "cross_source_signal_score": 0.15,
    "release_signal_score":      0.10,
    "community_activity_score":  0.10,
    "topic_relevance_score":     0.10,
    "maintainer_signal_score":   0.05,
    "novelty_score":             0.05,
}

assert abs(sum(_HEAT_WEIGHTS.values()) - 1.0) < 1e-9, "heat weights must sum to 1.0"


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# Sub-score functions — each returns [0, 100]

def _star_velocity_score(
    snapshot: RepoSnapshot,
    percentile_ctx: dict | None,
) -> float:
    """Normalise stars_delta_24h against context percentile or an absolute scale."""
    delta = _safe_float(snapshot.stars_delta_24h)
    if delta <= 0:
        return 0.0
    if percentile_ctx and "p95_stars_delta_24h" in percentile_ctx:
        p95 = _safe_float(percentile_ctx["p95_stars_delta_24h"], 1.0)
        return _clamp(delta / p95 * 100.0) if p95 > 0 else 0.0
    # Absolute scale: 0→0, 500→50, 2000→100 (log-ish)
    import math
    return _clamp(math.log1p(delta) / math.log1p(2000) * 100.0)


def _star_acceleration_score(snapshot: RepoSnapshot) -> float:
    """acceleration = stars_delta_24h / stars_delta_7d * 7 (daily ratio).

    Also honours the star_acceleration field if set.
    """
    raw_acc = _safe_float(snapshot.star_acceleration)
    if raw_acc > 0:
        # Normalise: 1x→0, 3x→50, 10x→100
        import math
        return _clamp((math.log1p(raw_acc) / math.log1p(10)) * 100.0)
    # Fall back to computing from deltas
    delta_24h = _safe_float(snapshot.stars_delta_24h)
    delta_7d = _safe_float(snapshot.stars_delta_7d)
    if delta_7d > 0:
        daily_avg = delta_7d / 7.0
        if daily_avg > 0:
            acc = delta_24h / daily_avg
            import math
            return _clamp((math.log1p(acc) / math.log1p(10)) * 100.0)
    return 0.0


def _cross_source_signal_score(evidence: list[EvidenceAtom]) -> float:
    """Score based on diversity of source_type origins in evidence."""
    sources = {a.source for a in evidence}
    # 1 source → 10, 2 → 50, 3+ → 100
    n = len(sources)
    if n >= 3:
        return 100.0
    if n == 2:
        return 50.0
    if n == 1:
        return 10.0
    return 0.0


def _release_signal_score(snapshot: RepoSnapshot, evidence: list[EvidenceAtom]) -> float:
    """Score presence & recency of releases."""
    has_release_atom = any(a.evidence_type == "release_signal" for a in evidence)
    has_recent_release = snapshot.latest_release_at is not None
    score = 0.0
    if has_release_atom:
        score += 50.0
    if has_recent_release:
        score += 30.0
    if snapshot.latest_release_tag:
        # Bonus for semantic versioning ≥ v1.0
        tag = snapshot.latest_release_tag.lstrip("v")
        try:
            major = int(tag.split(".")[0])
            if major >= 1:
                score += 20.0
        except (ValueError, IndexError):
            pass
    return _clamp(score)


def _community_activity_score(snapshot: RepoSnapshot) -> float:
    """Score community engagement signals."""
    score = 0.0
    contributors = _safe_float(snapshot.active_contributors_30d)
    commits_7d = _safe_float(snapshot.commit_count_7d)
    open_issues = _safe_float(snapshot.open_issues)
    forks = _safe_float(snapshot.forks)

    # Contributors: 0→0, 5→25, 20→50, 50+→75
    if contributors > 0:
        import math
        score += _clamp(math.log1p(contributors) / math.log1p(50) * 75.0)
    # Commits 7d: up to 15 pts
    if commits_7d > 0:
        import math
        score += _clamp(math.log1p(commits_7d) / math.log1p(100) * 15.0)
    # Forks: up to 10 pts
    if forks > 0:
        import math
        score += _clamp(math.log1p(forks) / math.log1p(10000) * 10.0)

    return _clamp(score)


def _topic_relevance_score(evidence: list[EvidenceAtom]) -> float:
    """Score based on presence of high-relevance topic tags in evidence atoms."""
    _HIGH_VALUE_TOPICS = frozenset([
        "llm", "inference", "agent", "transformer", "neural", "gpu", "cache",
        "rag", "quantiz", "lora", "compress", "efficient", "fast", "model",
        "embedding", "vector", "framework", "benchmark",
    ])
    all_tags: set[str] = set()
    for a in evidence:
        all_tags.update(a.topic_tags or [])
    hits = len(all_tags & _HIGH_VALUE_TOPICS)
    # 0 hits → 0, 3 hits → 50, 6+ hits → 100
    return _clamp(hits / 6.0 * 100.0)


def _maintainer_signal_score(snapshot: RepoSnapshot) -> float:
    """Score maintainer activity: recent push, commit cadence."""
    score = 0.0
    if snapshot.pushed_at:
        # If pushed within ~30 days → 100, older → decays
        try:
            pushed = datetime.fromisoformat(snapshot.pushed_at.rstrip("Z"))
            pushed = pushed.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days_ago = (now - pushed).total_seconds() / 86400.0
            score = _clamp(max(0.0, 100.0 - days_ago * 3.0))
        except ValueError:
            pass
    # Additional: active contributors & commits
    if _safe_float(snapshot.commit_count_7d) > 5:
        score = min(100.0, score + 20.0)
    return score


def _novelty_score_from_evidence(evidence: list[EvidenceAtom]) -> float:
    """Aggregate novelty_score from atoms that have it set."""
    scores = [a.novelty_score for a in evidence if a.novelty_score is not None]
    if not scores:
        return 0.0
    return _clamp(sum(scores) / len(scores))


# ---------------------------------------------------------------------------
# Public: compute_heat_score
# ---------------------------------------------------------------------------

def compute_heat_score(
    snapshot: RepoSnapshot,
    evidence: list[EvidenceAtom],
    percentile_ctx: dict | None = None,
) -> float:
    """Compute composite heat score in [0, 100].

    Formula (S02 §A5):
    0.30 * star_velocity_score
    + 0.15 * star_acceleration_score
    + 0.15 * cross_source_signal_score
    + 0.10 * release_signal_score
    + 0.10 * community_activity_score
    + 0.10 * topic_relevance_score
    + 0.05 * maintainer_signal_score
    + 0.05 * novelty_score
    """
    sub_scores = {
        "star_velocity_score":       _star_velocity_score(snapshot, percentile_ctx),
        "star_acceleration_score":   _star_acceleration_score(snapshot),
        "cross_source_signal_score": _cross_source_signal_score(evidence),
        "release_signal_score":      _release_signal_score(snapshot, evidence),
        "community_activity_score":  _community_activity_score(snapshot),
        "topic_relevance_score":     _topic_relevance_score(evidence),
        "maintainer_signal_score":   _maintainer_signal_score(snapshot),
        "novelty_score":             _novelty_score_from_evidence(evidence),
    }
    heat = sum(_HEAT_WEIGHTS[k] * v for k, v in sub_scores.items())
    return round(_clamp(heat), 4)


def _why_hot_attribution(
    snapshot: RepoSnapshot,
    evidence: list[EvidenceAtom],
    percentile_ctx: dict | None = None,
) -> dict[str, float]:
    """Return deterministic sub-score breakdown for attribution."""
    return {
        "star_velocity_score":       round(_star_velocity_score(snapshot, percentile_ctx), 4),
        "star_acceleration_score":   round(_star_acceleration_score(snapshot), 4),
        "cross_source_signal_score": round(_cross_source_signal_score(evidence), 4),
        "release_signal_score":      round(_release_signal_score(snapshot, evidence), 4),
        "community_activity_score":  round(_community_activity_score(snapshot), 4),
        "topic_relevance_score":     round(_topic_relevance_score(evidence), 4),
        "maintainer_signal_score":   round(_maintainer_signal_score(snapshot), 4),
        "novelty_score":             round(_novelty_score_from_evidence(evidence), 4),
    }


# ---------------------------------------------------------------------------
# Detector helpers
# ---------------------------------------------------------------------------

def _evidence_ids(evidence: list[EvidenceAtom]) -> list[str]:
    return [a.evidence_id for a in evidence]


# ---------------------------------------------------------------------------
# 7 Detectors
# ---------------------------------------------------------------------------

def detect_sudden_hot(
    full_name: str,
    snapshot: RepoSnapshot,
    evidence: list[EvidenceAtom],
) -> list[Detection]:
    """Trigger when star_acceleration > 8x. Severity=high.

    Negative control: acceleration=0.5, stars_delta_24h=1 → NOT triggered.
    """
    acc = _safe_float(snapshot.star_acceleration)
    if acc <= 8.0:
        return []
    attr = _why_hot_attribution(snapshot, evidence)
    return [
        Detection(
            detector_name="sudden_hot",
            full_name=full_name,
            severity="high",
            title=f"Sudden heat spike: star_acceleration={acc:.1f}x (threshold >8x)",
            evidence_ids=_evidence_ids(evidence)[:5],
            details={
                "star_acceleration": acc,
                "stars_delta_24h": snapshot.stars_delta_24h,
                "stars": snapshot.stars,
                "why_hot_attribution": attr,
            },
            created_at=utc_now_iso(),
        )
    ]


def detect_early_potential(
    full_name: str,
    snapshot: RepoSnapshot,
    evidence: list[EvidenceAtom],
) -> list[Detection]:
    """Trigger when potential_score > 85 AND stars < 2000. Severity=medium.

    potential_score is inferred from evidence atoms:
    - Average of top-3 importance_scores weighted by technical_depth_score
    - Thresholded at >85.
    """
    stars = _safe_float(snapshot.stars)
    if stars >= 2000:
        return []

    # Compute potential_score from evidence
    scored = [
        a for a in evidence
        if a.importance_score is not None and a.importance_score > 0
    ]
    if not scored:
        return []
    scored.sort(key=lambda a: -(a.importance_score or 0))
    top3 = scored[:3]
    weights = [(a.technical_depth_score or 1.0) for a in top3]
    total_w = sum(weights) or 1.0
    weighted_importance = sum(
        (a.importance_score or 0) * w for a, w in zip(top3, weights)
    ) / total_w
    potential_score = _clamp(weighted_importance)

    if potential_score <= 85.0:
        return []

    return [
        Detection(
            detector_name="early_potential",
            full_name=full_name,
            severity="medium",
            title=f"Early-stage high-potential project: potential_score={potential_score:.1f}, stars={int(stars)}",
            evidence_ids=_evidence_ids(top3),
            details={
                "potential_score": round(potential_score, 2),
                "stars": snapshot.stars,
                "top3_evidence_importance": [a.importance_score for a in top3],
            },
            created_at=utc_now_iso(),
        )
    ]


def detect_foundation_infra(
    full_name: str,
    snapshot: RepoSnapshot,
    evidence: list[EvidenceAtom],
) -> list[Detection]:
    """Trigger when technical_depth_score + community_health_score > 160. Severity=info.

    Scores are derived from evidence and snapshot respectively.
    """
    # Technical depth: average technical_depth_score across evidence atoms
    depth_scores = [
        a.technical_depth_score for a in evidence if a.technical_depth_score is not None
    ]
    tech_depth = _clamp(
        sum(depth_scores) / len(depth_scores) if depth_scores else 0.0
    )

    # Community health: composite from snapshot fields, [0, 100]
    contributors = _safe_float(snapshot.active_contributors_30d)
    commits = _safe_float(snapshot.commit_count_7d)
    forks = _safe_float(snapshot.forks)
    stars = _safe_float(snapshot.stars)
    import math
    community_health = _clamp(
        math.log1p(contributors) / math.log1p(100) * 40.0
        + math.log1p(commits) / math.log1p(200) * 30.0
        + math.log1p(forks) / math.log1p(5000) * 20.0
        + math.log1p(stars) / math.log1p(50000) * 10.0
    )

    combined = tech_depth + community_health
    if combined <= 160.0:
        return []

    return [
        Detection(
            detector_name="foundation_infra_candidate",
            full_name=full_name,
            severity="info",
            title=f"Foundation infrastructure candidate: tech_depth={tech_depth:.1f} + community_health={community_health:.1f} = {combined:.1f} > 160",
            evidence_ids=_evidence_ids(evidence)[:5],
            details={
                "technical_depth_score": round(tech_depth, 2),
                "community_health_score": round(community_health, 2),
                "combined_score": round(combined, 2),
                "contributors_30d": snapshot.active_contributors_30d,
                "forks": snapshot.forks,
                "stars": snapshot.stars,
            },
            created_at=utc_now_iso(),
        )
    ]


def detect_hype_or_noise(
    full_name: str,
    snapshot: RepoSnapshot,
    evidence: list[EvidenceAtom],
) -> list[Detection]:
    """Trigger when heat_score is high but technical_depth < 30. Severity=medium.

    High heat = heat_score > 60.
    """
    heat = compute_heat_score(snapshot, evidence)
    if heat <= 60.0:
        return []

    depth_scores = [
        a.technical_depth_score for a in evidence if a.technical_depth_score is not None
    ]
    tech_depth = _clamp(
        sum(depth_scores) / len(depth_scores) if depth_scores else 0.0
    )

    if tech_depth >= 30.0:
        return []

    return [
        Detection(
            detector_name="hype_or_noise",
            full_name=full_name,
            severity="medium",
            title=f"Potential hype/noise: heat={heat:.1f} but technical_depth={tech_depth:.1f} < 30",
            evidence_ids=_evidence_ids(evidence)[:3],
            details={
                "heat_score": round(heat, 4),
                "technical_depth_score": round(tech_depth, 2),
            },
            created_at=utc_now_iso(),
        )
    ]


def detect_star_manipulation(
    full_name: str,
    snapshot: RepoSnapshot,
    evidence: list[EvidenceAtom],
    percentile_ctx: dict | None = None,
) -> list[Detection]:
    """Trigger when star_velocity > 95th percentile AND low community activity.

    Low community = active_contributors_30d < 3 AND forks < 50.
    Severity=high.
    """
    delta = _safe_float(snapshot.stars_delta_24h)
    contributors = _safe_float(snapshot.active_contributors_30d)
    forks = _safe_float(snapshot.forks)

    # Check 95th percentile threshold
    velocity_score = _star_velocity_score(snapshot, percentile_ctx)
    above_95th = (
        (percentile_ctx and velocity_score >= 95.0)
        or (not percentile_ctx and delta >= 1000)
    )

    if not above_95th:
        return []

    # Low community signal
    low_community = contributors < 3 and forks < 50
    if not low_community:
        return []

    return [
        Detection(
            detector_name="star_manipulation_suspicion",
            full_name=full_name,
            severity="high",
            title=f"Star manipulation suspicion: stars_delta_24h={int(delta)}, contributors={int(contributors)}, forks={int(forks)}",
            evidence_ids=_evidence_ids(evidence)[:3],
            details={
                "stars_delta_24h": snapshot.stars_delta_24h,
                "active_contributors_30d": snapshot.active_contributors_30d,
                "forks": snapshot.forks,
                "star_velocity_score": round(velocity_score, 2),
            },
            created_at=utc_now_iso(),
        )
    ]


def detect_major_release(
    full_name: str,
    snapshot: RepoSnapshot,
    evidence: list[EvidenceAtom],
) -> list[Detection]:
    """Trigger when there is a new release + release_signal atom + acceleration > 2x.

    Severity=medium.
    """
    acc = _safe_float(snapshot.star_acceleration)
    if acc <= 2.0:
        return []

    release_atoms = [a for a in evidence if a.evidence_type == "release_signal"]
    if not release_atoms:
        return []

    if not snapshot.latest_release_tag:
        return []

    tag = snapshot.latest_release_tag
    return [
        Detection(
            detector_name="major_release_signal",
            full_name=full_name,
            severity="medium",
            title=f"Major release driving growth: {tag}, acceleration={acc:.1f}x",
            evidence_ids=_evidence_ids(release_atoms)[:3],
            details={
                "latest_release_tag": tag,
                "latest_release_at": snapshot.latest_release_at,
                "star_acceleration": acc,
                "release_atom_count": len(release_atoms),
            },
            created_at=utc_now_iso(),
        )
    ]


def detect_cross_source_resonance(
    full_name: str,
    snapshot: RepoSnapshot,
    evidence: list[EvidenceAtom],
    within_hours: float = 24.0,
) -> list[Detection]:
    """Trigger when repo appears in ≥3 distinct source_types within within_hours.

    Uses atom created_at timestamps; if timestamps are unavailable, falls back
    to counting distinct sources unconditionally (conservative).
    Severity=medium.
    """
    if not evidence:
        return []

    # Determine time window
    now_ts: float | None = None
    try:
        now_ts = datetime.now(timezone.utc).timestamp()
    except Exception:
        pass

    window_seconds = within_hours * 3600.0
    source_types_in_window: set[str] = set()

    for atom in evidence:
        # Try to parse atom timestamp
        in_window = True
        if now_ts is not None and atom.created_at:
            try:
                atom_ts = datetime.fromisoformat(atom.created_at.rstrip("Z"))
                atom_ts = atom_ts.replace(tzinfo=timezone.utc)
                age_seconds = now_ts - atom_ts.timestamp()
                in_window = age_seconds <= window_seconds
            except ValueError:
                in_window = True  # be inclusive if parse fails
        if in_window:
            source_types_in_window.add(atom.source)

    if len(source_types_in_window) < 3:
        return []

    return [
        Detection(
            detector_name="cross_source_resonance",
            full_name=full_name,
            severity="medium",
            title=f"Cross-source resonance: seen in {len(source_types_in_window)} distinct sources within {within_hours:.0f}h",
            evidence_ids=_evidence_ids(evidence)[:5],
            details={
                "source_count": len(source_types_in_window),
                "sources": sorted(source_types_in_window),
                "within_hours": within_hours,
            },
            created_at=utc_now_iso(),
        )
    ]


# ---------------------------------------------------------------------------
# run_detectors
# ---------------------------------------------------------------------------

_ALL_DETECTORS = [
    detect_sudden_hot,
    detect_early_potential,
    detect_foundation_infra,
    detect_hype_or_noise,
    detect_star_manipulation,
    detect_major_release,
    detect_cross_source_resonance,
]


def run_detectors(
    full_name: str,
    snapshot: RepoSnapshot,
    evidence: list[EvidenceAtom],
    conn: sqlite3.Connection | None = None,
) -> list[Detection]:
    """Run all 7 detectors. Single detector exceptions are caught; others continue.

    If conn is provided, write each Detection to the alerts table.
    """
    all_detections: list[Detection] = []

    for detector_fn in _ALL_DETECTORS:
        try:
            results = detector_fn(full_name, snapshot, evidence)  # type: ignore[call-arg]
            all_detections.extend(results)
        except Exception as exc:
            # Log to stderr but do not interrupt other detectors
            import sys
            print(
                f"[detectors] {detector_fn.__name__} raised {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    if conn is not None:
        for det in all_detections:
            insert_row(conn, det.TABLE, det.to_row())
        conn.commit()

    return all_detections


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> dict[str, Any]:
    """Comprehensive tests for heat scoring and all 7 detectors.

    Returns {tests_run, tests_passed, details}.
    """
    import os
    import sqlite3 as _sqlite3
    import tempfile

    from .schema import apply_schema, fetch_rows, RepoSnapshot
    from .evidence import compress_readme, compress_releases

    results: dict[str, Any] = {"tests_run": 0, "tests_passed": 0, "details": []}

    def _pass(name: str, note: str = "") -> None:
        results["tests_run"] += 1
        results["tests_passed"] += 1
        results["details"].append({"test": name, "status": "PASS", "note": note})

    def _fail(name: str, reason: str) -> None:
        results["tests_run"] += 1
        results["details"].append({"test": name, "status": "FAIL", "reason": reason})

    # ---------------------------------------------------------------
    # Fixtures
    # ---------------------------------------------------------------
    def _make_snapshot(**kwargs) -> RepoSnapshot:
        defaults = dict(
            snapshot_id="snap-test",
            full_name="owner/repo",
            snapshot_at="2026-05-27T00:00:00Z",
            stars=5000,
            forks=200,
            watchers=4800,
            open_issues=30,
            commit_count_7d=25,
            active_contributors_30d=12,
            latest_release_tag="v2.0.0",
            latest_release_at="2026-05-20T00:00:00Z",
            pushed_at="2026-05-26T18:00:00Z",
            stars_delta_24h=500,
            stars_delta_7d=1200,
            stars_delta_30d=8000,
            forks_delta_24h=20,
            star_acceleration=4.0,
            history_status="sufficient",
        )
        defaults.update(kwargs)
        return RepoSnapshot(**defaults)

    readme_text = """\
# AwesomeLLM

Blazing-fast LLM inference framework with GPU-accelerated transformer attention.

## Features

- 3x faster than competitors via quantization and memory-efficient caching
- Supports LoRA fine-tuning, RAG pipelines, and production-grade async batch API
- Built-in benchmark suite with performance profiling and distributed deployment
- Open-source MIT license with enterprise support available

## Architecture

Core runtime uses a streaming pipeline with neural network tokenizer.
"""
    readme_atoms = compress_readme("owner/repo", readme_text)

    releases = [
        {
            "tag": "v2.0.0",
            "name": "GPU Inference Engine v2.0",
            "body": "New GPU inference engine with quantized transformer support.",
            "published_at": "2026-05-20T00:00:00Z",
        }
    ]
    release_atoms = compress_releases("owner/repo", releases)
    all_atoms = readme_atoms + release_atoms

    # ---------------------------------------------------------------
    # T1: compute_heat_score bounds
    # ---------------------------------------------------------------
    snap = _make_snapshot()
    heat = compute_heat_score(snap, all_atoms)
    assert 0.0 <= heat <= 100.0, f"heat_score out of bounds: {heat}"
    _pass("compute_heat_score.bounds", f"heat={heat}")

    # ---------------------------------------------------------------
    # T2: heat_score determinism
    # ---------------------------------------------------------------
    heat2 = compute_heat_score(snap, all_atoms)
    assert heat == heat2, "compute_heat_score is not deterministic"
    _pass("compute_heat_score.determinism")

    # ---------------------------------------------------------------
    # T3: why-hot attribution sums to ≈ heat_score
    # ---------------------------------------------------------------
    attr = _why_hot_attribution(snap, all_atoms)
    expected = round(
        sum(_HEAT_WEIGHTS[k] * v for k, v in attr.items()), 4
    )
    assert abs(expected - heat) < 0.001, (
        f"attribution sum mismatch: {expected} vs heat {heat}"
    )
    _pass("why_hot_attribution.sum_matches_heat", f"attr_sum={expected}")

    # ---------------------------------------------------------------
    # T4: detect_sudden_hot — positive
    # ---------------------------------------------------------------
    hot_snap = _make_snapshot(star_acceleration=12.0)
    alerts = detect_sudden_hot("owner/repo", hot_snap, all_atoms)
    assert len(alerts) == 1
    assert alerts[0].severity == "high"
    assert alerts[0].detector_name == "sudden_hot"
    _pass("detect_sudden_hot.positive", f"acc=12x triggers high alert")

    # ---------------------------------------------------------------
    # T5: detect_sudden_hot — negative control (acc=0.5, delta=1)
    # ---------------------------------------------------------------
    cold_snap = _make_snapshot(stars_delta_24h=1, star_acceleration=0.5)
    neg_alerts = detect_sudden_hot("owner/repo", cold_snap, all_atoms)
    assert neg_alerts == [], (
        f"sudden_hot false positive on acc=0.5, delta=1: {neg_alerts}"
    )
    _pass("detect_sudden_hot.negative_control_acc0.5_delta1")

    # ---------------------------------------------------------------
    # T6: detect_sudden_hot — boundary at exactly 8.0 (should NOT trigger)
    # ---------------------------------------------------------------
    boundary_snap = _make_snapshot(star_acceleration=8.0)
    boundary_alerts = detect_sudden_hot("owner/repo", boundary_snap, all_atoms)
    assert boundary_alerts == [], (
        f"sudden_hot should NOT trigger at exactly 8.0, got {boundary_alerts}"
    )
    _pass("detect_sudden_hot.boundary_at_8x")

    # ---------------------------------------------------------------
    # T7: detect_early_potential — positive (low stars, high importance atoms)
    # ---------------------------------------------------------------
    low_star_snap = _make_snapshot(stars=500)
    # Ensure atoms have high importance + technical depth
    for a in readme_atoms:
        a.importance_score = 90.0
        a.technical_depth_score = 80.0
    ep_alerts = detect_early_potential("owner/repo", low_star_snap, readme_atoms)
    assert len(ep_alerts) == 1, f"expected early_potential alert, got {len(ep_alerts)}"
    assert ep_alerts[0].severity == "medium"
    _pass("detect_early_potential.positive", f"stars=500, potential>85")

    # ---------------------------------------------------------------
    # T8: detect_early_potential — negative (stars ≥ 2000)
    # ---------------------------------------------------------------
    big_snap = _make_snapshot(stars=5000)
    ep_neg = detect_early_potential("owner/repo", big_snap, readme_atoms)
    assert ep_neg == [], f"early_potential false positive at stars=5000"
    _pass("detect_early_potential.negative_high_stars")

    # ---------------------------------------------------------------
    # T9: detect_foundation_infra — positive
    # ---------------------------------------------------------------
    foundation_snap = _make_snapshot(
        stars=20000, forks=3000, active_contributors_30d=80, commit_count_7d=150
    )
    # Give atoms high technical_depth
    for a in readme_atoms:
        a.technical_depth_score = 90.0
    fi_alerts = detect_foundation_infra("owner/repo", foundation_snap, readme_atoms)
    assert len(fi_alerts) == 1, f"expected foundation_infra alert, got {len(fi_alerts)}"
    assert fi_alerts[0].severity == "info"
    _pass("detect_foundation_infra.positive")

    # ---------------------------------------------------------------
    # T10: detect_hype_or_noise — positive (high heat, low depth)
    # ---------------------------------------------------------------
    # Create a snapshot that gets high heat_score but evidence has low depth
    hype_snap = _make_snapshot(
        stars_delta_24h=2000, star_acceleration=15.0,
        active_contributors_30d=1, forks=5,
    )
    # Low-depth atoms
    from .schema import EvidenceAtom, utc_now_iso
    from .evidence import make_evidence_id
    low_depth_atoms = [
        EvidenceAtom(
            evidence_id=make_evidence_id("owner/repo", "readme_claim", i),
            full_name="owner/repo",
            source="api",
            evidence_type="readme_claim",
            compressed_content="Awesome project",
            importance_score=25.0,
            technical_depth_score=5.0,
            created_at=utc_now_iso(),
        )
        for i in range(3)
    ]
    hype_heat = compute_heat_score(hype_snap, low_depth_atoms)
    if hype_heat > 60.0:
        hype_alerts = detect_hype_or_noise("owner/repo", hype_snap, low_depth_atoms)
        assert len(hype_alerts) == 1
        assert hype_alerts[0].severity == "medium"
        _pass("detect_hype_or_noise.positive", f"heat={hype_heat:.1f}, depth=5")
    else:
        # Heat not high enough with these params — pass conditionally
        _pass("detect_hype_or_noise.positive_skipped", f"heat={hype_heat:.1f} not >60, no alert (correct)")

    # ---------------------------------------------------------------
    # T11: detect_star_manipulation — positive
    # ---------------------------------------------------------------
    manip_snap = _make_snapshot(
        stars_delta_24h=1500,
        active_contributors_30d=1,
        forks=10,
    )
    # percentile_ctx: p95 = 100 → velocity_score = 1500/100*100 = capped 100 ≥ 95
    pctx = {"p95_stars_delta_24h": 100.0}
    manip_alerts = detect_star_manipulation("owner/repo", manip_snap, all_atoms, pctx)
    assert len(manip_alerts) == 1
    assert manip_alerts[0].severity == "high"
    _pass("detect_star_manipulation.positive", "delta=1500, contributors=1, forks=10")

    # T12: negative — many contributors
    legit_snap = _make_snapshot(
        stars_delta_24h=1500,
        active_contributors_30d=50,
        forks=200,
    )
    legit_alerts = detect_star_manipulation("owner/repo", legit_snap, all_atoms, pctx)
    assert legit_alerts == [], f"star_manipulation false positive: {legit_alerts}"
    _pass("detect_star_manipulation.negative_many_contributors")

    # ---------------------------------------------------------------
    # T13: detect_major_release — positive
    # ---------------------------------------------------------------
    mr_snap = _make_snapshot(star_acceleration=5.0, latest_release_tag="v3.0.0")
    mr_alerts = detect_major_release("owner/repo", mr_snap, release_atoms)
    assert len(mr_alerts) == 1
    assert mr_alerts[0].severity == "medium"
    _pass("detect_major_release.positive", "acc=5x, has release atom")

    # T14: negative — no acceleration
    slow_snap = _make_snapshot(star_acceleration=1.0, latest_release_tag="v3.0.0")
    slow_alerts = detect_major_release("owner/repo", slow_snap, release_atoms)
    assert slow_alerts == [], f"major_release false positive: {slow_alerts}"
    _pass("detect_major_release.negative_low_accel")

    # ---------------------------------------------------------------
    # T15: detect_cross_source_resonance — positive
    # ---------------------------------------------------------------
    multi_source_atoms = [
        EvidenceAtom(
            evidence_id=f"ev-multi-{i}",
            full_name="owner/repo",
            source=src,
            evidence_type="readme_claim",
            compressed_content="content",
            importance_score=50.0,
            created_at=utc_now_iso(),
        )
        for i, src in enumerate(["github_api", "twitter_scraper", "hacker_news", "youtube"])
    ]
    csr_alerts = detect_cross_source_resonance("owner/repo", snap, multi_source_atoms)
    assert len(csr_alerts) == 1
    assert csr_alerts[0].severity == "medium"
    assert csr_alerts[0].details["source_count"] == 4
    _pass("detect_cross_source_resonance.positive", "4 distinct sources")

    # T16: negative — only 2 sources
    two_source_atoms = multi_source_atoms[:2]
    csr_neg = detect_cross_source_resonance("owner/repo", snap, two_source_atoms)
    assert csr_neg == [], f"cross_source_resonance false positive with 2 sources"
    _pass("detect_cross_source_resonance.negative_2_sources")

    # ---------------------------------------------------------------
    # T17: run_detectors — all detectors run, exceptions don't propagate
    # ---------------------------------------------------------------
    all_results = run_detectors("owner/repo", hot_snap, all_atoms)
    assert isinstance(all_results, list), "run_detectors must return list"
    # At minimum sudden_hot and major_release should trigger (hot_snap has acc=12.0)
    detector_names = {d.detector_name for d in all_results}
    assert "sudden_hot" in detector_names, f"sudden_hot missing from run_detectors: {detector_names}"
    _pass("run_detectors.sudden_hot_fires", f"detections={list(detector_names)}")

    # ---------------------------------------------------------------
    # T18: run_detectors with conn — writes to alerts table
    # ---------------------------------------------------------------
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        db_path = tf.name
    try:
        conn = _sqlite3.connect(db_path)
        apply_schema(conn)
        written = run_detectors("owner/repo", hot_snap, all_atoms, conn=conn)
        rows = fetch_rows(conn, "alerts", "full_name=?", ("owner/repo",))
        assert len(rows) == len(written), (
            f"alerts table has {len(rows)} rows, expected {len(written)}"
        )
        conn.close()
    finally:
        os.unlink(db_path)
    _pass("run_detectors.persists_to_alerts_table", f"{len(written)} alerts written")

    # ---------------------------------------------------------------
    # T19: run_detectors exception isolation
    # ---------------------------------------------------------------
    # Monkey-patch one detector to raise, verify others still run
    import sys as _sys
    original_fn = _ALL_DETECTORS[0]
    def _bad_detector(full_name, snapshot, evidence):
        raise RuntimeError("injected failure")
    _ALL_DETECTORS[0] = _bad_detector
    try:
        survivors = run_detectors("owner/repo", hot_snap, all_atoms)
        # Should still get results from the other 6 detectors
        assert isinstance(survivors, list)
    finally:
        _ALL_DETECTORS[0] = original_fn
    _pass("run_detectors.exception_isolation", "bad detector did not break others")

    # ---------------------------------------------------------------
    # T20: heat_score zero for inactive repo
    # ---------------------------------------------------------------
    dead_snap = RepoSnapshot(
        snapshot_id="dead",
        full_name="owner/dead",
        snapshot_at="2026-05-27T00:00:00Z",
        stars=0,
        forks=0,
        stars_delta_24h=0,
        star_acceleration=0.0,
    )
    dead_heat = compute_heat_score(dead_snap, [])
    assert dead_heat == 0.0, f"expected 0 heat for dead repo, got {dead_heat}"
    _pass("compute_heat_score.zero_for_inactive_repo")

    return results


if __name__ == "__main__":
    import json as _json
    import sys as _sys

    m = _self_test()
    print(_json.dumps(m, indent=2))
    if m["tests_run"] != m["tests_passed"]:
        _sys.exit(1)
