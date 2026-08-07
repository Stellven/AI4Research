from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.cli import build_parser, main
from research.survey.watch_automation import register_watch_run, tick_watch_config


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _make_survey_run(root):
    section_id = "ch01/sec01"
    _write_json(root / "survey_report_ast.json", {"sections": [{"section_id": section_id}]})
    _write_json(root / "sections" / "ch01" / "sec01" / "section.spec.json", {
        "section_id": section_id,
        "title": "Latent Reasoning Architecture",
        "research_question": "How should latent reasoning systems be evaluated?",
    })
    _write_json(root / "sections" / "ch01" / "sec01" / "evidence_pack.json", {
        "section_id": section_id,
        "status": "ready",
        "claim_ids": ["cl_1", "cl_2", "cl_3"],
        "evidence_ids": ["ev_1", "ev_2", "ev_3", "ev_4"],
        "source_ids": ["src_1", "src_2"],
        "source_types": ["paper", "code"],
    })
    rows = {
        "sources.jsonl": [
            {"id": "src_1", "source_type": "paper", "title": "Paper Source"},
            {"id": "src_2", "source_type": "code", "title": "Code Source"},
        ],
        "evidence.jsonl": [
            {"id": "ev_1", "source_id": "src_1", "content": "evidence one"},
            {"id": "ev_2", "source_id": "src_1", "content": "evidence two"},
            {"id": "ev_3", "source_id": "src_2", "content": "evidence three"},
            {"id": "ev_4", "source_id": "src_2", "content": "evidence four"},
        ],
        "claims.jsonl": [
            {"id": "cl_1", "claim_text": "claim one"},
            {"id": "cl_2", "claim_text": "claim two"},
            {"id": "cl_3", "claim_text": "claim three"},
        ],
    }
    for filename, values in rows.items():
        (root / filename).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in values), encoding="utf-8")
    return section_id


def _passing_response_text():
    return """# Latent Reasoning Architecture

## Research Question

This section explains the research question with [claim:cl_1] and [evidence:ev_1].

## Position

The architecture must separate mechanism, system boundary, and evaluation evidence [claim:cl_2] [evidence:ev_2].

## Architecture Synthesis

Latent reasoning should be treated as a system property rather than a slogan [claim:cl_3] [evidence:ev_3].

## Comparative Positioning

Paper evidence should define mechanisms, while code evidence should constrain implementation and reproducibility claims [claim:cl_1] [evidence:ev_1].

## Evaluation And Risk Boundary

Evaluation needs explicit benchmarks, failure modes, and reproducibility limits [claim:cl_1] [evidence:ev_4].

## Limitations And Failure Modes

The section must state where the evidence is narrow, where implementation gaps remain, and where benchmark results cannot be generalized [claim:cl_2] [evidence:ev_2].

## Contradiction Slots

Contradiction search must preserve weak and mixed evidence instead of hiding it.

## Open Problems

Open problems include observability, transfer, benchmark leakage, and cross-section consistency.
"""


def test_survey_watch_automation_commands_registered():
    subs = build_parser()._subparsers._group_actions[0].choices
    assert "survey-watch-register" in subs
    assert "survey-watch-tick" in subs


def test_watch_tick_pending_is_not_fake_completion(tmp_path):
    run_dir = tmp_path / "run"
    _make_survey_run(run_dir)
    config = tmp_path / "watch.json"
    register = register_watch_run(run_dir, config_path=config, min_chars=200)
    assert register["ok"] is True

    payload = tick_watch_config(config)
    assert payload["ok"] is True
    assert payload["processed_total"] == 0
    assert payload["pending_total"] == 1
    assert not (run_dir / "sections" / "ch01" / "sec01" / "final.md").exists()


def test_watch_tick_finalizes_returned_response(tmp_path):
    run_dir = tmp_path / "run"
    _make_survey_run(run_dir)
    response = run_dir / "sections" / "ch01" / "sec01" / "human_responses" / "round_00.md"
    response.parent.mkdir(parents=True, exist_ok=True)
    response.write_text(_passing_response_text(), encoding="utf-8")
    config = tmp_path / "watch.json"
    register_watch_run(run_dir, config_path=config, min_chars=200)

    payload = tick_watch_config(config)
    assert payload["ok"] is True
    assert payload["processed_total"] == 1
    assert payload["passed_total"] == 1
    assert (run_dir / "sections" / "ch01" / "sec01" / "final.md").exists()


def test_watch_tick_disabled_noop(tmp_path):
    run_dir = tmp_path / "run"
    _make_survey_run(run_dir)
    config = tmp_path / "watch.json"
    register_watch_run(run_dir, config_path=config, enabled=False)
    data = json.loads(config.read_text(encoding="utf-8"))
    data["enabled"] = False
    config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    payload = tick_watch_config(config)
    assert payload["ok"] is True
    assert payload["disabled"] is True
    assert payload["processed_total"] == 0


def test_survey_watch_register_and_tick_cli(tmp_path, capsys):
    run_dir = tmp_path / "run"
    _make_survey_run(run_dir)
    config = tmp_path / "watch.json"
    assert main([
        "survey-watch-register",
        "--output-dir", str(run_dir),
        "--config", str(config),
        "--min-chars", "200",
        "--json",
    ]) == 0
    capsys.readouterr()
    assert main([
        "survey-watch-tick",
        "--config", str(config),
        "--allow-pending",
        "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["processed_total"] == 0
    assert payload["pending_total"] == 1
