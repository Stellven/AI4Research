from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.survey.planner import create_survey_plan, write_survey_plan
from research.survey.source_gap import assess_source_gap, write_source_gap_handoff


def _append_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def test_source_gap_reports_missing_ledgers_and_writes_handoff(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    payload = write_source_gap_handoff(tmp_path, brief="latent reasoning")
    assert payload["ok"] is False
    assert "source_count_low:0<4" in payload["issues"]
    assert "paper" in payload["missing_source_types"]
    handoff = tmp_path / "survey_source_gap_handoff.md"
    assert handoff.exists()
    text = handoff.read_text(encoding="utf-8")
    assert "Solar DeepResearch Survey Source Gap Handoff" in text
    assert "External Search Results" in text
    assert "Copy/Paste returned_sources.md Template" in text
    assert "returned_sources.md" in text
    assert "solar-harness research survey-continue" in text
    assert "## Source 1: <title>" in text
    assert "Source Type: paper" in text
    assert "Research Angles: literature_lineage" in text
    assert "Required Research Angles" in text
    assert "literature_lineage" in text
    assert "method_taxonomy" in text
    assert "evaluation_protocol" in text
    assert "controversy" in text
    assert "engineering" in text
    assert "Required returned Source blocks" in text


def test_source_gap_handoff_scales_template_to_claim_and_evidence_gap(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    payload = write_source_gap_handoff(tmp_path, brief="latent reasoning", min_evidence=32, min_claims=32, max_results=12)
    assert payload["ok"] is False
    text = (tmp_path / "survey_source_gap_handoff.md").read_text(encoding="utf-8")
    assert "Evidence: `0/32`" in text
    assert "Claims: `0/32`" in text
    assert "Required returned Source blocks: `16` minimum" in text
    assert "## Source 16: <title>" in text
    for angle in ["literature_lineage", "method_taxonomy", "evaluation_protocol", "controversy", "engineering"]:
        assert f"Research Angles: {angle}" in text


def test_source_gap_passes_with_minimal_diverse_ledgers(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = [
        {"id": "src_p", "source_type": "paper", "title": "paper"},
        {"id": "src_o", "source_type": "official_doc", "title": "official"},
        {"id": "src_c", "source_type": "code", "title": "code"},
        {"id": "src_b", "source_type": "benchmark", "title": "benchmark"},
    ]
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(8)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(8)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    payload = assess_source_gap(tmp_path, brief="latent reasoning")
    assert payload["ok"] is True
    assert payload["issues"] == []
