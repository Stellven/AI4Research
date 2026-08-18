"""source_validation node implementation."""

from __future__ import annotations

import urllib.parse
import re
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


def _load_candidates(context: OperatorContext) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload, _ref = load_artifact(
        context,
        schemas=("research_synthesis.source_discovery.v1",),
        artifact_ids=("source_discovery",),
        filenames=("source_discovery.json",),
        payload_keys=(),
        expected_node_ids=("source_discovery",),
    )
    if payload:
        return [item for item in payload.get("candidates", []) if isinstance(item, dict)], payload
    raw = context.payload.get("candidates") or context.payload.get("source_candidates")
    return ([item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []), {}


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


_QUERY_STOPWORDS = {
    "about", "analysis", "analyze", "and", "for", "from", "into", "research", "report",
    "study", "that", "the", "their", "this", "using", "what", "with",
}


def _query_terms(value: str) -> set[str]:
    text = str(value or "").lower()
    terms = {
        token
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]{2,}", text)
        if token not in _QUERY_STOPWORDS
    }
    # CJK topics have no whitespace-delimited words. Overlapping two-character
    # windows provide a bounded lexical relevance signal without model calls.
    for run in re.findall(r"[\u3400-\u9fff]{2,}", text):
        terms.update(run[index:index + 2] for index in range(len(run) - 1))
    return terms


def _relevance_class(source: dict[str, Any], query: str) -> dict[str, Any]:
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
    provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
    channel = str(source.get("acquisition_channel") or provenance.get("acquisition_channel") or "")
    query_terms = _query_terms(query)
    source_terms = _query_terms(text)
    overlap = sorted(query_terms & source_terms)
    overlap_score = (len(overlap) / len(query_terms)) if query_terms else 0.0
    if channel == "live_search":
        proof = {
            "query_sha256": stable_json_sha256({"query": query}),
            "query_terms": sorted(query_terms),
            "matched_terms": overlap,
            "overlap_score": round(overlap_score, 6),
        }
        if not query_terms or not overlap:
            return {"class": "off_topic", "score": overlap_score, "proof": ["no task-query token overlap"], "query_binding": proof}
        return {"class": "query_matched", "score": overlap_score, "proof": ["task-query token overlap present"], "query_binding": proof}
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
    candidates, discovery = _load_candidates(context)
    query = str(discovery.get("query") or (context.payload.get("task_contract") or {}).get("user_intent") or "")
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
        relevance = _relevance_class(source, query)
        if authority["class"] == "unattributed":
            reasons.append("authority: unattributed source")
        if relevance["class"] == "low":
            reasons.append("relevance: declared low relevance")
        if relevance["class"] == "off_topic":
            reasons.append("relevance: no task-query token overlap")
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
            "acquisition_channel": str(source.get("acquisition_channel") or provenance.get("acquisition_channel") or "unknown"),
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
    acquisition_mode = str(discovery.get("acquisition_mode") or "source_pack")
    discovery_summary = discovery.get("acquisition_summary") if isinstance(discovery.get("acquisition_summary"), dict) else {}
    minimum_live = int(discovery_summary.get("minimum_live_sources") or 0)
    accepted_live = sum(1 for item in accepted if item.get("acquisition_channel") == "live_search")
    validation_limitations = [str(item) for item in discovery.get("limitations") or [] if str(item).strip()]
    live_requirement_met = accepted_live >= minimum_live if acquisition_mode in {"live_search", "hybrid"} else False
    if acquisition_mode == "hybrid" and not live_requirement_met:
        validation_limitations.append(
            f"Only {accepted_live} live public source(s) passed task-query validation; "
            "source-pack evidence remains usable but live coverage is not established."
        )
    artifact_payload = {
        "schema": "research_synthesis.source_validation.v1",
        "node_id": "source_validation",
        "created_at": utc_now(),
        "accepted": accepted,
        "rejected": rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "source_policy_summary": {
            "query": query,
            "query_sha256": stable_json_sha256({"query": query}),
            "acquisition_mode": acquisition_mode,
            "accepted_live_count": accepted_live,
            "accepted_source_pack_count": sum(1 for item in accepted if item.get("acquisition_channel") == "source_pack"),
            "minimum_live_sources": minimum_live,
            "live_requirement_met": live_requirement_met,
            "live_claim_allowed": live_requirement_met,
            "discovery_acquisition_summary": discovery_summary,
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
        "limitations": [
            *validation_limitations,
            "Validation classifies authority, task-query relevance, duplicates, and source failures; it does not assert source content truthfulness.",
        ],
    }
    artifact, hash_record = write_artifact(
        context,
        output_path(context, "source_validation.json"),
        artifact_payload,
        artifact_id="source_validation",
        schema="research_synthesis.source_validation.v1",
    )
    if not accepted or (acquisition_mode == "live_search" and not live_requirement_met):
        error_id = "source_validation.no_accepted_sources" if not accepted else "source_validation.minimum_live_sources_not_met"
        message = (
            "Source validation produced no accepted sources."
            if not accepted
            else f"Only {accepted_live} live source(s) passed validation; {minimum_live} required."
        )
        return build_node_result(
            context,
            status="blocked",
            output_artifacts=[artifact],
            evidence=[evidence_ref("source_validation.review", "source_validation", f"0 accepted and {len(rejected)} rejected source(s).", artifact["artifact_id"])],
            hashes=[hash_record],
            errors=[{
                "error_id": error_id,
                "error_type": "no_validated_sources" if not accepted else "insufficient_live_sources",
                "message": message,
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
