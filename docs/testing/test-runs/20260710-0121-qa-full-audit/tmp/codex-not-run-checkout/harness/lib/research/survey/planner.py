"""Survey planner for 5-10 万字 DeepResearch reports."""

from __future__ import annotations

import hashlib
import json
import re
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

CONFERENCE_CHAPTER_TITLES = [
    "问题定义与研究边界",
    "会议主议题与问题迁移",
    "论文热点与核心分歧",
    "规划、记忆与深度研究",
    "协议、规格与多 Agent 协作",
    "评测、基准与工程约束",
    "对 Solar 的吸收路径",
    "风险与后续实验",
]

CONFERENCE_SECTION_TITLES = [
    "会议在讨论什么问题",
    "代表论文与议题观点",
    "核心分歧与技术挑战",
    "对 Solar 的启示",
]


def _stable_id(prefix: str, text: str) -> str:
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"


def _normalize_brief(brief: str) -> str:
    return re.sub(r"\s+", " ", str(brief or "").strip())


def _is_conference_insight_brief(brief: str) -> bool:
    text = _normalize_brief(brief).lower()
    conference_signals = ("会议", "学术会议", "conference", "accepted papers", "workshops", "paper index", "program/")
    intent_signals = ("洞察", "发表问题", "讨论问题", "重大技术挑战", "如何发展")
    return any(token in text for token in conference_signals) and any(token in text for token in intent_signals)


def _conference_subject(brief: str) -> str:
    text = _normalize_brief(brief)
    match = re.search(r"\b([A-Z]{2,}\s*20\d{2})\b", text)
    if match:
        return re.sub(r"\s+", " ", match.group(1).strip()).upper()
    zh_match = re.search(r"([A-Za-z]{2,}\s*20\d{2}|20\d{2}\s*[A-Za-z]{2,})", text)
    if zh_match:
        return re.sub(r"\s+", " ", zh_match.group(1).strip()).upper()
    return text[:32] if text else "该会议"


def _conference_report_title(brief: str) -> str:
    subject = _conference_subject(brief)
    if "solar" in brief.lower():
        return f"深度报告：{subject} Agent 发展、技术挑战与 Solar 路线"
    return f"深度报告：{subject} Agent 议题与技术挑战"


def _chapter_objective(brief: str, title: str, *, conference_mode: bool) -> str:
    if not conference_mode:
        return f"Explain {title} for {brief}."
    subject = _conference_subject(brief)
    objective_map = {
        "问题定义与研究边界": f"Summarize what problems {subject} is actually defining for Agent systems, based on conference tracks, accepted papers, and workshops; avoid generic methodology talk.",
        "会议主议题与问题迁移": f"Explain how {subject} shifts the discussion from model capability to system capability, using official tracks and conference framing.",
        "论文热点与核心分歧": f"Extract the main problem clusters and disagreements emerging from {subject} accepted papers instead of listing papers mechanically.",
        "规划、记忆与深度研究": f"Synthesize how {subject} papers redefine planning horizon, long-horizon memory, and deep research workflows.",
        "协议、规格与多 Agent 协作": f"Explain how {subject} frames protocols, specifications, and multi-agent coordination as first-class system problems.",
        "评测、基准与工程约束": f"Summarize what {subject} implies for evaluation, benchmarking, deployment constraints, and operational cost.",
        "对 Solar 的吸收路径": f"Translate {subject} insights into concrete Solar architecture, product, and runtime absorption paths.",
        "风险与后续实验": f"Turn {subject} signals into falsifiable risks, open questions, and next experiments for Solar.",
    }
    return objective_map.get(title, f"Summarize {title} from {subject} conference signals and paper viewpoints.")


def _section_research_question(brief: str, chapter_title: str, section_title: str, *, conference_mode: bool) -> str:
    if not conference_mode:
        return f"{brief} 在“{chapter_title}/{section_title}”上的证据、架构取舍和争议是什么？"
    subject = _conference_subject(brief)
    section_map = {
        "会议在讨论什么问题": f"{subject} 在“{chapter_title}”这一章实际把 Agent 定义成了哪些系统问题？这些问题是从 conference tracks、accepted papers 和 workshops 里如何体现出来的？",
        "代表论文与议题观点": f"{subject} 的代表论文、official pages 和 workshops 在“{chapter_title}”上分别提出了什么判断？哪些观点彼此呼应？",
        "核心分歧与技术挑战": f"{subject} 在“{chapter_title}”上暴露出哪些尚未解决的技术挑战、分歧和工程难点？",
        "对 Solar 的启示": f"基于 {subject} 在“{chapter_title}”上的会议信号，Solar 应吸收哪些思想、避免哪些误判、优先建设哪些能力？",
    }
    return section_map.get(section_title, f"{subject} 在“{chapter_title}/{section_title}”上的会议观点、主要挑战和对 Solar 的启示是什么？")


def _question_text(brief: str, chapter_title: str, section_title: str | None = None, *, conference_mode: bool) -> str:
    if not conference_mode:
        return f"{brief}: {chapter_title}" if section_title is None else f"{brief}: {chapter_title} / {section_title}"
    subject = _conference_subject(brief)
    if section_title is None:
        return f"{subject}: {chapter_title} 这章应该总结哪些会议级问题？"
    return f"{subject}: {chapter_title} / {section_title}"


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
    conference_mode = _is_conference_insight_brief(brief)
    chapter_titles = CONFERENCE_CHAPTER_TITLES if conference_mode else DEFAULT_CHAPTER_TITLES
    section_titles = CONFERENCE_SECTION_TITLES if conference_mode else DEFAULT_SECTION_TITLES
    chapters_n = chapter_count_for_target(target_chars)
    if conference_mode:
        chapters_n = min(chapters_n, len(chapter_titles))
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
        title = chapter_titles[(cidx - 1) % len(chapter_titles)]
        chapter_id = f"ch{cidx:02d}"
        chapters.append(ChapterSpec(
            chapter_id=chapter_id,
            title=title,
            order=cidx,
            target_chars=chapter_chars,
            objective=_chapter_objective(brief, title, conference_mode=conference_mode),
        ))
        parent_q = SurveyQuestion(
            question_id=f"q{cidx:02d}",
            text=(f"{_conference_subject(brief)}: {title} 这一章从会议和论文信号中暴露出的核心问题是什么？" if conference_mode else f"{brief}: {title} 的核心问题是什么？"),
            depth=0,
            required_source_types=["paper", "official_doc", "code", "benchmark"],
        )
        questions.append(parent_q)
        for sidx in range(1, per_chapter + 1):
            section_id = f"{chapter_id}/sec{sidx:02d}"
            section_title = section_titles[(sidx - 1) % len(section_titles)]
            required = ["paper", "official_doc"] if sidx == 1 else ["paper", "code"] if sidx == 2 else ["paper", "benchmark"]
            sections.append(SectionSpec(
                section_id=section_id,
                chapter_id=chapter_id,
                title=f"{title}：{section_title}",
                order=(cidx - 1) * per_chapter + sidx,
                target_chars=section_chars,
                research_question=_section_research_question(brief, title, section_title, conference_mode=conference_mode),
                required_source_types=required,
                min_evidence=4,
                min_claims=3,
            ))
            questions.append(SurveyQuestion(
                question_id=f"q{cidx:02d}_{sidx:02d}",
                text=_question_text(brief, title, section_title, conference_mode=conference_mode),
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
        title=_conference_report_title(brief) if conference_mode else f"Professor-Grade Survey: {brief}",
        target_chars=target_chars,
        chapters=chapters,
        sections=sections,
    )
    return {
        "run": to_dict(run),
        "planner_mode": "conference_insight" if conference_mode else "general_survey",
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
