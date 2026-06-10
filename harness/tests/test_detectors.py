"""Tests for github_intelligence detector framework."""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path
import pytest
from unittest.mock import patch

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from github_intelligence.detectors import (
    Detection,
    SuddenHotDetector,
    EarlyPotentialDetector,
    FoundationInfraCandidateDetector,
    HypeOrNoiseDetector,
    StarManipulationSuspicionDetector,
    MajorReleaseSignalDetector,
    CrossSourceResonanceDetector,
    run_all_detectors,
    compute_potential_score,
)

# Test DB paths
TEST_DB_SRC = "~/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite"
TEST_DB_DST = "~/.gemini/antigravity-cli/scratch/test-detectors-B10.sqlite"


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


def test_sudden_hot_detector_triggers(conn):
    # Seed a repo that triggers sudden_hot
    repo = "test/sudden-hot-repo"
    conn.execute("DELETE FROM github_star_snapshots WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM github_repos WHERE full_name = ?", (repo,))
    
    conn.execute(
        "INSERT INTO github_repos (repo_id, full_name, owner, repo, html_url, stars, forks, watchers, open_issues, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1001, repo, "test", "sudden-hot-repo", f"https://github.com/{repo}", 500, 50, 50, 5, "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO github_star_snapshots (full_name, snapshot_at, stars, forks, watchers, open_issues, star_acceleration) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (repo, "2026-05-26T00:00:00Z", 500, 50, 50, 5, 12.5) # star_acceleration > 8.0
    )
    conn.commit()

    detector = SuddenHotDetector()
    detections = detector.detect(conn, repo)
    assert len(detections) == 1
    assert detections[0].detector_name == "sudden_hot"
    assert detections[0].severity == "high"
    assert "star_acceleration 12.5 > 8.0" in detections[0].trigger_condition
    assert detections[0].repo_full_name == repo


def test_early_potential_detector_triggers(conn):
    # Seed a repo that triggers early_potential: potential_score > 85.0 AND stars < 2000
    repo = "test/early-potential-repo"
    conn.execute("DELETE FROM github_star_snapshots WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM github_repos WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM repo_evidence_atoms WHERE repo_full_name = ?", (repo,))
    
    conn.execute(
        "INSERT INTO github_repos (repo_id, full_name, owner, repo, html_url, stars, forks, watchers, open_issues, latest_release_tag, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1002, repo, "test", "early-potential-repo", f"https://github.com/{repo}", 1200, 150, 80, 12, "v1.0.0", "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO github_star_snapshots (full_name, snapshot_at, stars, forks, watchers, open_issues, star_acceleration, commit_count_7d, active_contributors_30d) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (repo, "2026-05-26T00:00:00Z", 1200, 150, 80, 12, 1.0, 100, 50)
    )
    # Seed evidence atoms with high technical depth, novelty, release features, and issue/PR signals to maximize potential score
    conn.execute(
        "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, technical_depth, novelty_score, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("ghatom_ep_1", repo, "readme_claim", 0.9, 0.95, 0.95, "2026-05-26T00:00:00Z")
    )
    # Seed 4 release feature atoms to get max release score (30 + 4 * 20 = 110, capped at 100)
    for i in range(4):
        conn.execute(
            "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"ghatom_ep_rel_{i}", repo, "release_feature", 0.9, "2026-05-26T00:00:00Z")
        )
    # Seed 4 issue/PR signal atoms to get max maintainer score (4 * 25 = 100)
    for i in range(4):
        conn.execute(
            "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"ghatom_ep_maint_{i}", repo, "issue_signal", 0.9, "2026-05-26T00:00:00Z")
        )
    conn.commit()

    detector = EarlyPotentialDetector()
    detections = detector.detect(conn, repo)
    assert len(detections) == 1
    assert detections[0].detector_name == "early_potential"
    assert detections[0].severity == "high"
    assert "stars 1200 < 2000" in detections[0].trigger_condition
    assert detections[0].repo_full_name == repo


def test_foundation_infra_candidate_detector_triggers(conn):
    # Seed a repo that triggers foundation_infra_candidate
    repo = "test/foundation-infra-repo"
    conn.execute("DELETE FROM github_star_snapshots WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM github_repos WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM repo_evidence_atoms WHERE repo_full_name = ?", (repo,))
    
    conn.execute(
        "INSERT INTO github_repos (repo_id, full_name, owner, repo, html_url, stars, forks, watchers, open_issues, topics, description, language, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1003, repo, "test", "foundation-infra-repo", f"https://github.com/{repo}", 1200, 150, 80, 12, "mcp,agent", "A local runtime kernel database engine", "Python", "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, technical_depth, novelty_score, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("ghatom_fi_1", repo, "readme_claim", 0.9, 0.75, 0.6, "2026-05-26T00:00:00Z")
    )
    conn.commit()

    detector = FoundationInfraCandidateDetector()
    detections = detector.detect(conn, repo)
    assert len(detections) == 1
    assert detections[0].detector_name == "foundation_infra_candidate"
    assert detections[0].severity == "medium"


def test_hype_or_noise_detector_triggers(conn):
    # Seed a repo that triggers hype_or_noise
    repo = "test/hype-noise-repo"
    conn.execute("DELETE FROM github_star_snapshots WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM github_repos WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM repo_evidence_atoms WHERE repo_full_name = ?", (repo,))
    
    # We seed high heat score metrics: high stars delta, release, community commits & active contributors, cross source mentions
    conn.execute(
        "INSERT INTO github_repos (repo_id, full_name, owner, repo, html_url, stars, forks, watchers, open_issues, latest_release_tag, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1004, repo, "test", "hype-noise-repo", f"https://github.com/{repo}", 5000, 150, 80, 12, "v1.0.0", "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO github_star_snapshots (full_name, snapshot_at, stars, forks, watchers, open_issues, stars_delta_24h, star_acceleration, commit_count_7d, active_contributors_30d) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (repo, "2026-05-26T00:00:00Z", 5000, 150, 80, 12, 450, 8.0, 100, 50)
    )
    # Seed evidence atoms with low technical depth, but high social resonance/release features to boost heat. Also add tags to boost topic relevance.
    conn.execute(
        "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, technical_depth, novelty_score, raw_source_type, tags_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("ghatom_hn_1", repo, "readme_claim", 0.9, 0.2, 0.2, "github", '["mcp"]', "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, raw_source_type, tags_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("ghatom_hn_2", repo, "social_mention", 0.9, "social", '["mcp"]', "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, raw_source_type, tags_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("ghatom_hn_3", repo, "youtube_mention", 0.9, "youtube", '["mcp"]', "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, raw_source_type, tags_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("ghatom_hn_4", repo, "release_feature", 0.9, "github", '["mcp"]', "2026-05-26T00:00:00Z")
    )
    conn.commit()

    detector = HypeOrNoiseDetector()
    detections = detector.detect(conn, repo)
    assert len(detections) == 1
    assert detections[0].detector_name == "hype_or_noise"
    assert detections[0].severity == "medium"


def test_star_manipulation_suspicion_detector_triggers(conn):
    # Seed a repo that triggers star_manipulation_suspicion
    repo = "test/star-manipulation-repo"
    conn.execute("DELETE FROM github_star_snapshots WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM github_repos WHERE full_name = ?", (repo,))
    
    conn.execute(
        "INSERT INTO github_repos (repo_id, full_name, owner, repo, html_url, stars, forks, watchers, open_issues, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1005, repo, "test", "star-manipulation-repo", f"https://github.com/{repo}", 1200, 2, 80, 12, "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO github_star_snapshots (full_name, snapshot_at, stars, forks, watchers, open_issues, stars_delta_24h, forks_delta_24h, commit_count_7d, active_contributors_30d) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (repo, "2026-05-26T00:00:00Z", 1200, 2, 80, 12, 120, 0, 0, 1)
    )
    conn.commit()

    detector = StarManipulationSuspicionDetector()
    detections = detector.detect(conn, repo)
    assert len(detections) == 1
    assert detections[0].detector_name == "star_manipulation_suspicion"


def test_major_release_signal_detector_triggers(conn):
    # Seed a repo that triggers major_release_signal
    repo = "test/major-release-repo"
    conn.execute("DELETE FROM github_star_snapshots WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM github_repos WHERE full_name = ?", (repo,))
    
    conn.execute(
        "INSERT INTO github_repos (repo_id, full_name, owner, repo, html_url, stars, forks, watchers, open_issues, latest_release_tag, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1006, repo, "test", "major-release-repo", f"https://github.com/{repo}", 1200, 150, 80, 12, "v2.0.0", "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO github_star_snapshots (full_name, snapshot_at, stars, forks, watchers, open_issues) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (repo, "2026-05-26T00:00:00Z", 1200, 150, 80, 12)
    )
    conn.commit()

    detector = MajorReleaseSignalDetector()
    detections = detector.detect(conn, repo)
    assert len(detections) == 1
    assert detections[0].detector_name == "major_release_signal"


def test_cross_source_resonance_detector_triggers(conn):
    # Seed a repo that triggers cross_source_resonance
    repo = "test/cross-source-repo"
    conn.execute("DELETE FROM github_star_snapshots WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM github_repos WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM repo_evidence_atoms WHERE repo_full_name = ?", (repo,))
    
    conn.execute(
        "INSERT INTO github_repos (repo_id, full_name, owner, repo, html_url, stars, forks, watchers, open_issues, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1007, repo, "test", "cross-source-repo", f"https://github.com/{repo}", 1200, 150, 80, 12, "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO github_star_snapshots (full_name, snapshot_at, stars, forks, watchers, open_issues, stars_delta_24h) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (repo, "2026-05-26T00:00:00Z", 1200, 150, 80, 12, 10)
    )
    conn.execute(
        "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("ghatom_cs_1", repo, "social_mention", 0.9, "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("ghatom_cs_2", repo, "youtube_mention", 0.9, "2026-05-26T00:00:00Z")
    )
    conn.commit()

    detector = CrossSourceResonanceDetector()
    detections = detector.detect(conn, repo)
    assert len(detections) == 1
    assert detections[0].detector_name == "cross_source_resonance"


def test_run_all_detectors_isolation_and_aggregation(conn):
    # Seed a repo that triggers both sudden_hot and early_potential
    repo = "test/multi-trigger-repo"
    conn.execute("DELETE FROM github_star_snapshots WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM github_repos WHERE full_name = ?", (repo,))
    conn.execute("DELETE FROM repo_evidence_atoms WHERE repo_full_name = ?", (repo,))
    
    conn.execute(
        "INSERT INTO github_repos (repo_id, full_name, owner, repo, html_url, stars, forks, watchers, open_issues, latest_release_tag, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1008, repo, "test", "multi-trigger-repo", f"https://github.com/{repo}", 500, 150, 80, 12, "v1.0.0", "2026-05-26T00:00:00Z")
    )
    conn.execute(
        "INSERT INTO github_star_snapshots (full_name, snapshot_at, stars, forks, watchers, open_issues, star_acceleration, commit_count_7d, active_contributors_30d) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (repo, "2026-05-26T00:00:00Z", 500, 150, 80, 12, 12.0, 100, 50)
    )
    # Seed evidence atoms with high technical depth, novelty, release feature, and issue/PR signals to maximize potential score
    conn.execute(
        "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, technical_depth, novelty_score, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("ghatom_mt_1", repo, "readme_claim", 0.9, 0.95, 0.95, "2026-05-26T00:00:00Z")
    )
    for i in range(4):
        conn.execute(
            "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"ghatom_mt_rel_{i}", repo, "release_feature", 0.9, "2026-05-26T00:00:00Z")
        )
    for i in range(4):
        conn.execute(
            "INSERT INTO repo_evidence_atoms (atom_id, repo_full_name, evidence_type, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"ghatom_mt_maint_{i}", repo, "issue_signal", 0.9, "2026-05-26T00:00:00Z")
        )
    conn.commit()

    detections = run_all_detectors(conn, repo)
    names = [d.detector_name for d in detections]
    assert "sudden_hot" in names
    assert "early_potential" in names

    # Verify that a detector crashing does not stop the others
    with patch.object(SuddenHotDetector, 'detect', side_effect=ValueError("Test sudden hot crash")):
        detections_with_crash = run_all_detectors(conn, repo)
        names_with_crash = [d.detector_name for d in detections_with_crash]
        assert "sudden_hot" not in names_with_crash
        assert "early_potential" in names_with_crash
