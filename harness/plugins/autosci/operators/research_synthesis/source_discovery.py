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
    raw_mode = str(context.payload.get("acquisition_mode") or "").strip()
    mode = raw_mode or "source_pack"
    if mode not in {"source_pack", "live_search", "hybrid"}:
        raise ResearchOperatorError(f"Unsupported acquisition mode: {mode}", error_type="invalid_input")
    pack_candidates = _supplied_candidates(context.payload)
    candidates = []
    for item in pack_candidates:
        candidate = dict(item)
        candidate["acquisition_channel"] = "source_pack"
        provenance = dict(candidate.get("provenance") or {}) if isinstance(candidate.get("provenance"), dict) else {}
        provenance["acquisition_channel"] = "source_pack"
        candidate["provenance"] = provenance
        candidates.append(candidate)
    provider_usage: list[dict[str, Any]] = []
    limitations: list[str] = []
    discovery_trace = "source_pack"
    discovery_query = str((context.payload.get("task_contract") or {}).get("user_intent") or "")
    live_candidates: list[dict[str, Any]] = []
    # Preserve the pre-existing research_synthesis ABI: callers that do not
    # declare the new typed acquisition mode still use their injected discovery
    # service. The fixed workflow always declares a mode explicitly.
    legacy_provider_discovery = not raw_mode and not pack_candidates
    if mode in {"live_search", "hybrid"} or legacy_provider_discovery:
        discover_sources = context.services.get("discover_sources")
        if discover_sources is None:
            return no_provider_result(context, "discover_sources")
        try:
            response = discover_sources(seed_snapshot=seed_snapshot, payload=context.payload)
            if not isinstance(response, dict):
                raise ResearchOperatorError("discover_sources service must return a JSON object", error_type="provider_contract")
            for item in response.get("candidates", []):
                if not isinstance(item, dict):
                    continue
                candidate = dict(item)
                candidate["acquisition_channel"] = "provider_discovery" if legacy_provider_discovery else "live_search"
                provenance = dict(candidate.get("provenance") or {}) if isinstance(candidate.get("provenance"), dict) else {}
                provenance["acquisition_channel"] = candidate["acquisition_channel"]
                candidate["provenance"] = provenance
                live_candidates.append(candidate)
            provider_usage = [item for item in response.get("provider_usage", []) if isinstance(item, dict)]
            limitations = [str(item) for item in response.get("limitations", []) if str(item).strip()]
            discovery_trace = str(response.get("trace") or "discover_sources")
            discovery_query = str(response.get("query") or discovery_query)
        except ResearchOperatorError as exc:
            limitations.append(f"Live public discovery failed: {exc.error_type}: {exc}")
            if mode == "live_search":
                return build_node_result(
                    context,
                    status="blocked",
                    errors=[{
                        "error_id": "source_discovery.live_provider_unavailable",
                        "error_type": exc.error_type,
                        "message": str(exc),
                    }],
                    limitations=limitations,
                )
        candidates.extend(live_candidates)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.get("canonical_id") or candidate.get("url") or candidate.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    candidates = deduped
    minimum_live = max(0, int(context.payload.get("minimum_live_sources") or 0))
    if mode == "live_search" and len(live_candidates) < minimum_live:
        return build_node_result(
            context,
            status="blocked",
            errors=[{
                "error_id": "source_discovery.minimum_live_sources_not_met",
                "error_type": "insufficient_live_sources",
                "message": f"Live discovery returned {len(live_candidates)} source(s); {minimum_live} required.",
            }],
            model_provider_usage=provider_usage,
            limitations=[*limitations, "The minimum live-source threshold was not met."],
        )
    if mode == "hybrid" and len(live_candidates) < minimum_live:
        limitations.append(
            f"Hybrid acquisition retained source-pack evidence but live discovery returned "
            f"{len(live_candidates)} source(s), below the required {minimum_live}; this run must not claim live coverage."
        )
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
        "query": discovery_query,
        "acquisition_mode": mode,
        "acquisition_summary": {
            "source_pack_count": sum(1 for item in candidates if item.get("acquisition_channel") == "source_pack"),
            "live_source_count": sum(1 for item in candidates if item.get("acquisition_channel") == "live_search"),
            "minimum_live_sources": minimum_live,
            "live_requirement_met": len(live_candidates) >= minimum_live if mode in {"live_search", "hybrid"} else False,
            "live_claim_allowed": len(live_candidates) >= minimum_live if mode in {"live_search", "hybrid"} else False,
        },
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
