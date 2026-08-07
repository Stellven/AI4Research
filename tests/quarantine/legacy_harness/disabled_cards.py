"""Tests for github_intelligence card generator framework."""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path
import pytest

# Add lib directory to path
sys.path.insert(0, str((Path(__file__).resolve().parents[2] / 'harness') / "lib"))

from github_intelligence import cards
from github_intelligence.cards import generate_analysis_card, verify_card

# Test DB paths
TEST_DB_SRC = "~/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite"
TEST_DB_DST = "~/.gemini/antigravity-cli/scratch/test-cards-B12.sqlite"


@pytest.fixture(scope="module")
def conn():
    """Setup a temporary copy of the SQLite database for tests."""
    Path(TEST_DB_DST).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(TEST_DB_SRC, TEST_DB_DST)
    
    connection = sqlite3.connect(TEST_DB_DST)
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()
    if os.path.exists(TEST_DB_DST):
        os.remove(TEST_DB_DST)


def test_card_generation_requires_minimum_3_evidence_atoms(conn):
    repo = "test/thin-evidence-repo"
    
    # Clean database entries
    conn.execute("DELETE FROM repo_evidence_atoms WHERE repo_full_name = ?", (repo,))
    conn.execute("DELETE FROM repo_analysis_cards WHERE repo_full_name = ?", (repo,))
    conn.commit()
    
    # Insert only 2 evidence atoms
    for i in range(2):
        conn.execute(
            "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"thin_atom_{i}", repo, "readme_claim", 0.9, "2026-05-26T00:00:00Z")
        )
    conn.commit()
    
    with pytest.raises(ValueError) as excinfo:
        generate_analysis_card(conn, repo)
    
    assert "minimum 3 required" in str(excinfo.value)


def test_card_generation_succeeds_with_3_or_more_evidence_atoms(conn, monkeypatch):
    monkeypatch.setattr(cards, "call_qwen_local", lambda *args, **kwargs: "PASSED")
    repo = "test/good-evidence-repo"
    
    # Clean database entries
    conn.execute("DELETE FROM repo_evidence_atoms WHERE repo_full_name = ?", (repo,))
    conn.execute("DELETE FROM project_reasoning_packets WHERE repo_full_name = ?", (repo,))
    conn.execute("DELETE FROM repo_analysis_cards WHERE repo_full_name = ?", (repo,))
    conn.execute("DELETE FROM github_repos WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM github_star_snapshots WHERE full_name = ?", (repo,))
    conn.commit()
    
    # Insert repository and snapshot metadata
    conn.execute(
        "INSERT INTO github_repos (repo_id, full_name, owner, repo, html_url, stars, forks, watchers, open_issues, latest_release_tag, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (2001, repo, "test", "good-evidence-repo", f"https://github.com/{repo}", 1500, 200, 100, 10, "v1.2.0", "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO github_star_snapshots (full_name, snapshot_at, stars, forks, watchers, open_issues, star_acceleration) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (repo, "2026-05-26T00:00:00Z", 1500, 200, 100, 10, 4.5)
    )
    
    # Insert 3 evidence atoms
    atom_ids = []
    for i in range(3):
        atom_id = f"good_atom_{i}"
        atom_ids.append(atom_id)
        conn.execute(
            "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, compressed_content, confidence, technical_depth, novelty_score, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (atom_id, repo, "readme_claim", f"Factual claim reference number {i}", 0.9, 0.8, 0.7, "2026-05-26T00:00:00Z")
        )
    conn.commit()
    
    # Run the generator
    card = generate_analysis_card(conn, repo, model_used="test_dummy_model")
    
    assert card is not None
    assert card["repo_full_name"] == repo
    assert len(card["evidence_ids"]) == 3
    assert card["model_used"] == "test_dummy_model"
    assert card["verified"] == 1
    
    # Check database columns count and contents
    db_card_row = conn.execute(
        "SELECT * FROM repo_analysis_cards WHERE repo_full_name = ?", (repo,)
    ).fetchone()
    
    assert db_card_row is not None
    # Verify all 19 columns are present in database query
    keys = db_card_row.keys()
    assert len(keys) == 19
    assert "verified" in keys
    assert db_card_row["verified"] == 1
    assert db_card_row["model_used"] == "test_dummy_model"
    
    # Check that values are populated
    assert db_card_row["positioning"] != ""
    assert db_card_row["what_it_does"] != ""
    assert len(db_card_row["what_it_does"]) <= 200
    assert db_card_row["target_users"] != ""
    assert db_card_row["core_technical_idea"] != ""
    assert len(db_card_row["core_technical_idea"]) <= 200
    assert db_card_row["why_hot_facts"] != ""
    assert db_card_row["scores_json"] != ""
    
    # Check link to project reasoning packet
    packet_row = conn.execute(
        "SELECT packet_id FROM project_reasoning_packets WHERE repo_full_name = ?", (repo,)
    ).fetchone()
    assert packet_row is not None
