from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.cli import main
from research.survey.rewrite_queue import build_rewrite_queue


def _write_scorecard(root):
    payload = {
        "ok": False,
        "section_count": 4,
        "needs_rewrite_count": 3,
        "top_issues": [
            {
                "section_id": "ch01/sec01",
                "status": "needs_rewrite",
                "risk_score": 200,
                "p0_count": 2,
                "p1_count": 0,
                "p2_count": 0,
                "issues": [
                    {"severity": "P0", "code": "unknown_claim_ids", "detail": ["cl_bad"]},
                    {"severity": "P0", "code": "grounding_failures", "detail": [{"evidence_id": "ev_1"}]},
                ],
                "rewrite_recommended": True,
            },
            {
                "section_id": "ch01/sec02",
                "status": "needs_rewrite",
                "risk_score": 25,
                "p0_count": 0,
                "p1_count": 1,
                "p2_count": 0,
                "issues": [{"severity": "P1", "code": "section_structure_shallow", "detail": "3<6"}],
                "rewrite_recommended": True,
            },
            {
                "section_id": "ch01/sec03",
                "status": "pending",
                "risk_score": 100,
                "p0_count": 1,
                "p1_count": 0,
                "p2_count": 0,
                "issues": [{"severity": "P0", "code": "section_final_missing", "detail": "ch01/sec03"}],
                "rewrite_recommended": False,
            },
            {
                "section_id": "ch01/sec04",
                "status": "needs_rewrite",
                "risk_score": 5,
                "p0_count": 0,
                "p1_count": 0,
                "p2_count": 1,
                "issues": [{"severity": "P2", "code": "section_repetition_high", "detail": 0.25}],
                "rewrite_recommended": False,
            },
        ],
    }
    (root / "survey_section_scorecard.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_rewrite_queue_builds_only_actionable_items(tmp_path):
    _write_scorecard(tmp_path)
    payload = build_rewrite_queue(tmp_path)
    assert payload["ok"] is True
    assert payload["queue_count"] == 2
    assert [item["section_id"] for item in payload["items"]] == ["ch01/sec01", "ch01/sec02"]
    assert payload["items"][0]["priority"] == "P0"
    assert payload["items"][0]["target_response"].endswith("human_responses/round_01.md")
    assert (tmp_path / "survey_rewrite_queue.json").exists()


def test_rewrite_queue_filters_max_severity_and_limit(tmp_path):
    _write_scorecard(tmp_path)
    payload = build_rewrite_queue(tmp_path, max_severity="P0", limit=1)
    assert payload["queue_count"] == 1
    assert payload["items"][0]["section_id"] == "ch01/sec01"
    assert all(issue["severity"] == "P0" for issue in payload["items"][0]["issues"])


def test_rewrite_queue_accepts_sections_scorecard_shape(tmp_path):
    payload = {
        "sections": [
            {
                "section_id": "ch02/sec01",
                "status": "needs_rewrite",
                "risk_score": 40,
                "issues": [{"severity": "P1", "code": "citation_weak"}],
            }
        ],
    }
    (tmp_path / "survey_section_scorecard.json").write_text(json.dumps(payload), encoding="utf-8")
    result = build_rewrite_queue(tmp_path)
    assert result["queue_count"] == 1
    assert result["items"][0]["section_id"] == "ch02/sec01"


def test_rewrite_queue_cli(tmp_path, capsys):
    _write_scorecard(tmp_path)
    assert main([
        "survey-rewrite-queue",
        "--output-dir", str(tmp_path),
        "--max-severity", "P1",
        "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["queue_count"] == 2


def test_rewrite_queue_adds_chapter_review_items(tmp_path):
    (tmp_path / "sections" / "ch03" / "sec01").mkdir(parents=True)
    (tmp_path / "sections" / "ch03" / "sec01" / "final.md").write_text("current", encoding="utf-8")
    (tmp_path / "sections" / "ch03" / "sec01" / "section.spec.json").write_text("{}", encoding="utf-8")
    (tmp_path / "sections" / "ch03" / "sec01" / "evidence_pack.json").write_text("{}", encoding="utf-8")
    (tmp_path / "survey_section_scorecard.json").write_text(json.dumps({"top_issues": []}), encoding="utf-8")
    (tmp_path / "survey_chapter_review.json").write_text(json.dumps({
        "chapters": [
            {
                "chapter_id": "ch03",
                "title": "核心架构范式",
                "section_ids": ["ch03/sec01", "ch03/sec02"],
                "issues": [{"severity": "P1", "code": "chapter_source_diversity_low", "detail": "1<2"}],
            }
        ]
    }), encoding="utf-8")
    result = build_rewrite_queue(tmp_path)
    assert result["queue_count"] == 1
    assert result["items"][0]["chapter_id"] == "ch03"
    assert result["items"][0]["action"] == "rewrite_section_from_chapter_review"
