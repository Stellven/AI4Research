from __future__ import annotations

import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.survey.planner import create_survey_plan, write_survey_plan


def test_planner_creates_professor_grade_shape(tmp_path):
    plan = create_survey_plan("隐空间推理技术架构和演进方向", target_chars=50000)
    assert len(plan["report_ast"]["chapters"]) >= 8
    assert len(plan["report_ast"]["sections"]) >= 30
    assert len(plan["source_matrix"]) == len(plan["report_ast"]["sections"])
    assert all(section["min_evidence"] >= 4 for section in plan["report_ast"]["sections"])

    files = write_survey_plan(plan, tmp_path)
    assert (tmp_path / "survey_plan.json").exists()
    assert (tmp_path / "survey_report_ast.json").exists()
    assert files["source_matrix"].endswith("survey_source_matrix.json")


def test_planner_uses_conference_insight_mode_for_conference_briefs():
    brief = (
        "通过洞察 CAIS 2026 学术会议，分析当前 Agent 应如何发展、重大技术挑战是什么、"
        "Solar 该如何吸收这些思想。要求形成 DeepDive 风格的结构化、证据化、章节化洞察报告。"
    )

    plan = create_survey_plan(brief, target_chars=50000)

    assert plan["planner_mode"] == "conference_insight"
    assert plan["report_ast"]["title"] == "深度报告：CAIS 2026 Agent 发展、技术挑战与 Solar 路线"

    first_chapter = plan["report_ast"]["chapters"][0]
    first_section = plan["report_ast"]["sections"][0]
    first_question = plan["questions"][0]

    assert first_chapter["title"] == "问题定义与研究边界"
    assert "accepted papers" in first_chapter["objective"]
    assert "avoid generic methodology talk" in first_chapter["objective"]
    assert "Professor-Grade Survey" not in plan["report_ast"]["title"]
    assert "会议主议题与问题迁移" in [chapter["title"] for chapter in plan["report_ast"]["chapters"]]
    assert "会议在讨论什么问题" in first_section["title"]
    assert "conference tracks" in first_section["research_question"]
    assert any(section["title"].endswith("对 Solar 的启示") for section in plan["report_ast"]["sections"])
    assert "会议和论文信号" in first_question["text"]


def test_planner_keeps_general_mode_for_non_conference_briefs():
    plan = create_survey_plan("隐空间推理技术架构和演进方向", target_chars=50000)

    assert plan["planner_mode"] == "general_survey"
    assert plan["report_ast"]["title"] == "Professor-Grade Survey: 隐空间推理技术架构和演进方向"
    assert plan["report_ast"]["chapters"][1]["title"] == "历史脉络与技术演进"
