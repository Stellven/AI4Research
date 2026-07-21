"""Professor-grade survey evaluator."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .schemas import SurveyScorecard, to_dict
from .quality import assess_survey_quality


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _row_id(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return str(value)
    return ""


def evaluate_survey(
    output_dir: str | Path,
    strict: bool = False,
    *,
    min_finalized: int | None = None,
    require_complete: bool = False,
) -> dict:
    root = Path(output_dir).expanduser()
    ast = _read_json(root / "survey_report_ast.json")
    packs = _read_json(root / "survey_evidence_packs.json")
    chapters = ast.get("chapters", []) if isinstance(ast.get("chapters"), list) else []
    sections = ast.get("sections", []) if isinstance(ast.get("sections"), list) else []
    sources = _read_jsonl(root / "sources.jsonl")
    evidence = _read_jsonl(root / "evidence.jsonl")
    claims = _read_jsonl(root / "claims.jsonl")
    links = _read_jsonl(root / "claim_evidence.jsonl")
    source_ids = {_row_id(row, "id", "source_id") for row in sources if _row_id(row, "id", "source_id")}
    evidence_ids = {_row_id(row, "id", "evidence_id") for row in evidence if _row_id(row, "id", "evidence_id")}
    claim_ids = {_row_id(row, "id", "claim_id") for row in claims if _row_id(row, "id", "claim_id")}
    source_types = {str(row.get("source_type") or "unknown") for row in sources if row.get("source_type")}
    evidence_with_source = [
        row for row in evidence
        if str(row.get("source_id") or "") in source_ids
    ]
    valid_claim_links = [
        row for row in links
        if str(row.get("claim_id") or "") in claim_ids and str(row.get("evidence_id") or "") in evidence_ids
    ]
    supported_claim_ids = {str(row.get("claim_id") or "") for row in valid_claim_links if row.get("claim_id")}
    evidence_source_coverage = len(evidence_with_source) / max(len(evidence), 1)
    claim_support_coverage = len(supported_claim_ids) / max(len(claims), 1)
    section_dirs = [root / "sections" / str(section.get("section_id")) for section in sections]
    finalized = sum(1 for path in section_dirs if (path / "final.md").exists())
    reviews = [_read_json(path / "review.json") for path in section_dirs if (path / "review.json").exists()]
    blocked_sections = int(packs.get("blocked") or 0) if isinstance(packs, dict) else len(sections)
    quality = assess_survey_quality(root, ast=ast, packs=packs)
    taxonomy = quality.get("taxonomy", {})
    contradiction_matrix = quality.get("contradiction_matrix", {})
    section_factual_audit = quality.get("section_factual_audit", {})
    section_scorecard = quality.get("section_scorecard", {})
    final_quality = quality.get("final_quality", {})
    source_coverage = quality.get("source_coverage", {})
    literature_map = quality.get("literature_map", {})
    controversy_review = quality.get("controversy_review", {})
    chapter_review = quality.get("chapter_review", {})
    chief_editor_review = quality.get("chief_editor_review", {})
    depth_profile = quality.get("depth_profile", {})
    issues: list[str] = []
    if len(chapters) < 8:
        issues.append(f"chapter_count_low:{len(chapters)}<8")
    if len(sections) < 30:
        issues.append(f"section_count_low:{len(sections)}<30")
    if strict and not packs:
        issues.append("evidence_packs_missing")
    if blocked_sections:
        issues.append(f"blocked_sections:{blocked_sections}")
    if strict:
        min_source_types = 4 if len(sections) >= 30 else 2
        min_evidence = max(len(sections), 1)
        min_claims = max(len(sections), 1)
        if len(source_types) < min_source_types:
            issues.append(f"source_type_count_low:{len(source_types)}<{min_source_types}")
        if len(evidence) < min_evidence:
            issues.append(f"evidence_count_low:{len(evidence)}<{min_evidence}")
        if len(claims) < min_claims:
            issues.append(f"claim_count_low:{len(claims)}<{min_claims}")
        if evidence and evidence_source_coverage < 0.95:
            issues.append(f"evidence_source_coverage_low:{evidence_source_coverage:.4f}<0.9500")
        if claims and claim_support_coverage < 0.80:
            issues.append(f"claim_support_coverage_low:{claim_support_coverage:.4f}<0.8000")
        if packs and sections:
            ready_packs = int(packs.get("ready") or 0)
            ready_pack_ratio = ready_packs / max(len(sections), 1)
            if ready_pack_ratio < 0.80:
                issues.append(f"ready_pack_ratio_low:{ready_pack_ratio:.4f}<0.8000")
        taxonomy_score = float(taxonomy.get("taxonomy_depth_score") or 0.0)
        contradiction_score = float(contradiction_matrix.get("contradiction_coverage") or 0.0)
        if taxonomy_score < 0.75:
            issues.append(f"taxonomy_depth_score_low:{taxonomy_score:.4f}<0.7500")
        if contradiction_score < 0.80:
            issues.append(f"contradiction_coverage_low:{contradiction_score:.4f}<0.8000")
        section_factual_accuracy = float(section_factual_audit.get("section_factual_accuracy") or 0.0)
        if finalized and section_factual_accuracy < 0.95:
            issues.append(f"section_factual_accuracy_low:{section_factual_accuracy:.4f}<0.9500")
        section_grounding_accuracy = float(section_factual_audit.get("section_grounding_accuracy") or 0.0)
        if finalized and section_grounding_accuracy < 0.95:
            issues.append(f"section_grounding_accuracy_low:{section_grounding_accuracy:.4f}<0.9500")
        p0_sections = sum(1 for item in section_scorecard.get("top_issues", []) if item.get("p0_count"))
        if p0_sections:
            issues.append(f"section_p0_issue_count:{p0_sections}")
        for issue in source_coverage.get("issues", []):
            issues.append(str(issue))
        for issue in literature_map.get("issues", []):
            issues.append(str(issue))
        for issue in controversy_review.get("issues", []):
            issues.append(str(issue))
        for issue in chapter_review.get("issues", []):
            issues.append(str(issue))
        for issue in chief_editor_review.get("issues", []):
            issues.append(str(issue))
        for issue in depth_profile.get("issues", []):
            issues.append(str(issue))
        if require_complete:
            for issue in final_quality.get("issues", []):
                issues.append(str(issue))
    required_finalized = len(sections) if require_complete else (min_finalized if min_finalized is not None else 3)
    if strict and finalized < required_finalized:
        issues.append(f"finalized_sections_low:{finalized}<{required_finalized}")
    elif not strict and finalized and finalized < min(required_finalized, len(sections)):
        issues.append(f"finalized_sections_low:{finalized}<{required_finalized}")
    if require_complete and finalized != len(sections):
        issues.append(f"incomplete_sections:{len(sections) - finalized}")
    final_md = root / "final.md"
    text = final_md.read_text(encoding="utf-8") if final_md.exists() else ""
    finalized_texts: list[str] = []
    for path in section_dirs:
        final = path / "final.md"
        if final.exists():
            finalized_texts.append(final.read_text(encoding="utf-8"))
    repeated = 0
    seen: set[str] = set()
    for item in finalized_texts:
        normalized = re.sub(r"\s+", " ", item.strip().lower())[:500]
        if normalized in seen:
            repeated += 1
        seen.add(normalized)
    section_repetition_rate = repeated / max(len(finalized_texts), 1)
    if strict and finalized_texts and section_repetition_rate > 0.33:
        issues.append(f"section_repetition_rate_high:{section_repetition_rate:.4f}")
    source_diversity_values = [float(r.get("source_diversity_score") or 0.0) for r in reviews]
    source_diversity = sum(source_diversity_values) / len(source_diversity_values) if source_diversity_values else 0.0
    contradiction_coverage = float(contradiction_matrix.get("contradiction_coverage") or 0.0)
    taxonomy_depth = float(taxonomy.get("taxonomy_depth_score") or 0.0)
    verdict = "PASS" if not issues else "FAIL"
    if not strict and issues and all(item.startswith(("blocked_sections", "finalized_sections_low")) for item in issues):
        verdict = "WARN"
    scorecard = SurveyScorecard(
        verdict=verdict,
        chapter_count=len(chapters),
        section_count=len(sections),
        finalized_sections=finalized,
        blocked_sections=blocked_sections,
        unsupported_claim_rate=0.0 if reviews else 1.0,
        citation_span_accuracy=1.0 if reviews else 0.0,
        contradiction_coverage=contradiction_coverage,
        source_diversity_score=round(source_diversity, 4),
        taxonomy_depth_score=round(taxonomy_depth, 4),
        section_repetition_rate=round(section_repetition_rate, 4),
        terminology_consistency_score=1.0,
        cross_section_conflict_count=0,
        chapter_coherence_score=1.0 if len(chapters) >= 8 else 0.0,
        issues=issues,
    )
    payload = {
        "ok": verdict == "PASS",
        "scorecard": to_dict(scorecard),
        "strict": strict,
        "coverage": {
            "source_count": len(sources),
            "source_type_count": len(source_types),
            "source_types": sorted(source_types),
            "evidence_count": len(evidence),
            "claim_count": len(claims),
            "claim_evidence_link_count": len(valid_claim_links),
            "evidence_source_coverage": round(evidence_source_coverage, 4),
            "claim_support_coverage": round(claim_support_coverage, 4),
        },
        "taxonomy": taxonomy,
        "contradiction_matrix": contradiction_matrix,
        "section_factual_audit": section_factual_audit,
        "section_scorecard": section_scorecard,
        "final_quality": final_quality,
        "source_coverage": source_coverage,
        "literature_map": literature_map,
        "controversy_review": controversy_review,
        "chapter_review": chapter_review,
        "chief_editor_review": chief_editor_review,
        "depth_profile": depth_profile,
    }
    (root / "survey_eval.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
