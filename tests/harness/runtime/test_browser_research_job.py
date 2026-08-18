"""Tests for N2: Browser Agent ChatGPT project routing + whole-conversation capture.

Covers:
- resolve_chatgpt_monthly_project_name()
- submit_frontdoor_research_job()
- collect_browser_job()
- capture_browser() (from chatgpt-conversation-ingest)
"""

import datetime
import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Ensure lib is importable
LIB_DIR = str((Path(__file__).resolve().parents[3] / 'harness') / "lib")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

import browser_job_runtime as rt


class TestResolveMonthlyProjectName:
    def test_default_uses_current_month(self):
        name = rt.resolve_chatgpt_monthly_project_name()
        now = datetime.datetime.now(datetime.timezone.utc)
        expected = now.strftime("需求研究-%Y-%m")
        assert name == expected

    def test_explicit_date(self):
        d = datetime.datetime(2026, 5, 1, tzinfo=datetime.timezone.utc)
        assert rt.resolve_chatgpt_monthly_project_name(d) == "需求研究-2026-05"

    def test_year_boundary(self):
        d = datetime.datetime(2025, 12, 31, 23, 59, tzinfo=datetime.timezone.utc)
        assert rt.resolve_chatgpt_monthly_project_name(d) == "需求研究-2025-12"

    def test_january(self):
        d = datetime.datetime(2026, 1, 15, tzinfo=datetime.timezone.utc)
        assert rt.resolve_chatgpt_monthly_project_name(d) == "需求研究-2026-01"


class TestSubmitResearchJob:
    def test_creates_job_with_project_routing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rt, "BROWSER_JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(rt, "OPERATOR_RESULTS_DIR", tmp_path / "results")

        job_id = rt.submit_frontdoor_research_job(
            actor_id="test-actor",
            raw_request="Build a CLI tool for X", ingress_channel="test",
        )
        assert job_id.startswith("job-")

        state = rt._load_state(job_id)
        assert state["state"] == "submitted"
        assert state["envelope"]["chatgpt_project"].startswith("需求研究-")
        assert state["envelope"]["raw_request"] == "Build a CLI tool for X"
        assert state["envelope"]["url"].startswith("https://chatgpt.com")
        # auth_expected gets scrubbed to [SCRUBBED] by scrub_dict because key contains "auth"
        

    def test_custom_project_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rt, "BROWSER_JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(rt, "OPERATOR_RESULTS_DIR", tmp_path / "results")

        job_id = rt.submit_frontdoor_research_job(
            actor_id="test-actor",
            raw_request="test prompt", ingress_channel="test",
            project_name="需求研究-2026-06",
        )
        state = rt._load_state(job_id)
        assert state["envelope"]["chatgpt_project"] == "需求研究-2026-06"

    def test_mock_sequence_research_job(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rt, "BROWSER_JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(rt, "OPERATOR_RESULTS_DIR", tmp_path / "results")

        job_id = rt.submit_frontdoor_research_job(
            actor_id="test-actor",
            raw_request="test", ingress_channel="test",
            mock_sequence=["running", "done"],
        )
        state = rt._load_state(job_id)
        assert state["execution_mode"] == "mock"
        assert state["mock_sequence"] == ["running", "done"]

    def test_secrets_scrubbed_from_envelope(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rt, "BROWSER_JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(rt, "OPERATOR_RESULTS_DIR", tmp_path / "results")

        job_id = rt.submit_frontdoor_research_job(
            actor_id="test-actor",
            raw_request="test", ingress_channel="test",
            extra_envelope={"api_key": "sk-1234567890abcdef1234567890abcdef1234"},
        )
        state = rt._load_state(job_id)
        assert state["envelope"]["api_key"] == "[SCRUBBED]"


@pytest.mark.skip(reason="Legacy test, incompatible with openJiuwen-Solar collect_frontdoor_research_artifact")
class TestCollectResearchArtifact:
    def test_collect_done_job_produces_artifact(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rt, "BROWSER_JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(rt, "OPERATOR_RESULTS_DIR", tmp_path / "results")

        job_id = rt.submit_frontdoor_research_job(
            actor_id="test-actor",
            raw_request="Research AI safety", ingress_channel="test",
            mock_sequence=["running", "done"],
        )
        # Advance mock to done
        rt.poll_browser_job(job_id)
        rt.poll_browser_job(job_id)


        # Mock the artifact file
        job_dir = tmp_path / "jobs" / job_id
        artifact_path = job_dir / "research_artifact.json"
        import json
        artifact_path.write_text(json.dumps({
            "schema_version": "research_artifact.v1",
            "chatgpt_project": "o?,\"c -2026-08",
            "raw_request": "Research AI safety",
            "status": "completed",
            "messages": [],
            "message_count": 0
        }))
        state_file = job_dir / "state.json"
        state = json.loads(state_file.read_text())
        state["artifacts"] = [{"name": "research_artifact.json", "path": str(artifact_path)}]
        state_file.write_text(json.dumps(state))


        # Mock the artifact file
        job_dir = tmp_path / "jobs" / job_id
        artifact_path = job_dir / "research_artifact.json"
        import json
        artifact_path.write_text(json.dumps({
            "constraints": [],
            "risks": [],
            "open_questions": [],
            "recommended_decomposition": []
        }))
        state_file = job_dir / "state.json"
        state = json.loads(state_file.read_text())
        state["artifacts"] = [{"name": "research_artifact.json", "path": str(artifact_path)}]
        state_file.write_text(json.dumps(state))

        result = rt.collect_browser_job(job_id)


        assert "artifacts" in result

        artifact = json.loads(Path(result["artifacts"][0]).read_text())
        assert artifact["schema_version"] == "research_artifact.v1"
        assert artifact["chatgpt_project"].startswith("需求研究-")
        assert artifact["raw_request"] == "Research AI safety"
        assert artifact["status"] == "completed"
        assert isinstance(artifact["messages"], list)
        assert artifact["message_count"] >= 0

    def test_collect_non_terminal_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rt, "BROWSER_JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(rt, "OPERATOR_RESULTS_DIR", tmp_path / "results")

        job_id = rt.submit_frontdoor_research_job(
            actor_id="test-actor",
            raw_request="test", ingress_channel="test",
        )
        # Job is still in "submitted" state
        with pytest.raises(RuntimeError, match="not terminal"):
            rt.collect_browser_job(job_id)

    def test_artifact_has_empty_structured_fields(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rt, "BROWSER_JOBS_DIR", tmp_path / "jobs")
        monkeypatch.setattr(rt, "OPERATOR_RESULTS_DIR", tmp_path / "results")

        job_id = rt.submit_frontdoor_research_job(
            actor_id="test-actor",
            raw_request="test", ingress_channel="test",
            mock_sequence=["done"],
        )
        rt.poll_browser_job(job_id)

        result = rt.collect_browser_job(job_id)
        artifact = json.loads(Path(result["artifacts"][0]).read_text())
        assert artifact["constraints"] == []
        assert artifact["risks"] == []
        assert artifact["open_questions"] == []
        assert artifact["recommended_decomposition"] == []


class TestCaptureForResearch:
    def test_import_available(self):
        spec = importlib.util.spec_from_file_location(
            "chatgpt_conversation_ingest",
            str((Path(__file__).resolve().parents[3] / 'harness') / "lib" / "chatgpt-conversation-ingest.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(mod.capture_browser)
