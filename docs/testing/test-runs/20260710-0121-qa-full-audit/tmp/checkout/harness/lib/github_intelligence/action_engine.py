"""Action recommendation engine for GitHub Project Intelligence.

Transforms a project dossier into evidence-bound open-source action guidance.
The functions are deterministic and side-effect free so callers can unit-test
scoring without touching external systems.
"""
from __future__ import annotations

from typing import Any

from .schema import RepoProjectDossier


RECOMMENDED_ACTIONS: tuple[str, ...] = (
    "contribute_to_existing_project",
    "build_extension_or_plugin",
    "fork_and_specialize",
    "create_new_open_source_project",
    "write_analysis_report",
    "watch_only",
    "ignore",
)


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _evidence_ids(dossier: RepoProjectDossier) -> list[str]:
    return list(dossier.evidence_ids or [])[:8]


def _summary_list(dossier: RepoProjectDossier, key: str) -> list[str]:
    value = (dossier.local_evidence_summary or {}).get(key) or []
    return value if isinstance(value, list) else []


def compute_contribution_opportunity_score(dossier: RepoProjectDossier) -> dict[str, Any]:
    """Score how suitable the repo is for upstream contribution."""
    metrics = dossier.metrics or {}
    gate = dossier.license_gate or {}
    pain_points = _summary_list(dossier, "pain_points")
    moat = _summary_list(dossier, "moat")
    evidence_ids = _evidence_ids(dossier)

    open_issues = float(metrics.get("open_issues") or 0)
    contributors = float(metrics.get("active_contributors_30d") or 0)
    commits = float(metrics.get("commit_count_7d") or 0)
    license_bonus = 20.0 if gate.get("classification") == "allowed" and not gate.get("blocked") else 0.0

    components = {
        "license_fit": license_bonus,
        "pain_or_gap_signal": min(30.0, len(pain_points) * 15.0 + len(moat) * 8.0),
        "issue_surface": min(20.0, open_issues * 1.5),
        "maintainer_activity": min(20.0, contributors * 3.0 + commits * 0.35),
        "evidence_support": min(10.0, len(evidence_ids) * 2.0),
    }
    score = _clamp_score(sum(components.values()))
    return {
        "score": score,
        "components": components,
        "evidence_ids": evidence_ids,
        "explanation": (
            "contribution score combines license fit, pain/gap evidence, issue surface, "
            "maintainer activity, and evidence coverage"
        ),
    }


def compute_influence_opportunity_score(dossier: RepoProjectDossier) -> dict[str, Any]:
    """Score how attractive the repo is for influence-building action."""
    metrics = dossier.metrics or {}
    velocity = dossier.velocity or {}
    anomalies = dossier.anomaly_flags or []
    evidence_ids = _evidence_ids(dossier)

    stars = float(metrics.get("stars") or 0)
    delta24 = float(velocity.get("stars_delta_24h") or 0)
    delta7 = float(velocity.get("stars_delta_7d") or 0)
    acceleration = float(velocity.get("star_acceleration") or 0)
    anomaly_bonus = min(25.0, len(anomalies) * 12.5)
    summary = dossier.local_evidence_summary or {}
    novelty_count = len(summary.get("novelty") or []) if isinstance(summary.get("novelty"), list) else 0

    components = {
        "market_attention": min(20.0, stars / 250.0),
        "velocity": min(25.0, delta24 * 0.18 + delta7 * 0.03),
        "acceleration": min(20.0, acceleration * 4.0),
        "anomaly_signal": anomaly_bonus,
        "novelty_signal": min(10.0, novelty_count * 5.0),
        "evidence_support": min(10.0, len(evidence_ids) * 2.0),
    }
    score = _clamp_score(sum(components.values()))
    return {
        "score": score,
        "components": components,
        "evidence_ids": evidence_ids,
        "explanation": (
            "influence score combines attention, velocity, acceleration, anomalies, "
            "novelty, and evidence coverage"
        ),
    }


def choose_recommended_action(
    dossier: RepoProjectDossier,
    contribution: dict[str, Any],
    influence: dict[str, Any],
) -> str:
    """Choose one of the PM-required action enum values."""
    gate = dossier.license_gate or {}
    contrib = float(contribution.get("score") or 0.0)
    infl = float(influence.get("score") or 0.0)
    pain_points = _summary_list(dossier, "pain_points")
    moat = _summary_list(dossier, "moat")

    if gate.get("blocked"):
        return "ignore"
    if gate.get("classification") == "restricted":
        return "write_analysis_report"
    if contrib >= 70 and (pain_points or moat):
        return "contribute_to_existing_project"
    if infl >= 80 and contrib < 55:
        return "create_new_open_source_project"
    if contrib >= 55 and infl >= 65:
        return "build_extension_or_plugin"
    if infl >= 70 and contrib < 45:
        return "fork_and_specialize"
    if infl >= 30 or contrib >= 30:
        return "watch_only"
    return "ignore"


def build_suggested_contributions(dossier: RepoProjectDossier) -> list[dict[str, Any]]:
    evidence_ids = _evidence_ids(dossier)
    pain_points = _summary_list(dossier, "pain_points")
    base = pain_points[:3] or [dossier.summary or f"Review {dossier.full_name} contribution surface"]
    return [
        {
            "title": f"Address: {str(item)[:90]}",
            "type": "issue_or_pr",
            "rationale": str(item),
            "evidence_ids": evidence_ids,
        }
        for item in base
    ]


def build_action_brief(dossier: RepoProjectDossier, action: str, contribution: dict[str, Any], influence: dict[str, Any]) -> dict[str, Any]:
    evidence_ids = _evidence_ids(dossier)
    return {
        "recommended_action": action,
        "repo": dossier.full_name,
        "summary": dossier.summary,
        "contribution_opportunity_score": contribution["score"],
        "influence_opportunity_score": influence["score"],
        "score_explanation": {
            "contribution": contribution["explanation"],
            "influence": influence["explanation"],
        },
        "evidence_ids": evidence_ids,
    }


def build_title_options(dossier: RepoProjectDossier, action: str) -> list[str]:
    repo = dossier.full_name
    return [
        f"{repo}: {action.replace('_', ' ')}",
        f"Evidence-backed action plan for {repo}",
        f"{repo} opportunity brief",
    ]


def build_report_angles(dossier: RepoProjectDossier, contribution: dict[str, Any], influence: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_ids = _evidence_ids(dossier)
    return [
        {
            "angle": "contribution_opening",
            "claim": f"Contribution opportunity score {contribution['score']}",
            "evidence_ids": evidence_ids,
        },
        {
            "angle": "influence_timing",
            "claim": f"Influence opportunity score {influence['score']}",
            "evidence_ids": evidence_ids,
        },
    ]


def build_issue_pr_draft_scaffold(dossier: RepoProjectDossier, action: str) -> dict[str, Any]:
    evidence_ids = _evidence_ids(dossier)
    title = f"[GHPI] {dossier.summary or dossier.full_name}"
    body = "\n".join([
        f"Repo: {dossier.full_name}",
        f"Recommended action: {action}",
        f"Evidence IDs: {', '.join(evidence_ids)}",
        "",
        "Problem",
        dossier.summary or "Evidence-backed opportunity from GHPI.",
        "",
        "Proposed change",
        "Open a focused issue or PR scoped to the evidence above.",
        "",
        "Validation",
        "Confirm maintainers accept the problem statement before implementation.",
    ])
    return {
        "issue": {"title": title, "body": body, "labels": ["ghpi", action]},
        "pull_request": {"title": title, "body": body, "draft": True},
        "evidence_ids": evidence_ids,
    }


def build_development_requirement_brief(dossier: RepoProjectDossier, action: str) -> dict[str, Any]:
    if action not in {"contribute_to_existing_project", "create_new_open_source_project"}:
        return {}
    evidence_ids = _evidence_ids(dossier)
    return {
        "brief_type": "development_requirement",
        "mode": "contribute_existing" if action == "contribute_to_existing_project" else "create_new_project",
        "repo": dossier.full_name,
        "problem_statement": dossier.summary,
        "scope": [
            "derive implementation scope from evidence-bound GHPI action decision",
            "keep exports draft-only until human feedback accepts the action",
        ],
        "acceptance_criteria": [
            "all implementation tasks reference decision_id and evidence_ids",
            "issue/PR scaffold remains editable and side-effect free",
        ],
        "evidence_ids": evidence_ids,
    }


def build_action_recommendation(dossier: RepoProjectDossier) -> dict[str, Any]:
    contribution = compute_contribution_opportunity_score(dossier)
    influence = compute_influence_opportunity_score(dossier)
    action = choose_recommended_action(dossier, contribution, influence)
    return {
        "recommended_action": action,
        "contribution_opportunity_score": contribution["score"],
        "influence_opportunity_score": influence["score"],
        "score_details": {
            "contribution": contribution,
            "influence": influence,
        },
        "suggested_contributions": build_suggested_contributions(dossier),
        "action_brief": build_action_brief(dossier, action, contribution, influence),
        "title_options": build_title_options(dossier, action),
        "report_angles": build_report_angles(dossier, contribution, influence),
        "issue_pr_draft_scaffold": build_issue_pr_draft_scaffold(dossier, action),
        "development_requirement_brief": build_development_requirement_brief(dossier, action),
    }
