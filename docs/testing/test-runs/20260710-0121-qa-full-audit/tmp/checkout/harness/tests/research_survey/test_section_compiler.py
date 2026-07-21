from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.survey.evidence_pack import build_evidence_packs
from research.survey.backends import LocalCommandWriterError, PanePacketSurveyWriterBackend
from research.survey.planner import create_survey_plan, write_survey_plan
from research.survey.section_compiler import compile_section, compile_survey
from research.survey.writing_loop import run_ready_sections, run_section_revision_loop, watch_pane_responses


def _append_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _strong_fixture(root):
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


def test_compile_section_refuses_blocked_pack(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    build_evidence_packs(tmp_path, plan["report_ast"])
    result = compile_section(tmp_path, "ch01/sec01")
    assert result["ok"] is False
    assert result["reason"] == "evidence_pack_blocked"


def test_compile_section_and_survey(tmp_path):
    _strong_fixture(tmp_path)
    result = compile_section(tmp_path, "ch01/sec01")
    assert result["ok"] is True
    assert result["rounds"] >= 1
    assert result["writer_backend"] == "deterministic"
    assert (tmp_path / "sections" / "ch01" / "sec01" / "final.md").exists()
    assert (tmp_path / "sections" / "ch01" / "sec01" / "revision_trace.json").exists()
    assert (tmp_path / "sections" / "ch01" / "sec01" / "prompt_packets" / "round_00.json").exists()
    assert (tmp_path / "sections" / "ch01" / "sec01" / "prompt_packets" / "round_00.md").exists()
    packet = json.loads((tmp_path / "sections" / "ch01" / "sec01" / "prompt_packets" / "round_00.json").read_text(encoding="utf-8"))
    assert packet["writing_policy"]["policy_id"] == "solar.survey.professor_grade_writing.v1"
    template = packet["writing_policy"]["section_template"]
    assert "Literature Lineage" in template
    assert "Method Taxonomy" in template
    assert "Evaluation Protocol Matrix" in template
    assert "Controversy Matrix" in template
    assert packet["chapter_context"]["chapter_id"] == "ch01"
    assert (tmp_path / "chapters" / "ch01" / "prompt_packet.md").exists()
    assert "Professor-Grade Section Template" in (tmp_path / "chapters" / "ch01" / "prompt_packet.md").read_text(encoding="utf-8")
    compiled = compile_survey(tmp_path)
    assert compiled["ok"] is True
    assert (tmp_path / "final.md").exists()
    assert (tmp_path / "human_final.md").exists()
    assert (tmp_path / "survey_contribution_matrix.json").exists()
    assert (tmp_path / "survey_final_summary.json").exists()
    assert (tmp_path / "survey_human_final_summary.json").exists()
    assert (tmp_path / "survey_execution_metrics.json").exists()
    assert (tmp_path / "survey_human_execution_metrics.json").exists()
    assert (tmp_path / "chapters" / "ch01" / "editorial_review.json").exists()
    assert compiled["human_final_md"].endswith("human_final.md")
    assert compiled["execution_metrics"]["document_word_count"] > 0
    assert compiled["execution_metrics"]["total_token_consumption"] > 0
    final_text = (tmp_path / "final.md").read_text(encoding="utf-8")
    assert "## Executive Summary" in final_text
    assert "## Technical Summary" in final_text
    assert "## Contribution Matrix" in final_text
    assert "## Roadmap" in final_text
    assert "## Chapter Synthesis" in final_text
    assert "## Execution Metrics" in final_text
    assert "Total token consumption" in final_text
    assert "Document word count" in final_text
    human_text = (tmp_path / "human_final.md").read_text(encoding="utf-8")
    assert "## Contribution Matrix" not in human_text
    assert "## Technical Summary" not in human_text
    assert "## Claim Map" not in human_text
    assert "## Evidence Map" not in human_text
    assert "prompt packet" not in human_text.lower()
    assert "## 核心结论" in human_text
    assert "## 证据基础" in human_text
    matrix = json.loads((tmp_path / "survey_contribution_matrix.json").read_text(encoding="utf-8"))
    assert matrix["finalized_sections"] == 1
    assert matrix["rows"][0]["has_literature_lineage"] is True
    assert matrix["rows"][0]["has_method_taxonomy"] is True
    assert matrix["rows"][0]["has_comparative_positioning"] is True
    assert matrix["rows"][0]["has_terminology_evolution"] is True
    assert matrix["rows"][0]["has_evaluation_protocol_matrix"] is True
    assert matrix["rows"][0]["has_controversy_matrix"] is True
    summary = json.loads((tmp_path / "survey_final_summary.json").read_text(encoding="utf-8"))
    assert summary["technical_summary"]
    human_summary = json.loads((tmp_path / "survey_human_final_summary.json").read_text(encoding="utf-8"))
    assert human_summary["ok"] is True
    assert human_summary["template_heading_count"] == 0
    assert human_summary["char_count"] < len(final_text)
    assert human_summary["execution_metrics"]["document_word_count"] > 0


def test_deterministic_writer_outputs_professor_survey_scaffolds(tmp_path):
    _strong_fixture(tmp_path)
    result = run_section_revision_loop(tmp_path, "ch01/sec01", min_chars=3200, max_rounds=3)
    assert result["ok"] is True
    text = (tmp_path / "sections" / "ch01" / "sec01" / "final.md").read_text(encoding="utf-8")
    for heading in [
        "## Literature Lineage",
        "## Method Taxonomy",
        "## Terminology Evolution",
        "## Evaluation Protocol Matrix",
        "## Controversy Matrix",
    ]:
        assert heading in text
    assert "chain-of-thought" in text
    assert "baseline" in text
    assert "ablation" in text
    assert "negative evidence" in text or "负面证据" in text


def test_revision_loop_requires_enough_detail(tmp_path):
    _strong_fixture(tmp_path)
    result = run_section_revision_loop(tmp_path, "ch01/sec01", min_chars=3200, max_rounds=3)
    assert result["ok"] is True
    assert result["rounds"] > 1
    review = json.loads((tmp_path / "sections" / "ch01" / "sec01" / "review.json").read_text(encoding="utf-8"))
    assert review["verdict"] == "PASS"


def test_run_ready_sections_batches_without_manual_continue(tmp_path):
    _strong_fixture(tmp_path)
    result = run_ready_sections(tmp_path, limit=2, max_rounds=3, min_chars=1200)
    assert result["ok"] is True
    assert result["processed"] == 2
    assert result["passed"] == 2


def test_human_packet_backend_waits_for_response(tmp_path):
    _strong_fixture(tmp_path)
    result = run_section_revision_loop(tmp_path, "ch01/sec01", writer_backend="human-packet")
    assert result["ok"] is False
    assert result["reason"] == "human_response_missing"
    assert result["expected_response"].endswith("human_responses/round_00.md")
    assert (tmp_path / "sections" / "ch01" / "sec01" / "prompt_packets" / "round_00.md").exists()
    review = json.loads((tmp_path / "sections" / "ch01" / "sec01" / "review.json").read_text(encoding="utf-8"))
    assert review["verdict"] == "WAITING_FOR_HUMAN"


def test_human_packet_backend_consumes_response(tmp_path):
    _strong_fixture(tmp_path)
    section_dir = tmp_path / "sections" / "ch01" / "sec01"
    pack = json.loads((section_dir / "evidence_pack.json").read_text(encoding="utf-8"))
    claim_ids = pack["claim_ids"][:3]
    evidence_ids = pack["evidence_ids"][:4]
    response = section_dir / "human_responses" / "round_00.md"
    response.parent.mkdir(parents=True)
    response.write_text(
        "# Human Section\n\n"
        "## Architecture Synthesis\n\n"
        f"Human response with [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}].\n\n"
        "## Comparative Positioning\n\n"
        f"Comparison response with [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}].\n\n"
        "## Evaluation And Risk Boundary\n\n"
        f"Evaluation response with [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}].\n\n"
        "## Limitations And Failure Modes\n\n"
        f"Limitations response with [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}].\n\n"
        "## Contradiction Slots\n\n"
        f"Contradiction response with [claim:{claim_ids[2]}] [evidence:{evidence_ids[2]}] [evidence:{evidence_ids[3]}].\n\n"
        "## Source Map\n\n"
        "Sources are preserved.\n\n"
        "## Claim Map\n\n"
        "Claims are preserved.\n\n"
        "## Open Problems\n\n"
        "Open problems are preserved.\n",
        encoding="utf-8",
    )
    result = run_section_revision_loop(tmp_path, "ch01/sec01", writer_backend="human-packet", min_chars=100)
    assert result["ok"] is True
    assert result["writer_backend"] == "human-packet"
    assert "Human response" in (section_dir / "final.md").read_text(encoding="utf-8")


def test_human_packet_fallback_keeps_automation_running(tmp_path):
    _strong_fixture(tmp_path)
    result = run_section_revision_loop(tmp_path, "ch01/sec01", writer_backend="human-packet-fallback")
    assert result["ok"] is True
    assert result["writer_backend"] == "human-packet-fallback"


def test_local_command_backend_consumes_stdout(tmp_path):
    _strong_fixture(tmp_path)
    section_dir = tmp_path / "sections" / "ch01" / "sec01"
    pack = json.loads((section_dir / "evidence_pack.json").read_text(encoding="utf-8"))
    claim_ids = pack["claim_ids"][:3]
    evidence_ids = pack["evidence_ids"][:4]
    script = tmp_path / "writer.py"
    script.write_text(
        "import sys\n"
        "sys.stdin.read()\n"
        "print('# Local Command Section')\n"
        "print('\\n## Architecture Synthesis\\n')\n"
        f"print('Local command with [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}].')\n"
        "print('\\n## Comparative Positioning\\n')\n"
        f"print('Comparison with [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}].')\n"
        "print('\\n## Evaluation And Risk Boundary\\n')\n"
        f"print('Evaluation with [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}].')\n"
        "print('\\n## Limitations And Failure Modes\\n')\n"
        f"print('Limitations with [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}].')\n"
        "print('\\n## Contradiction Slots\\n')\n"
        f"print('Contradiction with [claim:{claim_ids[2]}] [evidence:{evidence_ids[2]}] [evidence:{evidence_ids[3]}].')\n"
        "print('\\n## Source Map\\nSources preserved.')\n"
        "print('\\n## Claim Map\\nClaims preserved.')\n"
        "print('\\n## Open Problems\\nOpen problems preserved.')\n",
        encoding="utf-8",
    )
    result = run_section_revision_loop(
        tmp_path,
        "ch01/sec01",
        writer_backend="local-command",
        writer_command=f"{sys.executable} {script}",
        min_chars=100,
    )
    assert result["ok"] is True
    assert result["writer_backend"] == "local-command"
    assert "Local command" in (section_dir / "final.md").read_text(encoding="utf-8")
    usage_rows = [
        json.loads(line)
        for line in (tmp_path / "model_usage.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert usage_rows
    assert usage_rows[0]["token_usage_is_estimated"] is True


def test_local_command_backend_records_real_usage_json(tmp_path):
    _strong_fixture(tmp_path)
    section_dir = tmp_path / "sections" / "ch01" / "sec01"
    pack = json.loads((section_dir / "evidence_pack.json").read_text(encoding="utf-8"))
    claim_ids = pack["claim_ids"][:3]
    evidence_ids = pack["evidence_ids"][:4]
    script = tmp_path / "writer_json.py"
    body = (
        "## Architecture Synthesis\n\n"
        f"JSON writer with [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}].\n\n"
        "## Comparative Positioning\n\nComparison text.\n\n"
        f"## Evaluation And Risk Boundary\n\nEvaluation with [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}].\n\n"
        f"## Limitations And Failure Modes\n\nLimitations with [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}].\n\n"
        f"## Contradiction Slots\n\nContradiction with [claim:{claim_ids[2]}] [evidence:{evidence_ids[2]}] [evidence:{evidence_ids[3]}].\n\n"
        "## Source Map\n\nSources.\n\n"
        "## Claim Map\n\nClaims.\n\n"
        "## Open Problems\n\nOpen problems.\n"
    )
    script.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        f"print(json.dumps({{'result': {body!r}, 'usage': {{'input_tokens': 123, 'output_tokens': 45, 'total_tokens': 168}}}}))\n",
        encoding="utf-8",
    )
    result = run_section_revision_loop(
        tmp_path,
        "ch01/sec01",
        writer_backend="local-command",
        writer_command=f"{sys.executable} {script}",
        min_chars=100,
    )
    assert result["ok"] is True
    assert "JSON writer" in (section_dir / "final.md").read_text(encoding="utf-8")
    usage_rows = [
        json.loads(line)
        for line in (tmp_path / "model_usage.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert usage_rows[0]["token_usage_is_estimated"] is False
    assert usage_rows[0]["total_tokens"] == 168


def test_local_command_backend_reports_missing_command(tmp_path):
    _strong_fixture(tmp_path)
    result = run_section_revision_loop(tmp_path, "ch01/sec01", writer_backend="local-command")
    assert result["ok"] is False
    assert result["reason"] == "writer_failed"
    assert result["writer_error"] == "missing_command"


def test_local_command_backend_reports_nonzero_exit(tmp_path):
    _strong_fixture(tmp_path)
    result = run_section_revision_loop(
        tmp_path,
        "ch01/sec01",
        writer_backend="local-command",
        writer_command=f"{sys.executable} -c 'import sys; print(\"bad\", file=sys.stderr); sys.exit(7)'",
    )
    assert result["ok"] is False
    assert result["reason"] == "writer_failed"
    assert result["writer_error"].startswith("exit_7:")


def test_pane_packet_backend_prepares_dispatch_and_waits(tmp_path):
    _strong_fixture(tmp_path)
    result = run_section_revision_loop(tmp_path, "ch01/sec01", writer_backend="pane-packet")
    assert result["ok"] is False
    assert result["reason"] == "pane_response_missing"
    assert result["pane_submitted"] is False
    assert result["pane_dispatch"].endswith("pane_dispatch/round_00.md")
    assert result["expected_response"].endswith("human_responses/round_00.md")
    assert (tmp_path / "sections" / "ch01" / "sec01" / "pane_dispatch" / "round_00.md").exists()
    review = json.loads((tmp_path / "sections" / "ch01" / "sec01" / "review.json").read_text(encoding="utf-8"))
    assert review["verdict"] == "WAITING_FOR_PANE"


def test_pane_packet_send_rejects_product_delivery_main_pane(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Result:
            returncode = 0
            stdout = "solar-harness\tPM 产品经理 | 模型:Opus\n"
            stderr = ""

        return Result()

    monkeypatch.delenv("SOLAR_ALLOW_MAIN_PANE_SURVEY_SEND", raising=False)
    monkeypatch.setattr("research.survey.backends.subprocess.run", fake_run)
    backend = PanePacketSurveyWriterBackend(pane_target="solar-harness:0.0", send=True)

    try:
        backend._send_to_pane("/tmp/dispatch.md", "/tmp/response.md")
    except LocalCommandWriterError as exc:
        assert exc.reason.startswith("pane_target_role_forbidden:solar-harness:0.0")
    else:
        raise AssertionError("Product Delivery PM pane should be rejected for survey pane-send")

    assert calls == [["tmux", "display-message", "-p", "-t", "solar-harness:0.0", "#{session_name}\t#{pane_title}"]]


def test_pane_packet_send_allows_lab_builder_pane(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Result:
            returncode = 0
            stderr = ""

        if cmd[:2] == ["tmux", "display-message"]:
            Result.stdout = "solar-harness-lab\tBuilder 1 | 模型:GLM\n"
        else:
            Result.stdout = ""
        return Result()

    monkeypatch.delenv("SOLAR_ALLOW_MAIN_PANE_SURVEY_SEND", raising=False)
    monkeypatch.setattr("research.survey.backends.subprocess.run", fake_run)
    backend = PanePacketSurveyWriterBackend(pane_target="solar-harness-lab:0.0", send=True)

    assert backend._send_to_pane("/tmp/dispatch.md", "/tmp/response.md") is True
    assert any(cmd[:3] == ["tmux", "send-keys", "-t"] for cmd in calls)


def test_pane_packet_backend_consumes_response(tmp_path):
    _strong_fixture(tmp_path)
    section_dir = tmp_path / "sections" / "ch01" / "sec01"
    pack = json.loads((section_dir / "evidence_pack.json").read_text(encoding="utf-8"))
    claim_ids = pack["claim_ids"][:3]
    evidence_ids = pack["evidence_ids"][:4]
    response = section_dir / "human_responses" / "round_00.md"
    response.parent.mkdir(parents=True)
    response.write_text(
        "# Pane Section\n\n"
        "## Architecture Synthesis\n\n"
        f"Pane response with [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}].\n\n"
        "## Comparative Positioning\n\n"
        f"Comparison response with [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}].\n\n"
        "## Evaluation And Risk Boundary\n\n"
        f"Evaluation response with [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}].\n\n"
        "## Limitations And Failure Modes\n\n"
        f"Limitations response with [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}].\n\n"
        "## Contradiction Slots\n\n"
        f"Contradiction response with [claim:{claim_ids[2]}] [evidence:{evidence_ids[2]}] [evidence:{evidence_ids[3]}].\n\n"
        "## Source Map\n\n"
        "Sources are preserved.\n\n"
        "## Claim Map\n\n"
        "Claims are preserved.\n\n"
        "## Open Problems\n\n"
        "Open problems are preserved.\n",
        encoding="utf-8",
    )
    result = run_section_revision_loop(tmp_path, "ch01/sec01", writer_backend="pane-packet", min_chars=100)
    assert result["ok"] is True
    assert result["writer_backend"] == "pane-packet"
    assert "Pane response" in (section_dir / "final.md").read_text(encoding="utf-8")


def test_pane_packet_fallback_keeps_automation_running(tmp_path):
    _strong_fixture(tmp_path)
    result = run_section_revision_loop(tmp_path, "ch01/sec01", writer_backend="pane-packet-fallback")
    assert result["ok"] is True
    assert result["writer_backend"] == "pane-packet-fallback"


def test_watch_pane_responses_reports_pending(tmp_path):
    _strong_fixture(tmp_path)
    result = watch_pane_responses(tmp_path)
    assert result["ok"] is False
    assert result["processed"] == 0
    assert result["pending_responses"] >= 30
    assert (tmp_path / "pane_response_watch.json").exists()


def test_watch_pane_responses_finalizes_existing_response(tmp_path):
    _strong_fixture(tmp_path)
    section_dir = tmp_path / "sections" / "ch01" / "sec01"
    pack = json.loads((section_dir / "evidence_pack.json").read_text(encoding="utf-8"))
    claim_ids = pack["claim_ids"][:3]
    evidence_ids = pack["evidence_ids"][:4]
    response = section_dir / "human_responses" / "round_00.md"
    response.parent.mkdir(parents=True)
    response.write_text(
        "# Watched Pane Section\n\n"
        "## Architecture Synthesis\n\n"
        f"Watched response with [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}].\n\n"
        "## Comparative Positioning\n\n"
        f"Comparison response with [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}].\n\n"
        "## Evaluation And Risk Boundary\n\n"
        f"Evaluation response with [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}].\n\n"
        "## Limitations And Failure Modes\n\n"
        f"Limitations response with [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}].\n\n"
        "## Contradiction Slots\n\n"
        f"Contradiction response with [claim:{claim_ids[2]}] [evidence:{evidence_ids[2]}] [evidence:{evidence_ids[3]}].\n\n"
        "## Source Map\n\n"
        "Sources are preserved.\n\n"
        "## Claim Map\n\n"
        "Claims are preserved.\n\n"
        "## Open Problems\n\n"
        "Open problems are preserved.\n",
        encoding="utf-8",
    )
    result = watch_pane_responses(tmp_path, limit=1, min_chars=100)
    assert result["ok"] is True
    assert result["processed"] == 1
    assert result["passed"] == 1
    assert "Watched response" in (section_dir / "final.md").read_text(encoding="utf-8")
