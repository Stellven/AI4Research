"""Convert workflow postmortem data to `workflow_evolution.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


COLLECTION_KEYS = (
    "failed_nodes",
    "gate_rejection_reasons",
    "ambiguous_manuals_or_prompts",
    "insufficient_schemas",
    "poor_operator_bindings",
    "human_intervention_points",
    "runtime_errors",
)


def _list_value(raw: dict[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    return value if isinstance(value, list) else []


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    collected_raw = raw.get("collected") if isinstance(raw.get("collected"), dict) else raw
    collected = {key: _list_value(collected_raw, key) for key in COLLECTION_KEYS}
    evidence_ids = list(raw.get("evidence_ids") or [])
    evolution = {
        "proposal_id": str(raw.get("proposal_id") or "proposal-workflow-evolution-001"),
        "scope": str(raw.get("scope") or "scientific research workflow"),
        "change_type": str(raw.get("change_type") or "workflow_template"),
        "rationale": str(raw.get("rationale") or "Workflow outcome evidence identified a bounded improvement opportunity."),
        "expected_effect": str(raw.get("expected_effect") or "Improve future workflow auditability without applying changes automatically."),
        "approval_state": str(raw.get("approval_state") or "proposed"),
        "evidence_ids": evidence_ids,
        "collected": collected,
        "proposed_changes": list(raw.get("proposed_changes") or []),
        "review": dict(raw.get("review") or {}),
    }
    if raw.get("recommended_changes_path"):
        evolution["recommended_changes_path"] = str(raw["recommended_changes_path"])
    if raw.get("patch_candidates_path"):
        evolution["patch_candidates_path"] = str(raw["patch_candidates_path"])
    if raw.get("approval_ref"):
        evolution["approval_ref"] = str(raw["approval_ref"])
    for key in ("pipeline", "stage_plan", "current_stage", "resume_from"):
        if raw.get(key) is not None:
            evolution[key] = raw[key]
    return evidence_base(
        "workflow_evolution.v1",
        envelope,
        {"evolution": evolution},
        artifacts=list(raw.get("artifacts") or []),
        status=str(raw.get("status") or "completed"),
        limitations=list(raw.get("limitations") or ["Workflow evolution is proposed only; no protected runtime changes were applied."]),
        operator_id="ScientificWorkflowEvolver",
    )
