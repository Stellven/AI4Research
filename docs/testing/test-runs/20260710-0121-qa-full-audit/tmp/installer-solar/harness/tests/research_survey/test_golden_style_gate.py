from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.survey.evaluator import evaluate_survey
from research.survey.golden_style_gate import assess_audience_hygiene, assess_golden_style, benchmark_html_stats


def test_benchmark_html_stats_extracts_structure(tmp_path):
    html = tmp_path / "quality_golden.html"
    html.write_text(
        """<!doctype html><html><body>
        <section><h2>总论 · 不是摘要而是判断</h2><p>最终判断：这不是普通综述，而是工程评价。</p></section>
        <section><h2>机制</h2><svg></svg><table><tr><td>评价</td></tr></table></section>
        </body></html>""",
        encoding="utf-8",
    )
    stats = benchmark_html_stats(html)
    assert stats["section_count"] == 2
    assert stats["svg_count"] == 1
    assert stats["table_count"] == 1
    assert stats["commentary_term_count"] >= 3


def test_golden_style_gate_rejects_smoke_like_report(tmp_path):
    (tmp_path / "quality_golden.html").write_text(
        """<!doctype html><html><body>
        <section><h2>样稿</h2><p>不是摘要，而是评价。最终判断和硬伤都必须出现。</p></section>
        </body></html>""",
        encoding="utf-8",
    )
    (tmp_path / "final.md").write_text(
        "# DeepResearch Report: smoke test\n\n## Summary\n\nThis section should summarize architecture for `executive_summary`.\n",
        encoding="utf-8",
    )
    payload = assess_golden_style(tmp_path)
    assert payload["enabled"] is True
    assert payload["ok"] is False
    assert any(issue.startswith("golden_final_chars_low:") for issue in payload["issues"])
    assert any(issue.startswith("golden_template_residue_count:") for issue in payload["issues"])
    assert (tmp_path / "survey_golden_style.json").exists()


def test_golden_style_gate_can_require_benchmark(tmp_path):
    (tmp_path / "final.md").write_text("# Report\n\n## 判断\n\n不是摘要，而是测试。\n", encoding="utf-8")
    payload = assess_golden_style(tmp_path, require_benchmark=True)
    assert payload["enabled"] is False
    assert payload["required"] is True
    assert payload["ok"] is False
    assert "golden_benchmark_required_missing" in payload["issues"]


def test_survey_eval_includes_enabled_golden_style_issues(tmp_path):
    (tmp_path / "quality_golden.html").write_text("<html><body><section><h2>golden</h2><p>不是而是评价硬伤最终判断</p></section></body></html>", encoding="utf-8")
    (tmp_path / "survey_report_ast.json").write_text(
        json.dumps({
            "title": "brief",
            "chapters": [{"chapter_id": "ch1", "title": "Brief"}],
            "sections": [{"section_id": "ch1/sec1", "chapter_id": "ch1", "title": "S1"}],
        }),
        encoding="utf-8",
    )
    (tmp_path / "survey_evidence_packs.json").write_text(json.dumps({"packs": [], "blocked": 0}), encoding="utf-8")
    (tmp_path / "final.md").write_text("# tiny\n\n## Summary\n\nsmoke test\n", encoding="utf-8")
    result = evaluate_survey(tmp_path, strict=True, require_complete=True)
    assert result["golden_style"]["enabled"] is True
    assert result["golden_style"]["ok"] is False
    assert any(issue.startswith("golden_") for issue in result["scorecard"]["issues"])


def test_survey_eval_can_require_golden_style_without_benchmark(tmp_path):
    (tmp_path / "survey_report_ast.json").write_text(
        json.dumps({
            "title": "brief",
            "chapters": [{"chapter_id": "ch1", "title": "Brief"}],
            "sections": [{"section_id": "ch1/sec1", "chapter_id": "ch1", "title": "S1"}],
        }),
        encoding="utf-8",
    )
    (tmp_path / "survey_evidence_packs.json").write_text(json.dumps({"packs": [], "blocked": 0}), encoding="utf-8")
    (tmp_path / "final.md").write_text("# tiny\n\n## Summary\n\n不是摘要，而是测试\n", encoding="utf-8")
    result = evaluate_survey(tmp_path, strict=True, require_golden_style=True)
    assert result["require_golden_style"] is True
    assert result["golden_style"]["required"] is True
    assert "golden_benchmark_required_missing" in result["scorecard"]["issues"]


def test_audience_hygiene_rejects_internal_report_process_html(tmp_path):
    (tmp_path / "final.md").write_text("# Report\n\n## 趋势判断\n\nAgent 系统正在演进。\n", encoding="utf-8")
    (tmp_path / "agent_trend_report.html").write_text(
        """<!doctype html><html><body>
        <section><h2>Solar-Harness 改造路线</h2>
        <p>P0 · Claim-ledger 写作。strict eval 必须失败。</p></section>
        </body></html>""",
        encoding="utf-8",
    )
    payload = assess_audience_hygiene(tmp_path)
    assert payload["ok"] is False
    assert any("internal_system_roadmap" in issue for issue in payload["issues"])
    assert any("internal_writer_process" in issue for issue in payload["issues"])
    assert (tmp_path / "survey_audience_hygiene.json").exists()


def test_survey_eval_strict_fails_on_audience_hygiene_leak(tmp_path):
    (tmp_path / "survey_report_ast.json").write_text(
        json.dumps({
            "title": "brief",
            "chapters": [{"chapter_id": "ch1", "title": "Brief"}],
            "sections": [{"section_id": "ch1/sec1", "chapter_id": "ch1", "title": "S1"}],
        }),
        encoding="utf-8",
    )
    (tmp_path / "survey_evidence_packs.json").write_text(json.dumps({"packs": [], "blocked": 0}), encoding="utf-8")
    (tmp_path / "final.md").write_text(
        "# Report\n\n## 趋势判断\n\nch02/sec04 这类内部结构不能写给用户。\n",
        encoding="utf-8",
    )
    result = evaluate_survey(tmp_path, strict=True)
    assert result["audience_hygiene"]["ok"] is False
    assert any(issue.startswith("audience_hygiene_leak:section_id_leak") for issue in result["scorecard"]["issues"])
