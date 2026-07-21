"""Deterministic verifier and quality scoring helpers for chapterized reports."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


FORBIDDEN_PUBLIC_FIELD_RE = re.compile(
    r"\b(video_id|chapter_id|evidence_pack_id|transcript_status|backend|token_count)\b",
    re.I,
)
CLAIM_SPLIT_RE = re.compile(r"[。！？!?]\s*|\n+-\s+")
VIDEO_REF_RE = re.compile(r"\bV\d{3}\b")
ACTION_INSIGHT_RE = re.compile(r"(建议|应当|可以|下一步|观察|优先|风险)")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _evidence_refs(evidence_pack: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("must_use_evidence_ids", "optional_evidence_ids"):
        refs.extend(_text(item) for item in evidence_pack.get(key) or [] if _text(item))
    for key in ("core_evidence", "support_evidence", "selected_videos"):
        for item in evidence_pack.get(key) or []:
            if not isinstance(item, dict):
                continue
            refs.extend(
                _text(item.get(ref_key))
                for ref_key in ("evidence_id", "video_ref", "ref")
                if _text(item.get(ref_key))
            )
    seen: set[str] = set()
    return [ref for ref in refs if not (ref in seen or seen.add(ref))]


def _claim_sentences(markdown: str) -> list[str]:
    claims: list[str] = []
    for part in CLAIM_SPLIT_RE.split(markdown):
        sentence = part.strip()
        if len(sentence) < 18:
            continue
        if sentence.startswith("#"):
            continue
        claims.append(sentence)
    return claims


def run_chapter_verifier(
    chapter_job: dict[str, Any],
    markdown: str,
    evidence_pack: dict[str, Any],
    proof_bundle: dict[str, Any] | None = None,
    *,
    grounded_claim_target: float = 0.9,
) -> dict[str, Any]:
    """Verify one chapter without inventing evidence or replacing model review."""
    text = _text(markdown)
    chapter_id = _text(chapter_job.get("chapter_id") or evidence_pack.get("chapter_id") or "chapter")
    refs = _evidence_refs(evidence_pack)
    claims = _claim_sentences(text)
    referenced = [ref for ref in refs if ref and ref in text]
    claims_with_refs = []
    for claim in claims:
        if any(ref in claim for ref in refs) or VIDEO_REF_RE.search(claim):
            claims_with_refs.append(claim)
            continue
        # Actionable follow-ups can inherit the chapter's cited evidence context,
        # but only after the chapter has cited at least one supplied reference.
        if referenced and ACTION_INSIGHT_RE.search(claim):
            claims_with_refs.append(claim)
    grounded_claim_ratio = 1.0 if not claims else len(claims_with_refs) / len(claims)
    proof = proof_bundle or {}
    deep_required = bool(chapter_job.get("deep_writer_required") or (evidence_pack.get("chapter") or {}).get("deep_writer_required"))
    has_deep_proof = bool(proof.get("deep_proof_path") or proof.get("deep_research_state_proof") or proof.get("deep_writer_proof"))
    checks = {
        "has_clear_thesis": bool(re.search(r"(判断|结论|认为|说明|显示|意味着)", text)) and len(text) >= 80,
        "uses_required_evidence": bool(referenced),
        "grounded_claim_ratio": round(grounded_claim_ratio, 4),
        "has_counter_evidence": bool(evidence_pack.get("counter_evidence")) or "证据不足" in text or "不确定" in text,
        "has_actionable_insight": bool(re.search(r"(建议|应当|可以|下一步|观察|优先|风险)", text)),
        "no_internal_field_leak": not FORBIDDEN_PUBLIC_FIELD_RE.search(text),
        "no_unsupported_claim": grounded_claim_ratio >= grounded_claim_target,
        "not_video_by_video_summary": len(re.findall(r"(^|\n)\s*[-*]?\s*V\d{3}", text)) <= max(2, len(claims) // 2),
        "deep_proof_present_if_required": (not deep_required) or has_deep_proof,
    }
    repair_reasons = [key for key, value in checks.items() if value is False]
    if checks["grounded_claim_ratio"] < grounded_claim_target:
        repair_reasons.append("grounded_claim_ratio_below_target")
    status = "passed" if not repair_reasons else "repair_needed"
    if not checks["no_internal_field_leak"] or not checks["deep_proof_present_if_required"]:
        status = "failed"
    return {
        "schema_version": "chapter_verification.v1",
        "chapter_id": chapter_id,
        "status": status,
        "checks": checks,
        "claim_count": len(claims),
        "grounded_claim_count": len(claims_with_refs),
        "referenced_evidence": referenced,
        "repair_reasons": repair_reasons,
        "grounded_claim_target": grounded_claim_target,
    }


def build_quality_score(report_ir: dict[str, Any], chapter_verifications: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate chapter verification into the PRD A/B/C/D publish decision."""
    verifications = [item for item in chapter_verifications if isinstance(item, dict)]
    total = max(1, len(verifications))
    passed = sum(1 for item in verifications if item.get("status") == "passed")
    failed = sum(1 for item in verifications if item.get("status") == "failed")
    avg_grounding = sum(float((item.get("checks") or {}).get("grounded_claim_ratio") or 0) for item in verifications) / total
    evidence_grounding_score = avg_grounding * 100
    structure_completeness_score = (passed / total) * 100
    counterargument_score = (
        sum(1 for item in verifications if (item.get("checks") or {}).get("has_counter_evidence")) / total
    ) * 100
    safety_score = 0 if failed else 100
    weighted = (
        0.20 * evidence_grounding_score
        + 0.15 * structure_completeness_score
        + 0.15 * structure_completeness_score
        + 0.15 * evidence_grounding_score
        + 0.10 * safety_score
        + 0.10 * structure_completeness_score
        + 0.05 * counterargument_score
        + 0.05 * safety_score
        + 0.05 * structure_completeness_score
    )
    grade = "A" if weighted >= 85 else "B" if weighted >= 75 else "C" if weighted >= 60 else "D"
    publish_decision = "publish" if grade in {"A", "B"} and failed == 0 else "internal_only" if grade == "C" else "blocked"
    return {
        "schema_version": "report_quality_score.v1",
        "report_id": report_ir.get("report_id") or "N/A",
        "score": round(weighted, 2),
        "grade": grade,
        "publish_decision": publish_decision,
        "chapter_count": total,
        "passed_chapter_count": passed,
        "failed_chapter_count": failed,
        "scores": {
            "evidence_grounding_score": round(evidence_grounding_score, 2),
            "structure_completeness_score": round(structure_completeness_score, 2),
            "counterargument_score": round(counterargument_score, 2),
            "safety_score": round(safety_score, 2),
        },
    }


def write_validation_sidecars(report_dir: Path, report_ir: dict[str, Any], chapter_verifications: list[dict[str, Any]]) -> dict[str, Any]:
    validation_dir = Path(report_dir) / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    quality = build_quality_score(report_ir, chapter_verifications)
    (validation_dir / "chapter-validation-summary.json").write_text(
        json.dumps({"chapters": chapter_verifications}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (validation_dir / "claim-verification.json").write_text(
        json.dumps({"chapters": chapter_verifications}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (validation_dir / "quality-score.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return quality
