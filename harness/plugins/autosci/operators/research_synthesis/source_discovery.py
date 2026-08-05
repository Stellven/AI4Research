"""source_discovery node implementation."""

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
    require_node,
    utc_now,
    write_artifact,
)


def _load_seed_snapshot(context: OperatorContext) -> dict[str, Any]:
    payload, _ref = load_artifact(
        context,
        schemas=("research_synthesis.seed_snapshot.v1",),
        artifact_ids=("seed_snapshot",),
        filenames=("seed_snapshot.json",),
        payload_keys=("seed_snapshot",),
        expected_node_ids=("seed_fetch",),
    )
    return payload


def _supplied_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("supplied_source_candidates") or payload.get("source_candidates") or payload.get("candidates") or []
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "source_discovery")
    seed_snapshot = _load_seed_snapshot(context)
    candidates = _supplied_candidates(context.payload)
    provider_usage: list[dict[str, Any]] = []
    limitations: list[str] = []
    discovery_trace = "supplied_candidates"
    if not candidates:
        discover_sources = context.services.get("discover_sources")
        if discover_sources is None:
            return no_provider_result(context, "discover_sources")
        response = discover_sources(seed_snapshot=seed_snapshot, payload=context.payload)
        if not isinstance(response, dict):
            raise ResearchOperatorError("discover_sources service must return a JSON object", error_type="provider_contract")
        candidates = [item for item in response.get("candidates", []) if isinstance(item, dict)]
        provider_usage = [item for item in response.get("provider_usage", []) if isinstance(item, dict)]
        limitations = [str(item) for item in response.get("limitations", []) if str(item).strip()]
        discovery_trace = str(response.get("trace") or "discover_sources")
    if not candidates:
        return build_node_result(
            context,
            status="blocked",
            errors=[{
                "error_id": "source_discovery.no_candidates",
                "error_type": "no_sources_discovered",
                "message": "Source discovery returned no candidate sources.",
            }],
            model_provider_usage=provider_usage,
            limitations=[*limitations, "No source candidate was available for validation."],
        )
    artifact_payload = {
        "schema": "research_synthesis.source_discovery.v1",
        "node_id": "source_discovery",
        "created_at": utc_now(),
        "discovery_trace": discovery_trace,
        "seed_snapshot_ref": seed_snapshot.get("schema", ""),
        "candidates": candidates,
        "candidate_count": len(candidates),
        "limitations": limitations,
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "source_discovery.json"),
        artifact_payload,
        artifact_id="source_discovery",
        schema="research_synthesis.source_discovery.v1",
    )
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact],
        evidence=[evidence_ref("source_discovery.candidates", "source_candidates", f"{len(candidates)} candidate source(s) recorded.", artifact["artifact_id"])],
        hashes=[hash_record],
        model_provider_usage=provider_usage,
        limitations=limitations,
    )
