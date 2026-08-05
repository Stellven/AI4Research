"""final_acceptance deterministic gate implementation."""

from __future__ import annotations

from typing import Any

from .base import (
    OperatorContext,
    build_node_result,
    evidence_ref,
    output_path,
    require_node,
    utc_now,
    write_artifact,
)


REJECTING_SEVERITIES = {"high", "critical"}
REJECTING_CATEGORIES = {"unsupported_claim", "citation_coverage", "task_success"}


def _load_review(context: OperatorContext) -> dict[str, Any]:
    if isinstance(context.payload.get("independent_review"), dict):
        return context.payload["independent_review"]
    for artifact_ref in context.input_artifact_refs():
        if artifact_ref.get("schema") == "research_synthesis.independent_review.v1" or "review" in str(artifact_ref.get("artifact_id", "")):
            return context.load_json_artifact(artifact_ref)
    return {}


def _required_artifacts(context: OperatorContext) -> list[str]:
    raw = context.payload.get("required_artifacts")
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    deliverable = task_contract.get("deliverable") if isinstance(task_contract.get("deliverable"), dict) else {}
    return [str(item) for item in deliverable.get("artifact_expectations", []) if str(item).strip()]


def _artifact_present(requirement: str, review: dict[str, Any], context: OperatorContext) -> bool:
    available = {str(ref.get("artifact_id") or "") for ref in context.input_artifact_refs()}
    available.update(str(ref.get("schema") or "") for ref in context.input_artifact_refs())
    available.update(str(value) for value in review.get("evidence_lineage", []) if str(value).strip())
    if not requirement:
        return True
    return any(requirement in value or value in requirement for value in available)


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "final_acceptance")
    review = _load_review(context)
    findings = [item for item in review.get("findings", []) if isinstance(item, dict)] if isinstance(review.get("findings"), list) else []
    high_risk_findings = [
        item for item in findings
        if str(item.get("severity") or "").lower() in REJECTING_SEVERITIES
        and str(item.get("category") or "").lower() in REJECTING_CATEGORIES
    ]
    missing_artifacts = [item for item in _required_artifacts(context) if not _artifact_present(item, review, context)]
    verdict_suggestion = str(review.get("verdict_suggestion") or "")
    accepted = not high_risk_findings and not missing_artifacts and verdict_suggestion not in {"reject", "revise_required"}
    decision = "accepted" if accepted else "rejected"
    reasons = []
    if high_risk_findings:
        reasons.append(f"{len(high_risk_findings)} high-risk review finding(s) block acceptance")
    if missing_artifacts:
        reasons.append("required artifact(s) missing: " + ", ".join(missing_artifacts))
    if verdict_suggestion in {"reject", "revise_required"}:
        reasons.append(f"review verdict suggestion is {verdict_suggestion}")
    if not reasons:
        reasons.append("Task success criteria, review findings, and required artifacts passed the deterministic gate.")
    artifact_payload = {
        "schema": "research_synthesis.final_acceptance.v1",
        "node_id": "final_acceptance",
        "created_at": utc_now(),
        "decision": decision,
        "accepted": accepted,
        "reasons": reasons,
        "review_verdict_suggestion": verdict_suggestion,
        "review_finding_count": len(findings),
        "missing_required_artifacts": missing_artifacts,
        "does_not_modify_graph_or_run_state": True,
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "final_acceptance.json"),
        artifact_payload,
        artifact_id="final_acceptance",
        schema="research_synthesis.final_acceptance.v1",
    )
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact],
        evidence=[evidence_ref("final_acceptance.decision", "final_acceptance", f"Deterministic acceptance decision: {decision}.", artifact["artifact_id"])],
        hashes=[hash_record],
        limitations=["Final acceptance emits evidence only; Solar remains responsible for run status and graph state."],
    )
