#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import (
    check_artifact_paths,
    finish,
    has_any_evidence_ids,
    outputs,
    require_non_empty_list,
    run_cli,
    validate_schema,
)

SCHEMA = "workflow_evolution.v1"
COLLECTION_KEYS = (
    "failed_nodes",
    "gate_rejection_reasons",
    "ambiguous_manuals_or_prompts",
    "insufficient_schemas",
    "poor_operator_bindings",
    "human_intervention_points",
    "runtime_errors",
)
PROPOSAL_CATEGORIES = {
    "capsule",
    "manual",
    "routing",
    "gate",
    "schema",
    "workflow_template",
    "adapter",
    "other",
}


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    evolution = outputs(payload).get("evolution")
    if not isinstance(evolution, dict):
        reasons.append("outputs.evolution must be an object")
        return finish(payload, reasons, warnings, path=path)
    applied_refine = _approved_refine_application(evolution, payload)
    if not has_any_evidence_ids(evolution.get("evidence_ids")):
        reasons.append("outputs.evolution.evidence_ids must contain at least one id")
    if evolution.get("approval_state") in {"approved", "applied"} and not (
        evolution.get("approval_ref") or (isinstance(evolution.get("review"), dict) and evolution["review"].get("approval_ref"))
    ):
        reasons.append("approved or applied workflow evolution requires approval_ref")
    if evolution.get("approval_state") == "applied" and not applied_refine:
        reasons.append("applied workflow evolution requires verified refine_apply evidence")
    _check_collected_evidence(evolution, reasons, applied_refine=applied_refine)
    _check_proposals(evolution, reasons, applied_refine=applied_refine)
    _check_review_controls(evolution, reasons, applied_refine=applied_refine)
    _check_recommended_changes_artifact(payload, reasons)
    _check_patch_candidates_artifact(payload, reasons)
    check_artifact_paths(payload, path, reasons)
    return finish(payload, reasons, warnings, path=path)


def _approved_refine_application(evolution: dict[str, Any], payload: dict[str, Any]) -> bool:
    review = evolution.get("review")
    if not isinstance(review, dict):
        return False
    refine_apply = review.get("refine_apply")
    if not isinstance(refine_apply, dict):
        return False
    artifacts = payload.get("artifacts")
    has_apply_artifact = isinstance(artifacts, list) and any(
        isinstance(artifact, dict) and artifact.get("type") == "refine_apply_writeback_json"
        for artifact in artifacts
    )
    return (
        evolution.get("approval_state") == "applied"
        and review.get("approval_contract_verified") is True
        and bool(str(review.get("approval_ref") or "").strip())
        and review.get("protected_core_edits_applied") is True
        and review.get("human_accept_reject_required") is False
        and str(review.get("application_state") or "") == "applied"
        and refine_apply.get("applied") is True
        and str(refine_apply.get("status") or "") == "completed"
        and has_apply_artifact
    )


def _check_collected_evidence(evolution: dict[str, Any], reasons: list[str], *, applied_refine: bool = False) -> None:
    collected = evolution.get("collected")
    if not isinstance(collected, dict):
        reasons.append("outputs.evolution.collected must be an object")
        return
    for key in COLLECTION_KEYS:
        if not isinstance(collected.get(key), list):
            reasons.append(f"outputs.evolution.collected.{key} must be a list")
    failed_nodes = collected.get("failed_nodes") if applied_refine else require_non_empty_list(
        collected.get("failed_nodes"),
        "outputs.evolution.collected.failed_nodes",
        reasons,
    )
    failed_nodes = failed_nodes if isinstance(failed_nodes, list) else []
    for index, node in enumerate(failed_nodes):
        if not isinstance(node, dict):
            reasons.append(f"failed_nodes[{index}] must be an object")
            continue
        if not str(node.get("node_id") or "").strip():
            reasons.append(f"failed_nodes[{index}].node_id must be present")
    gate_rejections = collected.get("gate_rejection_reasons")
    runtime_errors = collected.get("runtime_errors")
    if not gate_rejections and not runtime_errors:
        reasons.append("workflow evolution requires gate rejection reasons or runtime errors")


def _check_proposals(evolution: dict[str, Any], reasons: list[str], *, applied_refine: bool = False) -> None:
    proposals = require_non_empty_list(
        evolution.get("proposed_changes"),
        "outputs.evolution.proposed_changes",
        reasons,
    )
    categories: set[str] = set()
    for index, proposal in enumerate(proposals):
        if not isinstance(proposal, dict):
            reasons.append(f"proposed_changes[{index}] must be an object")
            continue
        category = str(proposal.get("category") or "")
        categories.add(category)
        if category not in PROPOSAL_CATEGORIES:
            reasons.append(f"proposed_changes[{index}].category is not supported: {category}")
        for field in ("change_id", "target", "description"):
            if not str(proposal.get(field) or "").strip():
                reasons.append(f"proposed_changes[{index}].{field} must be present")
        if proposal.get("review_required") is not True:
            reasons.append(f"proposed_changes[{index}].review_required must be true")
        allowed_states = {"proposed_only", "not_applied", "applied"} if applied_refine else {"proposed_only", "not_applied"}
        if str(proposal.get("application_state") or "") not in allowed_states:
            reasons.append(
                f"proposed_changes[{index}].application_state must be "
                + ("proposed_only, not_applied, or applied" if applied_refine else "proposed_only or not_applied")
            )
        if not has_any_evidence_ids(proposal.get("evidence_ids")):
            reasons.append(f"proposed_changes[{index}].evidence_ids must contain at least one id")
    if "manual" not in categories:
        reasons.append("proposed_changes must separate at least one manual change")
    if not ({"schema", "gate"} & categories):
        reasons.append("proposed_changes must separate at least one schema or gate change")


def _check_review_controls(evolution: dict[str, Any], reasons: list[str], *, applied_refine: bool = False) -> None:
    review = evolution.get("review")
    if not isinstance(review, dict):
        reasons.append("outputs.evolution.review must be an object")
        return
    if applied_refine:
        return
    if review.get("human_accept_reject_required") is not True:
        reasons.append("outputs.evolution.review.human_accept_reject_required must be true")
    if review.get("protected_core_edits_applied") is not False:
        reasons.append("outputs.evolution.review.protected_core_edits_applied must be false")
    if str(review.get("application_state") or "") not in {"proposed_only", "not_applied"}:
        reasons.append("outputs.evolution.review.application_state must be proposed_only or not_applied")


def _check_recommended_changes_artifact(payload: dict[str, Any], reasons: list[str]) -> None:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        reasons.append("artifacts must contain recommended_changes_markdown")
        return
    if not any(
        isinstance(artifact, dict)
        and artifact.get("type") == "recommended_changes_markdown"
        and str(artifact.get("path") or "").endswith(".md")
        for artifact in artifacts
    ):
        reasons.append("artifacts must include recommended_changes_markdown .md")


def _check_patch_candidates_artifact(payload: dict[str, Any], reasons: list[str]) -> None:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        reasons.append("artifacts must contain patch_candidates_directory")
        return
    if not any(
        isinstance(artifact, dict)
        and artifact.get("type") == "patch_candidates_directory"
        and Path(str(artifact.get("path") or "")).name == "patch_candidates"
        for artifact in artifacts
    ):
        reasons.append("artifacts must include patch_candidates_directory named patch_candidates")


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
