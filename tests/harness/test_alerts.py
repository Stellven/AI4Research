"""Tests for github_intelligence alert dispatcher."""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str((Path(__file__).resolve().parents[2] / 'harness') / "lib"))

from github_intelligence.detectors import Detection
from github_intelligence.alerts import (
    dispatch_alerts,
    load_tracked_repos,
    generate_alert_id,
    check_duplicate_alert
)

TEST_DB_SRC = "~/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite"
TEST_DB_DST = "~/.gemini/antigravity-cli/scratch/test-alerts-B11.sqlite"
TEST_CONFIG_PATH = "~/.gemini/antigravity-cli/scratch/test-github-config.yaml"


@pytest.fixture(scope="function")
def conn():
    """Setup a temporary copy of the SQLite database for tests."""
    Path(TEST_DB_DST).parent.mkdir(parents=True, exist_ok=True)
    if os.path.exists(TEST_DB_DST):
        os.remove(TEST_DB_DST)
    shutil.copy(TEST_DB_SRC, TEST_DB_DST)
    
    connection = sqlite3.connect(TEST_DB_DST)
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()
    if os.path.exists(TEST_DB_DST):
        os.remove(TEST_DB_DST)


@pytest.fixture(scope="module")
def setup_config():
    """Create a temporary yaml config file with tracked repos."""
    content = """
discovery:
  tracked_repos:
    - full_name: test/tracked-repo-high-growth
      priority: high
    - full_name: test/tracked-repo-resonance
      priority: high
    - full_name: test/tracked-repo-normal
      priority: medium
"""
    with open(TEST_CONFIG_PATH, "w") as f:
        f.write(content)
    yield TEST_CONFIG_PATH
    if os.path.exists(TEST_CONFIG_PATH):
        os.remove(TEST_CONFIG_PATH)


def test_alert_severity_mapping_default(conn, setup_config):
    # Repo with normal detection severity
    repo = "test/normal-repo"
    conn.execute("DELETE FROM alerts WHERE repo_full_name = ?", (repo,))
    conn.commit()

    detections = [
        Detection(
            detector_name="foundation_infra_candidate",
            severity="medium",
            evidence_ids=["ev_1"],
            repo_full_name=repo,
            trigger_condition="test",
            conditions_met_json={},
            recommended_action="none"
        )
    ]

    alert_ids = dispatch_alerts(
        conn,
        repo_full_name=repo,
        detections=detections,
        snapshot={},
        evidence_atoms=[],
        config_path=setup_config
    )

    assert len(alert_ids) == 1
    
    # Query database and assert
    row = conn.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_ids[0],)).fetchone()
    assert row is not None
    assert row["detector"] == "foundation_infra_candidate"
    assert row["severity"] == "medium"
    assert row["repo_full_name"] == repo


def test_tracked_repo_high_growth_alert(conn, setup_config):
    # Tracked repo: test/tracked-repo-high-growth
    repo = "test/tracked-repo-high-growth"
    conn.execute("DELETE FROM alerts WHERE repo_full_name = ?", (repo,))
    conn.commit()

    # 110 stars current, 100 stars 24h delta -> base is 10 stars.
    # Growth is 100/10 = 1000% (>10%)
    snapshot = {
        "stars": 110,
        "stars_delta_24h": 100,
        "star_acceleration": 2.0
    }

    detections = [
        Detection(
            detector_name="sudden_hot",
            severity="medium", # Should be escalated to high/critical
            evidence_ids=["ev_1"],
            repo_full_name=repo,
            trigger_condition="normal",
            conditions_met_json={},
            recommended_action="none"
        )
    ]

    alert_ids = dispatch_alerts(
        conn,
        repo_full_name=repo,
        detections=detections,
        snapshot=snapshot,
        evidence_atoms=[],
        config_path=setup_config
    )

    assert len(alert_ids) == 1
    row = conn.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_ids[0],)).fetchone()
    assert row is not None
    assert row["detector"] == "sudden_hot"
    assert row["severity"] == "high"


def test_tracked_repo_growth_alert_injected(conn, setup_config):
    # Tracked repo but NO sudden_hot detection returned by detectors
    repo = "test/tracked-repo-high-growth"
    conn.execute("DELETE FROM alerts WHERE repo_full_name = ?", (repo,))
    conn.commit()

    snapshot = {
        "stars": 110,
        "stars_delta_24h": 100,
        "star_acceleration": 2.0
    }

    alert_ids = dispatch_alerts(
        conn,
        repo_full_name=repo,
        detections=[], # No detections
        snapshot=snapshot,
        evidence_atoms=[],
        config_path=setup_config
    )

    # Should inject sudden_hot alert
    assert len(alert_ids) == 1
    row = conn.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_ids[0],)).fetchone()
    assert row is not None
    assert row["detector"] == "sudden_hot"
    assert row["severity"] == "high"


def test_cross_source_resonance_escalation(conn, setup_config):
    # X+YouTube+Trending all hit -> high severity alert
    repo = "test/tracked-repo-resonance"
    conn.execute("DELETE FROM alerts WHERE repo_full_name = ?", (repo,))
    conn.commit()

    snapshot = {
        "stars": 100,
        "stars_delta_24h": 5, # 5/95 = 5.26% (<10%)
        "star_acceleration": 2.0
    }

    evidence = [
        {"atom_id": "ev_s", "evidence_type": "social_mention"},
        {"atom_id": "ev_y", "evidence_type": "youtube_mention"},
        {"atom_id": "ev_g", "evidence_type": "growth_fact"}
    ]

    detections = [
        Detection(
            detector_name="cross_source_resonance",
            severity="medium", # Should be escalated
            evidence_ids=["ev_s", "ev_y"],
            repo_full_name=repo,
            trigger_condition="normal",
            conditions_met_json={},
            recommended_action="none"
        )
    ]

    alert_ids = dispatch_alerts(
        conn,
        repo_full_name=repo,
        detections=detections,
        snapshot=snapshot,
        evidence_atoms=evidence,
        config_path=setup_config
    )

    assert len(alert_ids) == 1
    row = conn.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_ids[0],)).fetchone()
    assert row is not None
    assert row["detector"] == "cross_source_resonance"
    assert row["severity"] == "high"


def test_duplicate_suppression_within_24h(conn, setup_config):
    repo = "test/normal-repo"
    conn.execute("DELETE FROM alerts WHERE repo_full_name = ?", (repo,))
    
    # Insert an alert from 12 hours ago
    import datetime
    last_triggered = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=12)).isoformat().replace("+00:00", "Z")
    alert_id_old = generate_alert_id(repo, "foundation_infra_candidate", last_triggered)
    
    conn.execute(
        "INSERT INTO alerts (alert_id, detector, repo_full_name, triggered_at, trigger_condition, severity, acknowledged) "
        "VALUES (?, ?, ?, ?, ?, ?, 0)",
        (alert_id_old, "foundation_infra_candidate", repo, last_triggered, "old alert", "medium")
    )
    conn.commit()

    detections = [
        Detection(
            detector_name="foundation_infra_candidate",
            severity="medium",
            evidence_ids=["ev_1"],
            repo_full_name=repo,
            trigger_condition="test new",
            conditions_met_json={},
            recommended_action="none"
        )
    ]

    # This should be suppressed as it is within 24h
    alert_ids = dispatch_alerts(
        conn,
        repo_full_name=repo,
        detections=detections,
        snapshot={},
        evidence_atoms=[],
        config_path=setup_config
    )

    assert len(alert_ids) == 0

    # Verify database has only the old alert
    rows = conn.execute("SELECT * FROM alerts WHERE repo_full_name = ?", (repo,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["alert_id"] == alert_id_old
