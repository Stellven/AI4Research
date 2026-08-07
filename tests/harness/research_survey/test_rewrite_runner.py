from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.cli import main
from research.survey.evidence_pack import build_evidence_packs
from research.survey.planner import create_survey_plan, write_survey_plan
from research.survey.rewrite_queue import build_rewrite_queue
from research.survey.rewrite_runner import run_rewrite_queue


def _append_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _fixture(root):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, root)
    sources = [{"id": f"src_{i}", "source_type": t, "title": t} for i, t in enumerate(["paper", "official_doc", "code", "benchmark"])]
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(16)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(12)]
    links = [{"claim_id": f"cl_{i % 12}", "evidence_id": f"ev_{i}"} for i in range(16)]
    _append_jsonl(root / "sources.jsonl", sources)
    _append_jsonl(root / "evidence.jsonl", evidence)
    _append_jsonl(root / "claims.jsonl", claims)
    _append_jsonl(root / "claim_evidence.jsonl", links)
    build_evidence_packs(root, plan["report_ast"])
    return plan


def _write_scorecard(root):
    payload = {
        "top_issues": [
            {
                "section_id": "ch01/sec01",
                "status": "needs_rewrite",
                "risk_score": 100,
                "issues": [{"severity": "P0", "code": "unsupported_claim"}],
            }
        ]
    }
    (root / "survey_section_scorecard.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_rewrite_runner_executes_queue_and_archives_previous_final(tmp_path):
    _fixture(tmp_path)
    _write_scorecard(tmp_path)
    build_rewrite_queue(tmp_path)
    section_dir = tmp_path / "sections" / "ch01" / "sec01"
    (section_dir / "final.md").write_text("old final\n", encoding="utf-8")
    payload = run_rewrite_queue(tmp_path, min_chars=100, max_rounds=2)
    assert payload["ok"] is True
    assert payload["processed"] == 1
    assert payload["passed"] == 1
    assert payload["results"][0]["rewrite_round_index"] == 1
    assert (section_dir / "final.before_rewrite.md").read_text(encoding="utf-8") == "old final\n"
    assert (section_dir / "prompt_packets" / "round_01.md").exists()
    assert "Verdict: PASS" in (section_dir / "final.md").read_text(encoding="utf-8")
    assert (tmp_path / "survey_rewrite_run.json").exists()


def test_rewrite_runner_human_packet_waits_on_round_01(tmp_path):
    _fixture(tmp_path)
    _write_scorecard(tmp_path)
    build_rewrite_queue(tmp_path)
    payload = run_rewrite_queue(tmp_path, writer_backend="human-packet", min_chars=100)
    assert payload["ok"] is False
    assert payload["waiting"] == 1
    assert payload["results"][0]["reason"] == "human_response_missing"
    assert payload["results"][0]["expected_response"].endswith("human_responses/round_01.md")


def test_rewrite_runner_cli_allow_pending(tmp_path, capsys):
    _fixture(tmp_path)
    _write_scorecard(tmp_path)
    build_rewrite_queue(tmp_path)
    rc = main([
        "survey-rewrite-run",
        "--output-dir", str(tmp_path),
        "--writer-backend", "human-packet",
        "--allow-pending",
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["waiting"] == 1
    assert payload["results"][0]["expected_response"].endswith("human_responses/round_01.md")
