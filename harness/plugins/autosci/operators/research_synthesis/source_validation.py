"""source_validation node implementation."""

from __future__ import annotations

import urllib.parse
from typing import Any

from .base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    evidence_ref,
    load_artifact,
    normalize_id,
    output_path,
    require_node,
    stable_json_sha256,
    utc_now,
    write_artifact,
)


def _load_candidates(context: OperatorContext) -> list[dict[str, Any]]:
    payload, _ref = load_artifact(
        context,
        schemas=("research_synthesis.source_discovery.v1",),
        artifact_ids=("source_discovery",),
        filenames=("source_discovery.json",),
        payload_keys=(),
        expected_node_ids=("source_discovery",),
    )
    if payload:
        return [item for item in payload.get("candidates", []) if isinstance(item, dict)]
    raw = context.payload.get("candidates") or context.payload.get("source_candidates")
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _canonical_key(source: dict[str, Any]) -> str:
    canonical_id = str(source.get("canonical_id") or source.get("doi") or "").strip()
    if canonical_id:
        return f"id:{canonical_id.lower()}"
    url = str(source.get("url") or source.get("source_ref") or "").strip()
    if url:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/").lower()
        query = urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)))
        return f"url:{netloc}{path}?{query}" if query else f"url:{netloc}{path}"
    title = str(source.get("title") or "").strip().lower()
    if title:
        return f"title:{title}"
    source_id = str(source.get("source_id") or source.get("id") or "").strip()
    return f"id:{source_id.lower()}" if source_id else ""


def _rejection(source: dict[str, Any], reasons: list[str], index: int) -> dict[str, Any]:
    return {
        "source_id": str(source.get("source_id") or source.get("id") or f"candidate-{index + 1:03d}"),
        "title": str(source.get("title") or ""),
        "url": str(source.get("url") or source.get("source_ref") or ""),
        "reasons": reasons,
        "candidate_sha256": stable_json_sha256(source),
    }


def _authority_class(source: dict[str, Any]) -> dict[str, Any]:
    provider = str(source.get("provider") or "").strip().lower()
    provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
    provenance_provider = str(provenance.get("provider") or "").strip().lower()
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    has_canonical = bool(str(source.get("canonical_id") or source.get("doi") or "").strip())
    has_url = bool(str(source.get("url") or source.get("source_ref") or "").strip())
    authority = str(source.get("authority") or metadata.get("authority") or "").strip().lower()
    authority_proof: list[str] = []
    if authority in {"primary", "canonical", "authoritative", "peer_reviewed"}:
        score = 1.0
        authority_class = "authoritative"
        authority_proof.append(f"declared_authority:{authority}")
    elif has_canonical or provider in {"semantic_scholar", "openalex", "crossref", "arxiv"} or provenance_provider in {"semantic_scholar", "openalex", "crossref", "arxiv"}:
        score = 0.85
        authority_class = "bibliographic"
        authority_proof.append("canonical bibliographic identifier or provider present")
    elif provider or provenance_provider or has_url:
        score = 0.55
        authority_class = "traceable"
        authority_proof.append("traceable provider or URL present")
    else:
        score = 0.2
        authority_class = "unattributed"
        authority_proof.append("no provider, provenance, URL, DOI, or canonical id")
    return {
        "class": authority_class,
        "score": score,
        "proof": authority_proof,
    }


def _relevance_class(source: dict[str, Any]) -> dict[str, Any]:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    raw_score = source.get("relevance_score", metadata.get("relevance_score"))
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        score = -1.0
    text = " ".join(
        str(source.get(key) or "")
        for key in ("title", "content_summary", "summary", "abstract")
    ).strip()
    if score >= 0.75:
        return {"class": "high", "score": score, "proof": ["declared relevance_score >= 0.75"]}
    if 0 <= score < 0.25:
        return {"class": "low", "score": score, "proof": ["declared relevance_score < 0.25"]}
    if len(text) >= 40:
        return {"class": "content_described", "score": None, "proof": ["title or content summary is substantive"]}
    return {"class": "unknown", "score": None, "proof": ["no explicit relevance score or substantive summary"]}


def _source_failure_reasons(source: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    status_values = [
        str(source.get("status") or ""),
        str(source.get("fetch_status") or ""),
        str(source.get("provider_status") or ""),
    ]
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    status_values.extend(str(metadata.get(key) or "") for key in ("status", "fetch_status", "provider_status"))
    if any(value.lower() in {"failed", "error", "timeout", "rate_limited", "unavailable"} for value in status_values):
        reasons.append("source_failure: provider or fetch status indicates failure")
    if source.get("error") or metadata.get("error"):
        reasons.append("source_failure: error detail present")
    return reasons


def execute(node_request: dict, context: OperatorContext) -> dict:
    require_node(context, "source_validation")
    candidates = _load_candidates(context)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for index, source in enumerate(candidates):
        reasons: list[str] = []
        title = str(source.get("title") or "").strip()
        key = _canonical_key(source)
        if not key:
            reasons.append("missing durable source identifier or URL")
        if not title:
            reasons.append("missing source title")
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
        if not metadata and not provenance and not source.get("provider"):
            reasons.append("missing provenance or provider metadata")
        if key and key in seen:
            reasons.append(f"duplicate_of:{seen[key]}")
        reasons.extend(_source_failure_reasons(source))
        authority = _authority_class(source)
        relevance = _relevance_class(source)
        if authority["class"] == "unattributed":
            reasons.append("authority: unattributed source")
        if relevance["class"] == "low":
            reasons.append("relevance: declared low relevance")
        if reasons:
            rejected.append(_rejection(source, reasons, index))
            continue
        source_id = str(source.get("source_id") or source.get("id") or normalize_id(title))
        seen[key] = source_id
        normalized = {
            "source_id": source_id,
            "title": title,
            "url": str(source.get("url") or source.get("source_ref") or ""),
            "canonical_id": str(source.get("canonical_id") or source.get("doi") or source_id),
            "provenance": provenance or {"provider": str(source.get("provider") or "supplied"), "trace": str(source.get("trace") or "")},
            "metadata": metadata,
            "content_summary": str(source.get("content_summary") or source.get("summary") or source.get("abstract") or ""),
            "candidate_sha256": stable_json_sha256(source),
            "validation": {
                "status": "accepted",
                "authority": authority,
                "relevance": relevance,
                "checks": [
                    "durable identifier or URL present",
                    "title present",
                    "provenance/provider metadata present",
                    f"authority classified as {authority['class']}",
                    f"relevance classified as {relevance['class']}",
                    "URL parse was not treated as content trust",
                ],
            },
        }
        accepted.append(normalized)
    artifact_payload = {
        "schema": "research_synthesis.source_validation.v1",
        "node_id": "source_validation",
        "created_at": utc_now(),
        "accepted": accepted,
        "rejected": rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "source_policy_summary": {
            "authority_classes": sorted({
                str((item.get("validation") or {}).get("authority", {}).get("class"))
                for item in accepted
                if isinstance(item.get("validation"), dict)
            }),
            "relevance_classes": sorted({
                str((item.get("validation") or {}).get("relevance", {}).get("class"))
                for item in accepted
                if isinstance(item.get("validation"), dict)
            }),
            "duplicate_rejections": sum(
                1 for item in rejected for reason in item.get("reasons", []) if str(reason).startswith("duplicate_of:")
            ),
            "source_failure_rejections": sum(
                1 for item in rejected for reason in item.get("reasons", []) if str(reason).startswith("source_failure:")
            ),
            "low_relevance_rejections": sum(
                1 for item in rejected for reason in item.get("reasons", []) if str(reason).startswith("relevance:")
            ),
            "authority_rejections": sum(
                1 for item in rejected for reason in item.get("reasons", []) if str(reason).startswith("authority:")
            ),
        },
        "limitations": ["Validation classifies authority, relevance, duplicates, and source failures; it does not assert source content truthfulness."],
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "source_validation.json"),
        artifact_payload,
        artifact_id="source_validation",
        schema="research_synthesis.source_validation.v1",
    )
    if not accepted:
        return build_node_result(
            context,
            status="blocked",
            output_artifacts=[artifact],
            evidence=[evidence_ref("source_validation.review", "source_validation", f"0 accepted and {len(rejected)} rejected source(s).", artifact["artifact_id"])],
            hashes=[hash_record],
            errors=[{
                "error_id": "source_validation.no_accepted_sources",
                "error_type": "no_validated_sources",
                "message": "Source validation produced no accepted sources.",
            }],
            limitations=artifact_payload["limitations"],
        )
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact],
        evidence=[evidence_ref("source_validation.review", "source_validation", f"{len(accepted)} accepted and {len(rejected)} rejected source(s).", artifact["artifact_id"])],
        hashes=[hash_record],
        limitations=artifact_payload["limitations"],
    )
