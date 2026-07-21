"""Compile survey sections from specs and evidence packs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from research.report_metrics import append_execution_metrics_section, write_execution_metrics

from .schemas import ChapterEditorialReview, SectionReview, to_dict
from .writing_loop import run_section_revision_loop


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def compile_section(output_dir: str | Path, section_id: str, finalize: bool = True) -> dict:
    root = Path(output_dir).expanduser()
    section_dir = root / "sections" / section_id
    spec = _read_json(section_dir / "section.spec.json")
    pack = _read_json(section_dir / "evidence_pack.json")
    section_dir.mkdir(parents=True, exist_ok=True)
    if not spec:
        return {"ok": False, "section_id": section_id, "reason": "section_spec_missing"}
    if not pack:
        return {"ok": False, "section_id": section_id, "reason": "evidence_pack_missing"}
    if pack.get("status") != "ready":
        review = SectionReview(
            section_id=section_id,
            verdict="BLOCKED",
            unsupported_claim_rate=1.0,
            citation_span_accuracy=0.0,
            source_diversity_score=0.0,
            repetition_score=0.0,
            issues=list(pack.get("blockers") or ["evidence_pack_blocked"]),
        )
        (section_dir / "review.json").write_text(json.dumps(to_dict(review), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"ok": False, "section_id": section_id, "reason": "evidence_pack_blocked", "review": to_dict(review)}
    return run_section_revision_loop(output_dir, section_id, finalize=finalize)


def _extract_tags(text: str, tag: str) -> list[str]:
    return [item.strip() for item in re.findall(rf"\[{re.escape(tag)}:([^\]]+)\]", text or "") if item.strip()]


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _source_type_counts(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in _read_jsonl(root / "sources.jsonl"):
        source_type = str(row.get("source_type") or "unknown")
        counts[source_type] = counts.get(source_type, 0) + 1
    return counts


def _source_lookup(root: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("id") or row.get("source_id") or ""): row for row in _read_jsonl(root / "sources.jsonl")}


def _evidence_lookup(root: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("id") or row.get("evidence_id") or ""): row for row in _read_jsonl(root / "evidence.jsonl")}


def _section_final(root: Path, section_id: str) -> str:
    path = root / "sections" / section_id / "final.md"
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def _build_contribution_matrix(root: Path, ast: dict) -> dict:
    rows = []
    for section in ast.get("sections", []):
        section_id = str(section.get("section_id") or "")
        text = _section_final(root, section_id)
        claims = sorted(set(_extract_tags(text, "claim")))
        evidence = sorted(set(_extract_tags(text, "evidence")))
        headings = [line.strip("# ").strip() for line in text.splitlines() if line.startswith("## ")]
        rows.append({
            "section_id": section_id,
            "chapter_id": str(section.get("chapter_id") or ""),
            "title": str(section.get("title") or section_id),
            "status": "finalized" if text else "pending",
            "claim_ids": claims,
            "evidence_ids": evidence,
            "claim_count": len(claims),
            "evidence_count": len(evidence),
            "has_literature_lineage": "Literature Lineage" in text,
            "has_method_taxonomy": "Method Taxonomy" in text,
            "has_architecture_synthesis": "Architecture Synthesis" in text,
            "has_comparative_positioning": "Comparative Positioning" in text,
            "has_terminology_evolution": "Terminology Evolution" in text,
            "has_evaluation_protocol_matrix": "Evaluation Protocol Matrix" in text,
            "has_evaluation_boundary": "Evaluation And Risk Boundary" in text,
            "has_limitations_failure_modes": "Limitations And Failure Modes" in text,
            "has_controversy_matrix": "Controversy Matrix" in text,
            "has_contradiction_slots": "Contradiction Slots" in text,
            "headings": headings[:20],
        })
    finalized = [row for row in rows if row["status"] == "finalized"]
    payload = {
        "ok": True,
        "section_count": len(rows),
        "finalized_sections": len(finalized),
        "pending_sections": len(rows) - len(finalized),
        "source_type_counts": _source_type_counts(root),
        "total_claim_tags": sum(row["claim_count"] for row in rows),
        "total_evidence_tags": sum(row["evidence_count"] for row in rows),
        "rows": rows,
    }
    (root / "survey_contribution_matrix.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _chapter_sections(ast: dict, chapter_id: str) -> list[dict]:
    return [
        section for section in ast.get("sections", [])
        if str(section.get("chapter_id") or "") == chapter_id
    ]


def _build_chapter_synthesis(root: Path, chapter: dict, sections: list[dict], matrix_rows: list[dict]) -> tuple[str, list[str]]:
    chapter_id = str(chapter.get("chapter_id") or "")
    title = str(chapter.get("title") or chapter_id)
    objective = str(chapter.get("objective") or "N/A")
    finalized_rows = [row for row in matrix_rows if row.get("chapter_id") == chapter_id and row.get("status") == "finalized"]
    missing = [str(section.get("section_id") or "") for section in sections if not _section_final(root, str(section.get("section_id") or ""))]
    claim_total = sum(int(row.get("claim_count") or 0) for row in finalized_rows)
    evidence_total = sum(int(row.get("evidence_count") or 0) for row in finalized_rows)
    coverage_bits = []
    for key, label in [
        ("has_architecture_synthesis", "architecture"),
        ("has_comparative_positioning", "comparison"),
        ("has_evaluation_boundary", "evaluation"),
        ("has_limitations_failure_modes", "limitations"),
        ("has_contradiction_slots", "contradiction"),
    ]:
        covered = sum(1 for row in finalized_rows if row.get(key))
        coverage_bits.append(f"{label}:{covered}/{max(len(finalized_rows), 1)}")
    primary_gap = "missing finalized section evidence" if missing else "cross-section claim alignment"
    section_titles = [str(row.get("title") or row.get("section_id") or "") for row in finalized_rows[:3]]
    section_focus = "; ".join(section_titles) if section_titles else "N/A"
    synthesis = [
        f"# {title}",
        "",
        "## Chapter Synthesis",
        "",
        f"{chapter_id} compiles {len(finalized_rows)}/{len(sections)} finalized sections for '{title}'. It carries {claim_total} claim tags and {evidence_total} evidence tags into the final report while preserving the chapter objective: {objective}.",
        "",
        "## Contribution Coverage",
        "",
        "- " + "\n- ".join(coverage_bits) if coverage_bits else "- N/A",
        "",
        "## Chapter-Level Open Problems",
        "",
        f"{chapter_id} preserves unresolved evidence gaps around {primary_gap}, contradiction slots from {len(finalized_rows)} finalized sections, and consistency risks across representative sections: {section_focus}. Chief-editor review for '{title}' should verify that this chapter objective remains bounded: {objective}.",
        "",
    ]
    return "\n".join(synthesis), missing


def _build_final_summary(root: Path, ast: dict, contribution: dict, chapter_reviews: list[dict]) -> dict:
    finalized = int(contribution.get("finalized_sections") or 0)
    total = int(contribution.get("section_count") or 0)
    source_counts = contribution.get("source_type_counts") if isinstance(contribution.get("source_type_counts"), dict) else {}
    source_summary = ", ".join(f"{key}={value}" for key, value in sorted(source_counts.items())) or "N/A"
    pending = int(contribution.get("pending_sections") or 0)
    review_issues = [issue for review in chapter_reviews for issue in review.get("issues", [])]
    payload = {
        "ok": True,
        "title": ast.get("title", "Professor-Grade Survey"),
        "executive_summary": [
            f"This survey compiles {finalized}/{total} finalized sections into a structured technical report.",
            f"The evidence base covers source types: {source_summary}.",
            "The report separates architecture synthesis, comparison, evaluation boundaries, limitations, contradictions, and open problems.",
        ],
        "technical_summary": [
            f"Claim tags: {contribution.get('total_claim_tags', 0)}.",
            f"Evidence tags: {contribution.get('total_evidence_tags', 0)}.",
            f"Pending sections: {pending}.",
            f"Chapter review issue count: {len(review_issues)}.",
        ],
        "roadmap": [
            "Use contribution gaps to drive section rewrites.",
            "Use chapter synthesis outputs for chief-editor coherence review.",
            "Use source/evidence ledgers to prevent unsupported expansion in final prose.",
        ],
    }
    (root / "survey_final_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


_HUMAN_SECTION_HEADINGS = {
    "position",
    "architecture synthesis",
    "comparative positioning",
    "evaluation and risk boundary",
    "limitations and failure modes",
    "controversy matrix",
    "contradiction slots",
    "open problems",
}

_HUMAN_DROP_PATTERNS = [
    re.compile(r"prompt packet", re.I),
    re.compile(r"只使用\s*prompt", re.I),
    re.compile(r"未列入清单"),
    re.compile(r"不得编造"),
    re.compile(r"本节坚持"),
    re.compile(r"本节不引入"),
    re.compile(r"本节只"),
    re.compile(r"本节不"),
    re.compile(r"Source Map", re.I),
    re.compile(r"Claim Map", re.I),
    re.compile(r"Evidence Map", re.I),
    re.compile(r"本节闭合于"),
    re.compile(r"本节向章级综合"),
    re.compile(r"为支持主编辑"),
    re.compile(r"矛盾槽位"),
    re.compile(r"Contradiction", re.I),
]


def _split_markdown_sections(text: str) -> dict[str, str]:
    blocks: dict[str, list[str]] = {}
    current = ""
    for line in (text or "").splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = match.group(1).strip().lower()
            blocks.setdefault(current, [])
            continue
        if current:
            blocks.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in blocks.items() if "\n".join(value).strip()}


def _clean_human_text(text: str, evidence_numbers: dict[str, int]) -> str:
    cleaned_lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^\s*[-*]\s+", "", line).strip()
        line = re.sub(r"^\s*\d+[.)]\s*", "", line).strip()
        if not line or re.fullmatch(r"\d+[.)]?", line):
            continue
        if line.endswith(("：", ":")):
            continue
        if any(pattern.search(line) for pattern in _HUMAN_DROP_PATTERNS):
            continue
        line = re.sub(r"^本节(?:的)?立场(?:是)?[：:]\s*", "", line)
        line = re.sub(r"^本节(?:的)?(?:认为|判断|主张)(?:是)?[：:]?\s*", "", line)
        line = re.sub(r"^本节(?:的)?工程风险边界", "工程风险边界", line)
        line = re.sub(r"^本节(?:的)?风险边界", "风险边界", line)
        line = re.sub(r"^本节(?:的)?局限", "局限", line)
        line = re.sub(r"^本节存在", "这里存在", line)
        line = re.sub(r"^本节绑定", "绑定", line)
        line = re.sub(r"^本节据此", "据此", line)
        for old, new in {
            "落到本节绑定的": "落到绑定的",
            "本节绑定": "绑定",
            "本节按": "按",
            "本节通过": "通过",
            "本节据此": "据此",
            "本节因此": "因此",
            "本节明确反对": "本文反对",
            "本节自我设定": "这里设定",
            "本节使用的": "这里使用的",
            "本节给出": "这里给出",
            "本节定义": "这里定义",
            "本节立场是": "本文判断",
            "本节立场": "本文判断",
            "本节认为": "本文认为",
            "本节无法": "目前无法",
            "与本节": "与上述",
        }.items():
            line = line.replace(old, new)
        line = re.sub(r"\[claim:[^\]]+\]", "", line)
        line = re.sub(
            r"\[evidence:([^\]]+)\]",
            lambda match: f"[^{evidence_numbers.setdefault(match.group(1), len(evidence_numbers) + 1)}]",
            line,
        )
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _first_units(text: str, limit: int = 2, max_chars: int = 700) -> list[str]:
    cleaned = re.sub(r"\n+", "\n", text or "").strip()
    units: list[str] = []
    for part in re.split(r"(?<=[。！？.!?])\s+|\n+", cleaned):
        part = part.strip()
        if not part:
            continue
        if len(part) < 24:
            continue
        if part.endswith(("：", ":")):
            continue
        if re.fullmatch(r"\d+[.)]?", part):
            continue
        if re.match(r"^(把|按|在|从|将).{0,28}(如下|可见|对照|排开|合成|组合|分类)", part):
            continue
        if "开放问题" in part and len(part) < 80:
            continue
        units.append(part)
        if len(units) >= limit or sum(len(item) for item in units) >= max_chars:
            break
    return units


def _append_unique(items: list[str], candidates: list[str], *, max_items: int) -> None:
    seen = {re.sub(r"\s+", " ", item).strip() for item in items}
    for candidate in candidates:
        key = re.sub(r"\s+", " ", candidate).strip()
        if not key or key in seen:
            continue
        items.append(candidate)
        seen.add(key)
        if len(items) >= max_items:
            break


def _human_chapter_block(root: Path, chapter: dict, sections: list[dict], evidence_numbers: dict[str, int]) -> tuple[str, dict[str, int]]:
    title = str(chapter.get("title") or chapter.get("chapter_id") or "N/A")
    positions: list[str] = []
    mechanisms: list[str] = []
    comparisons: list[str] = []
    risks: list[str] = []
    open_problems: list[str] = []
    for section in sections:
        text = _section_final(root, str(section.get("section_id") or ""))
        if not text:
            continue
        blocks = _split_markdown_sections(text)
        for heading, target, limit in [
            ("position", positions, 2),
            ("architecture synthesis", mechanisms, 2),
            ("comparative positioning", comparisons, 1),
            ("evaluation and risk boundary", risks, 1),
            ("limitations and failure modes", risks, 1),
            ("controversy matrix", risks, 1),
            ("contradiction slots", risks, 1),
            ("open problems", open_problems, 1),
        ]:
            content = blocks.get(heading, "")
            if not content:
                continue
            cleaned = _clean_human_text(content, evidence_numbers)
            _append_unique(target, _first_units(cleaned, limit=limit), max_items=6)

    metrics = {
        "positions": len(positions),
        "mechanisms": len(mechanisms),
        "comparisons": len(comparisons),
        "risks": len(risks),
        "open_problems": len(open_problems),
    }
    lines = [f"## {title}", ""]
    if positions:
        lines.extend(["### 本章判断", "", *[f"- {item}" for item in positions[:4]], ""])
    if mechanisms:
        lines.extend(["### 技术机制", "", *[f"- {item}" for item in mechanisms[:4]], ""])
    if comparisons:
        lines.extend(["### 横向比较", "", *[f"- {item}" for item in comparisons[:3]], ""])
    if risks:
        lines.extend(["### 风险与争议", "", *[f"- {item}" for item in risks[:4]], ""])
    if open_problems:
        lines.extend(["### 未解问题", "", *[f"- {item}" for item in open_problems[:3]], ""])
    return "\n".join(lines).strip() + "\n", metrics


def _build_human_readable_final(root: Path, ast: dict, contribution: dict) -> dict:
    evidence_numbers: dict[str, int] = {}
    source_counts = contribution.get("source_type_counts") if isinstance(contribution.get("source_type_counts"), dict) else {}
    evidence_rows = _evidence_lookup(root)
    source_rows = _source_lookup(root)
    chapters = ast.get("chapters", []) if isinstance(ast.get("chapters"), list) else []
    sections = ast.get("sections", []) if isinstance(ast.get("sections"), list) else []
    section_by_chapter: dict[str, list[dict]] = {}
    for section in sections:
        section_by_chapter.setdefault(str(section.get("chapter_id") or ""), []).append(section)

    chapter_blocks: list[str] = []
    chapter_metrics: list[dict[str, Any]] = []
    for chapter in chapters:
        chapter_id = str(chapter.get("chapter_id") or "")
        block, metrics = _human_chapter_block(root, chapter, section_by_chapter.get(chapter_id, []), evidence_numbers)
        chapter_blocks.append(block)
        chapter_metrics.append({"chapter_id": chapter_id, **metrics})

    source_summary = "、".join(f"{key} {value}" for key, value in sorted(source_counts.items())) or "N/A"
    title = str(ast.get("title") or "Professor-Grade Survey")
    lines = [
        f"# {title}",
        "",
        "## 核心结论",
        "",
        "2026 年的 Agentic Runtime 已经从“会调用工具的 LLM 应用”变成一类独立的执行系统：它必须同时处理长时状态、可恢复执行、控制权转移、执行边界安全、动作/权限/副作用风险，以及 session/state/artifact 生命周期治理。当前行业的主要矛盾不是缺少框架，而是框架文档、源码实现、外部 benchmark 与生产部署证据之间尚未形成闭环。",
        "",
        "## 证据基础",
        "",
        f"本报告基于 {int(contribution.get('finalized_sections') or 0)}/{int(contribution.get('section_count') or 0)} 个已审阅 section，来源类型覆盖：{source_summary}。正文只保留关键脚注；完整 claim/evidence ledger 保留在机器审计产物中。",
        "",
        *chapter_blocks,
    ]

    if evidence_numbers:
        lines.extend(["## 证据脚注", ""])
        for evidence_id, number in sorted(evidence_numbers.items(), key=lambda item: item[1]):
            evidence = evidence_rows.get(evidence_id, {})
            source = source_rows.get(str(evidence.get("source_id") or ""), {})
            title_text = str(source.get("title") or evidence.get("title") or evidence_id)
            source_type = str(source.get("source_type") or "unknown")
            url = str(source.get("url") or "")
            line = f"[^{number}]: {title_text} ({source_type})"
            if url:
                line += f" {url}"
            lines.append(line)
        lines.append("")

    text = "\n".join(lines).strip() + "\n"
    text, execution_metrics = append_execution_metrics_section(text, root)
    human_path = root / "human_final.md"
    human_path.write_text(text, encoding="utf-8")
    metrics_path = root / "survey_human_execution_metrics.json"
    write_execution_metrics(metrics_path, execution_metrics)
    summary = {
        "ok": True,
        "human_final_md": str(human_path),
        "char_count": len(text),
        "chapter_count": len(chapters),
        "evidence_note_count": len(evidence_numbers),
        "template_heading_count": sum(text.count(f"## {heading}") for heading in _HUMAN_SECTION_HEADINGS),
        "chapter_metrics": chapter_metrics,
        "execution_metrics": execution_metrics,
        "execution_metrics_path": str(metrics_path),
    }
    (root / "survey_human_final_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def compile_survey(output_dir: str | Path) -> dict:
    root = Path(output_dir).expanduser()
    ast = _read_json(root / "survey_report_ast.json")
    contribution = _build_contribution_matrix(root, ast)
    matrix_rows = contribution.get("rows", []) if isinstance(contribution.get("rows"), list) else []
    chapter_reviews: list[dict] = []
    chapter_blocks: list[str] = []
    finalized = 0
    for chapter in ast.get("chapters", []):
        chapter_dir = root / "chapters" / str(chapter.get("chapter_id"))
        chapter_dir.mkdir(parents=True, exist_ok=True)
        sections = _chapter_sections(ast, str(chapter.get("chapter_id") or ""))
        chapter_synthesis, missing = _build_chapter_synthesis(root, chapter, sections, matrix_rows)
        chapter_lines = [chapter_synthesis, ""]
        block_lines = [f"## {chapter.get('title')}", "", chapter_synthesis, ""]
        for section in ast.get("sections", []):
            if section.get("chapter_id") != chapter.get("chapter_id"):
                continue
            final = root / "sections" / str(section.get("section_id")) / "final.md"
            if final.exists():
                text = final.read_text(encoding="utf-8")
                block_lines.extend([text, ""])
                chapter_lines.extend([text, ""])
                finalized += 1
            else:
                block_lines.extend([f"### {section.get('title')}", "", "Status: pending final section.", ""])
        chapter_section_ids = [
            str(section.get("section_id"))
            for section in ast.get("sections", [])
            if section.get("chapter_id") == chapter.get("chapter_id")
        ]
        issues = []
        if missing:
            issues.append(f"missing_sections:{len(missing)}")
        review = ChapterEditorialReview(
            chapter_id=str(chapter.get("chapter_id")),
            verdict="PASS" if not missing else "REVISE",
            finalized_sections=len(chapter_section_ids) - len(missing),
            missing_sections=missing,
            issues=issues,
        )
        chapter_reviews.append(to_dict(review))
        (chapter_dir / "synthesis.md").write_text("\n".join(chapter_lines), encoding="utf-8")
        (chapter_dir / "editorial_review.json").write_text(json.dumps(to_dict(review), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (chapter_dir / "review.json").write_text(json.dumps(to_dict(review), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        chapter_blocks.append("\n".join(block_lines))
    final_summary = _build_final_summary(root, ast, contribution, chapter_reviews)
    lines = [
        f"# {ast.get('title', 'Professor-Grade Survey')}",
        "",
        "## Executive Summary",
        "",
        *[f"- {item}" for item in final_summary["executive_summary"]],
        "",
        "## Technical Summary",
        "",
        *[f"- {item}" for item in final_summary["technical_summary"]],
        "",
        "## Contribution Matrix",
        "",
        "| Section | Claims | Evidence | Architecture | Comparison | Evaluation | Limitations | Contradictions |",
        "| --- | ---: | ---: | --- | --- | --- | --- | --- |",
    ]
    for row in matrix_rows:
        lines.append(
            f"| {row.get('section_id')} | {row.get('claim_count')} | {row.get('evidence_count')} | "
            f"{'yes' if row.get('has_architecture_synthesis') else 'no'} | "
            f"{'yes' if row.get('has_comparative_positioning') else 'no'} | "
            f"{'yes' if row.get('has_evaluation_boundary') else 'no'} | "
            f"{'yes' if row.get('has_limitations_failure_modes') else 'no'} | "
            f"{'yes' if row.get('has_contradiction_slots') else 'no'} |"
        )
    lines.extend(["", "## Roadmap", ""])
    lines.extend(f"- {item}" for item in final_summary["roadmap"])
    lines.extend(["", *chapter_blocks])
    final_text, execution_metrics = append_execution_metrics_section("\n".join(lines), root)
    final_path = root / "final.md"
    final_path.write_text(final_text, encoding="utf-8")
    metrics_path = root / "survey_execution_metrics.json"
    write_execution_metrics(metrics_path, execution_metrics)
    human_summary = _build_human_readable_final(root, ast, contribution)
    return {
        "ok": True,
        "final_md": str(final_path),
        "human_final_md": human_summary.get("human_final_md"),
        "finalized_sections": finalized,
        "total_sections": len(ast.get("sections", [])),
        "contribution_matrix": str(root / "survey_contribution_matrix.json"),
        "final_summary": str(root / "survey_final_summary.json"),
        "human_final_summary": str(root / "survey_human_final_summary.json"),
        "execution_metrics": execution_metrics,
        "execution_metrics_path": str(metrics_path),
        "human_execution_metrics": human_summary.get("execution_metrics"),
    }
