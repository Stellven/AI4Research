"""test_browser_fallback_observability.py — Tests for browser agent fallback ladder and job observability."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import sys

import pytest

# Add lib and tools to sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tools"))

import operator_score as score
import monitor_bridge as bridge


def test_classify_actor_type():
    """Verify classify_actor_type correctly maps actor IDs/configurations to categories."""
    # 1. ChatGPT
    assert score.classify_actor_type("mini-chatgpt", {}) == "chatgpt"
    assert score.classify_actor_type("some-actor", {"model": "o3-mini"}) == "chatgpt"

    # 2. Gemini
    assert score.classify_actor_type("gemini-actor", {}) == "gemini"
    assert score.classify_actor_type("some-actor", {"model": "gemini-3.5-flash"}) == "gemini"

    # 3. Browser
    assert score.classify_actor_type("browser-actor", {}) == "browser"
    assert score.classify_actor_type("some-actor", {"capability_profile": {"browser_use": 1}}) == "browser"

    # 5. Local
    assert score.classify_actor_type("thunderomlx-actor", {}) == "local"
    assert score.classify_actor_type("some-actor", {"model": "qwen2.5"}) == "local"

    # 4. API (default)
    assert score.classify_actor_type("mini-claude-sonnet", {}) == "api"


def test_rank_actors_tie_breaker():
    """Verify rank_actors breaks ties using the fallback ladder precedence (ChatGPT > Gemini > Browser > API > Local)."""
    actors_cfg = {
        "local-actor": {"model": "thunder-local"},
        "chatgpt-actor": {"model": "o3-mini"},
        "gemini-actor": {"model": "gemini-3.5"},
        "browser-actor": {"capability_profile": {"browser_use": 3}},
        "api-actor": {"model": "claude-3-5"},
    }

    candidates = ["local-actor", "chatgpt-actor", "gemini-actor", "browser-actor", "api-actor"]
    
    # Run rank_actors with neutral task_fit and empty evidence (so scores are equal)
    ranked = score.rank_actors(candidates, actors_cfg=actors_cfg)
    
    # Expected order: chatgpt > gemini > browser > api > local
    expected_order = ["chatgpt-actor", "gemini-actor", "browser-actor", "api-actor", "local-actor"]
    assert [r.actor_id for r in ranked] == expected_order


def test_rank_actors_tie_breaker_alphabetical():
    """Verify rank_actors breaks ties alphabetically when scores and categories are identical."""
    actors_cfg = {
        "gemini-b": {"model": "gemini-3.5"},
        "gemini-a": {"model": "gemini-3.5"},
    }
    candidates = ["gemini-b", "gemini-a"]
    ranked = score.rank_actors(candidates, actors_cfg=actors_cfg)
    assert [r.actor_id for r in ranked] == ["gemini-a", "gemini-b"]


def test_monitor_bridge_browser_jobs():
    """Verify monitor bridge correctly loads browser jobs and exposes them with their attributes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        jobs_dir = tmp_path / "run" / "browser-jobs"
        jobs_dir.mkdir(parents=True)

        # Create mock job 1: healthy running job
        job1_dir = jobs_dir / "job-1"
        job1_dir.mkdir()
        job1_state = {
            "job_id": "job-1",
            "actor_id": "browser_agent_session",
            "state": "running",
            "envelope": {
                "profile_ref": "prod_profile",
                "account_label": "user1@example.com"
            },
            "artifacts": [{"name": "screenshot.png", "type": "screenshot"}]
        }
        (job1_dir / "state.json").write_text(json.dumps(job1_state))

        # Create mock job 2: failed job requiring reauth
        job2_dir = jobs_dir / "job-2"
        job2_dir.mkdir()
        job2_state = {
            "job_id": "job-2",
            "actor_id": "browser_agent_session",
            "state": "reauth_required",
            "envelope": {
                "profile_ref": "profile_needs_reauth",
                "account_label": "user2@example.com"
            },
            "artifacts": []
        }
        (job2_dir / "state.json").write_text(json.dumps(job2_state))

        # Dummy actors dict
        actors = {
            "browser_agent_session": {"state": "idle"}
        }

        # Load jobs via bridge helper
        jobs = bridge.load_browser_jobs(jobs_dir, actors)
        
        assert len(jobs) == 2
        
        # Verify job-1
        j1 = jobs[0]
        assert j1["job_id"] == "job-1"
        assert j1["async_state"] == "running"
        assert j1["login_state"] == "healthy"
        assert j1["quota_state"] == "ok"
        assert j1["evidence"] == ["screenshot.png"]
        assert any("screenshot.png" in p for p in j1["paths"])

        # Verify job-2
        j2 = jobs[1]
        assert j2["job_id"] == "job-2"
        assert j2["async_state"] == "reauth_required"
        assert j2["login_state"] == "reauth_required"
        assert j2["quota_state"] == "ok"
        assert j2["evidence"] == []
        assert j2["paths"] == []
