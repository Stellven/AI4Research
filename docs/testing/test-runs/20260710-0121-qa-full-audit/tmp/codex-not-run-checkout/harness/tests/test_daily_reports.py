from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from github_intelligence.reports.daily import generate_daily_report, render_daily_report_html


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE repo_analysis_cards (
            card_id TEXT PRIMARY KEY,
            repo_full_name TEXT NOT NULL,
            positioning TEXT NOT NULL DEFAULT '',
            what_it_does TEXT NOT NULL DEFAULT '',
            target_users TEXT NOT NULL DEFAULT '[]',
            core_technical_idea TEXT NOT NULL DEFAULT '',
            why_hot_facts TEXT NOT NULL DEFAULT '[]',
            scores_json TEXT NOT NULL DEFAULT '{}',
            tier TEXT NOT NULL DEFAULT 'B',
            confidence REAL NOT NULL DEFAULT 0.5,
            created_at TEXT NOT NULL,
            verified INTEGER DEFAULT 0
        );
        CREATE TABLE alerts (
            alert_id TEXT PRIMARY KEY,
            detector TEXT NOT NULL,
            repo_full_name TEXT NOT NULL,
            triggered_at TEXT NOT NULL,
            trigger_condition TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL,
            acknowledged INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE model_call_ledger (created_at TEXT NOT NULL);
        CREATE TABLE repo_evidence_atoms (atom_id TEXT PRIMARY KEY);
        CREATE TABLE daily_reports (
            report_id TEXT PRIMARY KEY,
            report_date TEXT NOT NULL UNIQUE,
            section_data_json TEXT NOT NULL DEFAULT '{}',
            repos_analyzed INTEGER NOT NULL DEFAULT 0,
            premium_model_calls INTEGER NOT NULL DEFAULT 0,
            detector_alerts INTEGER NOT NULL DEFAULT 0,
            evidence_atoms_total INTEGER NOT NULL DEFAULT 0,
            generated_at TEXT NOT NULL
        );
        """
    )
    return conn


def seed(conn: sqlite3.Connection):
    cards = [
        ("card_hot", "org/hot", "infra platform", "hot repo", json.dumps(["hot fact"]), json.dumps({"heat_score": 95}), "S", 0.9),
        ("card_warm", "org/warm", "tooling", "warm repo", json.dumps(["warm fact"]), json.dumps({"heat_score": 42}), "B", 0.7),
    ]
    for card in cards:
        conn.execute(
            """INSERT INTO repo_analysis_cards
               (card_id, repo_full_name, positioning, what_it_does, why_hot_facts, scores_json, tier, confidence, created_at, verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, '2026-05-26T00:00:00Z', 1)""",
            card,
        )
    conn.execute(
        "INSERT INTO alerts (alert_id, detector, repo_full_name, triggered_at, trigger_condition, severity) VALUES (?, ?, ?, ?, ?, ?)",
        ("a1", "cross_source_resonance", "org/hot", "2026-05-26T10:00:00Z", "x+yt", "high"),
    )
    conn.execute("INSERT INTO model_call_ledger (created_at) VALUES ('2026-05-26T01:00:00Z')")
    conn.execute("INSERT INTO repo_evidence_atoms (atom_id) VALUES ('ev1')")
    conn.commit()


def test_generate_daily_report_populates_eight_sections_and_unique_date():
    conn = make_conn()
    seed(conn)
    report = generate_daily_report(conn, "2026-05-26")
    sections = json.loads(report["section_data_json"])

    assert len(sections) == 8
    assert set(sections) == {
        "executive_summary", "sudden_hot", "early_potential", "foundation_infra",
        "cross_source_resonance", "risk_watch", "planning_pool", "evidence_health",
    }
    assert sections["sudden_hot"][0]["repo_full_name"] == "org/hot"
    assert sections["sudden_hot"][0]["heat_score"] >= sections["sudden_hot"][1]["heat_score"]
    assert "<html" in report["html"].lower()
    assert "Org" not in report["html"]  # renderer emits escaped data, not title-cased fake text

    report2 = generate_daily_report(conn, "2026-05-26")
    rows = conn.execute("SELECT COUNT(*) FROM daily_reports WHERE report_date='2026-05-26'").fetchone()[0]
    assert rows == 1
    assert report2["report_id"] == report["report_id"]


def test_render_daily_report_html_contains_sections():
    html = render_daily_report_html({"executive_summary": {"headline": "Hello"}, "sudden_hot": []})
    assert "Hello" in html
    assert "Sudden Hot" in html
