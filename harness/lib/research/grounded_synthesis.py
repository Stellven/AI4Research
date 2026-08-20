"""Compile verified source packs into a grounded, topic-general report bundle.

The model authors a small synthesis plan (claims plus evidence ids). This
module owns the deterministic boundary: source-pack validation and merge,
claim-schema validation, citation binding, report artifacts, and closeout.
It never invents topic prose or sources.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from . import ids
from .evaluator import evaluate_artifacts, evaluate_final_closeout, evaluate_retrieval_closeout
from .schemas import Claim


SYNTHESIS_PLAN_SCHEMA = "solar.grounded_synthesis_plan.v2"
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{3,}|[\u4e00-\u9fff]{2,}")
_MIN_EVIDENCE_QUOTE_CHARS = 20
_MAX_EVIDENCE_QUOTE_CHARS = 2000
_EVIDENCE_STATUSES = frozenset({"sufficient", "insufficient"})
_LINK_RELATIONS = frozenset({"supports", "contradicts", "qualifies", "contextualizes"})
_RELATION_STRENGTH = {
    "supports": 1.0,
    "contradicts": 1.0,
    "qualifies": 0.75,
    "contextualizes": 0.5,
}


class GroundedSynthesisError(ValueError):
    """The requested report cannot be compiled without violating grounding."""


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise GroundedSynthesisError(f"{label}_unreadable:{path}:{exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GroundedSynthesisError(f"{label}_invalid_json:line={line_number}") from exc
        if not isinstance(row, dict):
            raise GroundedSynthesisError(f"{label}_invalid_row:line={line_number}")
        rows.append(row)
    if not rows:
        raise GroundedSynthesisError(f"{label}_empty")
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _tokens(text: str) -> set[str]:
    value = str(text or "")
    tokens = {token.lower() for token in _TOKEN_RE.findall(value)}
    # A whole Chinese clause is one regex token, so paraphrases that share a
    # meaningful phrase (for example “计算材料学”) previously appeared to have
    # zero lexical overlap. Add CJK bigrams while retaining the original token
    # set; this is deterministic and still rejects unrelated Chinese claims.
    for segment in re.findall(r"[\u4e00-\u9fff]+", value):
        tokens.update(segment[index : index + 2] for index in range(len(segment) - 1))
    return tokens


def _normalize_extended_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Normalize the richer planner wire shape into the compiler wire shape.

    Early runtime planners emitted ``publishable_claims`` plus an outline while
    the deterministic compiler consumed ``sections``.  Both shapes claim the
    same v2 schema version.  The compatibility conversion is intentionally
    lossless: it copies only model-authored claims and exact evidence links,
    preserves every declared gap, and leaves the normal compiler validators in
    authority over publication.
    """
    if isinstance(plan.get("sections"), list) and plan.get("sections"):
        return plan
    claims = plan.get("publishable_claims")
    outline = plan.get("recommended_report_outline")
    if not isinstance(claims, list) or not claims or not isinstance(outline, list) or not outline:
        return plan

    claim_by_id = {
        str(item.get("claim_id") or ""): item
        for item in claims
        if isinstance(item, dict) and str(item.get("claim_id") or "")
    }
    confidence_map = {"high": 0.90, "medium": 0.75, "low": 0.55}
    sections: list[dict[str, Any]] = []
    for index, raw_section in enumerate(outline, start=1):
        if not isinstance(raw_section, dict):
            continue
        section_claims: list[dict[str, Any]] = []
        for claim_id in raw_section.get("claim_ids") or []:
            raw_claim = claim_by_id.get(str(claim_id))
            if not raw_claim:
                continue
            raw_confidence = raw_claim.get("confidence", 0.70)
            confidence = confidence_map.get(str(raw_confidence).strip().lower(), raw_confidence)
            relations = {
                str(link.get("relation") or "")
                for link in raw_claim.get("evidence_links") or []
                if isinstance(link, dict)
            }
            uncertainty = ""
            if "contradicts" in relations or str(raw_confidence).strip().lower() == "low":
                uncertainty = "；".join(
                    str(item) for item in (raw_claim.get("rejection_criteria") or [])[:2]
                )
            section_claims.append(
                {
                    "text": str(raw_claim.get("claim") or ""),
                    "claim_type": "predictive",
                    "evidence_links": list(raw_claim.get("evidence_links") or []),
                    "confidence": confidence,
                    "uncertainty": uncertainty,
                }
            )
        if section_claims:
            sections.append(
                {
                    "section_id": str(raw_section.get("section_id") or f"section-{index}"),
                    "title": str(raw_section.get("title") or f"Section {index}"),
                    "claims": section_claims,
                }
            )

    normalized_gaps: list[dict[str, Any]] = []
    for raw_gap in plan.get("evidence_gaps") or []:
        if not isinstance(raw_gap, dict):
            normalized_gaps.append(raw_gap)
            continue
        links = raw_gap.get("related_evidence_links") or []
        normalized_gaps.append(
            {
                **raw_gap,
                "text": str(raw_gap.get("text") or raw_gap.get("description") or ""),
                "evidence_ids": list(
                    raw_gap.get("evidence_ids")
                    or [
                        str(link.get("evidence_id"))
                        for link in links
                        if isinstance(link, dict) and str(link.get("evidence_id") or "")
                    ]
                ),
            }
        )

    normalized = dict(plan)
    normalized["title"] = str(plan.get("title") or plan.get("research_question") or "Grounded report")
    normalized["sections"] = sections
    normalized["evidence_gaps"] = normalized_gaps
    # In this richer wire shape, ``publishable_claims`` is an explicit
    # declaration that a bounded subset can be published even when overall
    # topic coverage is insufficient. Preserve that upstream status verbatim;
    # this flag only permits the declared subset to render together with its
    # mandatory gaps. Canonical insufficient plans retain no-publication.
    if sections and str(plan.get("evidence_status") or "").strip().lower() == "insufficient":
        normalized["bounded_partial_coverage"] = True
    return normalized


def _extract_filename(source_id: str) -> str:
    stem = _SAFE_NAME_RE.sub("_", source_id).strip("._-")[:80] or "source"
    suffix = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:12]
    return f"{stem}-{suffix}.md"


def _load_plan(value: Path | str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        plan = json.loads(json.dumps(value))
    else:
        path = Path(value).expanduser()
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GroundedSynthesisError(f"synthesis_plan_unreadable:{path}") from exc
    if not isinstance(plan, dict):
        raise GroundedSynthesisError("synthesis_plan_not_object")
    plan = _normalize_extended_plan(plan)
    if plan.get("schema_version") != SYNTHESIS_PLAN_SCHEMA:
        raise GroundedSynthesisError("synthesis_plan_schema_invalid")
    evidence_status = str(plan.get("evidence_status") or "").strip().lower()
    if evidence_status not in _EVIDENCE_STATUSES:
        raise GroundedSynthesisError("synthesis_plan_evidence_status_invalid")
    gaps = plan.get("evidence_gaps")
    if not isinstance(gaps, list):
        raise GroundedSynthesisError("synthesis_plan_evidence_gaps_invalid")
    for index, gap in enumerate(gaps, start=1):
        if not isinstance(gap, dict):
            raise GroundedSynthesisError(f"evidence_gap_invalid:{index}")
        if not " ".join(str(gap.get("text") or gap.get("description") or "").split()):
            raise GroundedSynthesisError(f"evidence_gap_text_missing:{index}")
        if not isinstance(gap.get("evidence_ids", []), list):
            raise GroundedSynthesisError(f"evidence_gap_ids_invalid:{index}")
    if evidence_status == "insufficient":
        if not gaps:
            raise GroundedSynthesisError("insufficient_evidence_gap_missing")
        return plan
    if not isinstance(plan.get("sections"), list) or not plan["sections"]:
        raise GroundedSynthesisError("synthesis_plan_sections_missing")
    return plan


def _canonical_evidence_id(
    raw_id: Any,
    *,
    evidence_by_id: dict[str, dict[str, Any]],
    evidence_aliases: dict[str, str],
) -> str:
    value = str(raw_id or "").strip()
    evidence_id = evidence_aliases.get(value, value)
    if evidence_id not in evidence_by_id:
        raise GroundedSynthesisError(f"evidence_id_unknown:{value or '?'}")
    return evidence_id


def _validated_evidence_links(
    raw_links: Any,
    *,
    section_id: str,
    claim_text: str,
    evidence_by_id: dict[str, dict[str, Any]],
    evidence_aliases: dict[str, str],
) -> list[dict[str, Any]]:
    if not isinstance(raw_links, list) or not raw_links:
        raise GroundedSynthesisError(f"claim_evidence_links_missing:{section_id}")
    links: list[dict[str, Any]] = []
    seen_evidence: set[str] = set()
    claim_tokens = _tokens(claim_text)
    for index, raw_link in enumerate(raw_links, start=1):
        if not isinstance(raw_link, dict):
            raise GroundedSynthesisError(f"evidence_link_invalid:{section_id}:{index}")
        evidence_id = _canonical_evidence_id(
            raw_link.get("evidence_id"),
            evidence_by_id=evidence_by_id,
            evidence_aliases=evidence_aliases,
        )
        if evidence_id in seen_evidence:
            raise GroundedSynthesisError(f"evidence_link_duplicate:{section_id}:{evidence_id}")
        seen_evidence.add(evidence_id)
        relation = str(raw_link.get("relation") or "").strip().lower()
        if relation not in _LINK_RELATIONS:
            raise GroundedSynthesisError(
                f"evidence_link_relation_invalid:{section_id}:{relation or '?'}"
            )
        quote = str(raw_link.get("quote") or "").strip()
        if not quote:
            raise GroundedSynthesisError(f"evidence_quote_missing:{section_id}:{evidence_id}")
        if len(quote) < _MIN_EVIDENCE_QUOTE_CHARS:
            raise GroundedSynthesisError(
                f"evidence_quote_too_short:{section_id}:{evidence_id}:"
                f"{len(quote)}<{_MIN_EVIDENCE_QUOTE_CHARS}"
            )
        if len(quote) > _MAX_EVIDENCE_QUOTE_CHARS:
            raise GroundedSynthesisError(
                f"evidence_quote_too_long:{section_id}:{evidence_id}:"
                f"{len(quote)}>{_MAX_EVIDENCE_QUOTE_CHARS}"
            )
        evidence_text = str(evidence_by_id[evidence_id].get("content") or "")
        if quote not in evidence_text:
            raise GroundedSynthesisError(
                f"evidence_quote_not_exact:{section_id}:{evidence_id}"
            )
        quote_tokens = _tokens(quote)
        cross_script_qualifier = (
            relation in {"qualifies", "contextualizes"}
            and bool(re.search(r"[\u4e00-\u9fff]", claim_text))
            and not bool(re.search(r"[\u4e00-\u9fff]", quote))
        )
        if not claim_tokens.intersection(quote_tokens) and not cross_script_qualifier:
            raise GroundedSynthesisError(f"claim_not_grounded:{section_id}:{evidence_id}")
        links.append(
            {
                "evidence_id": evidence_id,
                "relation": relation,
                "quote": quote,
                "quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
            }
        )
    if not any(link["relation"] == "supports" for link in links):
        raise GroundedSynthesisError(f"claim_support_missing:{section_id}")
    return links


def _validated_evidence_gaps(
    raw_gaps: Any,
    *,
    evidence_by_id: dict[str, dict[str, Any]],
    evidence_aliases: dict[str, str],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for index, raw_gap in enumerate(raw_gaps or [], start=1):
        if not isinstance(raw_gap, dict):
            raise GroundedSynthesisError(f"evidence_gap_invalid:{index}")
        text = " ".join(str(raw_gap.get("text") or "").split())
        if not text:
            raise GroundedSynthesisError(f"evidence_gap_text_missing:{index}")
        raw_ids = raw_gap.get("evidence_ids", [])
        if not isinstance(raw_ids, list):
            raise GroundedSynthesisError(f"evidence_gap_ids_invalid:{index}")
        evidence_ids: list[str] = []
        for raw_id in raw_ids:
            evidence_id = _canonical_evidence_id(
                raw_id,
                evidence_by_id=evidence_by_id,
                evidence_aliases=evidence_aliases,
            )
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
        gaps.append({"text": text, "evidence_ids": evidence_ids})
    return gaps


def _source_identity(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("url") or "").strip().lower(),
        str(row.get("content_sha256") or row.get("content_hash") or "").strip(),
    )


def _resolve_nested_extract(pack: Path, source: dict[str, Any]) -> Path:
    nested = source.get("extract") if isinstance(source.get("extract"), dict) else {}
    raw_path = str(source.get("extract_path") or nested.get("path") or "").strip()
    candidates: list[Path] = []
    if raw_path:
        given = Path(raw_path)
        if given.is_absolute():
            candidates.append(given)
        else:
            candidates.extend([pack / given, pack.parents[2] / given])
            candidates.append(pack / "extracts" / given.name)
    pack_root = pack.resolve(strict=False)
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        try:
            contained = resolved.is_relative_to(pack_root)
        except (AttributeError, OSError):
            contained = False
        if contained and resolved.is_file():
            return resolved
    source_id = str(source.get("id") or source.get("source_id") or "?")
    raise GroundedSynthesisError(f"source_extract_missing:{source_id}")


def _normalize_runtime_source_pack(pack: Path, destination: Path) -> Path:
    """Convert the runtime retrieval wire shape without weakening evidence checks."""
    sources = _read_jsonl(pack / "sources.jsonl", "sources_jsonl")
    evidence = _read_jsonl(pack / "evidence.jsonl", "evidence_jsonl")
    if all(str(row.get("extract_path") or "") and str(row.get("provider") or "") for row in sources):
        return pack

    evidence_by_source: dict[str, list[dict[str, Any]]] = {}
    for row in evidence:
        evidence_by_source.setdefault(str(row.get("source_id") or ""), []).append(row)

    destination.mkdir(parents=True, exist_ok=True)
    extracts_dir = destination / "extracts"
    extracts_dir.mkdir(parents=True, exist_ok=True)
    canonical_sources: list[dict[str, Any]] = []
    source_text: dict[str, str] = {}
    for source in sources:
        source_id = str(source.get("id") or source.get("source_id") or "").strip()
        # Access-failure inventory rows with no quoted evidence are useful to
        # the planner but are not compiler sources. Their limitation remains
        # represented by the plan's evidence_gaps.
        if not source_id or not evidence_by_source.get(source_id):
            continue
        extract = _resolve_nested_extract(pack, source)
        try:
            text = extract.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise GroundedSynthesisError(f"source_extract_unreadable:{source_id}") from exc
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        nested_extract = source.get("extract") if isinstance(source.get("extract"), dict) else {}
        declared_digest = str(
            source.get("content_sha256")
            or source.get("content_hash")
            or nested_extract.get("sha256")
            or ""
        ).strip()
        if not declared_digest or declared_digest != digest:
            raise GroundedSynthesisError(f"source_extract_hash_mismatch:{source_id}")
        output_name = _extract_filename(source_id)
        shutil.copyfile(extract, extracts_dir / output_name)
        retrieval = source.get("retrieval") if isinstance(source.get("retrieval"), dict) else {}
        canonical_sources.append(
            {
                "id": source_id,
                "source_id": source_id,
                "source_type": str(source.get("source_type") or "web"),
                "title": str(source.get("title") or ""),
                "url": str(source.get("url") or ""),
                "retrieved_at": str(source.get("retrieved_at") or ""),
                "provider": str(retrieval.get("method") or "runtime_retrieval"),
                "content_sha256": digest,
                "extract_path": f"extracts/{output_name}",
            }
        )
        source_text[source_id] = text

    canonical_evidence: list[dict[str, Any]] = []
    for row in evidence:
        source_id = str(row.get("source_id") or "").strip()
        text = source_text.get(source_id)
        if text is None:
            continue
        evidence_id = str(row.get("id") or row.get("evidence_id") or "").strip()
        content = str(row.get("content") or row.get("span_text") or row.get("quote") or "")
        location = row.get("location") if isinstance(row.get("location"), dict) else {}
        start = row.get("span_start", location.get("char_start"))
        end = row.get("span_end", location.get("char_end"))
        valid_span = (
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and 0 <= start <= end <= len(text)
            and text[start:end] == content
        )
        if not valid_span:
            start = text.find(content)
            end = start + len(content) if start >= 0 else -1
        if not evidence_id or not content or start < 0 or text[start:end] != content:
            raise GroundedSynthesisError(f"evidence_span_mismatch:{evidence_id or '?'}")
        canonical_evidence.append(
            {
                "id": evidence_id,
                "evidence_id": evidence_id,
                "source_id": source_id,
                "source_type": next(
                    item["source_type"] for item in canonical_sources if item["source_id"] == source_id
                ),
                "content": content,
                "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "span_start": start,
                "span_end": end,
            }
        )

    _write_jsonl(destination / "sources.jsonl", canonical_sources)
    _write_jsonl(destination / "evidence.jsonl", canonical_evidence)
    return destination


def _merge_source_packs(source_packs: list[Path], destination: Path) -> dict[str, Any]:
    extracts = destination / "extracts"
    extracts.mkdir(parents=True, exist_ok=True)
    source_by_id: dict[str, dict[str, Any]] = {}
    source_by_identity: dict[tuple[str, str], str] = {}
    evidence_by_id: dict[str, dict[str, Any]] = {}
    evidence_aliases: dict[str, str] = {}
    input_closeouts: list[dict[str, Any]] = []

    normalization_root = Path(
        tempfile.mkdtemp(prefix=".solar-normalized-source-packs-", dir=destination.parent)
    )
    try:
        for pack_index, pack in enumerate(source_packs, start=1):
            canonical_pack = _normalize_runtime_source_pack(
                pack,
                normalization_root / f"pack-{pack_index}",
            )
            closeout = evaluate_retrieval_closeout(canonical_pack)
            input_closeouts.append(
                {
                    "pack_dir": str(pack),
                    "normalized": canonical_pack != pack,
                    **closeout,
                }
            )
            if not closeout.get("ok"):
                issues = ",".join(str(item) for item in closeout.get("issues") or [])
                raise GroundedSynthesisError(
                    f"source_pack_invalid:{pack}:{closeout.get('verdict')}:{issues}"
                )

            pack_sources = _read_jsonl(canonical_pack / "sources.jsonl", "sources_jsonl")
            pack_evidence = _read_jsonl(canonical_pack / "evidence.jsonl", "evidence_jsonl")
            source_aliases: dict[str, str] = {}

            for source in pack_sources:
                source_id = str(source.get("id") or source.get("source_id") or "").strip()
                identity = _source_identity(source)
                if not source_id:
                    raise GroundedSynthesisError("source_id_missing")
                if not all(identity):
                    raise GroundedSynthesisError(f"source_identity_incomplete:{source_id}")

                if source_id in source_by_id:
                    if _source_identity(source_by_id[source_id]) != identity:
                        raise GroundedSynthesisError(f"source_id_collision:{source_id}")
                    canonical_id = source_id
                elif identity in source_by_identity:
                    canonical_id = source_by_identity[identity]
                else:
                    canonical_id = source_id
                    source_copy = dict(source)
                    source_copy["id"] = canonical_id
                    source_copy["source_id"] = canonical_id
                    input_extract = canonical_pack / str(source.get("extract_path") or "")
                    output_name = _extract_filename(canonical_id)
                    shutil.copyfile(input_extract, extracts / output_name)
                    source_copy["extract_path"] = f"extracts/{output_name}"
                    source_by_id[canonical_id] = source_copy
                    source_by_identity[identity] = canonical_id
                source_aliases[source_id] = canonical_id

            for evidence in pack_evidence:
                old_evidence_id = str(evidence.get("id") or evidence.get("evidence_id") or "").strip()
                old_source_id = str(evidence.get("source_id") or "").strip()
                if old_source_id not in source_aliases:
                    raise GroundedSynthesisError(f"evidence_source_unknown:{old_source_id or '?'}")
                canonical_source_id = source_aliases[old_source_id]
                start = evidence.get("span_start")
                end = evidence.get("span_end")
                digest = str(evidence.get("content_hash") or "").strip()
                canonical_evidence_id = old_evidence_id
                if canonical_source_id != old_source_id:
                    canonical_evidence_id = ids.evidence_id(canonical_source_id, int(start), int(end), digest)
                evidence_copy = dict(evidence)
                evidence_copy["id"] = canonical_evidence_id
                evidence_copy["evidence_id"] = canonical_evidence_id
                evidence_copy["source_id"] = canonical_source_id
                existing = evidence_by_id.get(canonical_evidence_id)
                if existing is not None:
                    comparable = ("source_id", "content", "content_hash", "span_start", "span_end")
                    if any(existing.get(key) != evidence_copy.get(key) for key in comparable):
                        raise GroundedSynthesisError(f"evidence_id_collision:{canonical_evidence_id}")
                else:
                    evidence_by_id[canonical_evidence_id] = evidence_copy
                evidence_aliases[old_evidence_id] = canonical_evidence_id
    finally:
        shutil.rmtree(normalization_root, ignore_errors=True)

    source_rows = [source_by_id[key] for key in sorted(source_by_id)]
    evidence_rows = [evidence_by_id[key] for key in sorted(evidence_by_id)]
    _write_jsonl(destination / "sources.jsonl", source_rows)
    _write_jsonl(destination / "evidence.jsonl", evidence_rows)
    return {
        "sources": source_rows,
        "evidence": evidence_rows,
        "evidence_aliases": evidence_aliases,
        "input_closeouts": input_closeouts,
    }


def _compile_plan(
    *,
    plan: dict[str, Any],
    question: str,
    merged: dict[str, Any],
    destination: Path,
) -> dict[str, Any]:
    evidence_by_id = {
        str(row.get("id") or row.get("evidence_id")): row
        for row in merged["evidence"]
    }
    evidence_aliases = dict(merged["evidence_aliases"])
    evidence_gaps = _validated_evidence_gaps(
        plan.get("evidence_gaps"),
        evidence_by_id=evidence_by_id,
        evidence_aliases=evidence_aliases,
    )
    title = " ".join(str(plan.get("title") or question).split())
    if not title:
        raise GroundedSynthesisError("synthesis_title_missing")
    language = str(plan.get("language") or "").strip().lower()
    chinese_report = language.startswith("zh") or bool(
        re.search(r"[\u4e00-\u9fff]", f"{title} {question}")
    )
    labels = (
        {
            "mixed_evidence": "证据不一致",
            "limited_support": "有限支持",
            "uncertainty": "不确定性",
            "unverified": "尚未验证",
            "gaps_heading": "证据缺口与不确定性",
            "question": "研究问题",
            "boundary_heading": "证据边界",
            "boundary_text": "本报告仅依据下列已验证的来源摘录与证据链接；缺失的证据不会被视为支持。",
            "sources_heading": "来源",
        }
        if chinese_report
        else {
            "mixed_evidence": "MIXED EVIDENCE",
            "limited_support": "LIMITED SUPPORT",
            "uncertainty": "Uncertainty",
            "unverified": "UNVERIFIED",
            "gaps_heading": "Evidence gaps and uncertainty",
            "question": "Research question",
            "boundary_heading": "Evidence boundary",
            "boundary_text": (
                "This report is limited to the verified source extracts and evidence links "
                "listed below. It does not treat missing evidence as support."
            ),
            "sources_heading": "Sources",
        }
    )

    claim_rows: list[dict[str, Any]] = []
    link_rows: list[dict[str, Any]] = []
    section_rows: list[dict[str, Any]] = []
    section_checks: list[dict[str, Any]] = []
    ast_sections: list[dict[str, Any]] = []
    rendered_sections: list[str] = []
    seen_section_ids: set[str] = set()
    claim_counter = 1
    contradiction_count = 0
    qualified_claim_count = 0
    uncertainty_count = 0
    exact_quote_count = 0

    for section_order, raw_section in enumerate(plan["sections"], start=1):
        if not isinstance(raw_section, dict):
            raise GroundedSynthesisError(f"section_invalid:{section_order}")
        section_id = str(raw_section.get("section_id") or f"section-{section_order}").strip()
        if not _SAFE_ID_RE.fullmatch(section_id) or section_id in seen_section_ids:
            raise GroundedSynthesisError(f"section_id_invalid_or_duplicate:{section_id}")
        seen_section_ids.add(section_id)
        section_title = " ".join(str(raw_section.get("title") or section_id).split())
        raw_claims = raw_section.get("claims")
        if not isinstance(raw_claims, list) or not raw_claims:
            raise GroundedSynthesisError(f"section_claims_missing:{section_id}")

        section_path = ids.section_id(1, section_order)
        lines = [f"## {section_title}", ""]
        for raw_claim in raw_claims:
            if not isinstance(raw_claim, dict):
                raise GroundedSynthesisError(f"claim_invalid:{section_id}")
            claim_text = " ".join(str(raw_claim.get("text") or "").split())
            if not claim_text:
                raise GroundedSynthesisError(f"claim_text_missing:{section_id}")
            evidence_links = _validated_evidence_links(
                raw_claim.get("evidence_links"),
                section_id=section_id,
                claim_text=claim_text,
                evidence_by_id=evidence_by_id,
                evidence_aliases=evidence_aliases,
            )
            supporting_ids = [
                link["evidence_id"] for link in evidence_links if link["relation"] == "supports"
            ]
            contradiction_ids = [
                link["evidence_id"] for link in evidence_links if link["relation"] == "contradicts"
            ]
            qualifying_ids = [
                link["evidence_id"]
                for link in evidence_links
                if link["relation"] in {"qualifies", "contextualizes"}
            ]
            supporting_sources = {
                str(evidence_by_id[evidence_id].get("source_id") or "")
                for evidence_id in supporting_ids
            }
            uncertainty = " ".join(str(raw_claim.get("uncertainty") or "").split())
            if contradiction_ids and not uncertainty:
                raise GroundedSynthesisError(f"claim_uncertainty_missing:{section_id}")
            if contradiction_ids:
                support_rating = "weak"
                confidence_ceiling = 0.60
                claim_label = labels["mixed_evidence"]
                contradiction_count += len(contradiction_ids)
            elif qualifying_ids or len(supporting_sources) < 2:
                support_rating = "moderate"
                confidence_ceiling = 0.80
                claim_label = labels["limited_support"]
                qualified_claim_count += 1
            else:
                support_rating = "strong"
                confidence_ceiling = 0.95
                claim_label = ""
            if uncertainty:
                uncertainty_count += 1
            try:
                requested_confidence = float(raw_claim.get("confidence", confidence_ceiling))
            except (TypeError, ValueError) as exc:
                raise GroundedSynthesisError(
                    f"claim_schema_invalid:{section_id}:confidence_not_numeric"
                ) from exc
            if not 0.0 <= requested_confidence <= 1.0:
                raise GroundedSynthesisError(
                    f"claim_schema_invalid:{section_id}:confidence_out_of_range"
                )
            confidence = min(requested_confidence, confidence_ceiling)

            claim_id = ids.claim_id(claim_counter, claim_text)
            try:
                claim = Claim(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    section_path=section_path,
                    source_method=(
                        "synthesized_from_multiple"
                        if len(evidence_links) > 1
                        else "extracted_from_evidence"
                    ),
                    claim_type=str(raw_claim.get("claim_type") or "factual"),
                    support_rating=support_rating,
                    evidence_ids=supporting_ids,
                    contradiction_ids=contradiction_ids,
                    confidence=confidence,
                )
            except (TypeError, ValueError) as exc:
                raise GroundedSynthesisError(
                    f"claim_schema_invalid:{section_id}:{exc}"
                ) from exc
            claim_row = asdict(claim)
            claim_row["id"] = claim_id
            claim_row["requested_confidence"] = requested_confidence
            claim_row["uncertainty"] = uncertainty
            claim_row["supporting_source_count"] = len(supporting_sources)
            claim_rows.append(claim_row)
            for link in evidence_links:
                evidence_id = link["evidence_id"]
                link_id = ids.link_id(claim_id, evidence_id)
                link_rows.append(
                    {
                        "id": link_id,
                        "link_id": link_id,
                        "claim_id": claim_id,
                        "evidence_id": evidence_id,
                        "relation": link["relation"],
                        "link_type": link["relation"],
                        "quote": link["quote"],
                        "quote_sha256": link["quote_sha256"],
                        "strength": _RELATION_STRENGTH[link["relation"]],
                        "relevance_score": 1.0,
                    }
                )
                exact_quote_count += 1
            citations = " ".join(
                f"[cite:{link['evidence_id']}]" for link in evidence_links
            )
            label = (
                f"**{claim_label}{'：' if chinese_report else ':'}** " if claim_label else ""
            )
            uncertainty_note = (
                f" — *{labels['uncertainty']}:* {uncertainty}" if uncertainty else ""
            )
            lines.append(f"- {label}{claim_text}{uncertainty_note} {citations}")
            claim_counter += 1

        content = "\n".join(lines).strip() + "\n"
        if len(content) < 220:
            raise GroundedSynthesisError(f"section_too_thin:{section_id}:{len(content)}<220")
        section_rows.append(
            {
                "id": section_id,
                "section_id": section_id,
                "section_type": "grounded_synthesis",
                "title": section_title,
                "content": content,
                "char_count": len(content),
                "section_order": section_order,
            }
        )
        section_checks.append(
            {
                "id": f"check_{hashlib.sha256(section_id.encode()).hexdigest()[:16]}",
                "section_id": section_id,
                "check_type": "grounding",
                "score": 1.0,
                "details": "all claim links resolve to exact quoted spans in verified evidence",
                "passed": True,
            }
        )
        ast_sections.append(
            {
                "section_id": section_path,
                "db_section_id": section_id,
                "section_type": "grounded_synthesis",
                "title": section_title,
                "order": section_order,
                "target_chars": len(content),
                "actual_chars": len(content),
                "status": "final",
            }
        )
        rendered_sections.append(content.rstrip())

    run_id = f"grounded_{ids.make_id(question, *sorted(evidence_by_id))[:12]}"
    source_lines = [
        f"- [{row.get('title')}]({row.get('url')}) (`{row.get('source_type')}`)"
        for row in merged["sources"]
    ]
    gap_lines = [
        f"- **{labels['unverified']}{'：' if chinese_report else ':'}** "
        + gap["text"]
        + (
            " " + " ".join(f"[cite:{evidence_id}]" for evidence_id in gap["evidence_ids"])
            if gap["evidence_ids"]
            else ""
        )
        for gap in evidence_gaps
    ]
    gap_block = (
        [f"## {labels['gaps_heading']}", "", *gap_lines, ""]
        if gap_lines
        else []
    )
    final_text = "\n".join(
        [
            f"# {title}",
            "",
            f"**{labels['question']}{'：' if chinese_report else ':'}** {question}",
            "",
            *rendered_sections,
            "",
            *gap_block,
            f"## {labels['boundary_heading']}",
            "",
            labels["boundary_text"],
            "",
            f"## {labels['sources_heading']}",
            "",
            *source_lines,
            "",
        ]
    )

    _write_jsonl(destination / "claims.jsonl", claim_rows)
    _write_jsonl(destination / "claim_evidence.jsonl", link_rows)
    _write_jsonl(destination / "sections.jsonl", section_rows)
    _write_jsonl(destination / "section_checks.jsonl", section_checks)
    _write_json(destination / "evidence_gaps.json", evidence_gaps)
    (destination / "final.md").write_text(final_text, encoding="utf-8")
    _write_json(destination / "synthesis_plan.json", plan)
    _write_json(
        destination / "report_ast.json",
        {
            "schema_version": "solar.report_ast.v1",
            "ast_id": ids.ast_id(run_id),
            "run_id": run_id,
            "title": title,
            "target_chars": len(final_text),
            "actual_chars": len(final_text),
            "depth_tier": "standard",
            "status": "completed",
            "target_chapters": 1,
            "target_sections": len(ast_sections),
            "chapters": [
                {
                    "chapter_id": ids.chapter_id(1),
                    "title": "Grounded Synthesis",
                    "order": 1,
                    "status": "final",
                    "sections": ast_sections,
                }
            ],
        },
    )
    _write_json(destination / "final.bibliography.json", merged["sources"])
    _write_json(
        destination / "research_eval.json",
        {
            "schema_version": "solar.research_eval.v1",
            "run_id": run_id,
            "status": "passed",
            "source_count": len(merged["sources"]),
            "evidence_count": len(merged["evidence"]),
            "claim_count": len(claim_rows),
            "claim_evidence_count": len(link_rows),
            "section_count": len(section_rows),
            "check_count": len(section_checks),
            "checks_passed": len(section_checks),
            "unsupported_claims": 0,
            "total_key_claims": len(claim_rows),
            "span_matches": exact_quote_count,
            "total_spans": len(link_rows),
            "unsupported_rate": 0.0,
            "citation_accuracy": 1.0,
            "citation_accuracy_definition": "exact_quote_membership_in_verified_evidence",
            "exact_quote_count": exact_quote_count,
            "contradiction_count": contradiction_count,
            "qualified_claim_count": qualified_claim_count,
            "uncertainty_count": uncertainty_count,
            "evidence_gap_count": len(evidence_gaps),
            "output_dir": ".",
            "final_md": "final.md",
            "research_profile": str(plan.get("research_profile") or "general"),
        },
    )
    return {
        "run_id": run_id,
        "source_count": len(merged["sources"]),
        "evidence_count": len(merged["evidence"]),
        "claim_count": len(claim_rows),
        "section_count": len(section_rows),
        "contradiction_count": contradiction_count,
        "evidence_gap_count": len(evidence_gaps),
    }


def compile_grounded_report(
    *,
    source_packs: Iterable[Path | str],
    synthesis_plan: Path | str | dict[str, Any],
    output_dir: Path | str,
    question: str,
) -> dict[str, Any]:
    """Compile and publish one report only after deterministic preflight passes."""
    normalized_question = " ".join(str(question or "").split())
    if not normalized_question:
        raise GroundedSynthesisError("research_question_missing")
    packs = [Path(path).expanduser().resolve(strict=False) for path in source_packs]
    if not packs:
        raise GroundedSynthesisError("source_packs_missing")
    if any(not pack.is_dir() for pack in packs):
        raise GroundedSynthesisError("source_pack_directory_missing")

    root = Path(output_dir).expanduser().resolve(strict=False)
    if root.exists() and not root.is_dir():
        raise GroundedSynthesisError(f"output_dir_not_directory:{root}")
    if root.exists() and any(root.iterdir()):
        raise GroundedSynthesisError(f"output_dir_not_empty:{root}")
    for pack in packs:
        if root == pack or root.is_relative_to(pack) or pack.is_relative_to(root):
            raise GroundedSynthesisError(f"output_overlaps_source_pack:{pack}")

    plan = _load_plan(synthesis_plan)
    if (
        str(plan.get("evidence_status") or "").strip().lower() == "insufficient"
        and not plan.get("bounded_partial_coverage")
    ):
        gaps = plan.get("evidence_gaps") or []
        first_gap = " ".join(str((gaps[0] or {}).get("text") or "").split()) if gaps else ""
        if not first_gap:
            raise GroundedSynthesisError("insufficient_evidence_gap_missing")
        raise GroundedSynthesisError(f"insufficient_evidence:{first_gap}")
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.grounded-", dir=root.parent))
    published = False
    try:
        merged = _merge_source_packs(packs, staging)
        retrieval_preflight = evaluate_retrieval_closeout(staging)
        if not retrieval_preflight.get("ok"):
            raise GroundedSynthesisError(
                f"merged_source_pack_invalid:{retrieval_preflight.get('verdict')}"
            )
        metrics = _compile_plan(
            plan=plan,
            question=normalized_question,
            merged=merged,
            destination=staging,
        )
        artifact_preflight = evaluate_artifacts(
            staging / "research_eval.json",
            strict_profile=True,
        )
        if not artifact_preflight.get("ok"):
            issues = ",".join(str(item) for item in artifact_preflight.get("errors") or [])
            raise GroundedSynthesisError(f"report_artifact_preflight_failed:{issues}")
        final_preflight = evaluate_final_closeout(staging, strict=True)
        if not final_preflight.get("ok"):
            issues = ",".join(str(item) for item in final_preflight.get("issues") or [])
            raise GroundedSynthesisError(f"report_final_preflight_failed:{issues}")

        if root.exists():
            root.rmdir()
        os.replace(staging, root)
        published = True
        try:
            retrieval_closeout = evaluate_retrieval_closeout(root)
            final_closeout = evaluate_final_closeout(root, strict=True, persist=True)
            if not retrieval_closeout.get("ok"):
                raise GroundedSynthesisError(
                    f"published_retrieval_closeout_failed:{retrieval_closeout.get('verdict')}"
                )
            if not final_closeout.get("ok"):
                issues = ",".join(str(item) for item in final_closeout.get("issues") or [])
                raise GroundedSynthesisError(f"published_final_closeout_failed:{issues}")
        except Exception:
            if root.exists():
                shutil.rmtree(root)
            published = False
            raise
        return {
            "ok": True,
            "output_dir": str(root),
            **metrics,
            "retrieval_closeout": retrieval_closeout,
            "final_closeout": final_closeout,
            "input_closeouts": merged["input_closeouts"],
        }
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)
