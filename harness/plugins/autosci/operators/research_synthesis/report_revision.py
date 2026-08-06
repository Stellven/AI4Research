"""report_revision node implementation."""

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
    redact_secrets,
    require_node,
    stable_json_sha256,
    utc_now,
    validate_scoped_path,
    write_artifact,
    _read_bytes,
    _write_bytes,
    display_path,
    sha256_bytes,
)
from .independent_review import _local_findings, _same_model_limitation
from .report_draft import _deliverable_requirements, _normalize_report


REPAIR_FINDING_SEVERITIES = {"medium", "high", "critical"}
REPAIR_VERDICTS = {"revise", "revise_required", "reject"}


def _load_artifact_by_schema(
    context: OperatorContext,
    *,
    schema: str,
    artifact_id: str,
    expected_node_id: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    return load_artifact(
        context,
        schemas=(schema,),
        artifact_ids=(artifact_id,),
        filenames=(f"{artifact_id}.json",),
        payload_keys=(),
        expected_node_ids=(expected_node_id,),
        require_hash=True,
    )


def _repair_required(review: dict[str, Any]) -> tuple[bool, list[dict[str, Any]], str]:
    findings = [item for item in review.get("findings", []) if isinstance(item, dict)] if isinstance(review.get("findings"), list) else []
    verdict = str(review.get("verdict_suggestion") or "").strip().lower()
    blocking = [
        item for item in findings
        if str(item.get("severity") or "").lower() in REPAIR_FINDING_SEVERITIES
    ]
    return verdict in REPAIR_VERDICTS or bool(blocking), blocking, verdict


def _normalize_review_response(
    response: dict[str, Any],
    *,
    report_payload: dict[str, Any],
    validation: dict[str, Any],
    task_contract: dict[str, Any],
) -> dict[str, Any]:
    local_findings, chain_validation = _local_findings(report_payload, validation, task_contract)
    service_findings: list[dict[str, Any]] = []
    raw_service_findings = response.get("findings", []) if isinstance(response.get("findings"), list) else []
    for index, item in enumerate(raw_service_findings):
        if not isinstance(item, dict):
            service_findings.append({
                "finding_id": f"revision_review.invalid_finding.{index + 1}",
                "severity": "high",
                "category": "review_contract",
                "message": "Reviewer returned a non-object finding.",
            })
            continue
        severity = str(item.get("severity") or "").lower()
        if severity not in {"low", "medium", "high", "critical"} or not str(item.get("category") or "").strip() or not str(item.get("message") or "").strip():
            service_findings.append({
                "finding_id": f"revision_review.invalid_finding.{index + 1}",
                "severity": "high",
                "category": "review_contract",
                "message": "Reviewer finding is missing a supported severity, category, or message.",
            })
            continue
        service_findings.append(item)
    findings = [*local_findings, *service_findings]
    requested_verdict = str(response.get("verdict_suggestion") or "").strip().lower()
    if requested_verdict not in {"accept", "revise", "revise_required", "reject"}:
        findings.append({
            "finding_id": "revision_review.invalid_verdict",
            "severity": "high",
            "category": "review_contract",
            "message": "Reviewer returned an empty or unsupported verdict suggestion.",
        })
        requested_verdict = "revise"
    high_risk = [
        item for item in findings
        if str(item.get("severity") or "").lower() in {"high", "critical"}
    ]
    verdict = "revise" if high_risk and requested_verdict == "accept" else requested_verdict
    return {
        "findings": findings,
        "verdict_suggestion": verdict,
        "reviewer_usage": provider_usage_from(response, usage_kind="llm"),
        "chain_validation": chain_validation,
        "limitations": [str(item) for item in response.get("limitations", []) if str(item).strip()],
        "evidence_lineage": [
            "report_revision",
            "report_draft",
            "evidence_synthesis" if chain_validation.get("evidence_synthesis_present") else "",
            "source_validation" if validation else "",
        ],
    }


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "report_revision")
    original_report, report_ref = _load_artifact_by_schema(
        context,
        schema="research_synthesis.report_draft.v1",
        artifact_id="report_draft",
        expected_node_id="report_draft",
    )
    review, review_ref = _load_artifact_by_schema(
        context,
        schema="research_synthesis.independent_review.v1",
        artifact_id="independent_review",
        expected_node_id="independent_review",
    )
    validation, validation_ref = _load_artifact_by_schema(
        context,
        schema="research_synthesis.source_validation.v1",
        artifact_id="source_validation",
        expected_node_id="source_validation",
    )
    synthesis, synthesis_ref = _load_artifact_by_schema(
        context,
        schema="research_synthesis.evidence_synthesis.v1",
        artifact_id="evidence_synthesis",
        expected_node_id="evidence_synthesis",
    )
    task_contract = context.payload.get("task_contract") if isinstance(context.payload.get("task_contract"), dict) else {}
    repair_required, blocking_findings, first_verdict = _repair_required(review)
    writer_usage: list[dict[str, Any]] = []
    reviewer_usage: list[dict[str, Any]] = []
    limitations: list[str] = []
    revised_report = original_report.get("report") if isinstance(original_report.get("report"), dict) else {}
    revision_review: dict[str, Any] = {}

    if repair_required:
        model_generate = context.services.get("model_generate")
        review_model = context.services.get("review_model_generate")
        if model_generate is None:
            return no_provider_result(context, "model_generate")
        if review_model is None:
            return no_provider_result(context, "review_model_generate")
        claims = [item for item in synthesis.get("claims", []) if isinstance(item, dict)]
        claim_ids = {str(item.get("claim_id")) for item in claims if item.get("claim_id")}
        if not claim_ids:
            raise ResearchOperatorError("No synthesis claims were available for report revision", error_type="missing_synthesis")
        response = model_generate(
            node_id="report_revision",
            task_contract=task_contract,
            deliverable_requirements=_deliverable_requirements(task_contract),
            evidence_synthesis=synthesis,
            source_validation=validation,
            original_report=original_report,
            independent_review=review,
            revision_attempt=1,
            max_revision_attempts=1,
        )
        if not isinstance(response, dict):
            raise ResearchOperatorError("model_generate service must return a JSON object", error_type="provider_contract")
        revised_report = _normalize_report(response, claim_ids)
        writer_usage = provider_usage_from(response, usage_kind="llm")
        limitations.extend(str(item) for item in response.get("limitations", []) if str(item).strip())
        revised_report_payload = {
            **original_report,
            "schema": "research_synthesis.report_draft.v1",
            "node_id": "report_draft",
            "report": revised_report,
            "claim_source_lineage": {
                str(item.get("claim_id")): [str(source_id) for source_id in item.get("evidence_ids", []) if str(source_id).strip()]
                for item in claims
                if item.get("claim_id")
            },
            "evidence_lineage": [
                "report_revision",
                "report_draft",
                "evidence_synthesis",
                "source_validation",
            ],
            "input_artifact_hashes": {
                "evidence_synthesis": str((synthesis_ref or {}).get("sha256") or ""),
                "base_report_draft": str((report_ref or {}).get("sha256") or ""),
                "base_independent_review": str((review_ref or {}).get("sha256") or ""),
            },
            "writer_usage": writer_usage,
            "limitations": limitations,
        }
        review_response = review_model(
            node_id="report_revision_review",
            task_contract=task_contract,
            report_draft=revised_report_payload,
            source_validation=validation,
            prior_review=review,
        )
        if not isinstance(review_response, dict):
            raise ResearchOperatorError("review_model_generate service must return a JSON object", error_type="provider_contract")
        revision_review = _normalize_review_response(
            review_response,
            report_payload=revised_report_payload,
            validation=validation,
            task_contract=task_contract,
        )
        reviewer_usage = revision_review["reviewer_usage"]
        revision_review["writer_usage"] = writer_usage
        revision_review["reviewed_artifact_hashes"] = {
            "revised_report": stable_json_sha256(revised_report),
            "source_validation": str((validation_ref or {}).get("sha256") or ""),
        }
        limitations.extend(revision_review.get("limitations") or [])
        limitations.extend(_same_model_limitation(writer_usage, reviewer_usage))

    claim_source_lineage = (
        revised_report_payload.get("claim_source_lineage")
        if repair_required and "revised_report_payload" in locals()
        else original_report.get("claim_source_lineage")
    )
    input_artifact_hashes = (
        revised_report_payload.get("input_artifact_hashes")
        if repair_required and "revised_report_payload" in locals()
        else original_report.get("input_artifact_hashes")
    )
    artifact_payload = {
        "schema": "research_synthesis.report_revision.v1",
        "node_id": "report_revision",
        "created_at": utc_now(),
        "revision_attempt": 1,
        "max_revision_attempts": 1,
        "revision_applied": repair_required,
        "basis_review_verdict": first_verdict,
        "basis_blocking_findings": blocking_findings,
        "base_artifact_hashes": {
            "report_draft": str((report_ref or {}).get("sha256") or ""),
            "independent_review": str((review_ref or {}).get("sha256") or ""),
            "source_validation": str((validation_ref or {}).get("sha256") or ""),
            "evidence_synthesis": str((synthesis_ref or {}).get("sha256") or ""),
        },
        "revised_report": revised_report,
        "revised_report_sha256": stable_json_sha256(revised_report),
        "claim_source_lineage": claim_source_lineage if isinstance(claim_source_lineage, dict) else {},
        "input_artifact_hashes": input_artifact_hashes if isinstance(input_artifact_hashes, dict) else {},
        "revision_review": revision_review,
        "evidence_lineage": [
            "report_revision",
            "report_draft",
            "independent_review",
            "evidence_synthesis",
            "source_validation",
        ],
        "writer_usage": writer_usage,
        "reviewer_usage": reviewer_usage,
        "limitations": list(dict.fromkeys(str(item) for item in limitations if str(item).strip())),
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "report_revision.json"),
        artifact_payload,
        artifact_id="report_revision",
        schema="research_synthesis.report_revision.v1",
    )
    report_path = validate_scoped_path(
        output_path(context, "report.md"),
        context.write_scope,
        workspace_root=context.workspace_root,
    )
    safe_body = str(redact_secrets(revised_report.get("body", ""), context.secret_refs, context.secret_values))
    _write_bytes(report_path, (safe_body.rstrip() + "\n").encode("utf-8"))
    report_digest = sha256_bytes(_read_bytes(report_path))
    report_artifact = {
        "artifact_id": "report_revision_markdown",
        "path": display_path(report_path, context.workspace_root),
        "schema": "text/markdown",
        "sha256": report_digest,
    }
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact, report_artifact],
        evidence=[
            evidence_ref(
                "report_revision.attempt",
                "bounded_report_revision",
                f"Revision attempt 1 applied={repair_required}; basis verdict={first_verdict or 'missing'}.",
                artifact["artifact_id"],
            ),
            evidence_ref(
                "report_revision.usable_markdown",
                "usable_report",
                "A non-empty Markdown report was written for the active revised-or-forwarded report.",
                report_artifact["artifact_id"],
            ),
        ],
        hashes=[hash_record, {"hash_id": "report_revision_markdown", "algorithm": "sha256", "value": report_digest}],
        model_provider_usage=[*writer_usage, *reviewer_usage],
        limitations=artifact_payload["limitations"],
    )
