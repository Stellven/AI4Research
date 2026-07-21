from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.cli import main
from research.survey.finalize_run import finalize_survey_run
from research.survey.evidence_pack import build_evidence_packs
from research.survey.planner import create_survey_plan, write_survey_plan


def _append_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _strong_sources():
    return [
        {"id": "src_0", "source_type": "paper", "title": "Latent Reasoning Paper", "url": "https://arxiv.org/abs/2412.06769"},
        {"id": "src_1", "source_type": "paper", "title": "Continuous Thought Paper", "url": "https://openreview.net/forum?id=latent-reasoning"},
        {"id": "src_2", "source_type": "paper", "title": "Reasoning Survey Proceedings", "url": "https://doi.org/10.1145/latent-reasoning"},
        {"id": "src_3", "source_type": "paper", "title": "Neural Computation Journal Article", "url": "https://ieeexplore.ieee.org/document/123456"},
        {"id": "src_4", "source_type": "official_doc", "title": "Official Developer Docs", "url": "https://docs.example.edu/latent-reasoning"},
        {"id": "src_5", "source_type": "code", "title": "Latent Reasoning Repository", "url": "https://github.com/example/latent-reasoning"},
        {"id": "src_6", "source_type": "benchmark", "title": "Latent Reasoning Benchmark", "url": "https://paperswithcode.com/task/latent-reasoning"},
        {"id": "src_7", "source_type": "benchmark", "title": "Hugging Face Evaluation Dataset", "url": "https://huggingface.co/datasets/example/latent-reasoning"},
    ]


def _ledgers(root, n=48):
    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(n)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(n)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(n)]
    _append_jsonl(root / "sources.jsonl", sources)
    _append_jsonl(root / "evidence.jsonl", evidence)
    _append_jsonl(root / "claims.jsonl", claims)
    _append_jsonl(root / "claim_evidence.jsonl", links)


def test_finalize_run_builds_pipeline_and_compiles(tmp_path):
    _ledgers(tmp_path)
    payload = finalize_survey_run(
        tmp_path,
        brief="latent reasoning",
        section_limit=1,
        repair_limit=1,
        min_finalized=1,
        min_chars=100,
        repair_passes=1,
    )
    assert payload["ok"] is True
    assert payload["reason"] == "passed"
    assert [step["step"] for step in payload["steps"]] == ["plan", "source_gap", "pack", "write", "eval", "auto_repair", "compile", "final_eval"]
    assert payload["compile"]["finalized_sections"] >= 1
    assert (tmp_path / "final.md").exists()
    assert (tmp_path / "survey_finalize_run.json").exists()


def test_finalize_run_can_reuse_existing_plan_and_pack(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    _ledgers(tmp_path)
    build_evidence_packs(tmp_path, plan["report_ast"])
    payload = finalize_survey_run(
        tmp_path,
        skip_plan=True,
        skip_pack=True,
        section_limit=1,
        min_finalized=1,
        min_chars=100,
    )
    assert payload["ok"] is True
    assert payload["steps"][0]["skipped"] is True
    assert payload["steps"][2]["skipped"] is True


def test_finalize_run_requires_brief_when_planning(tmp_path):
    payload = finalize_survey_run(tmp_path)
    assert payload["ok"] is False
    assert payload["reason"] == "brief_required_for_plan"


def test_finalize_run_stops_and_writes_handoff_when_ledgers_missing(tmp_path):
    payload = finalize_survey_run(tmp_path, brief="latent reasoning")
    assert payload["ok"] is False
    assert payload["reason"] == "source_gap_handoff_required"
    assert payload["handoff_path"].endswith("survey_source_gap_handoff.md")
    assert (tmp_path / "survey_source_gap_handoff.md").exists()
    assert (tmp_path / "survey_source_gap.json").exists()
    text = (tmp_path / "survey_source_gap_handoff.md").read_text(encoding="utf-8")
    assert "External Search Results" in text
    assert "paper" in text


def test_finalize_run_cli(tmp_path, capsys):
    _ledgers(tmp_path)
    rc = main([
        "survey-finalize-run",
        "--output-dir", str(tmp_path),
        "--brief", "latent reasoning",
        "--section-limit", "1",
        "--repair-limit", "1",
        "--min-finalized", "1",
        "--min-chars", "100",
        "--repair-passes", "1",
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["reason"] == "passed"
