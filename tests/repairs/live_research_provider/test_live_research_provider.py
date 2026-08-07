from __future__ import annotations

import json

import pytest

from plugins.autosci.backends.real_data_research import run_live_research
from plugins.autosci.operators.research_synthesis.base import ResearchOperatorError


def _provider(*, seed_snapshot, payload):
    topic = payload["topic"]
    return {
        "query": topic,
        "request_sha256": "a" * 64,
        "response_sha256": "b" * 64,
        "candidates": [
            {
                "source_id": f"openalex:{index}",
                "title": f"{topic} evidence {index}",
                "url": f"https://api.openalex.org/works/W{index}",
                "provider": "openalex",
                "content_summary": f"{topic} evaluation method and limitation {index}.",
                "provenance": {"discovered_at": "2026-08-07T00:00:00Z"},
            }
            for index in range(1, 4)
        ],
    }


def test_live_provider_run_persists_complete_boundary_and_relevant_report(tmp_path):
    topic = "retrieval augmented generation evaluation"
    result = run_live_research(topic=topic, run_dir=tmp_path, discover=_provider, retry_delays=(0,))
    assert result["status"] == "PASS"
    evidence = result["source_pack"]["provider_evidence"]
    assert len(evidence) == 3
    assert all(item["source_url"] and item["provider"] and item["query"] and item["retrieved_at"] and item["content_sha256"] for item in evidence)
    assert all(item["response_status"] == 200 for item in evidence)
    report = (tmp_path / "research-report.md").read_text(encoding="utf-8")
    assert topic in report
    assert all(item["source_url"] in report for item in evidence)
    state = json.loads((tmp_path / "research-run-state.json").read_text(encoding="utf-8"))
    assert state["completed_nodes"] == ["discover", "survey", "research"]
    assert state["state"] == "completed"


def test_timeout_is_bounded_and_resume_token_preserves_completed_prefix(tmp_path):
    calls = 0

    def timeout_provider(**_kwargs):
        nonlocal calls
        calls += 1
        raise ResearchOperatorError("timed out", error_type="provider_unavailable")

    result = run_live_research(topic="topic", run_dir=tmp_path, discover=timeout_provider, retry_delays=(0, 0, 0))
    assert result["status"] == "ENVIRONMENT_BLOCKED"
    assert calls == 3
    assert result["resume_token"]
    state = json.loads((tmp_path / "research-run-state.json").read_text(encoding="utf-8"))
    assert state["state"] == "resumable"
    assert state["resume_token"] == result["resume_token"]


def test_provider_failure_does_not_create_source_or_report_artifacts(tmp_path):
    def failing_provider(**_kwargs):
        raise ResearchOperatorError("provider returned 503", error_type="provider_http_error")

    result = run_live_research(topic="topic", run_dir=tmp_path, discover=failing_provider, retry_delays=(0, 0))
    assert result["status"] == "ENVIRONMENT_BLOCKED"
    assert not (tmp_path / "source-pack" / "sources.jsonl").exists()
    assert not (tmp_path / "research-report.md").exists()


def test_completed_run_is_not_reinvoked_or_rewritten(tmp_path):
    run_live_research(topic="topic", run_dir=tmp_path, discover=_provider, retry_delays=(0,))

    def should_not_run(**_kwargs):
        pytest.fail("completed provider request must not be charged twice")

    result = run_live_research(topic="topic", run_dir=tmp_path, discover=should_not_run, retry_delays=(0,))
    assert result["status"] == "PASS"
    assert result["resumed"] is True
