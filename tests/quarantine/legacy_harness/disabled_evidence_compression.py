"""Tests for github_intelligence evidence preprocessor pipeline."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
import pytest

# Add lib directory to path
sys.path.insert(0, str((Path(__file__).resolve().parents[2] / 'harness') / "lib"))

from github_intelligence.evidence import (
    clean_readme,
    github_repo_atom_id,
    github_extract_repo_entities,
    call_qwen_local,
    compress_readme,
    compress_releases,
    compress_issues_prs,
    extract_cross_source_mentions,
    generate_growth_facts,
    run_preprocess_pipeline,
)

# Test DB setup
TEST_DB_SRC = "~/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite"
TEST_DB_DST = "~/.gemini/antigravity-cli/scratch/test-evidence-B6.sqlite"
TEST_REPO = "test/evidence-B6-repo"


@pytest.fixture(scope="module")
def conn():
    """Setup a temporary copy of the SQLite database for tests."""
    # Ensure dst directory exists
    Path(TEST_DB_DST).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(TEST_DB_SRC, TEST_DB_DST)
    
    connection = sqlite3.connect(TEST_DB_DST)
    connection.row_factory = sqlite3.Row
    connection.execute("DELETE FROM github_star_snapshots WHERE full_name = ?", (TEST_REPO,))
    connection.execute("DELETE FROM github_repos WHERE full_name = ?", (TEST_REPO,))
    
    # Setup test repo metadata
    connection.execute(
        "INSERT OR IGNORE INTO github_repos "
        "(repo_id, full_name, owner, repo, html_url, description, topics, "
        "language, license, stars, forks, watchers, open_issues, "
        "default_branch, readme_text, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            88888, TEST_REPO, "test", "evidence-B6-repo",
            f"https://github.com/{TEST_REPO}",
            "An open source AI agent tool calling and RAG context project.",
            "agent,mcp,rag,inference", "Python", "MIT",
            1200, 150, 80, 12, "main",
            "# Evidence B6 Repo\nThis repository is a deep systems platform for AI inference and MCP servers.\n"
            "It is not a wrapper. It implements custom CUDA kernels.\n\n<!-- comment -->\n"
            "![banner](https://example.com/banner.png)\n",
            "2026-05-26T00:00:00Z"
        )
    )
    
    # Setup test repo star snapshots to test deltas & acceleration
    connection.execute(
        "INSERT INTO github_star_snapshots "
        "(full_name, snapshot_at, stars, forks, open_issues, watchers, stars_delta_24h, stars_delta_7d, star_acceleration) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (TEST_REPO, "2026-05-26T00:00:00Z", 1200, 150, 12, 80, 50, 200, 4.5)
    )
    
    connection.commit()
    yield connection
    
    connection.close()
    if os.path.exists(TEST_DB_DST):
        try:
            os.remove(TEST_DB_DST)
        except Exception:
            pass




@pytest.fixture(autouse=True)
def mock_thunderomlx_calls(monkeypatch):
    """Keep evidence compression tests deterministic and independent of live ThunderOMLX latency."""
    def fake_call_qwen_local(prompt, system, endpoint=None, api_key=None):
        system_text = str(system).lower()
        prompt_text = str(prompt).lower()
        if '"is_wrapper"' in system_text:
            if "chatbot ui wrapper" in prompt_text or "simple ui wrapper" in prompt_text:
                return json.dumps({
                    "is_wrapper": True,
                    "wrapper_type": "api_wrapper",
                    "technical_depth_score": 0.2,
                    "novelty_score": 0.2,
                    "confidence": 0.9,
                    "claims": [{
                        "claim_summary": "Simple API wrapper",
                        "compressed_content": "Simple API wrapper around chat completions without custom engineering.",
                        "importance_score": 80,
                        "novelty_score": 0.2,
                        "confidence": 0.9,
                        "tags": ["wrapper"],
                    }],
                })
            return json.dumps({
                "is_wrapper": False,
                "wrapper_type": None,
                "technical_depth_score": 0.8,
                "novelty_score": 0.7,
                "confidence": 0.9,
                "claims": [{
                    "claim_summary": "Deep systems repository",
                    "compressed_content": "Implements systems components with custom CUDA kernels and MCP/RAG integration.",
                    "importance_score": 85,
                    "novelty_score": 0.7,
                    "confidence": 0.9,
                    "tags": ["systems", "cuda", "mcp"],
                }],
            })
        if '"features"' in system_text:
            return json.dumps({
                "features": [{
                    "compressed_content": "Release adds MCP server integration and sqlite tooling improvements.",
                    "importance_score": 80,
                    "novelty_score": 0.6,
                    "confidence": 0.85,
                    "tags": ["release", "mcp"],
                }]
            })
        if '"signals"' in system_text:
            return json.dumps({
                "signals": [{
                    "signal_type": "issue_signal",
                    "compressed_content": "Inference loop memory leak is reported and a PR adds GPU memory release.",
                    "importance_score": 75,
                    "novelty_score": 0.5,
                    "confidence": 0.85,
                    "tags": ["memory", "gpu"],
                }]
            })
        if '"mentions"' in system_text:
            return json.dumps({
                "mentions": [{
                    "source_id": "tweet_1",
                    "source_type": "social_mention",
                    "compressed_content": "Positive mention highlights MCP RAG stack and deployment interest.",
                    "importance_score": 70,
                    "novelty_score": 0.45,
                    "confidence": 0.8,
                    "tags": ["social", "rag"],
                }]
            })
        return "{}"

    monkeypatch.setattr("github_intelligence.evidence.call_qwen_local", fake_call_qwen_local)

def test_clean_readme_logic():
    """Verify clean_readme strips HTML comments, image embeds, and cleans whitespace."""
    raw = """
    # My Project
    <!-- This is a secret comment -->
    Here is an image: ![banner](http://example.com/banner.jpg)
    <script>alert('dangerous')</script>
    <style>.banner { color: red; }</style>
    
    End of README.
    """
    cleaned = clean_readme(raw)
    assert "secret comment" not in cleaned
    assert "banner.jpg" not in cleaned
    assert "dangerous" not in cleaned
    assert "style" not in cleaned
    assert "My Project" in cleaned
    assert "End of README" in cleaned


def test_entities_extraction():
    """Verify github_extract_repo_entities identifies key technical and repository keywords."""
    text = "Comparing anthropics/claude-plugins-official with ChatGPT and Llama running in mlx."
    entities = github_extract_repo_entities(text)
    assert "mlx" in entities["technologies"]
    assert "anthropics/claude-plugins-official" in entities["repos"]
    assert "Llama" in entities["models"]


def test_growth_facts_atom(conn):
    """Verify generate_growth_facts compiles quantitative growth deltas and inserts atoms."""
    # Clean previous atoms
    conn.execute("DELETE FROM repo_evidence_atoms WHERE repo_full_name = ?", (TEST_REPO,))
    conn.commit()
    
    atoms = generate_growth_facts(conn, TEST_REPO)
    assert len(atoms) == 1
    atom = atoms[0]
    assert atom["evidence_type"] == "growth_fact"
    assert "delta_1d=50" in atom["compressed_content"]
    assert "acceleration=4.5" in atom["compressed_content"]
    assert len(atom["compressed_content"]) <= 500
    
    # Check DB insertion
    db_row = conn.execute("SELECT compressed_content FROM repo_evidence_atoms WHERE atom_id = ?", (atom["atom_id"],)).fetchone()
    assert db_row is not None
    assert db_row[0] == atom["compressed_content"]


def test_compress_readme_integration(conn):
    """Verify compress_readme calls ThunderOMLX, identifies wrapper correctly, and inserts atoms."""
    conn.execute("DELETE FROM repo_evidence_atoms WHERE repo_full_name = ?", (TEST_REPO,))
    conn.commit()
    
    atoms = compress_readme(conn, TEST_REPO)
    # The README states 'not a wrapper' and 'custom CUDA kernels'
    # So we expect wrapper detection to set is_wrapper to False and depth >= 0.35
    assert len(atoms) > 0
    for atom in atoms:
        assert atom["evidence_type"] == "readme_claim"
        assert len(atom["compressed_content"]) <= 500
        assert atom["technical_depth"] >= 0.35


def test_compress_readme_wrapper_detection(conn):
    """Verify wrapper detection sets technical depth low (< 0.35) for wrapper repos."""
    wrapper_repo = "test/wrapper-repo"
    conn.execute(
        "INSERT OR IGNORE INTO github_repos "
        "(repo_id, full_name, owner, repo, html_url, description, readme_text, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            88889, wrapper_repo, "test", "wrapper-repo",
            f"https://github.com/{wrapper_repo}",
            "A simple OpenAI API chatbot UI wrapper.",
            "# Chatbot UI Wrapper\nThis is a simple UI wrapper around the OpenAI API chat completions. "
            "It has no custom engineering. Simply forwards prompt requests to OpenAI key.",
            "2026-05-26T00:00:00Z"
        )
    )
    conn.commit()
    
    atoms = compress_readme(conn, wrapper_repo)
    # The README indicates a simple wrapper, so technical_depth should be set <= 0.30
    assert len(atoms) > 0
    for atom in atoms:
        assert atom["technical_depth"] <= 0.30


def test_compress_releases(conn):
    """Verify compress_releases summarizes detailed release logs, or falls back to tag info."""
    # Test detailed notes
    releases_data = [
        {
            "tag_name": "v1.2.0",
            "name": "MCP Integration Release",
            "body": "This release adds support for MCP servers. Now connects to standard sqlite tools."
        }
    ]
    atoms = compress_releases(conn, TEST_REPO, releases_data)
    assert len(atoms) > 0
    assert atoms[0]["evidence_type"] == "release_feature"
    assert len(atoms[0]["compressed_content"]) <= 500


def test_compress_issues_prs(conn):
    """Verify issues and PRs signals are successfully distilled."""
    issues = [{"title": "Memory leak on inference loops", "body": "Looping 1000 times causes OOM on GPU."}]
    prs = [{"title": "Fix memory leak in loop", "body": "Added GPU memory release on inference finish."}]
    
    atoms = compress_issues_prs(conn, TEST_REPO, issues_data=issues, prs_data=prs)
    assert len(atoms) > 0
    for atom in atoms:
        assert atom["evidence_type"] in ("issue_signal", "pr_signal")
        assert len(atom["compressed_content"]) <= 500


def test_cross_source_mentions(conn):
    """Verify cross-source mentions are correctly compiled from inputs."""
    social = [{"id": "tweet_1", "text": "Everyone should check out test/evidence-B6-repo! It has a super cool MCP RAG stack!"}]
    youtube = [{"id": "yt_1", "text": "[00:02:15] So we deploy the test/evidence-B6-repo model using Triton server."}]
    
    atoms = extract_cross_source_mentions(conn, TEST_REPO, social_data=social, youtube_data=youtube)
    assert len(atoms) > 0
    for atom in atoms:
        assert atom["evidence_type"] in ("social_mention", "youtube_mention")
        assert len(atom["compressed_content"]) <= 500


def test_pipeline_success_and_failure(conn, monkeypatch):
    """Verify run_preprocess_pipeline coordinates all tasks, and retry_queue tracks failures gracefully."""
    # 1. Success case
    conn.execute("DELETE FROM retry_queue WHERE source='github' AND source_id=?", (TEST_REPO,))
    conn.commit()
    
    social = [{"id": "tweet_1", "text": f"Positive mention of github.com/{TEST_REPO}"}]
    youtube = [{"id": "yt_1", "text": f"Video mention of github.com/{TEST_REPO}"}]
    res = run_preprocess_pipeline(conn, TEST_REPO, social_data=social, youtube_data=youtube)
    assert res is True
    
    # Check no failure entry in retry_queue
    failed_row = conn.execute(
        "SELECT COUNT(*) FROM retry_queue WHERE source='github' AND source_id=? AND status='abandoned'",
        (TEST_REPO,)
    ).fetchone()[0]
    assert failed_row == 0
    
    # 2. Failure case (ThunderOMLX down)
    # Monkeypatch call_qwen_local to raise a connection error
    def mock_crash(*args, **kwargs):
        raise ConnectionError("ThunderOMLX backend server unavailable")
        
    monkeypatch.setattr("github_intelligence.evidence.call_qwen_local", mock_crash)
    
    with pytest.raises(RuntimeError):
        run_preprocess_pipeline(conn, TEST_REPO, social_data=social, youtube_data=youtube)
        
    # Check failure entry in retry_queue
    failed_entry = conn.execute(
        "SELECT status, last_error FROM retry_queue WHERE source='github' AND source_id=? AND operation='preprocess'",
        (TEST_REPO,)
    ).fetchone()
    assert failed_entry is not None
    assert failed_entry[0] == "abandoned"
    assert "preprocess_failed" in failed_entry[1]
    assert "ThunderOMLX backend server unavailable" in failed_entry[1]
