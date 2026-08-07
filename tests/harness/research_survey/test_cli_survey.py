from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.cli import build_parser, main


def test_survey_cli_commands_registered():
    subs = build_parser()._subparsers._group_actions[0].choices
    for name in ["survey-plan", "survey-pack", "survey-write-section", "survey-run-sections", "survey-watch-responses", "survey-watch-register", "survey-watch-tick", "survey-rewrite-queue", "survey-rewrite-run", "survey-auto-repair", "survey-finalize-run", "survey-import-search-results", "survey-status-next-action", "survey-continue", "survey-review", "survey-compile", "survey-chief-editor", "survey-doctor", "survey-eval", "survey-diagnose"]:
        assert name in subs


def test_survey_plan_cli(tmp_path, capsys):
    assert main([
        "survey-plan",
        "--brief", "隐空间推理技术架构和演进方向",
        "--target-chars", "50000",
        "--output-dir", str(tmp_path),
        "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["chapter_count"] >= 8
    assert payload["section_count"] >= 30
    assert (tmp_path / "survey_report_ast.json").exists()


def test_survey_eval_cli_require_complete_fails_plan_only(tmp_path, capsys):
    assert main([
        "survey-plan",
        "--brief", "隐空间推理技术架构和演进方向",
        "--target-chars", "50000",
        "--output-dir", str(tmp_path),
        "--json",
    ]) == 0
    capsys.readouterr()
    rc = main([
        "survey-eval",
        "--output-dir", str(tmp_path),
        "--strict",
        "--require-complete",
        "--json",
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert any(item.startswith("finalized_sections_low:0<") for item in payload["scorecard"]["issues"])


def test_survey_diagnose_cli_reports_issue_groups_and_next_action(tmp_path, capsys):
    assert main([
        "survey-plan",
        "--brief", "隐空间推理技术架构和演进方向",
        "--target-chars", "50000",
        "--output-dir", str(tmp_path),
        "--json",
    ]) == 0
    capsys.readouterr()
    rc = main([
        "survey-diagnose",
        "--output-dir", str(tmp_path),
        "--write-md",
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["status"] == "fail"
    assert payload["summary"]["sections"] >= 30
    assert payload["summary"]["issue_count"] > 0
    assert any(item["group"] == "completion" for item in payload["issue_groups"])
    assert "survey-continue" in payload["next_action"] or "survey-import-search-results" in payload["next_action"]
    assert (tmp_path / "survey_diagnosis.json").exists()
    assert (tmp_path / "survey_diagnosis.md").exists()


def test_survey_write_rejects_unknown_backend(tmp_path):
    section_dir = tmp_path / "sections" / "ch01" / "sec01"
    section_dir.mkdir(parents=True)
    (section_dir / "section.spec.json").write_text(json.dumps({"section_id": "ch01/sec01", "title": "Test"}, ensure_ascii=False), encoding="utf-8")
    (section_dir / "evidence_pack.json").write_text(json.dumps({
        "section_id": "ch01/sec01",
        "status": "ready",
        "claim_ids": ["cl_1", "cl_2", "cl_3"],
        "evidence_ids": ["ev_1", "ev_2", "ev_3", "ev_4"],
        "source_types": ["paper", "code"],
    }, ensure_ascii=False), encoding="utf-8")
    rc = main([
        "survey-write-section",
        "--output-dir", str(tmp_path),
        "--section-id", "ch01/sec01",
        "--writer-backend", "missing",
        "--json",
    ])
    assert rc == 1


def test_survey_write_human_packet_returns_expected_response(tmp_path, capsys):
    section_dir = tmp_path / "sections" / "ch01" / "sec01"
    section_dir.mkdir(parents=True)
    (section_dir / "section.spec.json").write_text(json.dumps({"section_id": "ch01/sec01", "title": "Test"}, ensure_ascii=False), encoding="utf-8")
    (section_dir / "evidence_pack.json").write_text(json.dumps({
        "section_id": "ch01/sec01",
        "status": "ready",
        "claim_ids": ["cl_1", "cl_2", "cl_3"],
        "evidence_ids": ["ev_1", "ev_2", "ev_3", "ev_4"],
        "source_types": ["paper", "code"],
    }, ensure_ascii=False), encoding="utf-8")
    rc = main([
        "survey-write-section",
        "--output-dir", str(tmp_path),
        "--section-id", "ch01/sec01",
        "--writer-backend", "human-packet",
        "--json",
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "human_response_missing"
    assert payload["expected_response"].endswith("human_responses/round_00.md")


def test_survey_write_local_command_requires_command(tmp_path, capsys):
    section_dir = tmp_path / "sections" / "ch01" / "sec01"
    section_dir.mkdir(parents=True)
    (section_dir / "section.spec.json").write_text(json.dumps({"section_id": "ch01/sec01", "title": "Test"}, ensure_ascii=False), encoding="utf-8")
    (section_dir / "evidence_pack.json").write_text(json.dumps({
        "section_id": "ch01/sec01",
        "status": "ready",
        "claim_ids": ["cl_1", "cl_2", "cl_3"],
        "evidence_ids": ["ev_1", "ev_2", "ev_3", "ev_4"],
        "source_types": ["paper", "code"],
    }, ensure_ascii=False), encoding="utf-8")
    rc = main([
        "survey-write-section",
        "--output-dir", str(tmp_path),
        "--section-id", "ch01/sec01",
        "--writer-backend", "local-command",
        "--json",
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "writer_failed"
    assert payload["writer_error"] == "missing_command"


def test_survey_write_pane_packet_returns_dispatch(tmp_path, capsys):
    section_dir = tmp_path / "sections" / "ch01" / "sec01"
    section_dir.mkdir(parents=True)
    (section_dir / "section.spec.json").write_text(json.dumps({"section_id": "ch01/sec01", "title": "Test"}, ensure_ascii=False), encoding="utf-8")
    (section_dir / "evidence_pack.json").write_text(json.dumps({
        "section_id": "ch01/sec01",
        "status": "ready",
        "claim_ids": ["cl_1", "cl_2", "cl_3"],
        "evidence_ids": ["ev_1", "ev_2", "ev_3", "ev_4"],
        "source_types": ["paper", "code"],
    }, ensure_ascii=False), encoding="utf-8")
    rc = main([
        "survey-write-section",
        "--output-dir", str(tmp_path),
        "--section-id", "ch01/sec01",
        "--writer-backend", "pane-packet",
        "--json",
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "pane_response_missing"
    assert payload["pane_dispatch"].endswith("pane_dispatch/round_00.md")
    assert payload["expected_response"].endswith("human_responses/round_00.md")
    assert payload["pane_submitted"] is False


def test_survey_watch_responses_allow_pending(tmp_path, capsys):
    assert main([
        "survey-plan",
        "--brief", "隐空间推理技术架构和演进方向",
        "--target-chars", "50000",
        "--output-dir", str(tmp_path),
        "--json",
    ]) == 0
    capsys.readouterr()
    rc = main([
        "survey-watch-responses",
        "--output-dir", str(tmp_path),
        "--allow-pending",
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["processed"] == 0
    assert payload["pending_responses"] >= 30
