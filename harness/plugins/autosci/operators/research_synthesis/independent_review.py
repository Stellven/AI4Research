"""independent_review node implementation."""

from __future__ import annotations

from typing import Any

from .base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    evidence_ref,
    load_artifact,
    no_provider_result,
    output_path,
    provider_usage_from,
    require_node,
    utc_now,
    write_artifact,
)


def _load_artifact_by_schema(context: OperatorContext, schema: str, token: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    return load_artifact(
        context,
        schemas=(schema,),
        artifact_ids=(token,),
        filenames=(f"{token}.json",),
        payload_keys=(token,),
    )


def _local_findings(
    report_draft: dict[str, Any],
    validation: dict[str, Any],
    task_contract: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    report = report_draft.get("report") if isinstance(report_draft.get("report"), dict) else {}
    conclusions = [item for item in report.get("conclusions", []) if isinstance(item, dict)]
    accepted_ids = {str(item.get("source_id")) for item in validation.get("accepted", []) if item.get("source_id")}
    claim_source_lineage = report_draft.get("claim_source_lineage") if isinstance(report_draft.get("claim_source_lineage"), dict) else {}
    cited_claim_ids: set[str] = set()
    cited_source_ids: set[str] = set()
    if not conclusions:
        findings.append({
            "finding_id": "review.no_conclusions",
            "severity": "high",
            "category": "unsupported_claim",
            "message": "Report draft has no traceable conclusions.",
        })
    for index, conclusion in enumerate(conclusions):
        conclusion_claim_ids = [str(value) for value in conclusion.get("evidence_ids", []) if str(value).strip()]
        cited_claim_ids.update(conclusion_claim_ids)
        if not conclusion_claim_ids:
            findings.append({
                "finding_id": f"review.unsupported_conclusion.{index + 1}",
                "severity": "high",
                "category": "unsupported_claim",
                "message": "A report conclusion lacks evidence_ids.",
            })
        for claim_id in conclusion_claim_ids:
            source_ids = claim_source_lineage.get(claim_id)
            if not isinstance(source_ids, list) or not source_ids:
                findings.append({
                    "finding_id": f"review.unknown_claim.{index + 1}.{claim_id}",
                    "severity": "high",
                    "category": "unsupported_claim",
                    "message": f"Conclusion references claim `{claim_id}` without claim-to-source lineage.",
                })
                continue
            normalized_sources = {str(value) for value in source_ids if str(value).strip()}
            cited_source_ids.update(normalized_sources)
            unknown_sources = sorted(normalized_sources - accepted_ids)
            if unknown_sources:
                findings.append({
                    "finding_id": f"review.unknown_sources.{index + 1}.{claim_id}",
                    "severity": "critical",
                    "category": "citation_truthfulness",
                    "message": "Claim cites source ids outside the validated set: " + ", ".join(unknown_sources),
                })
    if validation and not accepted_ids:
        findings.append({
            "finding_id": "review.no_validated_sources",
            "severity": "high",
            "category": "citation_coverage",
            "message": "No accepted source validation entries are available.",
        })
    elif not validation:
        findings.append({
            "finding_id": "review.missing_source_validation",
            "severity": "high",
            "category": "citation_coverage",
            "message": "Source validation artifact is missing.",
        })
    success_criteria = task_contract.get("success_criteria") if isinstance(task_contract.get("success_criteria"), list) else []
    if success_criteria and not str(report.get("body") or "").strip() and not report.get("sections"):
        findings.append({
            "finding_id": "review.empty_report_body",
            "severity": "medium",
            "category": "task_success",
            "message": "Report has traceable conclusions but no body or sections for the requested deliverable.",
        })
    if not cited_claim_ids:
        findings.append({
            "finding_id": "review.citation_coverage_empty",
            "severity": "high",
            "category": "citation_coverage",
            "message": "No citation/evidence coverage was detected in report conclusions.",
        })
    lineage = [str(item) for item in report_draft.get("evidence_lineage", []) if str(item).strip()]
    synthesis_present = "evidence_synthesis" in lineage or "research_synthesis.evidence_synthesis.v1" in lineage
    validation_present = bool(validation) and bool(accepted_ids)
    chain_validation = {
        "report_draft_present": bool(report_draft) and bool(conclusions),
        "evidence_synthesis_present": synthesis_present,
        "source_validation_present": validation_present,
        "conclusion_count": len(conclusions),
        "cited_claim_count": len(cited_claim_ids),
        "cited_source_count": len(cited_source_ids),
        "report_body_present": bool(str(report.get("body") or "").strip() or report.get("sections")),
    }
    chain_validation["complete"] = all(
        chain_validation[key]
        for key in ("report_draft_present", "evidence_synthesis_present", "source_validation_present")
    ) and not any(str(item.get("severity") or "").lower() in {"high", "critical"} for item in findings)
    if not synthesis_present:
        findings.append({
            "finding_id": "review.missing_synthesis_lineage",
            "severity": "high",
            "category": "citation_coverage",
            "message": "Report draft does not preserve evidence_synthesis lineage.",
        })
        chain_validation["complete"] = False
    return findings, chain_validation


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
    report_draft, report_ref = _load_artifact_by_schema(context, "research_synthesis.report_draft.v1", "report_draft")
    validation, validation_ref = _load_artifact_by_schema(context, "research_synthesis.source_validation.v1", "source_validation")
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    response = review_model(
        node_id="independent_review",
        task_contract=task_contract,
        report_draft=report_draft,
        source_validation=validation,
    )
    if not isinstance(response, dict):
        raise ResearchOperatorError("review_model_generate service must return a JSON object", error_type="provider_contract")
    local_findings, chain_validation = _local_findings(report_draft, validation, task_contract)
    service_findings: list[dict[str, Any]] = []
    raw_service_findings = response.get("findings", []) if isinstance(response.get("findings"), list) else []
    for index, item in enumerate(raw_service_findings):
        if not isinstance(item, dict):
            service_findings.append({
                "finding_id": f"review.invalid_finding.{index + 1}",
                "severity": "high",
                "category": "review_contract",
                "message": "Reviewer returned a non-object finding.",
            })
            continue
        severity = str(item.get("severity") or "").lower()
        if severity not in {"low", "medium", "high", "critical"} or not str(item.get("category") or "").strip() or not str(item.get("message") or "").strip():
            service_findings.append({
                "finding_id": f"review.invalid_finding.{index + 1}",
                "severity": "high",
                "category": "review_contract",
                "message": "Reviewer finding is missing a supported severity, category, or message.",
            })
            continue
        service_findings.append(item)
    findings = [*local_findings, *service_findings]
    reviewer_usage = provider_usage_from(response, usage_kind="llm")
    writer_usage = [item for item in report_draft.get("writer_usage", []) if isinstance(item, dict)] if isinstance(report_draft.get("writer_usage"), list) else []
    limitations = [
        *[str(item) for item in response.get("limitations", []) if str(item).strip()],
        *_same_model_limitation(writer_usage, reviewer_usage),
    ]
    requested_verdict = str(response.get("verdict_suggestion") or "").strip().lower()
    if requested_verdict not in {"accept", "revise", "revise_required", "reject"}:
        findings.append({
            "finding_id": "review.invalid_verdict",
            "severity": "high",
            "category": "review_contract",
            "message": "Reviewer returned an empty or unsupported verdict suggestion.",
        })
        requested_verdict = "revise"
    blocking_findings = [
        item for item in findings
        if str(item.get("severity") or "").lower() in {"high", "critical"}
    ]
    verdict = "revise" if blocking_findings and requested_verdict == "accept" else requested_verdict
    evidence_lineage = [
        "independent_review",
        "report_draft" if report_draft else "",
        "evidence_synthesis" if chain_validation.get("evidence_synthesis_present") else "",
        "source_validation" if validation else "",
    ]
    artifact_payload = {
        "schema": "research_synthesis.independent_review.v1",
        "node_id": "independent_review",
        "created_at": utc_now(),
        "findings": findings,
        "verdict_suggestion": verdict,
        "reviewer_usage": reviewer_usage,
        "writer_usage": writer_usage,
        "chain_validation": chain_validation,
        "evidence_lineage": [item for item in evidence_lineage if item],
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
