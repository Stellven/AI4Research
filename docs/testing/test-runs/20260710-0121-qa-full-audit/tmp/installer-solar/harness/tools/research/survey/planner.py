"""Survey planner for 5-10 万字 DeepResearch reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schemas import (
    ChapterSpec,
    SectionSpec,
    SourceMatrix,
    SurveyQuestion,
    SurveyReportAST,
    SurveyRun,
    to_dict,
)

DEFAULT_CHAPTER_TITLES = [
    "问题定义与研究边界",
    "历史脉络与技术演进",
    "核心架构范式",
    "方法分类与代表系统",
    "评估方法与基准体系",
    "工程实现与部署约束",
    "风险、安全与可解释性",
    "产业生态与开源实现",
    "争议、反证与失败模式",
    "未来路线图与开放问题",
]

DEFAULT_SECTION_TITLES = [
    "研究问题与术语边界",
    "关键机制与设计空间",
    "证据链与代表工作",
    "工程取舍与评价标准",
]


def _stable_id(prefix: str, text: str) -> str:
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"


def chapter_count_for_target(target_chars: int) -> int:
    if target_chars >= 90000:
        return 12
    if target_chars >= 70000:
        return 10
    return 8


def sections_per_chapter(target_chars: int) -> int:
    return 4 if target_chars < 90000 else 5


def create_survey_plan(
    brief: str,
    target_chars: int = 50000,
    audience: str = "technical",
    domain: str = "ai",
    run_id: str | None = None,
) -> dict:
    run_id = run_id or _stable_id("survey", brief + str(target_chars))
    chapters_n = chapter_count_for_target(target_chars)
    per_chapter = sections_per_chapter(target_chars)
    total_sections = chapters_n * per_chapter
    chapter_chars = max(target_chars // chapters_n, 1)
    section_chars = max(target_chars // total_sections, 1)

    run = SurveyRun(run_id=run_id, brief=brief, target_chars=target_chars, audience=audience, domain=domain)
    chapters: list[ChapterSpec] = []
    sections: list[SectionSpec] = []
    questions: list[SurveyQuestion] = []
    source_matrix: list[SourceMatrix] = []

    for cidx in range(1, chapters_n + 1):
        title = DEFAULT_CHAPTER_TITLES[(cidx - 1) % len(DEFAULT_CHAPTER_TITLES)]
        chapter_id = f"ch{cidx:02d}"
        chapters.append(ChapterSpec(
            chapter_id=chapter_id,
            title=title,
            order=cidx,
            target_chars=chapter_chars,
            objective=f"Explain {title} for {brief}.",
        ))
        parent_q = SurveyQuestion(
            question_id=f"q{cidx:02d}",
            text=f"{brief}: {title} 的核心问题是什么？",
            depth=0,
            required_source_types=["paper", "official_doc", "code", "benchmark"],
        )
        questions.append(parent_q)
        for sidx in range(1, per_chapter + 1):
            section_id = f"{chapter_id}/sec{sidx:02d}"
            section_title = DEFAULT_SECTION_TITLES[(sidx - 1) % len(DEFAULT_SECTION_TITLES)]
            required = ["paper", "official_doc"] if sidx == 1 else ["paper", "code"] if sidx == 2 else ["paper", "benchmark"]
            sections.append(SectionSpec(
                section_id=section_id,
                chapter_id=chapter_id,
                title=f"{title}：{section_title}",
                order=(cidx - 1) * per_chapter + sidx,
                target_chars=section_chars,
                research_question=f"{brief} 在“{title}/{section_title}”上的证据、架构取舍和争议是什么？",
                required_source_types=required,
                min_evidence=4,
                min_claims=3,
            ))
            questions.append(SurveyQuestion(
                question_id=f"q{cidx:02d}_{sidx:02d}",
                text=f"{brief}: {title} / {section_title}",
                parent_id=parent_q.question_id,
                depth=1,
                required_source_types=required,
            ))
            source_matrix.append(SourceMatrix(
                section_id=section_id,
                required_source_types=required,
                recommended_source_types=["survey", "review", "dataset", "negative_result"],
                min_sources=4,
                min_evidence=4,
                contradiction_required=True,
            ))

    ast = SurveyReportAST(
        ast_id=_stable_id("survey_ast", run_id + brief),
        run_id=run_id,
        title=f"Professor-Grade Survey: {brief}",
        target_chars=target_chars,
        chapters=chapters,
        sections=sections,
    )
    return {
        "run": to_dict(run),
        "questions": to_dict(questions),
        "source_matrix": to_dict(source_matrix),
        "report_ast": to_dict(ast),
    }


def write_survey_plan(plan: dict, output_dir: str | Path) -> dict:
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    files = {
        "survey_plan": root / "survey_plan.json",
        "survey_report_ast": root / "survey_report_ast.json",
        "source_matrix": root / "survey_source_matrix.json",
    }
    files["survey_plan"].write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files["survey_report_ast"].write_text(json.dumps(plan["report_ast"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files["source_matrix"].write_text(json.dumps(plan["source_matrix"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {key: str(path) for key, path in files.items()}
