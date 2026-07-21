from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.survey.evidence_pack import build_evidence_packs
from research.survey.planner import create_survey_plan, write_survey_plan


def _append_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def test_evidence_pack_blocks_weak_sections(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    payload = build_evidence_packs(tmp_path, plan["report_ast"])
    assert payload["ok"] is True
    assert payload["blocked"] == len(plan["report_ast"]["sections"])


def test_evidence_pack_ready_with_diverse_sources(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = [
        {"id": "src_p", "source_type": "paper", "title": "paper"},
        {"id": "src_o", "source_type": "official_doc", "title": "official"},
        {"id": "src_c", "source_type": "code", "title": "code"},
        {"id": "src_b", "source_type": "benchmark", "title": "benchmark"},
    ]
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(12)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(8)]
    links = [{"claim_id": f"cl_{i % 8}", "evidence_id": f"ev_{i}"} for i in range(12)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)

    payload = build_evidence_packs(tmp_path, plan["report_ast"])
    assert payload["ready"] > 0
    first = json.loads((tmp_path / "sections" / "ch01" / "sec01" / "evidence_pack.json").read_text())
    assert first["status"] == "ready"
    assert len(first["evidence_ids"]) >= 4
