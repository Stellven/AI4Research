#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import understand_anything_local_pipeline as ualp  # noqa: E402


def _make_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "README.md").write_text("# Demo Repo\n", encoding="utf-8")
    src = repo / "src"
    src.mkdir()
    for idx in range(1, 7):
        (src / f"mod_{idx}.py").write_text(
            "\n".join(
                [
                    f"def fn_{idx}():",
                    f"    return 'value-{idx}'",
                    "",
                    f"class Class{idx}:",
                    "    pass",
                    "",
                    ("#" * 200),
                ]
            ),
            encoding="utf-8",
        )


def test_run_pipeline_chunks_and_resumes(tmp_path):
    repo = tmp_path / "repo"
    out = tmp_path / "out"
    _make_repo(repo)

    calls: list[str] = []

    def runner(prompt: str):
        calls.append(prompt)
        if "分片代码库语义分析器" in prompt:
            marker = prompt.split("- chunk_id: ", 1)[1].splitlines()[0].strip()
            return {"choices": [{"message": {"content": f"{marker} 局部摘要"}}], "usage": {"prompt_tokens": 10}}
        return {"choices": [{"message": {"content": "最终汇总摘要"}}], "usage": {"completion_tokens": 20}}

    result = ualp.run_pipeline(
        str(repo),
        output_dir=str(out),
        language="zh",
        objective="test objective",
        semantic_runner=runner,
    )
    assert result["ok"] is True
    assert result["chunks_total"] >= 2
    assert result["chunks_completed"] == result["chunks_total"]
    assert result["resumed"] is False
    assert len(calls) == result["chunks_total"] + 1
    manifest = json.loads((out / "chunk-manifest.json").read_text(encoding="utf-8"))
    resume = json.loads((out / "resume-state.json").read_text(encoding="utf-8"))
    graph = json.loads((out / "knowledge-graph.json").read_text(encoding="utf-8"))
    assert manifest["chunk_count"] == result["chunks_total"]
    assert resume["final_synthesis_completed"] is True
    assert len(resume["completed_chunks"]) == result["chunks_total"]
    assert graph["provenance"]["resume_supported"] is True
    assert len(graph["chunk_summaries"]) == result["chunks_total"]

    calls.clear()
    resumed = ualp.run_pipeline(
        str(repo),
        output_dir=str(out),
        language="zh",
        objective="test objective",
        semantic_runner=runner,
    )
    assert resumed["resumed"] is True
    assert len(calls) == 1
    assert "最终汇总摘要" in (out / "semantic-summary.md").read_text(encoding="utf-8")


def test_run_pipeline_groups_final_synthesis_when_needed(tmp_path):
    repo = tmp_path / "repo"
    out = tmp_path / "out"
    _make_repo(repo)

    old_items = ualp.FINAL_SYNTHESIS_GROUP_ITEMS
    old_chars = ualp.FINAL_SYNTHESIS_GROUP_TOTAL_CHARS
    ualp.FINAL_SYNTHESIS_GROUP_ITEMS = 2
    ualp.FINAL_SYNTHESIS_GROUP_TOTAL_CHARS = 40
    try:
        calls: list[str] = []

        def runner(prompt: str):
            calls.append(prompt)
            if "分片代码库语义分析器" in prompt:
                marker = prompt.split("- chunk_id: ", 1)[1].splitlines()[0].strip()
                return {"choices": [{"message": {"content": f"{marker} 局部摘要，包含额外说明用于放大总汇编体积。"}}]}
            if "## Chunk Summaries" in prompt and "synthesis-group-" not in prompt:
                return {"choices": [{"message": {"content": "中间分组合成摘要"}}]}
            return {"choices": [{"message": {"content": "最终汇总摘要"}}]}

        result = ualp.run_pipeline(
            str(repo),
            output_dir=str(out),
            language="zh",
            objective="grouped synthesis",
            semantic_runner=runner,
        )
        assert result["ok"] is True
        assert len(calls) > result["chunks_total"] + 1
        resume = json.loads((out / "resume-state.json").read_text(encoding="utf-8"))
        assert resume["final_synthesis_completed"] is True
        assert resume["completed_synthesis_groups"]
        assert (out / "synthesis-artifacts" / "summaries").exists()
        assert "最终汇总摘要" in (out / "semantic-summary.md").read_text(encoding="utf-8")
    finally:
        ualp.FINAL_SYNTHESIS_GROUP_ITEMS = old_items
        ualp.FINAL_SYNTHESIS_GROUP_TOTAL_CHARS = old_chars
