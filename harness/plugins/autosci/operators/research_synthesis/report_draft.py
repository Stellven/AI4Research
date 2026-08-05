"""report_draft node implementation."""

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


def _load_synthesis(context: OperatorContext) -> dict[str, Any]:
    if isinstance(context.payload.get("evidence_synthesis"), dict):
        return context.payload["evidence_synthesis"]
    for artifact_ref in context.input_artifact_refs():
        if artifact_ref.get("schema") == "research_synthesis.evidence_synthesis.v1" or "synthesis" in str(artifact_ref.get("artifact_id", "")):
            return context.load_json_artifact(artifact_ref)
    return {}


def _task_contract(context: OperatorContext) -> dict[str, Any]:
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    return task_contract


def _deliverable_requirements(task_contract: dict[str, Any]) -> dict[str, Any]:
    deliverable = task_contract.get("deliverable") if isinstance(task_contract.get("deliverable"), dict) else {}
    return {
        "kind": str(deliverable.get("kind") or ""),
        "description": str(deliverable.get("description") or ""),
        "language": str(deliverable.get("language") or ""),
        "format": str(deliverable.get("format") or ""),
        "length": deliverable.get("length") or deliverable.get("length_words") or deliverable.get("target_length"),
        "artifact_expectations": [str(item) for item in deliverable.get("artifact_expectations", []) if str(item).strip()],
    }


def _normalize_report(response: dict[str, Any], claim_ids: set[str]) -> dict[str, Any]:
    report = response.get("report") if isinstance(response.get("report"), dict) else response
    conclusions = report.get("conclusions") if isinstance(report.get("conclusions"), list) else []
    normalized_conclusions: list[dict[str, Any]] = []
    for index, item in enumerate(conclusions):
        if not isinstance(item, dict):
            continue
        evidence_ids = [str(value) for value in item.get("evidence_ids", []) if str(value).strip()]
        if not evidence_ids:
            raise ResearchOperatorError("Every major report conclusion must include evidence_ids", error_type="unsupported_report_claim")
        invalid = sorted(set(evidence_ids) - claim_ids)
        if invalid:
            raise ResearchOperatorError(f"Report conclusion references unknown synthesis evidence: {', '.join(invalid)}", error_type="unsupported_report_claim")
        normalized_conclusions.append({
            "conclusion_id": str(item.get("conclusion_id") or f"conclusion-{index + 1:03d}"),
            "text": str(item.get("text") or ""),
            "evidence_ids": evidence_ids,
        })
    if not normalized_conclusions:
        raise ResearchOperatorError("model_generate returned no traceable report conclusions", error_type="provider_contract")
    return {
        "title": str(report.get("title") or "Research synthesis draft"),
        "body": str(report.get("body") or report.get("markdown") or ""),
        "sections": [item for item in report.get("sections", []) if isinstance(item, dict)] if isinstance(report.get("sections"), list) else [],
        "conclusions": normalized_conclusions,
    }


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "report_draft")
    model_generate = context.services.get("model_generate")
    if model_generate is None:
        return no_provider_result(context, "model_generate")
    synthesis = _load_synthesis(context)
    claims = [item for item in synthesis.get("claims", []) if isinstance(item, dict)]
    if not claims:
        return build_node_result(
            context,
            status="blocked",
            errors=[{"error_id": "report_draft.no_claims", "error_type": "missing_synthesis", "message": "No synthesized claims were available for report drafting."}],
            limitations=["Report draft only consumes evidence_synthesis output."],
        )
    task_contract = _task_contract(context)
    deliverable_requirements = _deliverable_requirements(task_contract)
    response = model_generate(
        node_id="report_draft",
        task_contract=task_contract,
        deliverable_requirements=deliverable_requirements,
        evidence_synthesis=synthesis,
    )
    if not isinstance(response, dict):
        raise ResearchOperatorError("model_generate service must return a JSON object", error_type="provider_contract")
    claim_ids = {str(item.get("claim_id")) for item in claims if item.get("claim_id")}
    report = _normalize_report(response, claim_ids)
    usage = provider_usage_from(response, usage_kind="llm")
    limitations = [str(item) for item in response.get("limitations", []) if str(item).strip()]
    artifact_payload = {
        "schema": "research_synthesis.report_draft.v1",
        "node_id": "report_draft",
        "created_at": utc_now(),
        "deliverable_requirements": deliverable_requirements,
        "report": report,
        "writer_usage": usage,
        "limitations": limitations,
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "report_draft.json"),
        artifact_payload,
        artifact_id="report_draft",
        schema="research_synthesis.report_draft.v1",
    )
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact],
        evidence=[evidence_ref("report_draft.traceable", "traceable_report_draft", "Report draft conclusions are linked to synthesis evidence.", artifact["artifact_id"])],
        hashes=[hash_record],
        model_provider_usage=usage,
        limitations=limitations,
    )
