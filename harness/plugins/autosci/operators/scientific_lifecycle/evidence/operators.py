"""Bounded physical implementations for evidence-producing lifecycle nodes."""

from __future__ import annotations

import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from ....adapters.autosci_to_research_paper import convert as convert_paper
from ....backends.literature_discover import discover_literature
from ....backends.paper_prepare import read_paper_source
from ...research_synthesis.base import (
    OperatorContext,
    ResearchOperatorError,
    display_path,
    sha256_bytes,
    validate_scoped_path,
)
from .base import (
    PRODUCT_FAILURE,
    PROVIDER_ENVIRONMENT_FAILURE,
    SUCCESS,
    OperatorSpec,
    envelope,
    evidence_document,
    load_evidence_inputs,
)


_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_SENTENCE = re.compile(r"(?<=[.!?。！？])\s+")
_STOPWORDS = {
    "about", "after", "also", "and", "are", "because", "been", "before", "being", "between",
    "both", "can", "could", "from", "have", "into", "more", "most", "not", "only", "other",
    "our", "paper", "results", "section", "should", "show", "study", "such", "than", "that",
    "the", "their", "these", "they", "this", "through", "using", "was", "were", "which", "with",
}
_CODE_SUFFIXES = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go", ".java", ".c", ".cc", ".cpp", ".h", ".hpp", ".sh", ".ps1"}


def _product_error(message: str) -> ResearchOperatorError:
    return ResearchOperatorError(message, error_type=PRODUCT_FAILURE)


def _normalized_candidates(values: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, value in enumerate(values if isinstance(values, list) else [], start=1):
        if not isinstance(value, dict):
            continue
        title = str(value.get("title") or "").strip()
        if not title:
            continue
        source_channels = [str(item) for item in value.get("source_channels") or [] if str(item).strip()]
        if not source_channels:
            source_channels = [
                str(value.get("provider") or value.get("source") or "injected_provider")
            ]
        candidates.append(
            {
                **value,
                "candidate_id": str(
                    value.get("candidate_id")
                    or value.get("source_id")
                    or value.get("paperId")
                    or f"candidate-{index:03d}"
                ),
                "title": title,
                "source_channels": source_channels,
                "ranking_score": float(value.get("ranking_score") or 0.0),
                "ranking_rationale": str(value.get("ranking_rationale") or "Returned by the bounded discovery provider."),
                "dedup_status": str(value.get("dedup_status") or "unknown"),
                "fetch_status": str(value.get("fetch_status") or "not_requested"),
            }
        )
    return candidates


def _local_source_candidates(
    context: OperatorContext,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Convert exact scheduler-bound local files into traceable candidates."""

    candidates: list[dict[str, Any]] = []
    limitations: list[str] = []
    seen_hashes: set[str] = set()
    for row in context.payload.get("local_sources") or []:
        if not isinstance(row, dict):
            continue
        raw_path = str(row.get("path") or "").strip()
        if not raw_path:
            continue
        path = validate_scoped_path(
            raw_path,
            context.read_scope,
            workspace_root=context.workspace_root,
            must_exist=True,
            allow_external_exact=True,
        )
        if not path.is_file():
            raise _product_error(f"Local source is not a regular file: {raw_path}")
        digest = sha256_bytes(path.read_bytes())
        expected_hash = str(row.get("sha256") or "").lower()
        if not expected_hash or expected_hash != digest:
            raise _product_error(f"Local source hash mismatch: {raw_path}")
        if digest in seen_hashes:
            limitations.append(
                f"Excluded identical local source content: {path.name} ({digest[:16]})."
            )
            continue
        seen_hashes.add(digest)
        candidates.append(
            {
                "candidate_id": f"local-{digest[:16]}",
                "title": path.stem,
                "source_channels": ["local"],
                "source_ref": str(path),
                "content_sha256": digest,
                "ranking_score": 1.0,
                "ranking_rationale": "Controller-frozen local seed explicitly required by the accepted source contract.",
                "dedup_status": "new",
                "fetch_status": "fetched",
            }
        )
    return candidates, limitations


def _merge_discovery_candidates(
    local_candidates: list[dict[str, Any]],
    provider_candidates: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    identities: set[str] = set()
    for candidate in [*local_candidates, *provider_candidates]:
        identity = str(
            candidate.get("content_sha256")
            or candidate.get("source_ref")
            or candidate.get("url")
            or candidate.get("candidate_id")
            or ""
        ).strip()
        if not identity or identity in identities:
            continue
        identities.add(identity)
        merged.append(candidate)
        if len(merged) >= limit:
            break
    return merged


def _study_protocol(
    payload: dict[str, Any],
    raw: dict[str, Any],
    *,
    query: str,
    mode: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Describe the bounded discovery policy without inventing missing scope."""

    source_channels = sorted(
        {
            str(channel).strip()
            for candidate in candidates
            for channel in candidate.get("source_channels") or []
            if str(channel).strip()
        }
    )
    year = raw.get("year") if raw.get("year") not in (None, "") else payload.get("year")
    time_range = {
        "status": "resolved" if year not in (None, "") else "unresolved",
        "start": str(year) if year not in (None, "") else None,
        "end": str(year) if year not in (None, "") else None,
        "rationale": (
            f"Discovery was explicitly limited to publication year {year}."
            if year not in (None, "")
            else "No publication-date boundary was supplied; the report must disclose this limitation."
        ),
    }
    unresolved_fields = [] if time_range["status"] == "resolved" else ["time_range"]
    return {
        "protocol_status": "resolved" if not unresolved_fields else "partially_resolved",
        "search_strategy": (
            f"Run bounded {mode or 'topic'} discovery for query {query or 'unresolved'}"
            + (
                f" across the returned source channels: {', '.join(source_channels)}."
                if source_channels
                else "; no provider source channel returned usable candidates."
            )
            + " Preserve provider ranking rationale and deduplication status for every candidate."
        ),
        "source_selection_criteria": [
            "Candidate has a non-empty title and at least one declared source channel.",
            "Candidate remains relevant to the submitted discovery query under the provider ranking.",
            "Candidate retains ranking rationale and deduplication status for audit.",
        ],
        "time_range": time_range,
        "inclusion_criteria": [
            "Retain ranked, traceable candidates relevant to the submitted query.",
            "Retain the source channel, ranking score, rationale, and deduplication state.",
        ],
        "exclusion_criteria": [
            "Exclude records without a usable title.",
            "Exclude explicitly negative or duplicate identifiers from the selected shortlist.",
            "Leave candidates without fetchable source references visible as downstream ingestion limitations.",
        ],
        "unresolved_fields": unresolved_fields,
    }


def literature_discovery(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    payload = context.payload
    query = str(payload.get("query") or payload.get("topic") or "").strip()
    mode = str(payload.get("mode") or ("topic" if query else "")).strip()
    if not mode:
        raise _product_error("Literature discovery requires query/topic, anchors, venue, or an explicit mode")
    wiki_root_raw = str(payload.get("wiki_root") or "").strip()
    if wiki_root_raw:
        wiki_root = validate_scoped_path(
            wiki_root_raw, context.read_scope, workspace_root=context.workspace_root, must_exist=True
        )
    else:
        wiki_root = context.workspace_root / ".autosci-no-wiki-input"
    production_backend = context.services.get("discover_sources")
    backend = context.services.get("discover_literature") or discover_literature
    local_candidates, local_limitations = _local_source_candidates(context)
    candidate_limit = max(1, min(int(payload.get("limit") or 10), 200))
    try:
        if callable(production_backend):
            production_payload = dict(payload)
            production_payload.setdefault("topic", query)
            raw = production_backend(
                seed_snapshot={
                    "schema": "research_seed_snapshot.v1",
                    "seeds": [
                        {
                            "seed_id": "planner-topic",
                            "seed_kind": "topic",
                            "content": query,
                        }
                    ],
                },
                payload=production_payload,
            )
        else:
            raw = backend(
                query=query,
                mode=mode,
                anchors=list(payload.get("anchors") or []),
                negative_ids=list(payload.get("negative_ids") or []),
                venue=str(payload.get("venue") or ""),
                year=payload.get("year"),
                limit=int(payload.get("limit") or 10),
                wiki_root=wiki_root,
                workspace_root=context.workspace_root,
                repository_root=context.workspace_root,
                allow_network_fetch=bool(payload.get("allow_network_fetch", True)),
                no_citation_expand=bool(payload.get("no_citation_expand", False)),
                fixture_fallback=False,
                max_retries=payload.get("max_retries"),
                max_retry_wait_seconds=payload.get("max_retry_wait_seconds"),
            )
    except Exception as exc:
        if local_candidates:
            candidates = local_candidates[:candidate_limit]
            protocol = _study_protocol(
                payload,
                {},
                query=query or "unresolved",
                mode=mode,
                candidates=candidates,
            )
            evidence = evidence_document(
                context,
                spec,
                {
                    "query": query or "unresolved",
                    "candidates": candidates,
                    "mode": mode,
                    "study_protocol": protocol,
                },
                status="completed",
                limitations=[
                    *local_limitations,
                    f"Discovery provider failed; continued with {len(candidates)} controller-frozen local seed(s): {type(exc).__name__}: {exc}",
                    *[
                        f"Study protocol field remains unresolved: {field}."
                        for field in protocol["unresolved_fields"]
                    ],
                ],
                artifacts=[
                    {
                        "type": "local_seed",
                        "path": str(candidate["source_ref"]),
                        "sha256": str(candidate["content_sha256"]),
                    }
                    for candidate in candidates
                ],
            )
            return {
                "evidence": evidence,
                "outcome_class": SUCCESS,
                "summary": (
                    f"Preserved {len(candidates)} local literature seed(s); "
                    "external discovery was recorded as unavailable."
                ),
            }
        protocol = _study_protocol(
            payload,
            {},
            query=query or "unresolved",
            mode=mode,
            candidates=[],
        )
        evidence = evidence_document(
            context,
            spec,
            {
                "query": query or "unresolved",
                "candidates": [],
                "mode": mode,
                "study_protocol": protocol,
            },
            status="inconclusive",
            limitations=[
                f"Discovery provider failed: {type(exc).__name__}: {exc}",
                *[
                    f"Study protocol field remains unresolved: {field}."
                    for field in protocol["unresolved_fields"]
                ],
            ],
        )
        return {
            "evidence": evidence,
            "outcome_class": PROVIDER_ENVIRONMENT_FAILURE,
            "summary": "Literature provider failed before candidates were returned.",
            "error": str(exc),
        }
    provider_candidates = _normalized_candidates(raw.get("candidates"))
    candidates = _merge_discovery_candidates(
        local_candidates,
        provider_candidates,
        limit=candidate_limit,
    )
    provider_status = str(raw.get("status") or ("completed" if provider_candidates else "inconclusive"))
    # Providers may report an environment failure as a structured
    # ``inconclusive`` result instead of raising.  The accepted workflow's
    # degraded-mode contract still has usable controller-frozen local seeds,
    # so that provider status must not erase the successful local handoff.
    local_fallback_used = provider_status == "inconclusive" and bool(local_candidates)
    status = "completed" if local_fallback_used else provider_status
    outputs = {
        key: raw[key]
        for key in ("query", "mode", "limit", "anchors", "negative_ids", "venue", "year", "source_fan_in", "source_provider_boundary")
        if raw.get(key) not in (None, "", [])
    }
    outputs["query"] = str(outputs.get("query") or query or "unresolved")
    outputs["candidates"] = candidates
    outputs["study_protocol"] = _study_protocol(
        payload,
        raw,
        query=outputs["query"],
        mode=str(outputs.get("mode") or mode),
        candidates=candidates,
    )
    limitations = [*local_limitations, *list(raw.get("limitations") or [])]
    if local_fallback_used:
        limitations.append(
            f"External discovery was inconclusive; continued with {len(local_candidates[:candidate_limit])} "
            "controller-frozen local seed(s)."
        )
    limitations.extend(
        f"Study protocol field remains unresolved: {field}."
        for field in outputs["study_protocol"]["unresolved_fields"]
    )
    evidence = evidence_document(
        context,
        spec,
        outputs,
        status=status if status in {"completed", "failed", "inconclusive"} else "inconclusive",
        limitations=limitations,
        artifacts=[
            *list(raw.get("artifacts") or []),
            *[
                {
                    "type": "local_seed",
                    "path": str(candidate["source_ref"]),
                    "sha256": str(candidate["content_sha256"]),
                }
                for candidate in local_candidates[:candidate_limit]
            ],
        ],
    )
    if status == "completed" and candidates:
        return {
            "evidence": evidence,
            "outcome_class": SUCCESS,
            "summary": f"Discovered {len(candidates)} traceable literature candidate(s).",
        }
    outcome = PRODUCT_FAILURE if status == "failed" else PROVIDER_ENVIRONMENT_FAILURE
    return {
        "evidence": evidence,
        "outcome_class": outcome,
        "summary": "Literature discovery completed without usable candidates.",
        "error": (evidence["limitations"] or ["No usable literature candidates were returned."])[0],
    }


def _source_path(context: OperatorContext) -> tuple[str, Path | None]:
    source = str(
        context.payload.get("source")
        or context.payload.get("paper_path")
        or context.payload.get("material_path")
        or context.payload.get("url")
        or ""
    ).strip()
    if not source:
        raise _product_error("Ingestion requires source, paper_path, material_path, or url")
    if re.match(r"^https?://", source, re.IGNORECASE):
        return source, None
    return source, validate_scoped_path(
        source,
        context.read_scope,
        workspace_root=context.workspace_root,
        must_exist=True,
        allow_external_exact=True,
    )


def import_existing_evidence(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    """Create execution-produced provenance for already existing evidence."""

    task_contract = context.payload.get("task_contract")
    supplied = task_contract.get("supplied_evidence") if isinstance(task_contract, dict) else None
    refs = [dict(item) for item in supplied or [] if isinstance(item, dict)]
    if not refs:
        raise _product_error("Evidence import requires at least one supplied evidence reference")
    imported: list[dict[str, Any]] = []
    for ref in refs:
        path = validate_scoped_path(
            str(ref.get("path") or ""),
            context.read_scope,
            workspace_root=context.workspace_root,
            must_exist=True,
        )
        digest = sha256_bytes(path.read_bytes())
        expected = str(ref.get("sha256") or "")
        if expected and expected.lower() != digest:
            raise _product_error(f"Imported evidence hash mismatch: {ref.get('path')}")
        imported.append(
            {
                "artifact_id": str(ref.get("artifact_id") or f"import-{len(imported) + 1}"),
                "path": display_path(path, context.workspace_root),
                "sha256": digest,
                "provenance": dict(ref.get("provenance") or {}),
            }
        )
    evidence = evidence_document(
        context,
        spec,
        {"imported_evidence": imported, "imported_count": len(imported)},
        limitations=["Imported content is hash-verified provenance; its scientific claims are not accepted without downstream evaluation."],
    )
    return {
        "evidence": evidence,
        "outcome_class": SUCCESS,
        "summary": f"Imported and re-hashed {len(imported)} evidence artifact(s).",
    }


def ingest_source(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    source, local_path = _source_path(context)
    backend = context.services.get("read_paper_source") or read_paper_source
    try:
        with tempfile.TemporaryDirectory(prefix="solar-autosci-ingest-") as raw_dir:
            raw = backend(
                local_path or source,
                raw_root=Path(raw_dir),
                workspace_root=context.workspace_root,
                repository_root=context.workspace_root,
                paper_id=str(context.payload.get("paper_id") or ""),
                title=str(context.payload.get("title") or ""),
                arxiv_id=str(context.payload.get("arxiv_id") or ""),
                allow_network_fetch=bool(context.payload.get("allow_network_fetch", True)),
                analyzed=False,
            )
    except Exception as exc:
        outcome = PROVIDER_ENVIRONMENT_FAILURE if re.match(r"^https?://", source, re.IGNORECASE) else PRODUCT_FAILURE
        failed = {
            "paper_id": str(context.payload.get("paper_id") or "paper-unresolved"),
            "title": str(context.payload.get("title") or "Unresolved source"),
            "source_type": "url" if local_path is None else "unknown",
            "source_ref": source,
            "parse_status": "failed",
            "sections": [],
            "status": "failed" if outcome == PRODUCT_FAILURE else "inconclusive",
            "limitations": [f"Ingestion backend failed: {type(exc).__name__}: {exc}"],
        }
        return {
            "evidence": convert_paper(failed, envelope(context)),
            "outcome_class": outcome,
            "summary": "Source ingestion failed.",
            "error": str(exc),
        }
    if local_path is not None:
        original = display_path(local_path, context.workspace_root)
        raw["source_ref"] = original
        for section in raw.get("sections") or []:
            anchor = str(section.get("source_anchor") or "")
            section["source_anchor"] = f"{original}#{anchor.rsplit('#', 1)[-1] or section.get('section_id', 'body')}"
        raw["artifacts"] = [{"type": "ingested_source", "path": original, "sha256": sha256_bytes(local_path.read_bytes())}]
    evidence = convert_paper(raw, envelope(context))
    if raw.get("status") == "completed" and evidence["outputs"]["paper"].get("sections"):
        return {
            "evidence": evidence,
            "outcome_class": SUCCESS,
            "summary": f"Ingested {len(evidence['outputs']['paper']['sections'])} source section(s).",
        }
    return {
        "evidence": evidence,
        "outcome_class": PRODUCT_FAILURE,
        "summary": "Source ingestion produced no usable sections.",
        "error": (evidence.get("limitations") or ["No usable source sections were produced."])[0],
    }


def ingest_discovered_sources(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    """Ingest traceable discovery candidates without inventing missing sources."""

    documents = load_evidence_inputs(
        context,
        "literature_discovery.v1",
        payload_keys=("literature_discovery", "discovery_evidence"),
    )
    if not documents:
        raise _product_error("Discovery ingestion requires literature_discovery.v1 input")
    candidates = [
        candidate
        for document in documents
        for candidate in document.get("outputs", {}).get("candidates") or []
        if isinstance(candidate, dict)
    ]
    if not candidates:
        raise _product_error("Discovery evidence contains no candidates")
    requested_limit = context.payload.get("max_sources")
    limit = min(
        len(candidates),
        max(1, min(int(requested_limit), 200)) if requested_limit is not None else 200,
    )
    evidence_items: list[dict[str, Any]] = []
    limitations: list[str] = []
    for candidate in candidates[:limit]:
        source = next(
            (
                str(candidate.get(key) or "").strip()
                for key in ("source_ref", "url", "pdf_url", "doi", "arxiv_id")
                if str(candidate.get(key) or "").strip()
            ),
            "",
        )
        candidate_id = str(candidate.get("candidate_id") or "unresolved")
        if not source:
            limitations.append(
                f"Skipped {candidate_id}: discovery supplied no fetchable source reference."
            )
            continue
        child_request = dict(context.node_request)
        child_request["typed_inputs"] = {
            "payload": {
                **context.payload,
                "source": source,
                "paper_id": candidate_id,
                "title": str(candidate.get("title") or candidate_id),
            }
        }
        child_context = OperatorContext.from_request(
            child_request,
            services=context.services,
            workspace_root=context.workspace_root,
        )
        raw = ingest_source(child_context, spec)
        if raw.get("outcome_class") == SUCCESS and raw.get("evidence", {}).get("status") == "completed":
            evidence_items.append(
                {
                    "evidence": raw["evidence"],
                    "summary": raw.get("summary"),
                }
            )
        else:
            limitations.append(
                f"Failed to ingest {candidate_id}: "
                f"{str(raw.get('error') or raw.get('summary') or 'unknown ingestion failure')[:240]}"
            )
    if not evidence_items:
        return {
            "evidence_items": [],
            "error_type": "product_failure",
            "error": "No discovered candidate produced parsed paper evidence",
            "limitations": limitations,
        }
    return {
        "evidence_items": evidence_items,
        "limitations": limitations,
        "summary": f"Ingested {len(evidence_items)} of {min(len(candidates), limit)} selected candidates.",
    }


def assess_research_sources(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    """Resolve source relevance and metadata credibility without claiming truth.

    This reuses the fixed research workflow's existing authority and topic-
    relevance classification.  The new artifact makes those decisions
    available to generated scientific plans and records unresolved cases
    instead of silently promoting a ranked discovery candidate.
    """

    from ...research_synthesis.source_validation import (  # local import avoids a registry import cycle
        _authority_class,
        _relevance_class,
    )

    discovery_documents = load_evidence_inputs(
        context,
        "literature_discovery.v1",
        payload_keys=("literature_discovery", "discovery_evidence"),
    )
    paper_documents = load_evidence_inputs(
        context,
        "research_paper.v1",
        payload_keys=("research_paper", "paper_evidence"),
    )
    if not discovery_documents:
        raise _product_error("Source assessment requires literature_discovery.v1 input")
    if not paper_documents:
        raise _product_error("Source assessment requires parsed research_paper.v1 input")

    discovery = discovery_documents[0]
    discovery_outputs = discovery.get("outputs") if isinstance(discovery.get("outputs"), dict) else {}
    query = str(discovery_outputs.get("query") or "").strip()
    if not query:
        raise _product_error("Source assessment discovery input has no query")
    candidates = [
        item for item in discovery_outputs.get("candidates") or [] if isinstance(item, dict)
    ]
    if not candidates:
        raise _product_error("Source assessment discovery input has no candidates")

    papers: dict[str, dict[str, Any]] = {}
    for document in paper_documents:
        values = document.get("outputs") if isinstance(document.get("outputs"), dict) else {}
        paper = values.get("paper") if isinstance(values.get("paper"), dict) else None
        if not paper:
            continue
        paper_id = str(paper.get("paper_id") or "").strip()
        if paper_id:
            papers[paper_id] = paper

    assessments: list[dict[str, Any]] = []
    benchmark_candidates: list[dict[str, Any]] = []
    unresolved_questions: list[str] = []
    for candidate in candidates:
        source_id = str(candidate.get("candidate_id") or "").strip()
        if not source_id:
            continue
        paper = papers.get(source_id, {})
        channels = [
            str(item).strip()
            for item in candidate.get("source_channels") or []
            if str(item).strip()
        ] or ["unknown"]
        identifiers = paper.get("identifiers") if isinstance(paper.get("identifiers"), dict) else {}
        section_text = " ".join(
            str(section.get("text") or "")
            for section in paper.get("sections") or []
            if isinstance(section, dict)
        )[:4000]
        source_for_validation = {
            **candidate,
            "source_id": source_id,
            "provider": channels[0],
            "canonical_id": str(
                identifiers.get("doi")
                or identifiers.get("arxiv")
                or candidate.get("doi")
                or candidate.get("arxiv_id")
                or ""
            ),
            "url": str(candidate.get("source_ref") or candidate.get("url") or paper.get("source_ref") or ""),
            "content_summary": str(
                candidate.get("abstract")
                or paper.get("abstract")
                or section_text
                or candidate.get("ranking_rationale")
                or ""
            ),
            "acquisition_channel": "live_search",
            "provenance": {"provider": channels[0], "source_channels": channels},
        }
        relevance_raw = _relevance_class(source_for_validation, query)
        authority_raw = _authority_class(source_for_validation)
        relevance_class = str(relevance_raw.get("class") or "unknown")
        authority_class = str(authority_raw.get("class") or "unattributed")
        if relevance_class in {"off_topic", "low"}:
            relevance_status = "not_relevant"
        elif relevance_class == "unknown":
            relevance_status = "unresolved"
        else:
            relevance_status = "relevant"
        if authority_class in {"authoritative", "bibliographic"}:
            credibility_status = "credible"
        elif authority_class == "traceable":
            credibility_status = "traceable"
        else:
            credibility_status = "unresolved"

        parse_status = str(paper.get("parse_status") or "not_available")
        if parse_status not in {"parsed", "partial", "failed"}:
            parse_status = "not_available"
        if relevance_status == "not_relevant":
            decision = "excluded"
        elif (
            relevance_status == "relevant"
            and credibility_status == "credible"
            and parse_status in {"parsed", "partial"}
        ):
            decision = "selected"
        else:
            decision = "unresolved"
            unresolved_questions.append(
                f"Source {source_id} remains unresolved: relevance={relevance_status}, "
                f"credibility={credibility_status}, ingestion={parse_status}."
            )

        assessments.append(
            {
                "source_id": source_id,
                "title": str(candidate.get("title") or paper.get("title") or source_id),
                "source_ref": str(source_for_validation.get("url") or ""),
                "source_channels": channels,
                "relevance": {
                    "status": relevance_status,
                    "score": relevance_raw.get("score"),
                    "basis": [
                        *[str(item) for item in relevance_raw.get("proof") or [] if str(item).strip()],
                        str(candidate.get("ranking_rationale") or "Discovery supplied no ranking rationale."),
                    ],
                },
                "credibility": {
                    "status": credibility_status,
                    "authority_class": authority_class,
                    "score": float(authority_raw.get("score") or 0.0),
                    "basis": [str(item) for item in authority_raw.get("proof") or [] if str(item).strip()],
                },
                "ingestion": {"status": parse_status, "paper_id": str(paper.get("paper_id") or "")},
                "decision": decision,
                "evidence_ids": sorted(
                    {
                        f"literature_discovery:{source_id}",
                        *([f"research_paper:{source_id}"] if paper else []),
                    }
                ),
            }
        )

        benchmark_text = " ".join(
            [
                str(candidate.get("title") or ""),
                str(candidate.get("abstract") or paper.get("abstract") or ""),
            ]
        ).lower()
        explicit_kind = str(candidate.get("record_kind") or candidate.get("type") or "").lower()
        benchmark_signal = explicit_kind in {"benchmark", "dataset"} or any(
            token in benchmark_text
            for token in ("benchmark", "dataset", "corpus", "question answering", "question-answering")
        )
        if benchmark_signal:
            benchmark_candidates.append(
                {
                    "source_id": source_id,
                    "title": str(candidate.get("title") or paper.get("title") or source_id),
                    "identification_basis": (
                        f"Discovery record kind declared {explicit_kind}."
                        if explicit_kind in {"benchmark", "dataset"}
                        else "Title or abstract contains an explicit benchmark/dataset/question-answering signal."
                    ),
                    "availability_status": (
                        "public_reference_present"
                        if str(source_for_validation.get("url") or "")
                        else "candidate_only"
                    ),
                }
            )

    if not assessments:
        raise _product_error("Source assessment produced no source decisions")
    if not benchmark_candidates:
        unresolved_questions.append(
            "No public question-answering benchmark was independently identified in the retained discovery and paper evidence."
        )
    selected = [item["source_id"] for item in assessments if item["decision"] == "selected"]
    excluded = [item["source_id"] for item in assessments if item["decision"] == "excluded"]
    unresolved = [item["source_id"] for item in assessments if item["decision"] == "unresolved"]
    evidence = evidence_document(
        context,
        spec,
        {
            "query": query,
            "assessments": assessments,
            "selected_source_ids": selected,
            "excluded_source_ids": excluded,
            "unresolved_source_ids": unresolved,
            "benchmark_candidates": benchmark_candidates,
            "unresolved_questions": unresolved_questions,
        },
        status="completed",
        limitations=[
            "Credibility classifies source authority and traceability from retained metadata; it does not establish scientific truth.",
            "Benchmark identification records candidates from explicit metadata or title/abstract signals; dataset availability and suitability require experiment-time verification.",
        ],
    )
    return {
        "evidence": evidence,
        "outcome_class": SUCCESS,
        "summary": (
            f"Assessed {len(assessments)} source(s): {len(selected)} selected, "
            f"{len(excluded)} excluded, {len(unresolved)} unresolved."
        ),
    }


def _first_evidence(context: OperatorContext, schemas: tuple[str, ...], keys: tuple[str, ...]) -> dict[str, Any]:
    values = load_evidence_inputs(context, *schemas, payload_keys=keys)
    if not values:
        raise _product_error(f"Required typed input missing; expected one of: {', '.join(schemas)}")
    return values[0]


def _papers_from(context: OperatorContext) -> list[dict[str, Any]]:
    documents = load_evidence_inputs(
        context,
        "research_paper.v1",
        payload_keys=("paper_evidence", "research_paper"),
    )
    if not documents:
        raise _product_error("Required typed input missing; expected one of: research_paper.v1")
    papers = [
        paper
        for document in documents
        for paper in [document.get("outputs", {}).get("paper")]
        if isinstance(paper, dict) and str(paper.get("parse_status") or "") != "failed"
    ]
    if not papers:
        raise _product_error("research_paper.v1 input has no parsed outputs.paper object")
    return papers


def _paper_from(context: OperatorContext) -> dict[str, Any]:
    return _papers_from(context)[0]


def _section_texts(paper: dict[str, Any]) -> list[tuple[str, str, str]]:
    values: list[tuple[str, str, str]] = []
    for section in paper.get("sections") or []:
        if not isinstance(section, dict):
            continue
        text = str(section.get("text") or "").strip()
        if text:
            values.append((str(section.get("title") or "Section"), text, str(section.get("source_anchor") or paper.get("source_ref") or "unknown")))
    return values


def _source_sentences(text: str, *, minimum_length: int) -> list[str]:
    """Split prose without treating Markdown's soft line wrapping as meaning loss."""

    unwrapped = re.sub(r"\s+", " ", str(text or "")).strip()
    return [item.strip() for item in _SENTENCE.split(unwrapped) if len(item.strip()) >= minimum_length]


def _analyze_paper_document(paper: dict[str, Any]) -> tuple[dict[str, Any], int]:
    paper = dict(paper)
    sections = _section_texts(paper)
    if not sections:
        raise _product_error("Paper/content analysis requires at least one non-empty source section")
    tokens = Counter(
        token.lower()
        for _title, text, _anchor in sections
        for token in _WORD.findall(text)
        if token.lower() not in _STOPWORDS
    )
    highlights = [
        {"section": title, "source_anchor": anchor, "excerpt": re.sub(r"\s+", " ", text)[:280]}
        for title, text, anchor in sections[:8]
    ]
    paper["analysis"] = {
        "summary": " ".join(item["excerpt"] for item in highlights[:3])[:900],
        "key_concepts": [word for word, _count in tokens.most_common(12)],
        "section_highlights": highlights,
        "evidence_ids": [item["source_anchor"] for item in highlights],
        "analysis_mode": "bounded_local_source_analysis",
    }
    return paper, len(sections)


def analyze_content(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    paper, section_count = _analyze_paper_document(_paper_from(context))
    evidence = evidence_document(
        context,
        spec,
        {"paper": paper},
        limitations=["Analysis is extractive and source-grounded; it does not independently verify paper claims."],
    )
    return {
        "evidence": evidence,
        "outcome_class": SUCCESS,
        "summary": f"Analyzed {section_count} non-empty source section(s).",
    }


def analyze_papers(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    """Analyze every frozen research-paper document as a separate typed artifact."""

    evidence_items: list[dict[str, Any]] = []
    for paper in _papers_from(context):
        analyzed, section_count = _analyze_paper_document(paper)
        evidence_items.append(
            {
                "evidence": evidence_document(
                    context,
                    spec,
                    {"paper": analyzed},
                    limitations=[
                        "Analysis is extractive and source-grounded; it does not independently verify paper claims."
                    ],
                ),
                "summary": f"Analyzed {section_count} non-empty source section(s).",
            }
        )
    return {
        "evidence_items": evidence_items,
        "limitations": [
            f"Analyzed {len(evidence_items)} frozen research-paper artifact(s) independently."
        ],
    }


def memory_update(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    final = spec.node_id == "memory_update_final"
    if final:
        schemas = (
            "scientific_report.v1",
            "artifact_review.v1",
            "claim_verdict.v1",
            "publication_bundle.v1",
            "research_final_evaluation.v1",
        )
        keys = ("source_evidence", "report_evidence", "review_evidence", "verdict_evidence")
    else:
        schemas = ("research_paper.v1",)
        keys = ("paper_evidence", "research_paper")
    documents = load_evidence_inputs(context, *schemas, payload_keys=keys)
    if not documents:
        raise _product_error(f"{spec.node_id} requires typed upstream evidence")
    changes: list[dict[str, Any]] = []
    for index, document in enumerate(documents, start=1):
        source_schema = str(document.get("schema"))
        if source_schema == "research_paper.v1":
            paper = document.get("outputs", {}).get("paper") or {}
            entity_id = str(paper.get("paper_id") or f"paper-{index:03d}")
            title = str(paper.get("title") or entity_id)
            evidence_ids = [
                str(item.get("source_anchor"))
                for item in paper.get("sections") or []
                if isinstance(item, dict) and item.get("source_anchor")
            ] or [str(paper.get("source_ref") or entity_id)]
            summary = f"Propose recording source-grounded metadata and analysis for {title}."
            path = f"knowledge/research/papers/{entity_id}.md"
            entity_type = "paper"
        else:
            entity_id = f"{source_schema.replace('.v1', '')}-{index:03d}"
            evidence_ids = [f"{source_schema}:{document.get('node_id', index)}"]
            summary = f"Propose final memory reconciliation from accepted {source_schema} evidence."
            path = f"knowledge/research/runs/{context.node_request['run_id']}/{entity_id}.md"
            entity_type = "research_result"
        changes.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "operation": "propose",
                "path": path,
                "evidence_ids": evidence_ids,
                "confidence": 1.0,
                "summary": summary,
            }
        )
    evidence = evidence_document(
        context,
        spec,
        {"changes": changes, "mutation_applied": False, "phase": "final" if final else "initial"},
        limitations=["This physical operator emits evidence-backed proposals; Solar owns approval and state mutation."],
    )
    return {
        "evidence": evidence,
        "outcome_class": SUCCESS,
        "summary": f"Produced {len(changes)} memory proposal(s) without mutating global state.",
    }


def graph_update(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    document = _first_evidence(
        context, ("research_memory_update.v1",), ("memory_evidence", "research_memory_update")
    )
    changes = document.get("outputs", {}).get("changes")
    if not isinstance(changes, list) or not changes:
        raise _product_error("Graph update requires at least one evidence-backed memory change")
    edges: list[dict[str, Any]] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        source = str(change.get("entity_id") or "").strip()
        if not source:
            continue
        for evidence_id in change.get("evidence_ids") or []:
            edges.append(
                {
                    "source": source,
                    "target": str(evidence_id),
                    "relation": "supported_by",
                    "operation": "propose",
                    "evidence_ids": [str(evidence_id)],
                }
            )
    if not edges:
        raise _product_error("Graph update found no traceable evidence IDs in memory proposals")
    evidence = evidence_document(
        context,
        spec,
        {"edges": edges, "mutation_applied": False},
        limitations=["Graph edges are proposals; Solar owns approval and graph mutation."],
    )
    return {
        "evidence": evidence,
        "outcome_class": SUCCESS,
        "summary": f"Produced {len(edges)} traceable graph edge proposal(s).",
    }


def _extract_claim_rows(context: OperatorContext, *, limit: int) -> list[dict[str, Any]]:
    papers = _papers_from(context)
    limit = max(1, min(int(limit), 50))
    cue = re.compile(r"\b(?:show|shows|demonstrat|improv|reduc|increas|achiev|outperform|result|found|find)\w*\b", re.IGNORECASE)
    anchor_counts = Counter(
        anchor
        for paper in papers
        for _title, _text, anchor in _section_texts(paper)
        if anchor
    )
    candidates_by_text: dict[str, dict[str, Any]] = {}
    paper_candidate_keys: list[list[str]] = []
    for paper in papers:
        paper_id = str(paper.get("paper_id") or "paper-unresolved")
        keys: list[str] = []
        seen_in_paper: set[str] = set()
        for _title, text, raw_anchor in _section_texts(paper):
            anchor = (
                f"{paper_id}::{raw_anchor}"
                if raw_anchor and anchor_counts[raw_anchor] > 1
                else raw_anchor
            )
            sentences = _source_sentences(text, minimum_length=30)
            selected = [
                item
                for item in sentences
                if 30 <= len(item) <= 1_000 and cue.search(item)
            ]
            for sentence in selected:
                normalized_sentence = " ".join(sentence.split()).casefold()
                existing = candidates_by_text.get(normalized_sentence)
                if existing is None:
                    existing = {
                        "text": sentence,
                        "claim_type": "result",
                        "source_anchor": anchor,
                        "testability": "testable" if re.search(r"\d|%|compared|than", sentence, re.IGNORECASE) else "partially_testable",
                        "verification_status": "unverified",
                        "evidence_ids": [anchor],
                    }
                    candidates_by_text[normalized_sentence] = existing
                elif anchor not in existing["evidence_ids"]:
                    existing["evidence_ids"].append(anchor)
                if normalized_sentence not in seen_in_paper:
                    keys.append(normalized_sentence)
                    seen_in_paper.add(normalized_sentence)
        if keys:
            paper_candidate_keys.append(keys)

    claims: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    round_index = 0
    while len(claims) < limit:
        added = False
        for keys in paper_candidate_keys:
            if round_index >= len(keys):
                continue
            key = keys[round_index]
            if key in selected_keys:
                continue
            claims.append(
                {
                    "claim_id": f"claim-{len(claims) + 1:03d}",
                    **candidates_by_text[key],
                }
            )
            selected_keys.add(key)
            added = True
            if len(claims) >= limit:
                break
        if not added and all(round_index >= len(keys) for keys in paper_candidate_keys):
            break
        round_index += 1
    if not claims:
        raise _product_error("No claim-like source sentences were found; synthetic claims were not generated")
    return claims


def extract_claims(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    claims = _extract_claim_rows(
        context,
        limit=int(context.payload.get("limit") or 12),
    )
    evidence = evidence_document(
        context,
        spec,
        {"claims": claims},
        limitations=["Claims are extracted and unverified; downstream verification is required."],
    )
    return {
        "evidence": evidence,
        "outcome_class": SUCCESS,
        "summary": f"Extracted {len(claims)} source-anchored unverified claim(s).",
    }


def select_one_testable_claim(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    """Select one validation-priority claim using disclosed stable criteria.

    The selection remains deterministic, but it is not based on testability
    alone.  A node may supply its scientific objective through the frozen task
    contract; lexical alignment to that objective becomes the first tie-break
    among testable claims, followed by retained evidence and specificity.
    """

    claims = _extract_claim_rows(context, limit=50)
    rank = {"testable": 0, "partially_testable": 1, "unknown": 2, "not_testable": 3}

    task_contract = (
        context.payload.get("task_contract")
        if isinstance(context.payload.get("task_contract"), dict)
        else {}
    )
    priority_text = " ".join(
        str(value or "")
        for value in (
            context.payload.get("priority_objective"),
            context.payload.get("topic"),
            context.payload.get("title"),
            task_contract.get("user_intent"),
        )
    )
    stopwords = {
        "about", "after", "again", "against", "among", "and", "before",
        "claim", "claims", "exactly", "from", "highest", "into", "most",
        "one", "priority", "research", "select", "selected", "that", "the",
        "then", "this", "using", "validation", "with",
    }
    priority_terms = {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", priority_text.casefold())
        if token not in stopwords
    }

    def topical_overlap(claim: dict[str, Any]) -> int:
        claim_terms = set(
            re.findall(r"[a-z0-9][a-z0-9_-]{2,}", str(claim.get("text") or "").casefold())
        )
        return len(priority_terms & claim_terms)

    def selection_key(claim: dict[str, Any]) -> tuple[int, int, int, int, str]:
        evidence_ids = [str(item) for item in claim.get("evidence_ids") or [] if str(item).strip()]
        return (
            rank.get(str(claim.get("testability") or "unknown"), 2),
            -topical_overlap(claim),
            -len(evidence_ids),
            -len(str(claim.get("text") or "")),
            str(claim.get("claim_id") or ""),
        )

    selected = min(claims, key=selection_key)
    evidence = evidence_document(
        context,
        spec,
        {
            "claims": [selected],
            "selection": {
                "selected_claim_id": str(selected["claim_id"]),
                "candidate_count": len(claims),
                "criteria": [
                    "prefer testable over partially_testable, unknown, and not_testable",
                    "prefer greater lexical alignment with the frozen validation objective",
                    "prefer more retained evidence identifiers",
                    "prefer the more specific claim text when earlier criteria tie",
                    "break remaining ties by stable claim identifier",
                ],
                "priority_objective": priority_text.strip(),
                "selected_objective_term_overlap": topical_overlap(selected),
            },
        },
        limitations=[
            "The operator selects one claim for validation by disclosed deterministic testability, "
            "objective-alignment, evidence, and specificity criteria. It does not assert universal "
            "scientific importance beyond the frozen validation objective."
        ],
    )
    return {
        "evidence": evidence,
        "outcome_class": SUCCESS,
        "summary": (
            f"Selected exactly one {selected['testability']} claim from {len(claims)} "
            "source-anchored candidate(s)."
        ),
    }


def extract_methods(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    papers = _papers_from(context)
    methods: list[dict[str, Any]] = []
    methods_by_text: dict[str, dict[str, Any]] = {}
    method_heading = re.compile(r"method|approach|experiment|implementation|procedure|setup|protocol", re.IGNORECASE)
    description_cue = re.compile(
        r"\b(?:we\s+(?:use|used|apply|applied|implement|implemented|evaluate|evaluated|measure|measured|"
        r"compare|compared|collect|collected|train|trained|run|ran)|using|implemented\s+with|evaluated\s+(?:on|using)|"
        r"measured\s+(?:with|using)|configured\s+to|dataset|benchmark\s+suite|experimental\s+setup|"
        r"(?:the|this|our)\s+(?:method|approach|procedure|implementation|protocol)\s+"
        r"(?:uses?|used|applies?|applied|implements?|implemented|evaluates?|evaluated|measures?|measured|"
        r"compares?|compared|collects?|collected|trains?|trained|runs?|ran|ingests?|ingested|preserves?|"
        r"preserved|extracts?|extracted|records?|recorded|configures?|configured))\b",
        re.IGNORECASE,
    )

    def record_method(
        *,
        name: str,
        procedure: list[str],
        anchor: str,
        extraction_basis: str,
        confidence: float,
        source_paper_id: str,
    ) -> None:
        summary = " ".join(procedure)[:500]
        normalized_summary = " ".join(summary.split()).casefold()
        existing = methods_by_text.get(normalized_summary)
        if existing is not None:
            if anchor not in existing["evidence_ids"]:
                existing["evidence_ids"].append(anchor)
            if source_paper_id not in existing["source_papers"]:
                existing["source_papers"].append(source_paper_id)
            return
        method = {
            "method_id": f"method-{len(methods) + 1:03d}",
            "name": name,
            "summary": summary,
            "procedure": procedure,
            "source_papers": [source_paper_id],
            "evidence_ids": [anchor],
            "extraction_basis": extraction_basis,
            "confidence": confidence,
        }
        methods.append(method)
        methods_by_text[normalized_summary] = method

    for paper in papers:
        source_paper_id = str(paper.get("paper_id") or "paper-unresolved")
        for title, text, anchor in _section_texts(paper):
            if not method_heading.search(title):
                continue
            procedure = _source_sentences(text, minimum_length=15)[:12]
            if not procedure:
                continue
            record_method(
                name=title,
                procedure=procedure,
                anchor=anchor,
                extraction_basis="explicit_method_heading",
                confidence=1.0,
                source_paper_id=source_paper_id,
            )
    if not methods:
        for paper in papers:
            source_paper_id = str(paper.get("paper_id") or "paper-unresolved")
            for title, text, anchor in _section_texts(paper):
                sentences = _source_sentences(text, minimum_length=20)
                grounded = [item for item in sentences if description_cue.search(item)][:8]
                if not grounded:
                    continue
                record_method(
                    name=f"Method description in {title}",
                    procedure=grounded,
                    anchor=anchor,
                    extraction_basis="method_description_without_heading",
                    confidence=0.6,
                    source_paper_id=source_paper_id,
                )
    if not methods:
        limitation = (
            "Method evidence is insufficient: no explicit method heading or source-grounded method description "
            "was found. No method was synthesized."
        )
        evidence = evidence_document(
            context,
            spec,
            {"methods": [], "method_evidence_status": "insufficient_evidence"},
            limitations=[limitation],
        )
        return {
            "evidence": evidence,
            "outcome_class": SUCCESS,
            "summary": "Recorded insufficient method evidence without inventing a method.",
        }
    inferred = any(item.get("extraction_basis") == "method_description_without_heading" for item in methods)
    limitations = ["Method steps are extractive and retain their source anchors."]
    if inferred:
        limitations.append(
            "At least one method was cautiously extracted from descriptive text without an explicit Method heading."
        )
    evidence = evidence_document(
        context,
        spec,
        {
            "methods": methods,
            "method_evidence_status": "extracted_with_inference" if inferred else "explicitly_extracted",
        },
        limitations=limitations,
    )
    return {
        "evidence": evidence,
        "outcome_class": SUCCESS,
        "summary": f"Extracted {len(methods)} source-grounded method(s).",
    }


def _claim_documents(context: OperatorContext) -> list[dict[str, Any]]:
    values = load_evidence_inputs(context, "research_claims.v1", payload_keys=("claims_evidence", "research_claims"))
    if not values:
        raise _product_error("Code/evidence mapping requires research_claims.v1 input")
    return values


def map_code_evidence(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    documents = _claim_documents(context)
    claims = [
        claim
        for document in documents
        for claim in document.get("outputs", {}).get("claims") or []
        if isinstance(claim, dict)
    ]
    if not claims:
        raise _product_error("Code/evidence mapping requires at least one claim")
    repo_raw = str(context.payload.get("repo_path") or context.payload.get("code_path") or "").strip()
    if not repo_raw:
        raise _product_error("Code/evidence mapping requires repo_path or code_path")
    repo = validate_scoped_path(repo_raw, context.read_scope, workspace_root=context.workspace_root, must_exist=True)
    paths = [repo] if repo.is_file() else sorted(path for path in repo.rglob("*") if path.is_file() and path.suffix.lower() in _CODE_SUFFIXES)
    paths = paths[:500]
    indexed: list[tuple[Path, list[str]]] = []
    for path in paths:
        try:
            if path.stat().st_size > 1_000_000:
                continue
            indexed.append((path, path.read_text(encoding="utf-8", errors="ignore").splitlines()))
        except OSError:
            continue
    mappings: list[dict[str, Any]] = []
    for index, claim in enumerate(claims, start=1):
        terms = {token.lower() for token in _WORD.findall(str(claim.get("text") or "")) if token.lower() not in _STOPWORDS}
        matches: list[tuple[int, Path, int]] = []
        for path, lines in indexed:
            for line_number, line in enumerate(lines, start=1):
                overlap = len(terms & {token.lower() for token in _WORD.findall(line)})
                if overlap >= 2:
                    matches.append((overlap, path, line_number))
        matches.sort(key=lambda item: (-item[0], str(item[1]), item[2]))
        top = matches[:5]
        files = [f"{display_path(path, context.workspace_root)}:{line_number}" for _score, path, line_number in top]
        mappings.append(
            {
                "mapping_id": f"map-{index:03d}",
                "claim_id": str(claim.get("claim_id") or f"claim-{index:03d}"),
                "repo_or_path": display_path(repo, context.workspace_root),
                "files": files,
                "execution_entrypoint": str(context.payload.get("execution_entrypoint") or ""),
                "mapping_status": "mapped" if files else "unknown",
                "relevance_label": "direct" if files and top[0][0] >= 3 else "related" if files else "unknown",
                "relevance_reason": (
                    "Source lines share multiple meaningful terms with the claim; this is relevance evidence, not proof of correctness."
                    if files
                    else "No source line met the bounded lexical-overlap threshold."
                ),
                "evidence_ids": [str(item) for item in claim.get("evidence_ids") or [str(claim.get("source_anchor") or "unresolved")]],
            }
        )
    evidence = evidence_document(
        context,
        spec,
        {"mappings": mappings, "files_scanned": len(indexed)},
        limitations=["Mappings indicate code relevance only; they do not establish claim verification."],
    )
    return {
        "evidence": evidence,
        "outcome_class": SUCCESS,
        "summary": f"Mapped {len(mappings)} claim(s) against {len(indexed)} bounded code file(s).",
    }
