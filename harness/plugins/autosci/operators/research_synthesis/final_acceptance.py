"""final_acceptance deterministic gate implementation."""

from __future__ import annotations

import re
from typing import Any

from .base import (
    OperatorContext,
    build_node_result,
    evidence_ref,
    load_artifact,
    output_path,
    require_node,
    utc_now,
    write_artifact,
)


REJECTING_SEVERITIES = {"high", "critical"}
REJECTING_VERDICTS = {"revise", "revise_required", "reject"}
BASELINE_ARTIFACTS = ("independent_review", "report_draft", "evidence_synthesis", "source_validation")


def _load_review(context: OperatorContext) -> dict[str, Any]:
    payload, _ref = load_artifact(
        context,
        schemas=("research_synthesis.independent_review.v1",),
        artifact_ids=("independent_review",),
        filenames=("independent_review.json",),
        payload_keys=("independent_review",),
    )
    return payload


def _required_artifacts(context: OperatorContext) -> list[str]:
    raw = context.payload.get("required_artifacts")
    if isinstance(raw, list):
        requested = [str(item) for item in raw if str(item).strip()]
        return list(dict.fromkeys([*BASELINE_ARTIFACTS, *requested]))
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    deliverable = task_contract.get("deliverable") if isinstance(task_contract.get("deliverable"), dict) else {}
    requested = [str(item) for item in deliverable.get("artifact_expectations", []) if str(item).strip()]
    return list(dict.fromkeys([*BASELINE_ARTIFACTS, *requested]))


def _artifact_kind(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    aliases = (
        ("independent_review", ("independent_review", "review_verdict", "review_outcome")),
        ("report_draft", ("report_draft", "draft_report", "report")),
        ("evidence_synthesis", ("evidence_synthesis", "synthesis_notes", "synthesis")),
        ("source_validation", ("source_validation", "validated_sources", "source_list")),
    )
    for kind, values in aliases:
        if normalized in values:
            return kind
    return ""


def _artifact_present(requirement: str, review: dict[str, Any], context: OperatorContext) -> bool:
    required_kind = _artifact_kind(requirement)
    if not required_kind:
        return False
    available = {_artifact_kind(str(ref.get("artifact_id") or "")) for ref in context.input_artifact_refs()}
    available.update(_artifact_kind(str(ref.get("schema") or "")) for ref in context.input_artifact_refs())
    available.update(_artifact_kind(str(value)) for value in review.get("evidence_lineage", []) if str(value).strip())
    return required_kind in available


def _evaluate_success_criteria(task_contract: dict[str, Any], review: dict[str, Any]) -> list[dict[str, str]]:
    criteria = task_contract.get("success_criteria") if isinstance(task_contract.get("success_criteria"), list) else []
    chain = review.get("chain_validation") if isinstance(review.get("chain_validation"), dict) else {}
    verdict = str(review.get("verdict_suggestion") or "").lower()
    evaluations: list[dict[str, str]] = []
    for raw in criteria:
        criterion = str(raw).strip()
        normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", criterion.lower()).split())
        status = "unsupported"
        evidence = "No deterministic evaluator is defined for this criterion."
        if "conclusion" in normalized and any(token in normalized for token in ("evidence", "citation", "source")):
            passed = bool(chain.get("complete")) and int(chain.get("conclusion_count") or 0) > 0
            status = "passed" if passed else "failed"
            evidence = "Conclusion-to-claim-to-validated-source lineage is complete." if passed else "Conclusion evidence lineage is incomplete."
        elif "validated source" in normalized and any(token in normalized for token in ("trace", "ground", "cite", "linked")):
            passed = bool(chain.get("complete")) and int(chain.get("cited_source_count") or 0) > 0
            status = "passed" if passed else "failed"
            evidence = "Cited sources are present in source validation." if passed else "Citations do not resolve to validated sources."
        elif "report" in normalized and any(token in normalized for token in ("non empty", "body", "content")):
            passed = bool(chain.get("report_body_present"))
            status = "passed" if passed else "failed"
            evidence = "Report body or sections are present." if passed else "Report body and sections are empty."
        elif "independent review" in normalized and any(token in normalized for token in ("accept", "outcome", "verdict")):
            passed = verdict == "accept"
            status = "passed" if passed else "failed"
            evidence = f"Independent review verdict is `{verdict or 'missing'}`."
        elif all(token in normalized for token in ("seed", "validated source", "synthesis", "review")):
            passed = bool(chain.get("complete")) and verdict == "accept"
            status = "passed" if passed else "failed"
            evidence = "Required research evidence chain and accepting review are present." if passed else "Required research evidence chain or accepting review is missing."
        evaluations.append({"criterion": criterion, "status": status, "evidence": evidence})
    return evaluations


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "final_acceptance")
    review = _load_review(context)
    findings = [item for item in review.get("findings", []) if isinstance(item, dict)] if isinstance(review.get("findings"), list) else []
    high_risk_findings = [
        item for item in findings
        if str(item.get("severity") or "").lower() in REJECTING_SEVERITIES
    ]
    missing_artifacts = [item for item in _required_artifacts(context) if not _artifact_present(item, review, context)]
    verdict_suggestion = str(review.get("verdict_suggestion") or "").strip().lower()
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    criteria_evaluation = _evaluate_success_criteria(task_contract, review)
    criteria_passed = bool(criteria_evaluation) and all(item["status"] == "passed" for item in criteria_evaluation)
    chain = review.get("chain_validation") if isinstance(review.get("chain_validation"), dict) else {}
    accepted = bool(review) and bool(chain.get("complete")) and not high_risk_findings and not missing_artifacts and verdict_suggestion == "accept" and criteria_passed
    decision = "accepted" if accepted else "rejected"
    reasons = []
    if high_risk_findings:
        reasons.append(f"{len(high_risk_findings)} high-risk review finding(s) block acceptance")
    if missing_artifacts:
        reasons.append("required artifact(s) missing: " + ", ".join(missing_artifacts))
    if not review:
        reasons.append("independent review artifact is missing")
    if not chain.get("complete"):
        reasons.append("report, synthesis, validation, and citation lineage chain is incomplete")
    if not verdict_suggestion:
        reasons.append("independent review verdict is missing")
    elif verdict_suggestion in REJECTING_VERDICTS or verdict_suggestion != "accept":
        reasons.append(f"review verdict suggestion is {verdict_suggestion}")
    if not criteria_evaluation:
        reasons.append("task contract has no evaluable minimum success criteria")
    elif not criteria_passed:
        reasons.append("one or more task success criteria failed or are unsupported")
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
        "success_criteria_evaluation": criteria_evaluation,
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
