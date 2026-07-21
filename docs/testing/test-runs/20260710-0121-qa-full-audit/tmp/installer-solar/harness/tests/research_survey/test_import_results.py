from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.cli import main
from research.survey.import_results import diagnose_survey_search_markdown, import_survey_search_results, parse_survey_search_markdown
from research.survey.planner import create_survey_plan, write_survey_plan


MARKDOWN = """# External Search Results: latent reasoning

## Source 1: Coconut Paper
URL: https://arxiv.org/abs/2412.06769
Publisher: arXiv
Published: 2024-12-09
Source Type: paper
Research Angles: literature_lineage, method_taxonomy

Summary:
- Coconut uses continuous latent thought for reasoning.
- The method changes evaluation and compute tradeoffs.

Key Claims:
- Latent reasoning can shift reasoning from text tokens into hidden states.
- Continuous thought creates new evaluation requirements.

Relevant Quotes:
> Continuous thought changes reasoning dynamics.

## Source 2: Coconut Code
URL: https://github.com/facebookresearch/coconut
Publisher: GitHub
Published: N/A
Source Type: repo
Research Angles: engineering

Summary:
- The repository exposes reproducibility and implementation boundaries.

Key Claims:
- Code availability is needed to evaluate implementation constraints.
- Repository details expose reproducibility boundaries.

Relevant Quotes:
> N/A
"""


OFFICIAL_AND_BENCHMARK_MARKDOWN = """# External Search Results: latent reasoning

## Source 1: Coconut Official Notes
URL: https://docs.example.edu/coconut-official
Publisher: Example Lab
Published: 2025-01-01
Source Type: official_doc
Research Angles: literature_lineage

Summary:
- Official notes describe latent reasoning architecture constraints.

Key Claims:
- Official documentation is needed to bound deployment assumptions.
- Official docs preserve terminology and system scope.

Relevant Quotes:
> Official notes preserve system boundaries.

## Source 2: Coconut Benchmark
URL: https://paperswithcode.com/task/coconut-benchmark
Publisher: Example Eval
Published: 2025-02-01
Source Type: benchmark
Research Angles: evaluation_protocol, controversy

Summary:
- Benchmark evidence defines evaluation coverage and failure modes.

Key Claims:
- Benchmark evidence is needed to compare latent reasoning methods.
- Benchmark design exposes failure modes and coverage limits.

Relevant Quotes:
> Benchmark coverage controls evaluation claims.
"""


def _source_url(source_type: str, idx: int) -> str:
    occurrence = (idx - 1) // 4
    urls = {
        "paper": ["https://arxiv.org/abs/2412.06769", "https://openreview.net/forum?id=latent-reasoning", "https://doi.org/10.1145/latent-reasoning", "https://ieeexplore.ieee.org/document/123456"],
        "repo": ["https://github.com/example/latent-reasoning", "https://github.com/facebookresearch/coconut", "https://github.com/example/latent-eval", "https://github.com/example/continuous-thought"],
        "official_doc": ["https://docs.example.edu/latent-reasoning", "https://docs.example.edu/latent-reasoning/api", "https://docs.example.edu/latent-reasoning/eval", "https://docs.example.edu/latent-reasoning/deploy"],
        "benchmark": ["https://paperswithcode.com/task/latent-reasoning", "https://huggingface.co/datasets/example/latent-reasoning", "https://paperswithcode.com/dataset/latent-eval", "https://huggingface.co/spaces/example/latent-benchmark"],
    }
    values = urls[source_type]
    return values[occurrence % len(values)]


def test_parse_survey_search_markdown_normalizes_source_types():
    records = parse_survey_search_markdown(MARKDOWN)
    assert len(records) == 2
    assert records[0]["source_type"] == "paper"
    assert records[0]["research_angles"] == ["literature_lineage", "method_taxonomy"]
    assert records[1]["source_type"] == "code"
    assert records[1]["research_angles"] == ["engineering"]
    assert len(records[0]["key_claims"]) == 2


def test_diagnose_survey_search_markdown_reports_missing_schema_fields():
    diagnostics = diagnose_survey_search_markdown("# Notes\n\n## Source 1: Missing URL\nSource Type: paper\n")
    assert diagnostics["source_heading_count"] == 1
    assert diagnostics["url_count"] == 0
    assert diagnostics["has_external_search_results_heading"] is False
    assert diagnostics["missing_fields_by_source"][0]["missing_fields"] == ["URL", "Research Angles", "Summary", "Key Claims"]
    assert diagnostics["missing_research_angles"] == ["literature_lineage", "method_taxonomy", "evaluation_protocol", "controversy", "engineering"]
    assert "## Source 1: <title>" in diagnostics["example"]
    assert "Research Angles:" in diagnostics["example"]


def test_import_survey_search_results_failure_writes_actionable_diagnostics(tmp_path):
    md = tmp_path / "bad.md"
    md.write_text("# Search notes\n- https://example.com only\n", encoding="utf-8")
    payload = import_survey_search_results(tmp_path, md)
    assert payload["ok"] is False
    assert payload["reason"] == "no_importable_sources"
    assert payload["diagnostics"]["source_heading_count"] == 0
    assert payload["diagnostics"]["url_count"] == 1
    assert "returned_sources.md" in payload["diagnostics"]["repair_hint"]
    persisted = json.loads((tmp_path / "survey_import_search_results.json").read_text(encoding="utf-8"))
    assert persisted["diagnostics"]["expected_source_heading"] == "## Source 1: <title>"


def test_import_survey_search_results_writes_ledgers(tmp_path):
    md = tmp_path / "results.md"
    md.write_text(MARKDOWN, encoding="utf-8")
    payload = import_survey_search_results(tmp_path, md)
    assert payload["ok"] is True
    assert payload["imported_sources"] == 2
    assert payload["imported_evidence"] == 4
    assert payload["imported_claims"] == 4
    assert payload["imported_links"] == 4
    assert len((tmp_path / "sources.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    assert len((tmp_path / "evidence.jsonl").read_text(encoding="utf-8").splitlines()) == 4
    assert len((tmp_path / "claims.jsonl").read_text(encoding="utf-8").splitlines()) == 4
    source_rows = [json.loads(line) for line in (tmp_path / "sources.jsonl").read_text(encoding="utf-8").splitlines()]
    assert source_rows[0]["research_angle"] == "literature_lineage"
    assert source_rows[0]["research_angles"] == ["literature_lineage", "method_taxonomy"]
    evidence_text = (tmp_path / "evidence.jsonl").read_text(encoding="utf-8")
    assert "Research Angles: literature_lineage, method_taxonomy" in evidence_text
    assert (tmp_path / "survey_import_search_results.json").exists()


def test_import_survey_search_results_tracks_research_angle_coverage(tmp_path):
    md = tmp_path / "results.md"
    angles = ["literature_lineage", "method_taxonomy", "evaluation_protocol", "controversy", "engineering"]
    blocks = ["# External Search Results: latent reasoning"]
    for idx, angle in enumerate(angles, start=1):
        blocks.append(f"""
## Source {idx}: Angle Source {idx}
URL: https://example.com/source-{idx}
Publisher: Example
Published: 2025-01-{idx:02d}
Source Type: paper
Research Angles: {angle}

Summary:
- This source covers {angle} for latent reasoning.

Key Claims:
- Latent reasoning requires {angle} evidence.
- Professor-grade surveys must distinguish {angle} from generic source stuffing.

Relevant Quotes:
> Angle-specific evidence matters.
""")
    md.write_text("\n".join(blocks), encoding="utf-8")
    payload = import_survey_search_results(tmp_path, md)
    assert payload["ok"] is True
    assert payload["missing_research_angles"] == []
    assert payload["research_angle_counts"] == {angle: 1 for angle in angles}
    source_rows = [json.loads(line) for line in (tmp_path / "sources.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["research_angle"] for row in source_rows] == angles


def test_import_survey_search_results_dedupes_sources(tmp_path):
    md = tmp_path / "results.md"
    md.write_text(MARKDOWN, encoding="utf-8")
    first = import_survey_search_results(tmp_path, md)
    second = import_survey_search_results(tmp_path, md)
    assert first["imported_sources"] == 2
    assert second["imported_sources"] == 0
    assert second["imported_evidence"] == 0
    assert second["imported_claims"] == 0


def test_import_survey_search_results_continue_finalize(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    md = tmp_path / "results.md"
    source_types = ["paper", "repo", "official_doc", "benchmark"]
    blocks = ["# External Search Results: latent reasoning"]
    for idx in range(1, 33):
        source_type = source_types[(idx - 1) % len(source_types)]
        blocks.append(f"""
## Source {idx}: Latent Reasoning Source {idx}
URL: {_source_url(source_type, idx)}
Publisher: Example
Published: 2025-01-{idx:02d}
Source Type: {source_type}
Research Angles: {["literature_lineage", "method_taxonomy", "evaluation_protocol", "controversy", "engineering"][(idx - 1) % 5]}

Summary:
- Latent reasoning source {idx} covers architecture evaluation deployment.

Key Claims:
- Latent reasoning claim {idx}A requires evidence for architecture evaluation.
- Latent reasoning claim {idx}B requires evidence for deployment constraints.

Relevant Quotes:
> Latent reasoning source {idx} preserves evidence boundaries.
""")
    md.write_text("\n".join(blocks), encoding="utf-8")
    payload = import_survey_search_results(
        tmp_path,
        md,
        continue_finalize=True,
        brief="latent reasoning",
        section_limit=1,
        repair_limit=1,
        min_finalized=1,
        min_chars=100,
    )
    assert payload["ok"] is True
    assert payload["finalize"]["ok"] is True
    assert (tmp_path / "final.md").exists()


def test_import_survey_search_results_continue_finalize_require_complete(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    md = tmp_path / "results.md"
    source_types = ["paper", "repo", "official_doc", "benchmark"]
    blocks = ["# External Search Results: latent reasoning"]
    for idx in range(1, 17):
        source_type = source_types[(idx - 1) % len(source_types)]
        blocks.append(f"""
## Source {idx}: Latent Reasoning Source {idx}
URL: {_source_url(source_type, idx)}
Publisher: Example
Published: 2025-01-{idx:02d}
Source Type: {source_type}
Research Angles: {["literature_lineage", "method_taxonomy", "evaluation_protocol", "controversy", "engineering"][(idx - 1) % 5]}

Summary:
- Latent reasoning source {idx} covers architecture evaluation deployment.

Key Claims:
- Latent reasoning claim {idx}A requires evidence for architecture evaluation.
- Latent reasoning claim {idx}B requires evidence for deployment constraints.

Relevant Quotes:
> Latent reasoning source {idx} preserves evidence boundaries.
""")
    md.write_text("\n".join(blocks), encoding="utf-8")
    payload = import_survey_search_results(
        tmp_path,
        md,
        continue_finalize=True,
        brief="latent reasoning",
        section_limit=1,
        min_finalized=1,
        min_chars=100,
        require_complete=True,
    )
    assert payload["ok"] is True
    assert payload["finalize"]["ok"] is False
    assert any(item.startswith("incomplete_sections:") for item in payload["finalize"]["final_eval"]["scorecard"]["issues"])


def test_import_survey_search_results_cli(tmp_path, capsys):
    md = tmp_path / "results.md"
    md.write_text(MARKDOWN, encoding="utf-8")
    rc = main([
        "survey-import-search-results",
        "--output-dir", str(tmp_path),
        "--input-md", str(md),
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["imported_sources"] == 2


def test_import_survey_search_results_cli_continue_finalize_preserves_target_chars(tmp_path, capsys):
    md = tmp_path / "results.md"
    source_types = ["paper", "repo", "official_doc", "benchmark"]
    blocks = ["# External Search Results: latent reasoning"]
    for idx in range(1, 33):
        source_type = source_types[(idx - 1) % len(source_types)]
        blocks.append(f"""
## Source {idx}: Latent Reasoning Source {idx}
URL: {_source_url(source_type, idx)}
Publisher: Example
Published: 2025-01-{idx:02d}
Source Type: {source_type}
Research Angles: {["literature_lineage", "method_taxonomy", "evaluation_protocol", "controversy", "engineering"][(idx - 1) % 5]}

Summary:
- Latent reasoning source {idx} covers architecture evaluation deployment.

Key Claims:
- Latent reasoning claim {idx}A requires evidence for architecture evaluation.
- Latent reasoning claim {idx}B requires evidence for deployment constraints.

Relevant Quotes:
> Latent reasoning source {idx} preserves evidence boundaries.
""")
    md.write_text("\n".join(blocks), encoding="utf-8")
    rc = main([
        "survey-import-search-results",
        "--output-dir", str(tmp_path),
        "--input-md", str(md),
        "--continue-finalize",
        "--brief", "latent reasoning",
        "--target-chars", "100000",
        "--section-limit", "1",
        "--min-finalized", "1",
        "--min-chars", "100",
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    ast = json.loads((tmp_path / "survey_report_ast.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert ast["target_chars"] == 100000
    assert len(ast["chapters"]) == 12
    assert len(ast["sections"]) == 60


def test_import_survey_search_results_cli_continue_finalize_accepts_narrative_args(tmp_path, capsys):
    md = tmp_path / "results.md"
    source_types = ["paper", "repo", "official_doc", "benchmark"]
    blocks = ["# External Search Results: latent reasoning"]
    for idx in range(1, 33):
        source_type = source_types[(idx - 1) % len(source_types)]
        blocks.append(f"""
## Source {idx}: Latent Reasoning Source {idx}
URL: {_source_url(source_type, idx)}
Publisher: Example
Published: 2025-01-{idx:02d}
Source Type: {source_type}
Research Angles: {["literature_lineage", "method_taxonomy", "evaluation_protocol", "controversy", "engineering"][(idx - 1) % 5]}

Summary:
- Latent reasoning source {idx} covers architecture evaluation deployment.

Key Claims:
- Latent reasoning claim {idx}A requires evidence for architecture evaluation.
- Latent reasoning claim {idx}B requires evidence for deployment constraints.

Relevant Quotes:
> Latent reasoning source {idx} preserves evidence boundaries.
""")
    md.write_text("\n".join(blocks), encoding="utf-8")
    rc = main([
        "survey-import-search-results",
        "--output-dir", str(tmp_path),
        "--input-md", str(md),
        "--continue-finalize",
        "--brief", "latent reasoning",
        "--target-chars", "100000",
        "--section-limit", "1",
        "--min-finalized", "1",
        "--min-chars", "100",
        "--narrative-backend", "deterministic",
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["finalize"]["ok"] is True


def test_parse_survey_search_markdown_accepts_gemini_deep_search_report_format():
    markdown = """# Gemini Deep Search

## 文献与链接清单
- [某条链接](https://example.com/ignore-me)

## 参考结论
类别 A：CAIS 2026 官方信号与复合 AI 系统（官方会议信号）
ACM launches CAIS 2026, a new conference on AI and agentic systems
来源/作者: ACM / EurekAlert! 官方新闻
核心价值: 明确了 CAIS 2026 的系统组合、编排、端到端评估基调。
URL: https://www.eurekalert.org/news-releases/1116428

类别 B：重大技术挑战：长轨迹、工具使用与多 Agent 编排（扩展补充信号）
AgentOrchestra: Orchestrating Multi-Agent Intelligence with the Tool-Environment-Agent(TEA) Protocol
来源/作者: arXiv [2506.12508v6]
核心价值: 提出了层次化多 Agent 树状路由框架。
URL: https://arxiv.org/html/2506.12508v6

类别 C：开源框架
LangGraph Repository
来源/作者: GitHub
核心价值: 展示了 stateful graph orchestration 的工程实现。
URL: https://github.com/langchain-ai/langgraph
"""
    records = parse_survey_search_markdown(markdown)
    assert len(records) == 3
    assert records[0]["source_type"] == "official_doc"
    assert "literature_lineage" in records[0]["research_angles"]
    assert records[1]["source_type"] == "paper"
    assert "method_taxonomy" in records[1]["research_angles"]
    assert records[2]["source_type"] == "code"
    assert "engineering" in records[2]["research_angles"]
