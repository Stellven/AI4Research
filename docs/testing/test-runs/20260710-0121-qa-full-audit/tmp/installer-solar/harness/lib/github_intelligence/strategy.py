"""P0 strategy backbone for GitHub Project Intelligence.

This module is the Python-side convergence point for strategy tracks, license
gates, project dossiers and first-pass strategy decisions. It mirrors the
existing tech-hotspot-radar shell policy without shelling out, so tests and
library callers can exercise the real GHPI chain in-process.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .action_engine import build_action_recommendation
from .evidence import extract_local_semantic_summary
from .schema import (
    DecisionFeedback,
    EvidenceAtom,
    RepoProjectDossier,
    RepoSnapshot,
    StrategyDecision,
    TaskCandidateDraft,
    insert_row,
    utc_now_iso,
)


DECISION_ACTIONS: dict[str, str] = {
    "build_new": "create_new_open_source_project",
    "contribute_existing": "contribute_to_existing_project",
    "feature_intake": "build_extension_or_plugin",
    "boost_own_project": "build_extension_or_plugin",
    "write_analysis": "write_analysis_report",
    "watch": "watch_only",
    "ignore": "ignore",
}

DECISION_TASK_TYPES: dict[str, str] = {
    "build_new": "build_new",
    "contribute_existing": "contribute_existing",
    "feature_intake": "feature_intake",
    "boost_own_project": "boost_own_project",
    "write_analysis": "write_analysis",
    "watch": "watch",
}

_ALLOWED_LICENSES = frozenset({"MIT", "APACHE-2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "ISC", "UNLICENSE", "CC0-1.0"})
_RESTRICTED_LICENSES = frozenset({"GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0", "MPL-2.0", "EPL-2.0", "SSPL-1.0"})
_FORBIDDEN_LICENSES = frozenset({"PROPRIETARY", "ALL-RIGHTS-RESERVED", "CUSTOM-NONCOMMERCIAL"})


def load_strategy_tracks(path: str | Path) -> list[dict[str, Any]]:
    """Load strategy track config from the existing tech-hotspot-radar YAML."""
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    tracks = data.get("tracks") or []
    if not isinstance(tracks, list):
        raise ValueError("strategy tracks config must contain a list at tracks")
    return [track for track in tracks if isinstance(track, dict) and track.get("name")]


def upsert_strategy_tracks(conn: sqlite3.Connection, tracks: list[dict[str, Any]]) -> int:
    """Persist tracks into the existing tech-hotspot-radar-compatible table."""
    count = 0
    for track in tracks:
        name = str(track.get("name") or "").strip()
        if not name:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO strategy_tracks
               (name, keywords, github_topics, languages, internal_capabilities, alert_threshold)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                name,
                json.dumps(track.get("keywords") or [], ensure_ascii=False),
                json.dumps(track.get("github_topics") or [], ensure_ascii=False),
                json.dumps(track.get("languages") or [], ensure_ascii=False),
                json.dumps(track.get("internal_capabilities") or [], ensure_ascii=False),
                float(track.get("alert_threshold") or 1.0),
            ),
        )
        count += 1
    conn.commit()
    return count


def load_strategy_tracks_from_db(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Load strategy tracks from the shared `strategy_tracks` table."""
    rows = conn.execute(
        """SELECT name, keywords, github_topics, languages, internal_capabilities, alert_threshold
           FROM strategy_tracks ORDER BY name"""
    ).fetchall()
    tracks: list[dict[str, Any]] = []
    for row in rows:
        tracks.append({
            "name": row[0],
            "keywords": _loads_list(row[1]),
            "github_topics": _loads_list(row[2]),
            "languages": _loads_list(row[3]),
            "internal_capabilities": _loads_list(row[4]),
            "alert_threshold": row[5],
        })
    return tracks


def _loads_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    try:
        parsed = json.loads(value or "[]")
    except Exception:
        parsed = []
    return [str(v) for v in parsed] if isinstance(parsed, list) else []


def match_strategy_track(repo: dict[str, Any], tracks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the best matching strategy track for discovery/filtering/scoring."""
    text = " ".join(
        str(repo.get(key) or "")
        for key in ("full_name", "description", "language", "topics", "readme")
    ).lower()
    best: tuple[float, str, dict[str, Any]] | None = None
    for track in tracks:
        keywords = [str(k).lower() for k in track.get("keywords") or []]
        topics = [str(k).lower() for k in track.get("github_topics") or []]
        languages = [str(k).lower() for k in track.get("languages") or []]
        score = 0.0
        score += sum(2.0 for keyword in keywords if keyword and keyword in text)
        score += sum(1.5 for topic in topics if topic and topic in text)
        repo_lang = str(repo.get("language") or "").lower()
        if repo_lang and repo_lang in languages:
            score += 0.5
        if score <= 0:
            continue
        candidate = (score, str(track["name"]), track)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return None
    return {"name": best[1], "score": best[0], "track": best[2]}


TRAFFIC_METRICS = frozenset({
    "views",
    "clones",
    "referrers",
    "popular_paths",
    "popular_referrers",
})


def metric_availability(metric_name: str, *, access_level: str | None = None) -> dict[str, Any]:
    """Classify whether a metric is stable, conditional, or only inferred.

    GitHub traffic endpoints are available only for repositories the token can
    administer or otherwise access with traffic scope. External public repos
    cannot expose views/clones/referrers/popular content through the public API.
    """
    metric = metric_name.strip().lower()
    access = (access_level or "external_repo").strip().lower()
    if metric in TRAFFIC_METRICS:
        if access == "own_or_authorized_repo":
            return {
                "tier": "conditional",
                "available": True,
                "boundary": "own_or_authorized_repo_only",
                "reason": "GitHub traffic API requires repo ownership or authorized access.",
            }
        return {
            "tier": "inferred",
            "available": False,
            "boundary": "own_or_authorized_repo_only",
            "reason": "External repo traffic metrics are not available; use public proxies only.",
        }
    return {
        "tier": "stable",
        "available": True,
        "boundary": "public_repo_api",
        "reason": "Public repository metadata can be collected through normal repo/search APIs.",
    }


def build_metric_availability(access_level: str | None = None) -> dict[str, dict[str, Any]]:
    metrics = [
        "stars",
        "forks",
        "open_issues",
        "commit_count_7d",
        "active_contributors_30d",
        "views",
        "clones",
        "referrers",
        "popular_paths",
        "popular_referrers",
    ]
    return {name: metric_availability(name, access_level=access_level) for name in metrics}


def normalize_license(license_id: str | None) -> str:
    normalized = (license_id or "").strip().upper().replace(" ", "")
    return normalized or "UNKNOWN"


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def evaluate_license_gate(license_id: str | None, *, text: str = "") -> dict[str, Any]:
    """Classify SPDX-ish license and converge license/IP/security hard gates."""
    normalized = normalize_license(license_id)
    if normalized in _ALLOWED_LICENSES:
        classification = "allowed"
        reason = "spdx allow-list"
    elif normalized in _FORBIDDEN_LICENSES:
        classification = "forbidden"
        reason = "spdx forbid-list"
    elif normalized in _RESTRICTED_LICENSES:
        classification = "restricted"
        reason = "spdx restrict-list"
    elif normalized in {"NOASSERTION", "UNKNOWN", "NONE"}:
        classification = "restricted"
        reason = "license missing or NOASSERTION"
    else:
        classification = "restricted"
        reason = "spdx not on any list"

    lower = text.lower()
    security_terms = ("vulnerability", "exploit", "malware", "ransomware", "cve-", "red team")
    ip_terms = ("all rights reserved", "proprietary", "commercial license", "source available only")
    security_hits = [term for term in security_terms if term in lower]
    ip_hits = [term for term in ip_terms if term in lower]
    security_flag = bool(security_hits)
    ip_flag = bool(ip_hits)
    block_copyleft = _truthy_env("RADAR_BLOCK_COPYLEFT")
    block_restricted = _truthy_env("RADAR_BLOCK_RESTRICTED")
    copy_left_flag = normalized.startswith(("GPL", "AGPL", "LGPL"))
    blocked = (
        classification == "forbidden"
        or security_flag
        or (block_copyleft and copy_left_flag)
        or (block_restricted and classification == "restricted")
    )
    block_reasons = [
        reason for reason, enabled in (
            (f"license {normalized} on forbid-list", classification == "forbidden"),
            ("security-sensitive wording detected", security_flag),
            (f"copyleft license {normalized} blocked by RADAR_BLOCK_COPYLEFT=1", block_copyleft and copy_left_flag),
            (f"restricted license {normalized} blocked by RADAR_BLOCK_RESTRICTED=1", block_restricted and classification == "restricted"),
        ) if enabled
    ]
    return {
        "license_id": normalized,
        "classification": classification,
        "classification_reason": reason,
        "copy_left_flag": copy_left_flag,
        "auto_block_default": classification == "forbidden",
        "ip_flag": ip_flag,
        "security_flag": security_flag,
        "license_gate": {
            "license_id": normalized,
            "classification": classification,
            "classification_reason": reason,
            "copy_left_flag": copy_left_flag,
            "auto_block_default": classification == "forbidden",
        },
        "ip_gate": {
            "flagged": ip_flag,
            "matched_terms": ip_hits,
            "blocked": False,
        },
        "security_gate": {
            "flagged": security_flag,
            "matched_terms": security_hits,
            "blocked": security_flag,
        },
        "blocked": blocked,
        "block_reasons": block_reasons,
        "config": {
            "RADAR_BLOCK_COPYLEFT": block_copyleft,
            "RADAR_BLOCK_RESTRICTED": block_restricted,
        },
    }


def compute_velocity_and_anomalies(snapshot: RepoSnapshot, evidence_ids: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compute 1h/24h/7d/30d velocity fields and anomaly flags."""
    velocity = {
        "stars_delta_1h": snapshot.stars_delta_1h,
        "stars_delta_24h": snapshot.stars_delta_24h,
        "stars_delta_7d": snapshot.stars_delta_7d,
        "stars_delta_30d": snapshot.stars_delta_30d,
        "star_acceleration": snapshot.star_acceleration,
        "history_status": snapshot.history_status,
    }
    anomalies: list[dict[str, Any]] = []
    delta24 = float(snapshot.stars_delta_24h or 0)
    delta7 = float(snapshot.stars_delta_7d or 0)
    acc = float(snapshot.star_acceleration or 0)
    if acc > 8.0:
        anomalies.append({"name": "sudden_hot", "score": acc, "evidence_ids": evidence_ids[:5]})
    if delta24 > 0 and delta7 > 0 and delta24 > max(10.0, (delta7 / 7.0) * 3.0):
        anomalies.append({"name": "trending_velocity", "score": round(delta24 / max(delta7 / 7.0, 1.0), 4), "evidence_ids": evidence_ids[:5]})
    if snapshot.stars and snapshot.stars < 2000 and delta24 >= 25:
        anomalies.append({"name": "early_potential", "score": delta24, "evidence_ids": evidence_ids[:5]})
    return velocity, anomalies


def build_project_dossier(
    full_name: str,
    snapshot: RepoSnapshot,
    evidence: list[EvidenceAtom],
    *,
    strategy_track: str | None = None,
    license_id: str | None = None,
    repo_text: str = "",
    access_level: str | None = None,
) -> RepoProjectDossier:
    evidence_ids = [atom.evidence_id for atom in evidence]
    local_summary = extract_local_semantic_summary(evidence)
    velocity, anomalies = compute_velocity_and_anomalies(snapshot, evidence_ids)
    metrics = {
        "stars": snapshot.stars,
        "forks": snapshot.forks,
        "open_issues": snapshot.open_issues,
        "commit_count_7d": snapshot.commit_count_7d,
        "active_contributors_30d": snapshot.active_contributors_30d,
        "metric_availability": build_metric_availability(access_level),
    }
    top_summary = next((atom.one_sentence_summary for atom in evidence if atom.one_sentence_summary), None)
    created_at = utc_now_iso()
    return RepoProjectDossier(
        dossier_id=RepoProjectDossier.make_id(full_name, created_at),
        full_name=full_name,
        created_at=created_at,
        strategy_track=strategy_track,
        summary=top_summary or f"{full_name} project intelligence dossier",
        metrics={k: v for k, v in metrics.items() if v is not None},
        velocity={k: v for k, v in velocity.items() if v is not None},
        anomaly_flags=anomalies,
        local_evidence_summary=local_summary,
        license_gate=evaluate_license_gate(license_id, text=repo_text),
        evidence_ids=evidence_ids,
    )


def decide_strategy(
    dossier: RepoProjectDossier,
    *,
    owned_repos: set[str] | None = None,
) -> StrategyDecision:
    owned_repos = owned_repos or set()
    gate = dossier.license_gate or {}
    velocity = dossier.velocity or {}
    anomalies = {item.get("name"): item for item in dossier.anomaly_flags if isinstance(item, dict)}
    evidence_ids = list(dossier.evidence_ids or [])
    evidence_floor_met = len(evidence_ids) >= 3
    risks = list(gate.get("block_reasons") or [])

    action_recommendation: dict[str, Any] = {
        "recommended_action": "watch_only",
        "contribution_opportunity_score": 0.0,
        "influence_opportunity_score": 0.0,
        "action_brief": {"recommended_action": "watch_only"},
        "development_requirement_brief": {},
    }

    if gate.get("blocked"):
        decision = "ignore"
        route_reason = "hard gate blocked"
        recommended_action = DECISION_ACTIONS[decision]
    elif not evidence_floor_met:
        if float(velocity.get("stars_delta_24h") or 0) > 0:
            decision = "watch"
            route_reason = "insufficient evidence for actionable conclusion"
        else:
            decision = "ignore"
            route_reason = "insufficient evidence and no positive velocity"
        recommended_action = DECISION_ACTIONS[decision]
    elif dossier.full_name in owned_repos:
        decision = "boost_own_project"
        route_reason = "owned project match"
        action_recommendation = build_action_recommendation(dossier)
        recommended_action = action_recommendation["recommended_action"]
    elif gate.get("classification") == "restricted":
        decision = "write_analysis"
        route_reason = "license requires review"
        recommended_action = DECISION_ACTIONS[decision]
    else:
        action_recommendation = build_action_recommendation(dossier)
        recommended_action = action_recommendation["recommended_action"]
        if recommended_action == "contribute_to_existing_project":
            decision = "contribute_existing"
            route_reason = "action engine contribution opportunity"
        elif recommended_action == "create_new_open_source_project":
            decision = "build_new"
            route_reason = "action engine new project opportunity"
        elif "sudden_hot" in anomalies or "trending_velocity" in anomalies:
            decision = "build_new"
            route_reason = "velocity anomaly"
        elif recommended_action in {"build_extension_or_plugin", "fork_and_specialize"}:
            decision = "feature_intake"
            route_reason = "action engine extension/fork opportunity"
        elif (dossier.local_evidence_summary.get("pain_points") or []):
            decision = "feature_intake"
            route_reason = "issue/pr pain evidence"
        elif (dossier.local_evidence_summary.get("moat") or []):
            decision = "contribute_existing"
            route_reason = "technical moat evidence"
        elif float(velocity.get("stars_delta_24h") or 0) > 0:
            decision = "watch"
            route_reason = "positive velocity"
        else:
            decision = "ignore"
            route_reason = "insufficient actionable signal"

    confidence = 0.55
    confidence += min(0.25, len(evidence_ids) * 0.03)
    confidence += 0.10 if dossier.anomaly_flags else 0.0
    confidence -= 0.10 if gate.get("classification") == "restricted" else 0.0
    confidence = round(max(0.51, min(0.98, confidence)), 3)

    technical_entry_point = dossier.summary or "review repo dossier and evidence atoms"
    if decision in {"build_new", "contribute_existing"} and recommended_action not in {
        DECISION_ACTIONS["build_new"],
        DECISION_ACTIONS["contribute_existing"],
    }:
        recommended_action = DECISION_ACTIONS[decision]
        action_recommendation["recommended_action"] = recommended_action
        if isinstance(action_recommendation.get("action_brief"), dict):
            action_recommendation["action_brief"]["recommended_action"] = recommended_action

    evidence_map = {
        "repo": dossier.full_name,
        "evidence_ids": evidence_ids,
        "dossier_id": dossier.dossier_id,
        "strategy_track": dossier.strategy_track,
        "anomaly_flags": dossier.anomaly_flags,
        "gate_status": gate,
        "license_gate": gate.get("license_gate") or gate,
        "ip_gate": gate.get("ip_gate", {}),
        "security_gate": gate.get("security_gate", {}),
        "evidence_floor_met": evidence_floor_met,
        "route_reason": route_reason,
        "recommended_action": recommended_action,
        "action_recommendation": action_recommendation,
        "contribution_opportunity_score": action_recommendation["contribution_opportunity_score"],
        "influence_opportunity_score": action_recommendation["influence_opportunity_score"],
        "metric_availability": dossier.metrics.get("metric_availability", {}),
    }
    if decision in {"ignore", "write_analysis", "watch"}:
        action_recommendation["recommended_action"] = DECISION_ACTIONS[decision]
        recommended_action = action_recommendation["recommended_action"]
    created_at = utc_now_iso()
    strategy_decision = StrategyDecision(
        decision_id=StrategyDecision.make_id(dossier.full_name, decision, created_at),
        full_name=dossier.full_name,
        decision=decision,
        confidence=confidence,
        recommended_action=recommended_action,
        technical_entry_point=technical_entry_point,
        risks=risks or ["no immediate blocking risk detected"],
        task_candidates=[],
        evidence_map=evidence_map,
        gate_status=gate,
        created_at=created_at,
    )
    strategy_decision.task_candidates = [
        asdict(build_task_candidate(strategy_decision, dossier))
    ] if decision in DECISION_TASK_TYPES else []
    return strategy_decision


def build_development_requirement_brief(
    decision: StrategyDecision,
    dossier: RepoProjectDossier,
) -> dict[str, Any]:
    """Build the internal development brief for create/contribute decisions."""
    action_payload = {}
    if isinstance(decision.evidence_map, dict):
        action_payload = decision.evidence_map.get("action_recommendation") or {}
    action_brief = action_payload.get("development_requirement_brief") or {}
    if action_brief:
        enriched = dict(action_brief)
        enriched["decision_id"] = decision.decision_id
        return enriched
    if decision.recommended_action not in {"create_new_open_source_project", "contribute_to_existing_project"}:
        if decision.decision not in {"build_new", "contribute_existing"}:
            return {}
        action = "create_new_open_source_project" if decision.decision == "build_new" else "contribute_to_existing_project"
    else:
        action = decision.recommended_action
    if action not in {"create_new_open_source_project", "contribute_to_existing_project"}:
        return {}
    mode = "create_new_project" if action == "create_new_open_source_project" else "contribute_existing"
    return {
        "brief_type": "development_requirement",
        "mode": mode,
        "repo": dossier.full_name,
        "problem_statement": decision.technical_entry_point,
        "recommended_action": decision.recommended_action,
        "scope": [
            "derive requirement from evidence-backed GHPI decision",
            "keep task export as draft until human feedback accepts it",
        ],
        "acceptance_criteria": [
            "links back to decision_id and evidence_ids",
            "contains no external task creation side effects",
        ],
        "risk_notes": list(decision.risks or []),
        "evidence_ids": list(dossier.evidence_ids or [])[:8],
    }


def build_task_candidate(
    decision: StrategyDecision,
    dossier: RepoProjectDossier,
) -> TaskCandidateDraft:
    """Convert a strategy decision to a draft-only Jira/GitLab task candidate."""
    if decision.decision not in DECISION_TASK_TYPES:
        raise ValueError(f"decision cannot be converted to task candidate: {decision.decision}")
    evidence_ids = list(dossier.evidence_ids or [])
    task_type = DECISION_TASK_TYPES[decision.decision]
    candidate_id = "task_" + hashlib.sha256(
        f"{decision.decision_id}\0{dossier.full_name}\0{task_type}".encode()
    ).hexdigest()[:16]
    feedbackable_id = f"feedback:{decision.decision_id}:{candidate_id}"
    title = f"{dossier.full_name} / {task_type}"
    body = "\n".join([
        f"Decision: {decision.decision}",
        f"Recommended action: {decision.recommended_action}",
        f"Technical entry point: {decision.technical_entry_point}",
        f"Evidence IDs: {', '.join(evidence_ids[:8])}",
    ])
    action_payload = {}
    if isinstance(decision.evidence_map, dict):
        action_payload = decision.evidence_map.get("action_recommendation") or {}
    draft_exports = {
        "jira": {
            "draft_only": True,
            "project_key": None,
            "issue_type": "Task",
            "summary": title,
            "description": body,
            "labels": ["ghpi", task_type],
            "ghpi_action": action_payload.get("action_brief", {}),
        },
        "gitlab": {
            "draft_only": True,
            "project_id": None,
            "title": title,
            "description": body,
            "labels": ["ghpi", task_type],
            "confidential": False,
            "ghpi_action": action_payload.get("action_brief", {}),
        },
    }
    return TaskCandidateDraft(
        candidate_id=candidate_id,
        decision_id=decision.decision_id,
        full_name=dossier.full_name,
        task_type=task_type,
        title=title,
        priority=90 if task_type in {"build_new", "boost_own_project"} else 70 if task_type in {"contribute_existing", "feature_intake", "write_analysis"} else 50,
        recommended_action=decision.recommended_action,
        technical_entry_point=decision.technical_entry_point,
        draft_exports=draft_exports,
        development_requirement_brief=build_development_requirement_brief(decision, dossier),
        evidence_ids=evidence_ids[:8],
        feedbackable_id=feedbackable_id,
    )


def persist_project_intelligence(
    conn: sqlite3.Connection,
    dossier: RepoProjectDossier,
    decision: StrategyDecision,
) -> None:
    insert_row(conn, RepoProjectDossier.TABLE, dossier.to_row())
    insert_row(conn, StrategyDecision.TABLE, decision.to_row())
    for item in decision.task_candidates:
        draft = TaskCandidateDraft.from_row(item)
        insert_row(conn, TaskCandidateDraft.TABLE, draft.to_row())
    conn.commit()


def record_decision_feedback(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    candidate_id: str | None = None,
    feedback_status: str,
    execution_status: str = "not_started",
    outcome: str | None = None,
    lessons_learned: list[str] | None = None,
) -> DecisionFeedback:
    feedback_id = "fb_" + hashlib.sha256(
        f"{decision_id}\0{candidate_id or ''}".encode()
    ).hexdigest()[:18]
    feedback = DecisionFeedback(
        feedback_id=feedback_id,
        decision_id=decision_id,
        candidate_id=candidate_id,
        feedback_status=feedback_status,
        execution_status=execution_status,
        outcome=outcome,
        lessons_learned=lessons_learned or [],
    )
    insert_row(conn, DecisionFeedback.TABLE, feedback.to_row())
    conn.commit()
    return feedback


def to_jsonable(value: Any) -> Any:
    if isinstance(value, (RepoProjectDossier, StrategyDecision)):
        return value.to_row()
    return json.loads(json.dumps(value, ensure_ascii=False))
