"""Contradiction matrix gate — O3 implementation.

S03 N5 implementation per S02 contradiction-matrix-arch.md.

Pure deterministic functions: build a ``ContradictionMatrix`` from an
evidence pack + claim-evidence rows, check synthesis references, and detect
decorative matrices.  No external I/O, no LLM calls, no randomness.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..schemas import ClaimEvidenceLink, ContradictionMatrix
from . import register_gate
from .config_defaults import CLAIM_GRANULARITY


@dataclass
class MissingRef:
    """A chapter whose synthesis text does not reference any matrix claim."""

    chapter_id: str
    total_claims_in_matrix: int


@dataclass
class SynthesisReferenceReport:
    """Output of ``check_synthesis_references``."""

    unreferenced_chapters: list[str]
    decorative_warning: bool
    per_claim_reference_count: dict[str, int]


def _make_link(row: dict[str, Any], source_type_map: dict[str, str]) -> ClaimEvidenceLink:
    return ClaimEvidenceLink(
        evidence_id=str(row.get("evidence_id", "")),
        source_id=str(row.get("source_id", "")),
        source_type=source_type_map.get(str(row.get("source_id", "")), "unknown"),
        relation_strength=str(row.get("relation_strength", "weak")),
    )


def build_contradiction_matrix(
    evidence_pack: dict[str, Any],
    claim_evidence_rows: list[dict[str, Any]],
    *,
    claim_texts: dict[str, str] | None = None,
    source_type_map: dict[str, str] | None = None,
    chapter_map: dict[str, str] | None = None,
) -> list[ContradictionMatrix]:
    """Build contradiction matrix rows from an evidence pack and claim-evidence links.

    Parameters
    ----------
    evidence_pack:
        A serialised ``EvidencePack`` dict (must contain ``claim_ids``,
        ``contradiction_slots``, ``section_id``).
    claim_evidence_rows:
        Rows from ``claim_evidence.jsonl``; each must have ``claim_id``,
        ``evidence_id``, ``source_id``, ``relation_type``.
    claim_texts:
        Optional mapping ``claim_id → claim_text`` (from ``claims.jsonl``).
    source_type_map:
        Optional mapping ``source_id → source_type`` (from ``sources.jsonl``).
    chapter_map:
        Optional mapping ``section_id → chapter_id`` for chapter assignment.
    """
    _ = CLAIM_GRANULARITY  # consumed for dual-indexing validation elsewhere

    claim_texts = claim_texts or {}
    source_type_map = source_type_map or {}
    chapter_map = chapter_map or {}

    pack_claim_ids: list[str] = [
        str(c) for c in (evidence_pack.get("claim_ids") or [])
    ]
    section_id = str(evidence_pack.get("section_id", ""))

    # Group claim_evidence rows by claim_id, then by relation_type
    by_claim: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in claim_evidence_rows:
        cid = str(row.get("claim_id", ""))
        if cid not in pack_claim_ids:
            continue
        rt = str(row.get("relation_type", "uncertain"))
        by_claim.setdefault(cid, {}).setdefault(rt, []).append(row)

    rows: list[ContradictionMatrix] = []
    for cid in pack_claim_ids:
        groups = by_claim.get(cid, {})
        supporting = [_make_link(r, source_type_map) for r in groups.get("supporting", [])]
        contradicting = [_make_link(r, source_type_map) for r in groups.get("contradicting", [])]
        uncertain = [_make_link(r, source_type_map) for r in groups.get("uncertain", [])]
        ch_id = chapter_map.get(section_id, "")
        rows.append(
            ContradictionMatrix(
                claim_id=cid,
                claim_text=claim_texts.get(cid, ""),
                supporting_evidence=supporting,
                contradicting_evidence=contradicting,
                uncertain_evidence=uncertain,
                chapter_ids=[ch_id] if ch_id else [],
                synthesis_referenced=False,
            )
        )

    return rows


def check_synthesis_references(
    matrix_rows: list[ContradictionMatrix],
    chapter_syntheses: list[dict[str, Any]],
) -> SynthesisReferenceReport:
    """Scan chapter synthesis text for claim_id references.

    References are detected via inline tags ``[claim:<claim_id>]`` or
    plain ``claim_id`` strings in the synthesis text.

    Parameters
    ----------
    matrix_rows:
        The matrix rows produced by ``build_contradiction_matrix``.
    chapter_syntheses:
        List of dicts with ``chapter_id`` and ``synthesis_text`` keys.
    """
    claim_ids = {row.claim_id for row in matrix_rows}
    per_claim_count: dict[str, int] = {cid: 0 for cid in claim_ids}

    referenced_chapters: set[str] = set()
    for ch in chapter_syntheses:
        ch_id = str(ch.get("chapter_id", ""))
        text = str(ch.get("synthesis_text", ""))
        found = False
        for cid in claim_ids:
            if re.search(rf"\b{re.escape(cid)}\b", text) or f"[claim:{cid}]" in text:
                per_claim_count[cid] += 1
                found = True
        if found:
            referenced_chapters.add(ch_id)

    all_chapter_ids = [str(ch.get("chapter_id", "")) for ch in chapter_syntheses]
    unreferenced = [cid for cid in all_chapter_ids if cid and cid not in referenced_chapters]
    total_refs = sum(per_claim_count.values())
    decorative = total_refs == 0 and len(matrix_rows) > 0

    report = SynthesisReferenceReport(
        unreferenced_chapters=unreferenced,
        decorative_warning=decorative,
        per_claim_reference_count=per_claim_count,
    )

    # Update synthesis_referenced flag on matrix rows
    for row in matrix_rows:
        row.synthesis_referenced = per_claim_count.get(row.claim_id, 0) > 0

    return report


def detect_decorative_matrix(matrix_rows: list[ContradictionMatrix]) -> bool:
    """Return *True* when every matrix row has ``synthesis_referenced == False``.

    A decorative matrix exists in the report but is never cited in any
    chapter synthesis — the matrix is window-dressing, not integrated.
    """
    if not matrix_rows:
        return False
    return all(not row.synthesis_referenced for row in matrix_rows)


@register_gate("controversy")
def controversy_gate(
    evidence_pack: dict[str, Any],
    claim_evidence_rows: list[dict[str, Any]],
    *,
    claim_texts: dict[str, str] | None = None,
    source_type_map: dict[str, str] | None = None,
    chapter_map: dict[str, str] | None = None,
    chapter_syntheses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Gate entry point registered in the plugin registry.

    Builds the contradiction matrix, checks synthesis references, and
    returns a verdict dict with the matrix rows and reference report.
    """
    matrix_rows = build_contradiction_matrix(
        evidence_pack,
        claim_evidence_rows,
        claim_texts=claim_texts,
        source_type_map=source_type_map,
        chapter_map=chapter_map,
    )

    ref_report: SynthesisReferenceReport | None = None
    if chapter_syntheses is not None:
        ref_report = check_synthesis_references(matrix_rows, chapter_syntheses)

    decorative = detect_decorative_matrix(matrix_rows)

    verdict = "pass"
    reasons: list[str] = []

    if not matrix_rows:
        verdict = "warn"
        reasons.append("empty_matrix")
    elif decorative:
        verdict = "warn"
        reasons.append("decorative_matrix_warning")

    if ref_report and ref_report.unreferenced_chapters:
        if verdict == "pass":
            verdict = "warn"
        reasons.append(
            "unreferenced_chapters:" + ",".join(ref_report.unreferenced_chapters)
        )

    return {
        "verdict": verdict,
        "verdict_reasons": reasons,
        "matrix_row_count": len(matrix_rows),
        "decorative": decorative,
        "rows": [
            {
                "claim_id": r.claim_id,
                "synthesis_referenced": r.synthesis_referenced,
                "supporting_count": len(r.supporting_evidence),
                "contradicting_count": len(r.contradicting_evidence),
                "uncertain_count": len(r.uncertain_evidence),
            }
            for r in matrix_rows
        ],
    }
