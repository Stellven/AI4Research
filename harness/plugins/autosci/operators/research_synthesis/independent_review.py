"""independent_review node implementation."""

from __future__ import annotations

from typing import Any

from .base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    evidence_ref,
    no_provider_result,
    output_path,
    provider_usage_from,
    require_node,
    utc_now,
    write_artifact,
)


def _load_artifact_by_schema(context: OperatorContext, schema: str, token: str) -> dict[str, Any]:
    payload_key = token
    if isinstance(context.payload.get(payload_key), dict):
        return context.payload[payload_key]
    for artifact_ref in context.input_artifact_refs():
        if artifact_ref.get("schema") == schema or token in str(artifact_ref.get("artifact_id", "")):
            return context.load_json_artifact(artifact_ref)
    return {}


def _local_findings(report_draft: dict[str, Any], validation: dict[str, Any], task_contract: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    report = report_draft.get("report") if isinstance(report_draft.get("report"), dict) else {}
    conclusions = [item for item in report.get("conclusions", []) if isinstance(item, dict)]
    accepted_ids = {str(item.get("source_id")) for item in validation.get("accepted", []) if item.get("source_id")}
    claim_ids = {
        str(evidence_id)
        for conclusion in conclusions
        for evidence_id in conclusion.get("evidence_ids", [])
        if str(evidence_id).strip()
    }
    if not conclusions:
        findings.append({
            "finding_id": "review.no_conclusions",
            "severity": "high",
            "category": "unsupported_claim",
            "message": "Report draft has no traceable conclusions.",
        })
    for index, conclusion in enumerate(conclusions):
        if not conclusion.get("evidence_ids"):
            findings.append({
                "finding_id": f"review.unsupported_conclusion.{index + 1}",
                "severity": "high",
                "category": "unsupported_claim",
                "message": "A report conclusion lacks evidence_ids.",
            })
    if validation and not accepted_ids:
        findings.append({
            "finding_id": "review.no_validated_sources",
            "severity": "high",
            "category": "citation_coverage",
            "message": "No accepted source validation entries are available.",
        })
    success_criteria = task_contract.get("success_criteria") if isinstance(task_contract.get("success_criteria"), list) else []
    if success_criteria and not str(report.get("body") or "").strip() and not report.get("sections"):
        findings.append({
            "finding_id": "review.empty_report_body",
            "severity": "medium",
            "category": "task_success",
            "message": "Report has traceable conclusions but no body or sections for the requested deliverable.",
        })
    if not claim_ids:
        findings.append({
            "finding_id": "review.citation_coverage_empty",
            "severity": "high",
            "category": "citation_coverage",
            "message": "No citation/evidence coverage was detected in report conclusions.",
        })
    return findings


def _same_model_limitation(writer_usage: list[dict[str, Any]], reviewer_usage: list[dict[str, Any]]) -> list[str]:
    if not writer_usage or not reviewer_usage:
        return []
    writer = writer_usage[0]
    reviewer = reviewer_usage[0]
    if str(writer.get("provider")) == str(reviewer.get("provider")) and str(writer.get("model")) == str(reviewer.get("model")):
        return ["Reviewer and writer used the same provider/model identity; independence is limited."]
    return []


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "independent_review")
    review_model = context.services.get("review_model_generate")
    if review_model is None:
        return no_provider_result(context, "review_model_generate")
    report_draft = _load_artifact_by_schema(context, "research_synthesis.report_draft.v1", "report_draft")
    validation = _load_artifact_by_schema(context, "research_synthesis.source_validation.v1", "source_validation")
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    response = review_model(
        node_id="independent_review",
        task_contract=task_contract,
        report_draft=report_draft,
        source_validation=validation,
    )
    if not isinstance(response, dict):
        raise ResearchOperatorError("review_model_generate service must return a JSON object", error_type="provider_contract")
    local_findings = _local_findings(report_draft, validation, task_contract)
    service_findings = [item for item in response.get("findings", []) if isinstance(item, dict)] if isinstance(response.get("findings"), list) else []
    findings = [*local_findings, *service_findings]
    reviewer_usage = provider_usage_from(response, usage_kind="llm")
    writer_usage = [item for item in report_draft.get("writer_usage", []) if isinstance(item, dict)] if isinstance(report_draft.get("writer_usage"), list) else []
    limitations = [
        *[str(item) for item in response.get("limitations", []) if str(item).strip()],
        *_same_model_limitation(writer_usage, reviewer_usage),
    ]
    verdict = str(response.get("verdict_suggestion") or ("revise" if any(item.get("severity") == "high" for item in findings) else "accept"))
    artifact_payload = {
        "schema": "research_synthesis.independent_review.v1",
        "node_id": "independent_review",
        "created_at": utc_now(),
        "findings": findings,
        "verdict_suggestion": verdict,
        "reviewer_usage": reviewer_usage,
        "writer_usage": writer_usage,
        "limitations": limitations,
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "independent_review.json"),
        artifact_payload,
        artifact_id="independent_review",
        schema="research_synthesis.independent_review.v1",
    )
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact],
        evidence=[evidence_ref("independent_review.findings", "independent_review", f"{len(findings)} review finding(s); suggestion={verdict}.", artifact["artifact_id"])],
        hashes=[hash_record],
        model_provider_usage=reviewer_usage,
        limitations=limitations,
    )
