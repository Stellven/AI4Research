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
            source_channels = [str(value.get("source") or "injected_provider")]
        candidates.append(
            {
                **value,
                "candidate_id": str(value.get("candidate_id") or value.get("paperId") or f"candidate-{index:03d}"),
                "title": title,
                "source_channels": source_channels,
                "ranking_score": float(value.get("ranking_score") or 0.0),
                "ranking_rationale": str(value.get("ranking_rationale") or "Returned by the bounded discovery provider."),
                "dedup_status": str(value.get("dedup_status") or "unknown"),
                "fetch_status": str(value.get("fetch_status") or "not_requested"),
            }
        )
    return candidates


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
    backend = context.services.get("discover_literature") or discover_literature
    try:
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
        )
    except Exception as exc:
        evidence = evidence_document(
            context,
            spec,
            {"query": query or "unresolved", "candidates": [], "mode": mode},
            status="inconclusive",
            limitations=[f"Discovery provider failed: {type(exc).__name__}: {exc}"],
        )
        return {
            "evidence": evidence,
            "outcome_class": PROVIDER_ENVIRONMENT_FAILURE,
            "summary": "Literature provider failed before candidates were returned.",
            "error": str(exc),
        }
    candidates = _normalized_candidates(raw.get("candidates"))
    status = str(raw.get("status") or ("completed" if candidates else "inconclusive"))
    outputs = {
        key: raw[key]
        for key in ("query", "mode", "limit", "anchors", "negative_ids", "venue", "year", "source_fan_in", "source_provider_boundary")
        if raw.get(key) not in (None, "", [])
    }
    outputs["query"] = str(outputs.get("query") or query or "unresolved")
    outputs["candidates"] = candidates
    evidence = evidence_document(
        context,
        spec,
        outputs,
        status=status if status in {"completed", "failed", "inconclusive"} else "inconclusive",
        limitations=list(raw.get("limitations") or []),
        artifacts=list(raw.get("artifacts") or []),
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
        source, context.read_scope, workspace_root=context.workspace_root, must_exist=True
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


def _first_evidence(context: OperatorContext, schemas: tuple[str, ...], keys: tuple[str, ...]) -> dict[str, Any]:
    values = load_evidence_inputs(context, *schemas, payload_keys=keys)
    if not values:
        raise _product_error(f"Required typed input missing; expected one of: {', '.join(schemas)}")
    return values[0]


def _paper_from(context: OperatorContext) -> dict[str, Any]:
    document = _first_evidence(context, ("research_paper.v1",), ("paper_evidence", "research_paper"))
    paper = document.get("outputs", {}).get("paper")
    if not isinstance(paper, dict):
        raise _product_error("research_paper.v1 input has no outputs.paper object")
    return paper


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


def analyze_content(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    paper = dict(_paper_from(context))
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
    evidence = evidence_document(
        context,
        spec,
        {"paper": paper},
        limitations=["Analysis is extractive and source-grounded; it does not independently verify paper claims."],
    )
    return {
        "evidence": evidence,
        "outcome_class": SUCCESS,
        "summary": f"Analyzed {len(sections)} non-empty source section(s).",
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


def extract_claims(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    paper = _paper_from(context)
    claims: list[dict[str, Any]] = []
    claims_by_text: dict[str, dict[str, Any]] = {}
    limit = max(1, min(int(context.payload.get("limit") or 12), 50))
    cue = re.compile(r"\b(?:show|shows|demonstrat|improv|reduc|increas|achiev|outperform|result|found|find)\w*\b", re.IGNORECASE)
    for _title, text, anchor in _section_texts(paper):
        sentences = _source_sentences(text, minimum_length=30)
        selected = [item for item in sentences if len(item) >= 30 and cue.search(item)]
        for sentence in selected:
            normalized_sentence = " ".join(sentence.split()).casefold()
            existing = claims_by_text.get(normalized_sentence)
            if existing is not None:
                if anchor not in existing["evidence_ids"]:
                    existing["evidence_ids"].append(anchor)
                continue
            claim = {
                "claim_id": f"claim-{len(claims) + 1:03d}",
                "text": sentence,
                "claim_type": "result",
                "source_anchor": anchor,
                "testability": "testable" if re.search(r"\d|%|compared|than", sentence, re.IGNORECASE) else "partially_testable",
                "verification_status": "unverified",
                "evidence_ids": [anchor],
            }
            claims.append(claim)
            claims_by_text[normalized_sentence] = claim
            if len(claims) >= limit:
                break
        if len(claims) >= limit:
            break
    if not claims:
        raise _product_error("No claim-like source sentences were found; synthetic claims were not generated")
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


def extract_methods(context: OperatorContext, spec: OperatorSpec) -> dict[str, Any]:
    paper = _paper_from(context)
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
    ) -> None:
        summary = " ".join(procedure)[:500]
        normalized_summary = " ".join(summary.split()).casefold()
        existing = methods_by_text.get(normalized_summary)
        if existing is not None:
            if anchor not in existing["evidence_ids"]:
                existing["evidence_ids"].append(anchor)
            return
        method = {
            "method_id": f"method-{len(methods) + 1:03d}",
            "name": name,
            "summary": summary,
            "procedure": procedure,
            "source_papers": [str(paper.get("paper_id") or "paper-unresolved")],
            "evidence_ids": [anchor],
            "extraction_basis": extraction_basis,
            "confidence": confidence,
        }
        methods.append(method)
        methods_by_text[normalized_summary] = method

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
        )
    if not methods:
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
