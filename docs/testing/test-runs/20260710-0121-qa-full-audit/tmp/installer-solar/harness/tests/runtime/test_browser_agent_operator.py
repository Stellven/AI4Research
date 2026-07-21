"""test_browser_agent_operator.py — Unit tests for async Browser Agent job runtime and mock adapter.

Verifies submit, poll, collect, and cancel flows under the mock job runner.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Path setup
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

import browser_job_runtime as bjrt


@pytest.fixture(autouse=True)
def setup_teardown_env(monkeypatch):
    """Fixture to isolate run directories for test execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        monkeypatch.setattr(bjrt, "BROWSER_JOBS_DIR", tmp_path / "run" / "browser-jobs")
        monkeypatch.setattr(bjrt, "OPERATOR_RESULTS_DIR", tmp_path / "run" / "operator-results")
        yield


def test_submit_browser_job():
    """Verify submit_browser_job initializes state on disk and returns a valid ID."""
    envelope = {
        "task_id": "T001",
        "sprint_id": "sprint-test",
        "node_id": "N3",
        "operator_id": "mini-browser-deepresearch",
        "task_type": "RESEARCH",
        "objective": "Test async submission"
    }

    job_id = bjrt.submit_browser_job("mini-browser-deepresearch", envelope)
    assert job_id.startswith("job-")

    # Check state on disk
    job_dir = bjrt.BROWSER_JOBS_DIR / job_id
    assert job_dir.exists()
    state_file = job_dir / "state.json"
    assert state_file.exists()

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["job_id"] == job_id
    assert state["actor_id"] == "mini-browser-deepresearch"
    assert state["state"] == "submitted"
    assert state["envelope"] == envelope


def test_poll_mock_sequence():
    """Verify poll transitions the job state according to the mock sequence."""
    envelope = {"task_id": "T001"}
    sequence = ["running", "waiting_human", "reauth_required", "done"]

    job_id = bjrt.submit_browser_job("mini-browser-deepresearch", envelope, mock_sequence=sequence)

    # Initial poll should be at the start of mock sequence
    r1 = bjrt.poll_browser_job(job_id)
    assert r1["state"] == "running"

    # Subsequent polls transition state
    r2 = bjrt.poll_browser_job(job_id)
    assert r2["state"] == "waiting_human"

    r3 = bjrt.poll_browser_job(job_id)
    assert r3["state"] == "reauth_required"

    r4 = bjrt.poll_browser_job(job_id)
    assert r4["state"] == "done"
    assert len(r4["artifacts"]) == 2
    assert any(a["name"] == "screenshot.png" for a in r4["artifacts"])

    # Polling after done should remain done
    r5 = bjrt.poll_browser_job(job_id)
    assert r5["state"] == "done"


def test_collect_browser_job_success():
    """Verify collect writes a structured result.json and copies artifacts on success."""
    envelope = {
        "task_id": "T001",
        "sprint_id": "sprint-test",
        "node_id": "N3",
        "operator_id": "mini-browser-deepresearch"
    }
    sequence = ["running", "done"]

    job_id = bjrt.submit_browser_job("mini-browser-deepresearch", envelope, mock_sequence=sequence)

    # Poll twice to reach done state
    bjrt.poll_browser_job(job_id)
    bjrt.poll_browser_job(job_id)

    # Collect the job results
    with tempfile.TemporaryDirectory() as outdir:
        out_path = Path(outdir)
        result = bjrt.collect_browser_job(job_id, output_dir=out_path)

        assert result["task_id"] == "T001"
        assert result["operator_id"] == "mini-browser-deepresearch"
        assert result["status"] == "completed"
        assert result["exit_code"] == 0
        assert "screenshot.png" in [Path(a).name for a in result["artifacts"]]

        # Verify output directory contains result.json and artifacts
        assert (out_path / "result.json").exists()
        assert (out_path / "screenshot.png").exists()
        assert (out_path / "logs.txt").exists()


def test_collect_browser_job_not_terminal():
    """Verify collect raises RuntimeError if the job is not in a terminal state."""
    envelope = {"task_id": "T001"}
    sequence = ["running", "done"]
    job_id = bjrt.submit_browser_job("mini-browser-deepresearch", envelope, mock_sequence=sequence)

    bjrt.poll_browser_job(job_id)  # State is running (non-terminal)

    with pytest.raises(RuntimeError, match="Cannot collect job"):
        bjrt.collect_browser_job(job_id)


def test_collect_browser_job_failed():
    """Verify collect processes failed and timeout states correctly."""
    envelope = {
        "task_id": "T001",
        "sprint_id": "sprint-test",
        "node_id": "N3",
        "operator_id": "mini-browser-deepresearch"
    }
    sequence = ["running", "failed"]

    job_id = bjrt.submit_browser_job("mini-browser-deepresearch", envelope, mock_sequence=sequence)
    bjrt.poll_browser_job(job_id)
    bjrt.poll_browser_job(job_id)

    with tempfile.TemporaryDirectory() as outdir:
        out_path = Path(outdir)
        result = bjrt.collect_browser_job(job_id, output_dir=out_path)

        assert result["status"] == "failed"
        assert result["exit_code"] == 1
        assert (out_path / "result.json").exists()


def test_resolve_chatgpt_monthly_project_name() -> None:
    value = bjrt.resolve_chatgpt_monthly_project_name(
        datetime.datetime(2026, 5, 29, 12, 0, tzinfo=datetime.timezone.utc)
    )
    assert value == "需求研究-2026-05"


def test_build_frontdoor_research_job_envelope() -> None:
    envelope = bjrt.build_frontdoor_research_job_envelope(
        raw_request="请研究这个需求",
        ingress_channel="codex",
        now=datetime.datetime(2026, 5, 29, 12, 0, tzinfo=datetime.timezone.utc),
    )
    assert envelope["chatgpt_project"] == "需求研究-2026-05"
    assert envelope["project_routing"]["create_if_missing"] is True
    assert envelope["capture_policy"]["messages_required"] is True
    assert "messages" in envelope["research_artifact_schema"]["required_fields"]


def test_build_frontdoor_research_artifact_preserves_whole_messages() -> None:
    class FakeIngest:
        @staticmethod
        def build_conversation(**kwargs):
            return {
                "conversation_id": "conv-123",
                "source_url": "https://chatgpt.com/c/conv-123",
                "canonical_url": "https://chatgpt.com/c/conv-123",
                "capture_method": "chatgpt-role-attribute",
                "capture_schema_version": 2,
                "metadata": {"site_name": "ChatGPT"},
                "partial_transcript": False,
                "messages": [
                    {"role": "user", "text": "需求一"},
                    {"role": "assistant", "text": "分析一"},
                    {"role": "user", "text": "需求二"},
                    {"role": "assistant", "text": "最终总结"},
                ],
            }

    original = bjrt._CHATGPT_INGEST_CACHE
    bjrt._CHATGPT_INGEST_CACHE = FakeIngest()
    try:
        artifact = bjrt.build_frontdoor_research_artifact(
            {
                "conversation_id": "conv-123",
                "url": "https://chatgpt.com/c/conv-123",
                "canonical_url": "https://chatgpt.com/c/conv-123",
                "captured_at": "2026-05-29T15:00:00Z",
                "messages": [
                    {"role": "user", "text": "需求一"},
                    {"role": "assistant", "text": "分析一"},
                    {"role": "user", "text": "需求二"},
                    {"role": "assistant", "text": "最终总结"},
                ],
            },
            raw_request="请研究这个需求",
            ingress_channel="codex",
            project_name="需求研究-2026-05",
        )
    finally:
        bjrt._CHATGPT_INGEST_CACHE = original

    assert artifact["conversation_id"] == "conv-123"
    assert artifact["chatgpt_project"] == "需求研究-2026-05"
    assert [m["text"] for m in artifact["messages"]] == ["需求一", "分析一", "需求二", "最终总结"]
    assert artifact["summary"] == "最终总结"


def test_submit_frontdoor_research_job_writes_monthly_project_to_state() -> None:
    job_id = bjrt.submit_frontdoor_research_job(
        "mini-browser-deepresearch",
        raw_request="请研究这个需求",
        ingress_channel="codex",
        now=datetime.datetime(2026, 5, 29, 12, 0, tzinfo=datetime.timezone.utc),
        mock_sequence=["running", "done"],
    )
    state = json.loads((bjrt.BROWSER_JOBS_DIR / job_id / "state.json").read_text(encoding="utf-8"))
    assert state["envelope"]["chatgpt_project"] == "需求研究-2026-05"
    assert state["envelope"]["project_routing"]["create_if_missing"] is True
    assert state["envelope"]["capture_policy"]["final_answer_only_forbidden"] is True


def test_cancel_browser_job():
    """Verify cancel_browser_job terminates the job and marks it as failed."""
    envelope = {"task_id": "T001"}
    job_id = bjrt.submit_browser_job("mini-browser-deepresearch", envelope)

    cancelled = bjrt.cancel_browser_job(job_id)
    assert cancelled is True

    # Polling should reflect cancelled/failed state
    state = bjrt.poll_browser_job(job_id)
    assert state["state"] == "failed"
    assert "cancelled" in state["logs"].lower()


def test_poll_real_browser_job_executes_probe(monkeypatch, tmp_path):
    """Verify a real browser job transitions to done and collects path-based artifacts."""
    artifact_dir = tmp_path / "probe"
    artifact_dir.mkdir(parents=True)
    shot = artifact_dir / "screenshot.png"
    shot.write_bytes(b"png")
    html = artifact_dir / "page.html"
    html.write_text("<html><title>ChatGPT</title></html>", encoding="utf-8")
    text = artifact_dir / "page.txt"
    text.write_text("ChatGPT landing page", encoding="utf-8")

    def fake_probe(job_id, envelope, timeout):
        return {
            "ok": True,
            "state": "done",
            "login_state": "healthy",
            "title": "ChatGPT",
            "final_url": "https://chatgpt.com/",
            "text_excerpt": "ChatGPT landing page",
            "artifacts": {
                "screenshot_path": str(shot),
                "html_path": str(html),
                "text_path": str(text),
            },
        }

    monkeypatch.setattr(bjrt, "_run_real_browser_probe", fake_probe)
    job_id = bjrt.submit_browser_job(
        "mini-browser-deepresearch",
        {"task_id": "T-real", "operator_id": "mini-browser-deepresearch", "url": "https://chatgpt.com", "objective": "Capture landing page"},
    )

    state = bjrt.poll_browser_job(job_id)
    assert state["state"] == "done"
    assert state["projected_state"] == "done"
    assert any(a["name"] == "screenshot.png" for a in state["artifacts"])

    with tempfile.TemporaryDirectory() as outdir:
        result = bjrt.collect_browser_job(job_id, output_dir=Path(outdir))
        assert result["status"] == "completed"
        assert (Path(outdir) / "screenshot.png").exists()
        assert (Path(outdir) / "page.html").exists()
        assert (Path(outdir) / "page.txt").exists()
        metadata = json.loads((Path(outdir) / "page.json").read_text(encoding="utf-8"))
        assert metadata["final_url"] == "https://chatgpt.com/"


def test_poll_real_browser_job_surfaces_reauth(monkeypatch, tmp_path):
    """Verify auth-gated browser jobs surface WAITING_HUMAN when login is required."""
    artifact_dir = tmp_path / "probe"
    artifact_dir.mkdir(parents=True)
    text = artifact_dir / "page.txt"
    text.write_text("Please sign in", encoding="utf-8")

    def fake_probe(job_id, envelope, timeout):
        return {
            "ok": True,
            "state": "reauth_required",
            "login_state": "reauth_required",
            "title": "Sign in",
            "final_url": "https://chatgpt.com/auth/login",
            "text_excerpt": "Please sign in",
            "artifacts": {
                "text_path": str(text),
            },
        }

    monkeypatch.setattr(bjrt, "_run_real_browser_probe", fake_probe)
    job_id = bjrt.submit_browser_job(
        "mini-browser-deepresearch",
        {"task_id": "T-reauth-real", "url": "https://chatgpt.com", "auth_expected": True, "objective": "Open authenticated area"},
    )

    state = bjrt.poll_browser_job(job_id)
    assert state["state"] == "reauth_required"
    assert state["projected_state"] == "WAITING_HUMAN"


def test_stage_browser_profile_removes_restore_artifacts(tmp_path):
    """Verify staged Chrome profile keeps auth data but strips session-restore junk."""
    root = tmp_path / "Chrome"
    profile = root / "Profile 1"
    profile.mkdir(parents=True)
    (profile / "Cookies").write_text("cookie-db", encoding="utf-8")
    (profile / "Current Tabs").write_text("tabs", encoding="utf-8")
    (profile / "Last Session").write_text("session", encoding="utf-8")
    (profile / "Sessions").mkdir()
    (root / "Local State").write_text('{"profile":{"last_used":"Profile 1"}}', encoding="utf-8")

    staged_dir, cleanup_dir = bjrt._stage_browser_profile(root, "Profile 1")
    assert cleanup_dir is not None
    staged_root = Path(staged_dir)
    staged_profile = staged_root / "Profile 1"

    assert (staged_profile / "Cookies").exists()
    assert (staged_root / "Local State").exists()
    assert not (staged_profile / "Current Tabs").exists()
    assert not (staged_profile / "Last Session").exists()
    assert not (staged_profile / "Sessions").exists()

    shutil.rmtree(cleanup_dir, ignore_errors=True)


def test_stage_browser_profile_skips_when_already_staged(tmp_path):
    """Verify already-staged temp profiles are passed through unchanged."""
    staged_root = tmp_path / "browser-use-user-data-dir-existing"
    profile = staged_root / "Profile 1"
    profile.mkdir(parents=True)

    staged_dir, cleanup_dir = bjrt._stage_browser_profile(staged_root, "Profile 1")
    assert Path(staged_dir) == staged_root
    assert cleanup_dir is None


def test_stage_browser_profile_uses_cache_inside_tmux_for_protected_app_data(tmp_path, monkeypatch):
    """Verify tmux workers reuse a Solar-owned cache instead of touching protected app data roots."""
    fake_home = tmp_path / "home"
    source_root = fake_home / "Library" / "Application Support" / "Google" / "Chrome"
    profile = source_root / "Profile 1"
    profile.mkdir(parents=True)
    (profile / "Cookies").write_text("cookie-db", encoding="utf-8")
    (source_root / "Local State").write_text('{"profile":{"last_used":"Profile 1"}}', encoding="utf-8")

    cache_root = tmp_path / "cache"
    monkeypatch.setattr(bjrt, "HOME", fake_home)
    monkeypatch.setattr(
        bjrt,
        "_PROTECTED_APP_DATA_ROOTS",
        (
            fake_home / "Library" / "Application Support",
            fake_home / "Library" / "Containers",
            fake_home / "Library" / "Group Containers",
        ),
    )
    monkeypatch.setattr(bjrt, "PROFILE_CACHE_ROOT", cache_root)

    refreshed = bjrt.refresh_browser_profile_cache(source_root, "Profile 1")
    assert refreshed is not None

    monkeypatch.setenv("TMUX", "/tmp/tmux-test")
    staged_dir, cleanup_dir = bjrt._stage_browser_profile(source_root, "Profile 1")
    assert cleanup_dir is not None
    staged_root = Path(staged_dir)
    staged_profile = staged_root / "Profile 1"
    assert (staged_profile / "Cookies").exists()
    assert (staged_root / "Local State").exists()

    shutil.rmtree(cleanup_dir, ignore_errors=True)


def test_prepare_browser_profile_runtime_reuses_persistent_copy(tmp_path, monkeypatch):
    root = tmp_path / "Chrome"
    profile = root / "Profile 1"
    profile.mkdir(parents=True)
    (profile / "Cookies").write_text("cookie-db", encoding="utf-8")
    (profile / "Current Tabs").write_text("tabs", encoding="utf-8")
    (root / "Local State").write_text('{"profile":{"last_used":"Profile 1"}}', encoding="utf-8")

    runtime_root = tmp_path / "runtime-cache"
    monkeypatch.setattr(bjrt, "PROFILE_RUNTIME_ROOT", runtime_root)

    first = bjrt.prepare_browser_profile_runtime(root, "Profile 1")
    assert first is not None
    first_profile = first / "Profile 1"
    assert (first_profile / "Cookies").exists()
    assert not (first_profile / "Current Tabs").exists()
    marker = first_profile / "Automation Marker"
    marker.write_text("persist-me", encoding="utf-8")

    second = bjrt.prepare_browser_profile_runtime(root, "Profile 1")
    assert second == first
    assert (second / "Profile 1" / "Automation Marker").read_text(encoding="utf-8") == "persist-me"


def test_stage_browser_profile_persistent_strategy_returns_reusable_runtime(tmp_path, monkeypatch):
    root = tmp_path / "Chrome"
    profile = root / "Profile 1"
    profile.mkdir(parents=True)
    (profile / "Cookies").write_text("cookie-db", encoding="utf-8")
    (root / "Local State").write_text('{"profile":{"last_used":"Profile 1"}}', encoding="utf-8")

    runtime_root = tmp_path / "runtime-cache"
    monkeypatch.setattr(bjrt, "PROFILE_RUNTIME_ROOT", runtime_root)

    staged_dir, cleanup_dir = bjrt._stage_browser_profile(root, "Profile 1", strategy="persistent")
    assert cleanup_dir is None
    assert staged_dir is not None
    staged_root = Path(staged_dir)
    assert (staged_root / "Profile 1" / "Cookies").exists()
    assert "browser-use-persistent-user-data-dir-" in staged_root.name


def test_stage_browser_profile_isolates_from_persistent_runtime(tmp_path, monkeypatch):
    root = tmp_path / "Chrome"
    profile = root / "Profile 1"
    profile.mkdir(parents=True)
    (profile / "Cookies").write_text("cookie-db", encoding="utf-8")
    (root / "Local State").write_text('{"profile":{"last_used":"Profile 1"}}', encoding="utf-8")

    runtime_root = tmp_path / "runtime-cache"
    monkeypatch.setattr(bjrt, "PROFILE_RUNTIME_ROOT", runtime_root)

    persistent = bjrt.prepare_browser_profile_runtime(root, "Profile 1")
    assert persistent is not None
    staged_dir, cleanup_dir = bjrt._stage_browser_profile(persistent, "Profile 1", strategy="isolated")
    assert cleanup_dir is not None
    assert staged_dir is not None
    staged_root = Path(staged_dir)
    assert staged_root != persistent
    assert "browser-use-user-data-dir-" in staged_root.name
    assert (staged_root / "Profile 1" / "Cookies").exists()

    shutil.rmtree(cleanup_dir, ignore_errors=True)
