"""source_validation node implementation."""

from __future__ import annotations

import urllib.parse
from typing import Any

from .base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    evidence_ref,
    normalize_id,
    output_path,
    require_node,
    stable_json_sha256,
    utc_now,
    write_artifact,
)


def _load_candidates(context: OperatorContext) -> list[dict[str, Any]]:
    raw = context.payload.get("candidates") or context.payload.get("source_candidates")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    for artifact_ref in context.input_artifact_refs():
        if artifact_ref.get("schema") == "research_synthesis.source_discovery.v1" or "discovery" in str(artifact_ref.get("artifact_id", "")):
            payload = context.load_json_artifact(artifact_ref)
            return [item for item in payload.get("candidates", []) if isinstance(item, dict)]
    return []


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
                "checks": [
                    "durable identifier or URL present",
                    "title present",
                    "provenance/provider metadata present",
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
        "limitations": ["Validation checks metadata and provenance only; it does not assert source content truthfulness."],
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "source_validation.json"),
        artifact_payload,
        artifact_id="source_validation",
        schema="research_synthesis.source_validation.v1",
    )
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact],
        evidence=[evidence_ref("source_validation.review", "source_validation", f"{len(accepted)} accepted and {len(rejected)} rejected source(s).", artifact["artifact_id"])],
        hashes=[hash_record],
        limitations=artifact_payload["limitations"],
    )
