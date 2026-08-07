from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.survey.finalize_run import finalize_survey_run
from research.survey.status_next import survey_status_next_action


def _write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def test_status_next_not_started(tmp_path):
    payload = survey_status_next_action(tmp_path, brief="latent reasoning")
    assert payload["ok"] is True
    assert payload["status"] == "not_started"
    assert "survey-finalize-run" in payload["next_action"]
    assert "--brief" in payload["next_action"]


def test_status_next_source_gap_requires_handoff_search(tmp_path):
    finalize_survey_run(tmp_path, brief="latent reasoning")
    payload = survey_status_next_action(tmp_path, brief="latent reasoning")
    assert payload["status"] == "need_search_results"
    assert payload["reason"] == "source_gap_handoff_required"
    assert payload["handoff_path"].endswith("survey_source_gap_handoff.md")
    assert "survey-import-search-results" in payload["next_action"]


def test_status_next_returned_markdown_requires_import(tmp_path):
    finalize_survey_run(tmp_path, brief="latent reasoning")
    returned = tmp_path / "returned_sources.md"
    returned.write_text("# External Search Results: latent reasoning\n", encoding="utf-8")
    payload = survey_status_next_action(tmp_path, brief="latent reasoning")
    assert payload["status"] == "need_import_results"
    assert payload["returned_md"] == str(returned)
    assert "--continue-finalize" in payload["next_action"]


def test_status_next_imported_ledgers_are_ready_to_finalize(tmp_path):
    _write_json(tmp_path / "survey_import_search_results.json", {"ok": True, "imported_sources": 4})
    _write_jsonl(tmp_path / "sources.jsonl", [{"id": "src_1", "source_type": "paper"}])
    _write_jsonl(tmp_path / "evidence.jsonl", [{"id": "ev_1", "source_id": "src_1"}])
    _write_jsonl(tmp_path / "claims.jsonl", [{"id": "cl_1", "claim_text": "latent reasoning"}])
    payload = survey_status_next_action(tmp_path, brief="latent reasoning")
    assert payload["status"] == "ready_to_finalize"
    assert payload["counts"]["sources"] == 1
    assert "survey-finalize-run" in payload["next_action"]


def test_status_next_done_when_finalize_passed(tmp_path):
    (tmp_path / "final.md").write_text("# Final\n", encoding="utf-8")
    _write_json(tmp_path / "survey_finalize_run.json", {"ok": True, "reason": "passed"})
    payload = survey_status_next_action(tmp_path)
    assert payload["status"] == "done"
    assert payload["next_action"].startswith("open ")


def test_status_next_detects_incomplete_quality_gate(tmp_path):
    _write_json(tmp_path / "survey_finalize_run.json", {
        "ok": False,
        "reason": "final_eval_failed",
        "final_eval": {"scorecard": {"issues": ["incomplete_sections:29", "pending_placeholder_count:29"]}},
    })
    _write_json(tmp_path / "survey_final_quality.json", {"pending_placeholder_count": 29})
    payload = survey_status_next_action(tmp_path, brief="latent reasoning", require_complete=True)
    assert payload["status"] == "needs_more_sections"
    assert payload["reason"] == "complete_survey_sections_required"
    assert "--require-complete" in payload["next_action"]


def test_status_next_detects_quality_gate_failure(tmp_path):
    _write_json(tmp_path / "survey_finalize_run.json", {
        "ok": False,
        "reason": "final_eval_failed",
        "final_eval": {"scorecard": {"issues": ["final_char_count_low:100<30000"]}},
    })
    payload = survey_status_next_action(tmp_path)
    assert payload["status"] == "quality_gate_failed"
    assert "survey-auto-repair" in payload["next_action"]
