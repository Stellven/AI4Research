from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.survey.evaluator import evaluate_survey
from research.survey.evidence_pack import build_evidence_packs
from research.survey.planner import create_survey_plan, write_survey_plan
from research.survey.section_compiler import compile_section, compile_survey
from research.survey.writing_loop import run_ready_sections


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


def test_e2e_professor_survey_smoke(tmp_path):
    plan = create_survey_plan("隐空间推理技术架构和演进方向", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    assert len(plan["report_ast"]["chapters"]) >= 8
    assert len(plan["report_ast"]["sections"]) >= 30

    weak = build_evidence_packs(tmp_path, plan["report_ast"])
    assert weak["blocked"] == len(plan["report_ast"]["sections"])
    assert evaluate_survey(tmp_path, strict=True)["ok"] is False

    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment survey"} for i in range(48)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence and deployment boundaries"} for i in range(48)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(48)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)

    strong = build_evidence_packs(tmp_path, plan["report_ast"])
    assert strong["ready"] >= 30
    batch = run_ready_sections(tmp_path, limit=3, max_rounds=3)
    assert batch["ok"] is True
    assert batch["processed"] == 3
    assert compile_survey(tmp_path)["ok"] is True
    result = evaluate_survey(tmp_path, strict=True)
    assert result["ok"] is True
    assert result["scorecard"]["finalized_sections"] == 3
    incomplete = evaluate_survey(tmp_path, strict=True, require_complete=True)
    assert incomplete["ok"] is False
    assert any(item.startswith("incomplete_sections:") for item in incomplete["scorecard"]["issues"])
    assert incomplete["final_quality"]["pending_placeholder_count"] > 0
    assert any(item.startswith("pending_placeholder_count:") for item in incomplete["scorecard"]["issues"])

    batch_all = run_ready_sections(tmp_path, limit=0, max_rounds=3)
    assert batch_all["ok"] is True
    assert batch_all["processed"] == len(plan["report_ast"]["sections"]) - 3
    assert compile_survey(tmp_path)["ok"] is True
    complete = evaluate_survey(tmp_path, strict=True, require_complete=True)
    assert complete["ok"] is True
    assert complete["scorecard"]["finalized_sections"] == len(plan["report_ast"]["sections"])
    assert complete["final_quality"]["ok"] is True
