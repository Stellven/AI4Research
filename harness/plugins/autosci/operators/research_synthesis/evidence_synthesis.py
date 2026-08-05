"""evidence_synthesis node implementation."""

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


def _load_validation(context: OperatorContext) -> dict[str, Any]:
    if isinstance(context.payload.get("source_validation"), dict):
        return context.payload["source_validation"]
    for artifact_ref in context.input_artifact_refs():
        if artifact_ref.get("schema") == "research_synthesis.source_validation.v1" or "validation" in str(artifact_ref.get("artifact_id", "")):
            return context.load_json_artifact(artifact_ref)
    return {}


def _load_seed(context: OperatorContext) -> dict[str, Any]:
    if isinstance(context.payload.get("seed_snapshot"), dict):
        return context.payload["seed_snapshot"]
    for artifact_ref in context.input_artifact_refs():
        if artifact_ref.get("schema") == "research_synthesis.seed_snapshot.v1" or "seed" in str(artifact_ref.get("artifact_id", "")):
            return context.load_json_artifact(artifact_ref)
    return {}


def _normalize_claims(response: dict[str, Any], accepted_ids: set[str]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for index, item in enumerate(response.get("claims", []) if isinstance(response.get("claims"), list) else []):
        if not isinstance(item, dict):
            continue
        evidence_ids = [str(value) for value in item.get("evidence_ids", []) if str(value).strip()]
        invalid = sorted(set(evidence_ids) - accepted_ids)
        if invalid:
            raise ResearchOperatorError(
                f"Model returned evidence ids outside validated source set: {', '.join(invalid)}",
                error_type="unvalidated_evidence",
            )
        claims.append(
            {
                "claim_id": str(item.get("claim_id") or f"claim-{index + 1:03d}"),
                "text": str(item.get("text") or ""),
                "evidence_ids": evidence_ids,
                "uncertainty": str(item.get("uncertainty") or "unknown"),
                "limitations": [str(value) for value in item.get("limitations", []) if str(value).strip()],
            }
        )
    return claims


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "evidence_synthesis")
    model_generate = context.services.get("model_generate")
    if model_generate is None:
        return no_provider_result(context, "model_generate")
    validation = _load_validation(context)
    accepted = [item for item in validation.get("accepted", []) if isinstance(item, dict)]
    if not accepted:
        return build_node_result(
            context,
            status="blocked",
            errors=[{"error_id": "evidence_synthesis.no_sources", "error_type": "missing_validated_sources", "message": "No validated sources were available for synthesis."}],
            limitations=["Evidence synthesis only consumes validated sources and cannot synthesize from unvalidated candidates."],
        )
    seed_snapshot = _load_seed(context)
    response = model_generate(
        node_id="evidence_synthesis",
        task_contract=context.payload.get("task_contract"),
        seed_snapshot=seed_snapshot,
        validated_sources=accepted,
    )
    if not isinstance(response, dict):
        raise ResearchOperatorError("model_generate service must return a JSON object", error_type="provider_contract")
    accepted_ids = {str(item.get("source_id")) for item in accepted if item.get("source_id")}
    claims = _normalize_claims(response, accepted_ids)
    if not claims:
        raise ResearchOperatorError("model_generate returned no grounded claims", error_type="provider_contract")
    limitations = [str(item) for item in response.get("limitations", []) if str(item).strip()]
    artifact_payload = {
        "schema": "research_synthesis.evidence_synthesis.v1",
        "node_id": "evidence_synthesis",
        "created_at": utc_now(),
        "source_ids": sorted(accepted_ids),
        "claims": claims,
        "claim_count": len(claims),
        "limitations": limitations,
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "evidence_synthesis.json"),
        artifact_payload,
        artifact_id="evidence_synthesis",
        schema="research_synthesis.evidence_synthesis.v1",
    )
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact],
        evidence=[evidence_ref("evidence_synthesis.claims", "claim_evidence_linkage", f"{len(claims)} grounded claim(s) synthesized.", artifact["artifact_id"])],
        hashes=[hash_record],
        model_provider_usage=provider_usage_from(response, usage_kind="llm"),
        limitations=limitations,
    )
