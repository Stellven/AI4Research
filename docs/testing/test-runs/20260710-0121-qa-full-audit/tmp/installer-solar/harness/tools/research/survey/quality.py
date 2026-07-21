"""Survey taxonomy and contradiction quality assessment."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from research.evaluator import audit_sources


def _read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _required_types_from_source_matrix(root: Path) -> set[str]:
    data = _read_json(root / "survey_source_matrix.json")
    rows = data if isinstance(data, list) else data.get("source_matrix", [])
    required: set[str] = set()
    if not isinstance(rows, list):
        return required
    for row in rows:
        if not isinstance(row, dict):
            continue
        for item in row.get("required_source_types", []):
            if item:
                required.add(str(item))
    return required


def _chapter_axis(chapter_title: str) -> str:
    text = str(chapter_title or "")
    rules = [
        ("definition", r"定义|边界|术语"),
        ("history", r"历史|演进|脉络"),
        ("evaluation", r"评估|基准|评价"),
        ("contradiction", r"争议|反证|失败"),
        ("architecture", r"架构|范式|系统"),
        ("method_taxonomy", r"分类|方法|代表系统"),
        ("engineering", r"工程|部署|实现"),
        ("risk", r"风险|安全|可解释"),
        ("ecosystem", r"产业|生态|开源"),
        ("roadmap", r"未来|路线图|开放问题"),
    ]
    for axis, pattern in rules:
        if re.search(pattern, text):
            return axis
    return "other"


def _extract_tags(text: str, tag: str) -> set[str]:
    return {item.strip() for item in re.findall(rf"\[{re.escape(tag)}:([^\]]+)\]", text or "") if item.strip()}


def _evidence_text(row: dict[str, Any]) -> str:
    return str(row.get("content") or row.get("span_text") or row.get("clean_markdown") or row.get("text") or row.get("title") or "")


def _tokens(text: str) -> set[str]:
    ascii_words = {part.lower() for part in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", text or "")}
    cjk = re.findall(r"[\u4e00-\u9fff]{2,}", text or "")
    cjk_bigrams: set[str] = set()
    for chunk in cjk:
        cjk_bigrams.update(chunk[idx:idx + 2] for idx in range(max(len(chunk) - 1, 0)))
    return ascii_words | cjk_bigrams


def _grounding_checks(text: str, evidence_tags: set[str], evidence_by_id: dict[str, str]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for line_no, line in enumerate((text or "").splitlines(), start=1):
        tags = _extract_tags(line, "evidence")
        if not tags:
            continue
        context_tokens = _tokens(line)
        for evidence_id in sorted(tags):
            evidence_tokens = _tokens(evidence_by_id.get(evidence_id, ""))
            if not evidence_tokens:
                checks.append({
                    "evidence_id": evidence_id,
                    "line": line_no,
                    "ok": False,
                    "reason": "evidence_span_text_missing",
                    "overlap": [],
                })
                continue
            overlap = sorted(context_tokens & evidence_tokens)
            checks.append({
                "evidence_id": evidence_id,
                "line": line_no,
                "ok": bool(overlap),
                "reason": "" if overlap else "citation_context_not_grounded",
                "overlap": overlap[:12],
            })
    return checks


def _grounding_failures_for_evidence(evidence_tags: set[str], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for evidence_id in sorted(evidence_tags):
        related = [item for item in checks if item.get("evidence_id") == evidence_id]
        if any(item.get("ok") for item in related):
            continue
        failures.append({
            "evidence_id": evidence_id,
            "ok": False,
            "reason": related[0].get("reason") if related else "citation_context_missing",
            "lines": [item.get("line") for item in related if item.get("line")],
        })
    return failures


def _section_factual_audit(
    root: Path,
    sections: list[dict[str, Any]],
    pack_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence_by_id = {
        str(row.get("id") or row.get("evidence_id")): _evidence_text(row)
        for row in evidence_rows
        if str(row.get("id") or row.get("evidence_id") or "")
    }
    audited = 0
    passed = 0
    grounded = 0
    missing_final: list[str] = []
    section_results: list[dict[str, Any]] = []
    for section in sections:
        section_id = str(section.get("section_id") or "")
        if not section_id:
            continue
        final_path = root / "sections" / section_id / "final.md"
        pack = next((row for row in pack_rows if str(row.get("section_id") or "") == section_id), {})
        allowed_claims = {str(item) for item in pack.get("claim_ids", []) if str(item)}
        allowed_evidence = {str(item) for item in pack.get("evidence_ids", []) if str(item)}
        if not final_path.exists():
            missing_final.append(section_id)
            continue
        audited += 1
        text = final_path.read_text(encoding="utf-8", errors="ignore")
        claim_tags = _extract_tags(text, "claim")
        evidence_tags = _extract_tags(text, "evidence")
        unknown_claims = sorted(claim_tags - allowed_claims)
        unknown_evidence = sorted(evidence_tags - allowed_evidence)
        missing_claim_tags = not bool(claim_tags)
        missing_evidence_tags = not bool(evidence_tags)
        grounding_checks = _grounding_checks(text, evidence_tags, evidence_by_id)
        grounding_failures = _grounding_failures_for_evidence(evidence_tags, grounding_checks)
        grounding_ok = bool(grounding_checks) and not grounding_failures
        ok = not unknown_claims and not unknown_evidence and not missing_claim_tags and not missing_evidence_tags and grounding_ok
        if ok:
            passed += 1
        if grounding_ok:
            grounded += 1
        section_results.append({
            "section_id": section_id,
            "ok": ok,
            "claim_tags": sorted(claim_tags),
            "evidence_tags": sorted(evidence_tags),
            "unknown_claim_ids": unknown_claims,
            "unknown_evidence_ids": unknown_evidence,
            "missing_claim_tags": missing_claim_tags,
            "missing_evidence_tags": missing_evidence_tags,
            "grounding_ok": grounding_ok,
            "grounding_failures": grounding_failures[:20],
        })
    accuracy = round(passed / max(audited, 1), 4)
    grounding_accuracy = round(grounded / max(audited, 1), 4)
    return {
        "ok": accuracy >= 0.95,
        "section_factual_accuracy": accuracy,
        "section_grounding_accuracy": grounding_accuracy,
        "audited_sections": audited,
        "passed_sections": passed,
        "grounded_sections": grounded,
        "missing_final_sections": missing_final[:50],
        "failed_sections": [item for item in section_results if not item.get("ok")][:50],
    }


def _build_section_scorecard(
    root: Path,
    sections: list[dict[str, Any]],
    pack_rows: list[dict[str, Any]],
    section_factual_audit: dict[str, Any],
) -> dict[str, Any]:
    failed_by_id = {
        str(item.get("section_id") or ""): item
        for item in section_factual_audit.get("failed_sections", [])
        if isinstance(item, dict)
    }
    rows: list[dict[str, Any]] = []
    for section in sections:
        section_id = str(section.get("section_id") or "")
        if not section_id:
            continue
        final_path = root / "sections" / section_id / "final.md"
        review = _read_json(root / "sections" / section_id / "review.json")
        pack = next((row for row in pack_rows if str(row.get("section_id") or "") == section_id), {})
        issues: list[dict[str, Any]] = []
        pending = False
        if not final_path.exists():
            pending = True
        failed = failed_by_id.get(section_id, {})
        if failed.get("unknown_claim_ids"):
            issues.append({"severity": "P0", "code": "unknown_claim_ids", "detail": failed.get("unknown_claim_ids")})
        if failed.get("unknown_evidence_ids"):
            issues.append({"severity": "P0", "code": "unknown_evidence_ids", "detail": failed.get("unknown_evidence_ids")})
        if failed.get("missing_claim_tags"):
            issues.append({"severity": "P0", "code": "missing_claim_tags", "detail": True})
        if failed.get("missing_evidence_tags"):
            issues.append({"severity": "P0", "code": "missing_evidence_tags", "detail": True})
        if failed.get("grounding_failures"):
            issues.append({"severity": "P0", "code": "grounding_failures", "detail": failed.get("grounding_failures")})
        if pack.get("status") != "ready":
            issues.append({"severity": "P0", "code": "evidence_pack_not_ready", "detail": pack.get("blockers", [])})
        for issue in review.get("issues", []) if isinstance(review.get("issues"), list) else []:
            code = str(issue)
            severity = "P1" if re.search(r"contradiction|evaluation|source_diversity", code, re.I) else "P2"
            issues.append({"severity": severity, "code": code.split(":", 1)[0], "detail": code})
        if final_path.exists():
            text = final_path.read_text(encoding="utf-8", errors="ignore")
            headings = len(re.findall(r"^##\s+", text, flags=re.M))
            if headings < 6:
                issues.append({"severity": "P1", "code": "section_structure_shallow", "detail": f"{headings}<6"})
            paragraphs = [re.sub(r"\s+", " ", p.strip().lower()) for p in text.split("\n\n") if p.strip()]
            repetition = 1.0 - (len(set(paragraphs)) / max(len(paragraphs), 1))
            if repetition > 0.20:
                issues.append({"severity": "P2", "code": "section_repetition_high", "detail": round(repetition, 4)})
        severity_weight = {"P0": 100, "P1": 25, "P2": 5}
        risk_score = sum(severity_weight.get(str(item.get("severity")), 1) for item in issues)
        rows.append({
            "section_id": section_id,
            "status": "pending" if pending else "pass" if not issues else "needs_rewrite",
            "risk_score": risk_score,
            "p0_count": sum(1 for item in issues if item.get("severity") == "P0"),
            "p1_count": sum(1 for item in issues if item.get("severity") == "P1"),
            "p2_count": sum(1 for item in issues if item.get("severity") == "P2"),
            "issues": issues,
            "rewrite_recommended": (not pending) and risk_score >= 25,
        })
    rows.sort(key=lambda item: (-int(item.get("risk_score") or 0), str(item.get("section_id") or "")))
    return {
        "ok": not any(item.get("p0_count") for item in rows),
        "section_count": len(rows),
        "needs_rewrite_count": sum(1 for item in rows if item.get("rewrite_recommended")),
        "top_issues": rows[:20],
    }


def _normalized_long_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\[[a-z]+:[^\]]+\]", "", text or "")
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"^\s*[#|>-].*$", " ", cleaned, flags=re.M)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    sentences = re.split(r"(?<=[.!?。！？])\s+", cleaned)
    return [item.strip() for item in sentences if len(item.strip()) >= 80]


def _duplicate_sentence_stats(sentences: list[str]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for sentence in sentences:
        counts[sentence] = counts.get(sentence, 0) + 1
    repeated = [
        {"sentence": sentence, "count": count}
        for sentence, count in counts.items()
        if count > 1
    ]
    repeated.sort(key=lambda item: (-int(item["count"]), str(item["sentence"])[:80]))
    duplicate_occurrences = sum(int(item["count"]) - 1 for item in repeated)
    return {
        "long_sentence_count": len(sentences),
        "unique_long_sentence_count": len(counts),
        "duplicate_long_sentence_occurrences": duplicate_occurrences,
        "duplicate_long_sentence_ratio": round(duplicate_occurrences / max(len(sentences), 1), 4),
        "max_duplicate_long_sentence_count": int(repeated[0]["count"]) if repeated else 0,
        "top_duplicate_long_sentences": repeated[:10],
    }


def _build_final_quality(root: Path, ast: dict[str, Any], sections: list[dict[str, Any]]) -> dict[str, Any]:
    final_path = root / "final.md"
    final_text = final_path.read_text(encoding="utf-8", errors="ignore") if final_path.exists() else ""
    target_chars = int(ast.get("target_chars") or sum(int(section.get("target_chars") or 0) for section in sections) or 0)
    finalized_lengths: list[int] = []
    missing_sections: list[str] = []
    for section in sections:
        section_id = str(section.get("section_id") or "")
        if not section_id:
            continue
        path = root / "sections" / section_id / "final.md"
        if not path.exists():
            missing_sections.append(section_id)
            continue
        finalized_lengths.append(len(path.read_text(encoding="utf-8", errors="ignore")))
    final_char_count = len(final_text)
    finalized_count = len(finalized_lengths)
    avg_section_chars = round(sum(finalized_lengths) / max(finalized_count, 1), 2)
    pending_placeholder_count = len(re.findall(r"Status:\s*pending final section\.", final_text))
    heading_count = len(re.findall(r"^#{2,4}\s+", final_text, flags=re.M))
    claim_tag_count = len(re.findall(r"\[claim:[^\]]+\]", final_text))
    evidence_tag_count = len(re.findall(r"\[evidence:[^\]]+\]", final_text))
    chars_k = max(final_char_count / 1000.0, 1.0)
    claim_tag_density = round(claim_tag_count / chars_k, 4)
    evidence_tag_density = round(evidence_tag_count / chars_k, 4)
    paragraphs = []
    for item in final_text.split("\n\n"):
        cleaned = re.sub(r"\[[a-z]+:[^\]]+\]", "", item.strip().lower())
        cleaned = re.sub(r"^#+\s+", "", cleaned, flags=re.M)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) >= 80:
            paragraphs.append(cleaned)
    repetition_rate = round(1.0 - (len(set(paragraphs)) / max(len(paragraphs), 1)), 4)
    sentence_stats = _duplicate_sentence_stats(_normalized_long_sentences(final_text))
    per_section_target = target_chars / max(len(sections), 1) if target_chars else 0
    min_final_chars = int(target_chars * 0.60) if target_chars else 0
    min_avg_section_chars = int(max(min(per_section_target * 0.45, 1200), 500)) if per_section_target else 500
    min_heading_count = max(finalized_count * 5, 1) if finalized_count else 0
    issues: list[str] = []
    if target_chars and final_char_count < min_final_chars:
        issues.append(f"final_char_count_low:{final_char_count}<{min_final_chars}")
    if finalized_count and avg_section_chars < min_avg_section_chars:
        issues.append(f"avg_section_chars_low:{avg_section_chars:.2f}<{min_avg_section_chars}")
    if pending_placeholder_count:
        issues.append(f"pending_placeholder_count:{pending_placeholder_count}")
    if finalized_count and heading_count < min_heading_count:
        issues.append(f"final_heading_count_low:{heading_count}<{min_heading_count}")
    if finalized_count and claim_tag_density < 0.80:
        issues.append(f"claim_tag_density_low:{claim_tag_density:.4f}<0.8000")
    if finalized_count and evidence_tag_density < 0.80:
        issues.append(f"evidence_tag_density_low:{evidence_tag_density:.4f}<0.8000")
    if repetition_rate > 0.99:
        issues.append(f"final_repetition_rate_high:{repetition_rate:.4f}>0.9900")
    duplicate_sentence_threshold = max(6, int(finalized_count * 0.25)) if finalized_count else 6
    if sentence_stats["max_duplicate_long_sentence_count"] >= duplicate_sentence_threshold:
        issues.append(f"final_duplicate_sentence_count_high:{sentence_stats['max_duplicate_long_sentence_count']}>={duplicate_sentence_threshold}")
    if finalized_count and sentence_stats["duplicate_long_sentence_ratio"] > 0.25:
        issues.append(f"final_duplicate_sentence_ratio_high:{sentence_stats['duplicate_long_sentence_ratio']:.4f}>0.2500")
    return {
        "ok": not issues,
        "final_md": str(final_path),
        "target_chars": target_chars,
        "final_char_count": final_char_count,
        "min_final_chars": min_final_chars,
        "finalized_sections": finalized_count,
        "total_sections": len(sections),
        "missing_sections": missing_sections[:50],
        "avg_section_chars": avg_section_chars,
        "min_avg_section_chars": min_avg_section_chars,
        "pending_placeholder_count": pending_placeholder_count,
        "heading_count": heading_count,
        "min_heading_count": min_heading_count,
        "claim_tag_count": claim_tag_count,
        "evidence_tag_count": evidence_tag_count,
        "claim_tag_density_per_1k_chars": claim_tag_density,
        "evidence_tag_density_per_1k_chars": evidence_tag_density,
        "repetition_rate": repetition_rate,
        **sentence_stats,
        "issues": issues,
    }


def _build_source_coverage(root: Path, sections: list[dict[str, Any]]) -> dict[str, Any]:
    sources = _read_jsonl(root / "sources.jsonl")
    evidence_rows = _read_jsonl(root / "evidence.jsonl")
    source_audit = audit_sources(root, research_profile="technical_architecture", strict_profile=True)
    type_counts = {
        str(key): int(value)
        for key, value in (source_audit.get("source_type_counts") or {}).items()
    }
    source_count = int(source_audit.get("source_count") or len(sources))
    required_types = {"paper", "official_doc", "code", "benchmark"}
    observed_types = set(type_counts.keys())
    missing_required = sorted(required_types - observed_types)
    paper_like_count = sum(type_counts.get(item, 0) for item in ("paper", "preprint"))
    low_value_count = sum(type_counts.get(item, 0) for item in ("web", "blog", "other", "unknown"))
    low_value_ratio = round(low_value_count / max(source_count, 1), 4)
    evidence_source_ids = {str(row.get("source_id") or "") for row in evidence_rows if row.get("source_id")}
    cited_source_ratio = round(len(evidence_source_ids) / max(source_count, 1), 4)
    high_authority_count = int(source_audit.get("source_high_authority_count") or 0)
    authority_average = float(source_audit.get("source_authority_average") or 0.0)
    min_sources = 8 if len(sections) >= 30 else 4
    min_paper_like = 4 if len(sections) >= 30 else 2
    min_high_authority = 4 if len(sections) >= 30 else 2
    issues: list[str] = []
    if source_count < min_sources:
        issues.append(f"survey_source_count_low:{source_count}<{min_sources}")
    if missing_required:
        issues.append("survey_missing_required_source_types:" + ",".join(missing_required))
    if paper_like_count < min_paper_like:
        issues.append(f"paper_like_source_count_low:{paper_like_count}<{min_paper_like}")
    if high_authority_count < min_high_authority:
        issues.append(f"high_authority_source_count_low:{high_authority_count}<{min_high_authority}")
    if authority_average < 0.55:
        issues.append(f"source_authority_average_low:{authority_average:.4f}<0.5500")
    if low_value_ratio > 0.40:
        issues.append(f"low_value_source_ratio_high:{low_value_ratio:.4f}>0.4000")
    if cited_source_ratio < 0.50:
        issues.append(f"cited_source_ratio_low:{cited_source_ratio:.4f}<0.5000")
    for issue in source_audit.get("errors", []):
        issues.append(str(issue))
    return {
        "ok": not issues,
        "source_count": source_count,
        "min_sources": min_sources,
        "source_type_counts": type_counts,
        "required_source_types": sorted(required_types),
        "missing_required_source_types": missing_required,
        "paper_like_source_count": paper_like_count,
        "min_paper_like_sources": min_paper_like,
        "high_authority_source_count": high_authority_count,
        "min_high_authority_sources": min_high_authority,
        "source_authority_average": authority_average,
        "low_value_source_count": low_value_count,
        "low_value_source_ratio": low_value_ratio,
        "cited_source_ratio": cited_source_ratio,
        "source_audit": source_audit,
        "issues": issues,
    }


def _build_literature_map(
    root: Path,
    chapters: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    pack_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    sources = _read_jsonl(root / "sources.jsonl")
    evidence_rows = _read_jsonl(root / "evidence.jsonl")
    claims = _read_jsonl(root / "claims.jsonl")
    links = _read_jsonl(root / "claim_evidence.jsonl")
    source_by_id = {str(row.get("id") or row.get("source_id") or ""): row for row in sources}
    evidence_by_id = {str(row.get("id") or row.get("evidence_id") or ""): row for row in evidence_rows}
    evidence_to_claims: dict[str, set[str]] = {}
    for link in links:
        claim_id = str(link.get("claim_id") or "")
        evidence_id = str(link.get("evidence_id") or "")
        if claim_id and evidence_id:
            evidence_to_claims.setdefault(evidence_id, set()).add(claim_id)
    section_by_id = {str(row.get("section_id") or ""): row for row in sections}
    chapter_by_id = {str(row.get("chapter_id") or ""): row for row in chapters}
    source_chapters: dict[str, set[str]] = {sid: set() for sid in source_by_id}
    source_sections: dict[str, set[str]] = {sid: set() for sid in source_by_id}
    source_evidence: dict[str, set[str]] = {sid: set() for sid in source_by_id}
    source_claims: dict[str, set[str]] = {sid: set() for sid in source_by_id}

    for evidence_id, evidence in evidence_by_id.items():
        source_id = str(evidence.get("source_id") or "")
        if source_id in source_by_id:
            source_evidence.setdefault(source_id, set()).add(evidence_id)
            source_claims.setdefault(source_id, set()).update(evidence_to_claims.get(evidence_id, set()))

    for pack in pack_rows:
        section_id = str(pack.get("section_id") or "")
        chapter_id = str(section_by_id.get(section_id, {}).get("chapter_id") or "")
        for source_id in pack.get("source_ids", []) if isinstance(pack.get("source_ids"), list) else []:
            sid = str(source_id or "")
            if sid in source_by_id:
                source_sections.setdefault(sid, set()).add(section_id)
                if chapter_id:
                    source_chapters.setdefault(sid, set()).add(chapter_id)
        for evidence_id in pack.get("evidence_ids", []) if isinstance(pack.get("evidence_ids"), list) else []:
            eid = str(evidence_id or "")
            ev = evidence_by_id.get(eid, {})
            sid = str(ev.get("source_id") or "")
            if sid in source_by_id:
                source_sections.setdefault(sid, set()).add(section_id)
                if chapter_id:
                    source_chapters.setdefault(sid, set()).add(chapter_id)

    rows: list[dict[str, Any]] = []
    for source_id, source in sorted(source_by_id.items()):
        rows.append({
            "source_id": source_id,
            "source_type": str(source.get("source_type") or "unknown"),
            "title": str(source.get("title") or ""),
            "url": str(source.get("url") or ""),
            "chapter_ids": sorted(source_chapters.get(source_id, set())),
            "section_ids": sorted(source_sections.get(source_id, set())),
            "evidence_ids": sorted(source_evidence.get(source_id, set())),
            "claim_ids": sorted(source_claims.get(source_id, set())),
        })

    chapter_rows: list[dict[str, Any]] = []
    covered_chapters = 0
    for chapter in chapters:
        chapter_id = str(chapter.get("chapter_id") or "")
        chapter_sources = [row for row in rows if chapter_id in row["chapter_ids"]]
        source_types = sorted({str(row.get("source_type") or "unknown") for row in chapter_sources})
        evidence_count = sum(len(row.get("evidence_ids") or []) for row in chapter_sources)
        claim_count = len({claim_id for row in chapter_sources for claim_id in row.get("claim_ids", [])})
        ok = len(source_types) >= 2 and evidence_count >= 2 and claim_count >= 1
        if ok:
            covered_chapters += 1
        chapter_rows.append({
            "chapter_id": chapter_id,
            "title": str(chapter.get("title") or ""),
            "axis": _chapter_axis(str(chapter.get("title") or "")),
            "ok": ok,
            "source_count": len(chapter_sources),
            "source_types": source_types,
            "evidence_count": evidence_count,
            "claim_count": claim_count,
        })

    source_types = sorted({str(row.get("source_type") or "unknown") for row in rows})
    chapter_coverage = round(covered_chapters / max(len(chapters), 1), 4)
    evidence_backed_sources = sum(1 for row in rows if row.get("evidence_ids"))
    evidence_backed_ratio = round(evidence_backed_sources / max(len(rows), 1), 4)
    claim_backed_sources = sum(1 for row in rows if row.get("claim_ids"))
    claim_backed_ratio = round(claim_backed_sources / max(len(rows), 1), 4)
    issues: list[str] = []
    if len(source_types) < 4:
        issues.append(f"literature_source_type_count_low:{len(source_types)}<4")
    if chapter_coverage < 0.80:
        issues.append(f"literature_chapter_coverage_low:{chapter_coverage:.4f}<0.8000")
    if evidence_backed_ratio < 0.75:
        issues.append(f"literature_evidence_backed_source_ratio_low:{evidence_backed_ratio:.4f}<0.7500")
    if claims and claim_backed_ratio < 0.50:
        issues.append(f"literature_claim_backed_source_ratio_low:{claim_backed_ratio:.4f}<0.5000")
    return {
        "ok": not issues,
        "source_count": len(rows),
        "source_types": source_types,
        "chapter_count": len(chapters),
        "covered_chapters": covered_chapters,
        "chapter_coverage": chapter_coverage,
        "evidence_backed_source_ratio": evidence_backed_ratio,
        "claim_backed_source_ratio": claim_backed_ratio,
        "sources": rows,
        "chapters": chapter_rows,
        "issues": issues,
    }


def _build_controversy_review(
    chapters: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    pack_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    section_by_id = {str(row.get("section_id") or ""): row for row in sections}
    chapter_axes = {_chapter_axis(str(row.get("title") or "")) for row in chapters}
    rows: list[dict[str, Any]] = []
    covered_chapters: set[str] = set()
    covered_sections = 0
    mixed_source_sections = 0
    for pack in pack_rows:
        section_id = str(pack.get("section_id") or "")
        section = section_by_id.get(section_id, {})
        chapter_id = str(section.get("chapter_id") or "")
        slots = [str(slot) for slot in pack.get("contradiction_slots", []) if str(slot).strip()] if isinstance(pack.get("contradiction_slots"), list) else []
        source_types = {str(item) for item in pack.get("source_types", []) if str(item)} if isinstance(pack.get("source_types"), list) else set()
        evidence_count = len(pack.get("evidence_ids", []) if isinstance(pack.get("evidence_ids"), list) else [])
        ok = bool(slots) and evidence_count >= 2
        if ok:
            covered_sections += 1
            if chapter_id:
                covered_chapters.add(chapter_id)
        if len(source_types) >= 2:
            mixed_source_sections += 1
        rows.append({
            "section_id": section_id,
            "chapter_id": chapter_id,
            "axis": _chapter_axis(str(section.get("title") or "")),
            "ok": ok,
            "contradiction_slots": slots,
            "source_types": sorted(source_types),
            "evidence_count": evidence_count,
            "mixed_source_evidence": len(source_types) >= 2,
        })
    section_coverage = round(covered_sections / max(len(sections), 1), 4)
    chapter_coverage = round(len(covered_chapters) / max(len(chapters), 1), 4)
    mixed_source_ratio = round(mixed_source_sections / max(len(pack_rows), 1), 4)
    axes_with_controversy_set = {row["axis"] for row in rows if row.get("ok")}
    axes_with_controversy = sorted(axes_with_controversy_set)
    issues: list[str] = []
    if section_coverage < 0.80:
        issues.append(f"controversy_section_coverage_low:{section_coverage:.4f}<0.8000")
    if chapter_coverage < 0.80:
        issues.append(f"controversy_chapter_coverage_low:{chapter_coverage:.4f}<0.8000")
    if mixed_source_ratio < 0.80:
        issues.append(f"controversy_mixed_source_ratio_low:{mixed_source_ratio:.4f}<0.8000")
    if len(axes_with_controversy_set & chapter_axes) < min(4, len(chapter_axes)):
        issues.append(f"controversy_axis_coverage_low:{len(axes_with_controversy_set & chapter_axes)}<{min(4, len(chapter_axes))}")
    return {
        "ok": not issues,
        "section_coverage": section_coverage,
        "chapter_coverage": chapter_coverage,
        "mixed_source_ratio": mixed_source_ratio,
        "axes_with_controversy": axes_with_controversy,
        "rows": rows[:200],
        "issues": issues,
    }


def _build_chapter_review(
    root: Path,
    chapters: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    pack_rows: list[dict[str, Any]],
    section_scorecard: dict[str, Any],
) -> dict[str, Any]:
    pack_by_section = {str(row.get("section_id") or ""): row for row in pack_rows}
    score_by_section = {
        str(row.get("section_id") or ""): row
        for row in section_scorecard.get("top_issues", [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for chapter in chapters:
        chapter_id = str(chapter.get("chapter_id") or "")
        chapter_sections = [row for row in sections if str(row.get("chapter_id") or "") == chapter_id]
        ready_packs = 0
        source_types: set[str] = set()
        p0_count = 0
        p1_count = 0
        missing_finals: list[str] = []
        total_chars = 0
        finalized = 0
        issues: list[dict[str, Any]] = []
        for section in chapter_sections:
            section_id = str(section.get("section_id") or "")
            pack = pack_by_section.get(section_id, {})
            if pack.get("status") == "ready":
                ready_packs += 1
            source_types.update(str(item) for item in pack.get("source_types", []) if str(item)) if isinstance(pack.get("source_types"), list) else None
            score = score_by_section.get(section_id, {})
            p0_count += int(score.get("p0_count") or 0)
            p1_count += int(score.get("p1_count") or 0)
            final_path = root / "sections" / section_id / "final.md"
            if final_path.exists():
                total_chars += len(final_path.read_text(encoding="utf-8", errors="ignore"))
                finalized += 1
            else:
                missing_finals.append(section_id)
        ready_ratio = round(ready_packs / max(len(chapter_sections), 1), 4)
        avg_final_chars = round(total_chars / max(finalized, 1), 2)
        if ready_ratio < 0.80:
            issues.append({"severity": "P0", "code": "chapter_ready_pack_ratio_low", "detail": f"{ready_ratio:.4f}<0.8000"})
        if len(source_types) < 2:
            issues.append({"severity": "P1", "code": "chapter_source_diversity_low", "detail": f"{len(source_types)}<2"})
        if p0_count:
            issues.append({"severity": "P0", "code": "chapter_section_p0_issues", "detail": p0_count})
        if p1_count >= max(len(chapter_sections), 1):
            issues.append({"severity": "P1", "code": "chapter_section_p1_issue_density_high", "detail": p1_count})
        if missing_finals:
            issues.append({"severity": "P2", "code": "chapter_missing_final_sections", "detail": missing_finals[:10]})
        rows.append({
            "chapter_id": chapter_id,
            "title": str(chapter.get("title") or ""),
            "axis": _chapter_axis(str(chapter.get("title") or "")),
            "section_ids": [str(row.get("section_id") or "") for row in chapter_sections if str(row.get("section_id") or "")],
            "section_count": len(chapter_sections),
            "ready_pack_ratio": ready_ratio,
            "source_types": sorted(source_types),
            "finalized_sections": finalized,
            "avg_final_chars": avg_final_chars,
            "p0_count": p0_count,
            "p1_count": p1_count,
            "issues": issues,
        })
    p0_chapters = sum(1 for row in rows for issue in row.get("issues", []) if issue.get("severity") == "P0")
    p1_chapters = sum(1 for row in rows for issue in row.get("issues", []) if issue.get("severity") == "P1")
    return {
        "ok": p0_chapters == 0,
        "chapter_count": len(rows),
        "p0_chapter_issue_count": p0_chapters,
        "p1_chapter_issue_count": p1_chapters,
        "chapters": rows,
        "issues": [f"chapter_p0_issue_count:{p0_chapters}" for _ in [0] if p0_chapters],
    }


def _normalized_section_fingerprint(text: str) -> str:
    cleaned = re.sub(r"\[[a-z]+:[^\]]+\]", "", text or "")
    cleaned = re.sub(r"^#+\s+.*$", "", cleaned, flags=re.M)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned[:800]


def _build_chief_editor_review(
    root: Path,
    chapters: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    chapter_review: dict[str, Any],
    literature_map: dict[str, Any],
    controversy_review: dict[str, Any],
) -> dict[str, Any]:
    section_by_chapter: dict[str, list[str]] = {}
    finalized_by_chapter: dict[str, int] = {}
    fingerprints: list[str] = []
    terminology_text_parts: list[str] = []
    for section in sections:
        section_id = str(section.get("section_id") or "")
        chapter_id = str(section.get("chapter_id") or "")
        if section_id:
            section_by_chapter.setdefault(chapter_id, []).append(section_id)
        final_path = root / "sections" / section_id / "final.md"
        if not final_path.exists():
            continue
        finalized_by_chapter[chapter_id] = finalized_by_chapter.get(chapter_id, 0) + 1
        text = final_path.read_text(encoding="utf-8", errors="ignore")
        terminology_text_parts.append(text)
        fingerprint = _normalized_section_fingerprint(text)
        if fingerprint:
            fingerprints.append(fingerprint)

    finalized_sections = len(fingerprints)
    duplicate_rate = round(1.0 - (len(set(fingerprints)) / max(finalized_sections, 1)), 4)
    chapters_with_final = len([chapter for chapter in chapters if finalized_by_chapter.get(str(chapter.get("chapter_id") or ""), 0)])
    chapter_final_coverage = round(chapters_with_final / max(len(chapters), 1), 4)
    complete_context = bool(sections) and finalized_sections == len(sections)
    chapter_p0_issue_count = int(chapter_review.get("p0_chapter_issue_count") or 0)
    issues: list[str] = []
    warnings: list[str] = []
    if complete_context and chapter_final_coverage < 1.0:
        issues.append(f"chief_editor_chapter_final_coverage_low:{chapter_final_coverage:.4f}<1.0000")
    if complete_context and duplicate_rate > 0.75:
        issues.append(f"chief_editor_section_duplicate_rate_high:{duplicate_rate:.4f}>0.7500")
    if complete_context and chapter_p0_issue_count:
        issues.append(f"chief_editor_chapter_p0_issue_count:{chapter_p0_issue_count}")
    if complete_context and not literature_map.get("ok"):
        issues.append("chief_editor_literature_map_not_ok")
    if complete_context and not controversy_review.get("ok"):
        issues.append("chief_editor_controversy_matrix_not_ok")
    if not complete_context and finalized_sections:
        warnings.append(f"chief_editor_partial_review:{finalized_sections}/{len(sections)}")
    terminology_profile = _terminology_profile("\n".join(terminology_text_parts))
    terminology_counts = dict(terminology_profile.get("counts") or {})
    terminology_variants = [key for key, value in terminology_counts.items() if value]
    if complete_context and len(terminology_variants) < 2:
        warnings.append("chief_editor_terminology_signal_sparse")
    chapter_rows = []
    for chapter in chapters:
        chapter_id = str(chapter.get("chapter_id") or "")
        chapter_rows.append({
            "chapter_id": chapter_id,
            "title": str(chapter.get("title") or ""),
            "section_count": len(section_by_chapter.get(chapter_id, [])),
            "finalized_sections": finalized_by_chapter.get(chapter_id, 0),
            "ready_for_chief_edit": finalized_by_chapter.get(chapter_id, 0) == len(section_by_chapter.get(chapter_id, [])) and bool(section_by_chapter.get(chapter_id, [])),
        })
    return {
        "ok": not issues,
        "complete_context": complete_context,
        "finalized_sections": finalized_sections,
        "total_sections": len(sections),
        "chapter_final_coverage": chapter_final_coverage,
        "section_duplicate_rate": duplicate_rate,
        "terminology_profile": str(terminology_profile.get("profile") or ""),
        "terminology_counts": terminology_counts,
        "terminology_variants": terminology_variants,
        "chapters": chapter_rows,
        "warnings": warnings,
        "issues": issues,
    }


def _count_pattern(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text or "", flags=re.I))


def _latent_reasoning_terminology_counts(text: str) -> dict[str, int]:
    lowered = (text or "").lower()
    return {
        "latent_reasoning": _count_pattern(lowered, r"latent reasoning|隐空间推理|潜空间推理"),
        "continuous_thought": _count_pattern(lowered, r"continuous[- ]thought|continuous reasoning|连续思维|连续推理"),
        "chain_of_thought": _count_pattern(lowered, r"chain[- ]of[- ]thought|\bcot\b|思维链|显式推理链"),
        "coconut": _count_pattern(lowered, r"\bcoconut\b"),
        "hidden_state": _count_pattern(lowered, r"hidden[- ]state|latent[- ]state|隐状态|潜状态"),
    }


def _agentic_runtime_terminology_counts(text: str) -> dict[str, int]:
    lowered = (text or "").lower()
    return {
        "runtime_orchestration": _count_pattern(lowered, r"agentic runtime|agent runtime|runtime|运行时|orchestrat|编排|orchestrator"),
        "tool_execution": _count_pattern(lowered, r"tool[- ]?(use|execution|calling)|function calling|mcp|工具调用|工具执行|动作|action"),
        "memory_state": _count_pattern(lowered, r"memory|state|checkpoint|durable execution|持久执行|状态|记忆|检查点"),
        "multi_agent_handoff": _count_pattern(lowered, r"multi[- ]agent|handoff|agent graph|agent network|多智能体|移交"),
        "evaluation_benchmark": _count_pattern(lowered, r"evaluation|eval|benchmark|metric|评估|基准|指标"),
        "safety_governance": _count_pattern(lowered, r"guardrail|policy|sandbox|permission|安全|治理|权限|策略"),
        "observability_trace": _count_pattern(lowered, r"trace|tracing|observability|telemetry|audit|可观测|追踪|审计"),
    }


def _terminology_profile(text: str) -> dict[str, Any]:
    """Return the dominant technical terminology profile for the report topic.

    The original depth gate was built for latent-reasoning surveys.  DeepResearch
    now supports other technical architecture domains, so the terminology check
    must score the actual report vocabulary instead of a fixed topic-specific
    lexicon.
    """
    latent_counts = _latent_reasoning_terminology_counts(text)
    runtime_counts = _agentic_runtime_terminology_counts(text)
    latent_signal = sum(latent_counts.values())
    runtime_signal = sum(runtime_counts.values())
    if runtime_signal > latent_signal:
        counts = runtime_counts
        edges = []
        if counts.get("runtime_orchestration") and counts.get("tool_execution"):
            edges.append("runtime_orchestration->tool_execution")
        if counts.get("tool_execution") and counts.get("memory_state"):
            edges.append("tool_execution->memory_state")
        if counts.get("memory_state") and counts.get("multi_agent_handoff"):
            edges.append("memory_state->multi_agent_handoff")
        if counts.get("multi_agent_handoff") and counts.get("evaluation_benchmark"):
            edges.append("multi_agent_handoff->evaluation_benchmark")
        if counts.get("evaluation_benchmark") and counts.get("safety_governance"):
            edges.append("evaluation_benchmark->safety_governance")
        if counts.get("safety_governance") and counts.get("observability_trace"):
            edges.append("safety_governance->observability_trace")
        return {
            "profile": "agentic_runtime",
            "counts": counts,
            "evolution_edges": edges,
        }

    edges = [
        "chain_of_thought->continuous_thought"
        for _ in [0]
        if latent_counts.get("chain_of_thought") and latent_counts.get("continuous_thought")
    ]
    if latent_counts.get("continuous_thought") and latent_counts.get("hidden_state"):
        edges.append("continuous_thought->hidden_state")
    if latent_counts.get("hidden_state") and latent_counts.get("latent_reasoning"):
        edges.append("hidden_state->latent_reasoning")
    if latent_counts.get("coconut") and latent_counts.get("latent_reasoning"):
        edges.append("coconut->latent_reasoning")
    return {
        "profile": "latent_reasoning",
        "counts": latent_counts,
        "evolution_edges": edges,
    }


def _terminology_counts(text: str) -> dict[str, int]:
    return dict(_terminology_profile(text).get("counts") or {})


def _academic_marker_counts(text: str) -> dict[str, int]:
    markers = {
        "taxonomy": r"taxonomy|分类|谱系",
        "mechanism": r"mechanism|机制|representation|表示",
        "evaluation_protocol": r"evaluation protocol|评估协议|metric|指标|benchmark|基准",
        "baseline_or_ablation": r"baseline|ablation|对照|消融",
        "reproducibility": r"reproducib|可复现|replication|复现实验",
        "deployment": r"deployment|部署|production|生产|engineering|工程",
        "failure_mode": r"failure mode|失败模式|局限|limitation",
        "controversy": r"contradiction|controversy|争议|反证|negative evidence",
        "auditability": r"audit|可审计|traceability|可追踪|observability|观测性",
        "evolution": r"evolution|演进|historical|历史|roadmap|路线图",
    }
    return {key: _count_pattern(text, pattern) for key, pattern in markers.items()}


def _build_depth_profile(
    root: Path,
    chapters: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    final_quality: dict[str, Any],
    literature_map: dict[str, Any],
    controversy_review: dict[str, Any],
) -> dict[str, Any]:
    contribution = _read_json(root / "survey_contribution_matrix.json")
    rows = contribution.get("rows") if isinstance(contribution, dict) and isinstance(contribution.get("rows"), list) else []
    final_path = root / "final.md"
    final_text = final_path.read_text(encoding="utf-8", errors="ignore") if final_path.exists() else ""
    finalized_sections = int(final_quality.get("finalized_sections") or 0)
    total_sections = len(sections)
    complete_context = bool(total_sections) and finalized_sections == total_sections

    structure_keys = [
        "has_architecture_synthesis",
        "has_comparative_positioning",
        "has_evaluation_boundary",
        "has_limitations_failure_modes",
        "has_contradiction_slots",
    ]
    complete_structure_rows = 0
    for row in rows:
        if all(row.get(key) for key in structure_keys):
            complete_structure_rows += 1
    chapter_structure_coverage = round(complete_structure_rows / max(len(rows), 1), 4)

    marker_counts = _academic_marker_counts(final_text)
    marker_variants = sorted(key for key, value in marker_counts.items() if value)
    terminology_profile = _terminology_profile(final_text)
    terminology_counts = dict(terminology_profile.get("counts") or {})
    terminology_variants = sorted(key for key, value in terminology_counts.items() if value)
    evolution_edges = list(terminology_profile.get("evolution_edges") or [])

    section_marker_rows: list[dict[str, Any]] = []
    covered_sections = 0
    for section in sections:
        section_id = str(section.get("section_id") or "")
        text_path = root / "sections" / section_id / "final.md"
        if not text_path.exists():
            continue
        counts = _academic_marker_counts(text_path.read_text(encoding="utf-8", errors="ignore"))
        variants = sorted(key for key, value in counts.items() if value)
        ok = len(variants) >= 5
        if ok:
            covered_sections += 1
        section_marker_rows.append({
            "section_id": section_id,
            "academic_marker_count": len(variants),
            "academic_markers": variants,
            "ok": ok,
        })
    section_marker_coverage = round(covered_sections / max(finalized_sections, 1), 4)

    claim_density = float(final_quality.get("claim_tag_density_per_1k_chars") or 0.0)
    evidence_density = float(final_quality.get("evidence_tag_density_per_1k_chars") or 0.0)
    issues: list[str] = []
    if complete_context and claim_density < 1.20:
        issues.append(f"depth_claim_tag_density_low:{claim_density:.4f}<1.2000")
    if complete_context and evidence_density < 1.50:
        issues.append(f"depth_evidence_tag_density_low:{evidence_density:.4f}<1.5000")
    if complete_context and chapter_structure_coverage < 0.95:
        issues.append(f"depth_chapter_structure_coverage_low:{chapter_structure_coverage:.4f}<0.9500")
    if complete_context and len(marker_variants) < 8:
        issues.append(f"depth_academic_marker_variety_low:{len(marker_variants)}<8")
    if complete_context and section_marker_coverage < 0.80:
        issues.append(f"depth_section_marker_coverage_low:{section_marker_coverage:.4f}<0.8000")
    if complete_context and len(terminology_variants) < 4:
        issues.append(f"depth_terminology_variant_count_low:{len(terminology_variants)}<4")
    if complete_context and len(evolution_edges) < 2:
        issues.append(f"depth_terminology_evolution_edges_low:{len(evolution_edges)}<2")
    if complete_context and not literature_map.get("ok"):
        issues.append("depth_literature_map_not_ok")
    if complete_context and not controversy_review.get("ok"):
        issues.append("depth_controversy_matrix_not_ok")
    return {
        "ok": not issues,
        "complete_context": complete_context,
        "finalized_sections": finalized_sections,
        "total_sections": total_sections,
        "claim_tag_density_per_1k_chars": claim_density,
        "evidence_tag_density_per_1k_chars": evidence_density,
        "chapter_structure_coverage": chapter_structure_coverage,
        "academic_marker_counts": marker_counts,
        "academic_marker_variants": marker_variants,
        "section_marker_coverage": section_marker_coverage,
        "section_marker_rows": section_marker_rows[:200],
        "terminology_profile": str(terminology_profile.get("profile") or ""),
        "terminology_counts": terminology_counts,
        "terminology_variants": terminology_variants,
        "terminology_evolution_edges": evolution_edges,
        "literature_map_ok": bool(literature_map.get("ok")),
        "controversy_matrix_ok": bool(controversy_review.get("ok")),
        "issues": issues,
    }


def assess_survey_quality(output_dir: str | Path, ast: dict | None = None, packs: dict | None = None) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    ast = ast or _read_json(root / "survey_report_ast.json")
    packs = packs or _read_json(root / "survey_evidence_packs.json")
    chapters = ast.get("chapters", []) if isinstance(ast.get("chapters"), list) else []
    sections = ast.get("sections", []) if isinstance(ast.get("sections"), list) else []
    sources = _read_jsonl(root / "sources.jsonl")
    evidence_rows = _read_jsonl(root / "evidence.jsonl")
    source_types = {str(row.get("source_type") or "") for row in sources if row.get("source_type")}
    required_source_types = _required_types_from_source_matrix(root)
    chapter_axes = sorted({_chapter_axis(str(row.get("title") or "")) for row in chapters if isinstance(row, dict)})
    method_axis_present = "method_taxonomy" in chapter_axes or "architecture" in chapter_axes
    evaluation_axis_present = "evaluation" in chapter_axes
    contradiction_axis_present = "contradiction" in chapter_axes
    taxonomy_depth_score = round(
        min(len(chapter_axes) / 8, 1.0)
        * min(max(len(required_source_types), len(source_types)) / 4, 1.0)
        * (1.0 if method_axis_present and evaluation_axis_present else 0.5),
        4,
    )
    taxonomy = {
        "ok": taxonomy_depth_score >= 0.75,
        "taxonomy_depth_score": taxonomy_depth_score,
        "chapter_axes": chapter_axes,
        "required_source_types": sorted(required_source_types),
        "observed_source_types": sorted(source_types),
        "method_axis_present": method_axis_present,
        "evaluation_axis_present": evaluation_axis_present,
        "contradiction_axis_present": contradiction_axis_present,
    }

    pack_rows = packs.get("packs", []) if isinstance(packs.get("packs"), list) else []
    required_contradictions = len(sections)
    covered = 0
    missing: list[str] = []
    for section in sections:
        section_id = str(section.get("section_id") or "")
        pack = next((row for row in pack_rows if str(row.get("section_id") or "") == section_id), {})
        slots = [slot for slot in pack.get("contradiction_slots", []) if str(slot).strip()]
        if slots:
            covered += 1
        elif section_id:
            missing.append(section_id)
    contradiction_coverage = round(covered / max(required_contradictions, 1), 4)
    contradiction_matrix = {
        "ok": contradiction_coverage >= 0.80,
        "contradiction_coverage": contradiction_coverage,
        "required_sections": required_contradictions,
        "covered_sections": covered,
        "missing_section_ids": missing[:50],
        "contradiction_axis_present": contradiction_axis_present,
    }
    section_factual_audit = _section_factual_audit(root, sections, pack_rows, evidence_rows)
    section_scorecard = _build_section_scorecard(root, sections, pack_rows, section_factual_audit)
    final_quality = _build_final_quality(root, ast, sections)
    source_coverage = _build_source_coverage(root, sections)
    literature_map = _build_literature_map(root, chapters, sections, pack_rows)
    controversy_review = _build_controversy_review(chapters, sections, pack_rows)
    chapter_review = _build_chapter_review(root, chapters, sections, pack_rows, section_scorecard)
    chief_editor_review = _build_chief_editor_review(root, chapters, sections, chapter_review, literature_map, controversy_review)
    depth_profile = _build_depth_profile(root, chapters, sections, final_quality, literature_map, controversy_review)

    payload = {
        "ok": taxonomy["ok"] and contradiction_matrix["ok"] and section_factual_audit["ok"] and section_scorecard["ok"] and final_quality["ok"] and source_coverage["ok"] and literature_map["ok"] and controversy_review["ok"] and chapter_review["ok"] and chief_editor_review["ok"] and depth_profile["ok"],
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
    (root / "survey_taxonomy.json").write_text(json.dumps(taxonomy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "survey_contradiction_matrix.json").write_text(json.dumps(contradiction_matrix, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "survey_section_factual_audit.json").write_text(json.dumps(section_factual_audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "survey_section_scorecard.json").write_text(json.dumps(section_scorecard, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "survey_final_quality.json").write_text(json.dumps(final_quality, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "survey_source_coverage.json").write_text(json.dumps(source_coverage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "survey_literature_map.json").write_text(json.dumps(literature_map, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "survey_controversy_matrix.json").write_text(json.dumps(controversy_review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "survey_chapter_review.json").write_text(json.dumps(chapter_review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "survey_chief_editor.json").write_text(json.dumps(chief_editor_review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "survey_depth_profile.json").write_text(json.dumps(depth_profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
