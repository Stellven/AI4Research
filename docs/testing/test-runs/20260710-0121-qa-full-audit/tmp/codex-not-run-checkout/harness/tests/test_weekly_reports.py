from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from github_intelligence.reports.weekly import generate_weekly_report, week_key


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
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
        CREATE TABLE repo_analysis_cards (
            card_id TEXT PRIMARY KEY,
            repo_full_name TEXT NOT NULL,
            tier TEXT NOT NULL DEFAULT 'B',
            confidence REAL NOT NULL DEFAULT 0.5,
            scores_json TEXT NOT NULL DEFAULT '{}',
            verified INTEGER DEFAULT 0
        );
        CREATE TABLE repo_planning_briefs (
            brief_id TEXT PRIMARY KEY,
            repo_full_name TEXT NOT NULL,
            card_id TEXT NOT NULL,
            opportunity TEXT NOT NULL DEFAULT '',
            mvp_sketch TEXT NOT NULL DEFAULT '',
            validation_metrics TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE weekly_reports (
            report_id TEXT PRIMARY KEY,
            report_week TEXT NOT NULL UNIQUE,
            section_data_json TEXT NOT NULL DEFAULT '{}',
            repos_analyzed INTEGER NOT NULL DEFAULT 0,
            premium_model_calls INTEGER NOT NULL DEFAULT 0,
            deep_analysis_count INTEGER NOT NULL DEFAULT 0,
            detector_alerts_weekly INTEGER NOT NULL DEFAULT 0,
            evidence_atoms_total INTEGER NOT NULL DEFAULT 0,
            generated_at TEXT NOT NULL
        );
        """
    )
    return conn


def test_weekly_report_aggregates_mon_sun_and_planning_pool():
    conn = make_conn()
    conn.execute(
        "INSERT INTO daily_reports VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("d1", "2026-05-25", json.dumps({"sudden_hot":[{"repo_full_name":"org/a","heat_score":20},{"repo_full_name":"org/b","heat_score":90}]}), 2, 1, 3, 5, "2026-05-25T00:00:00Z"),
    )
    conn.execute("INSERT INTO repo_analysis_cards VALUES (?, ?, ?, ?, ?, ?)", ("c1", "org/a", "A", 0.9, json.dumps({"heat_score":20}), 1))
    conn.execute("INSERT INTO repo_planning_briefs VALUES (?, ?, ?, ?, ?, ?)", ("b1", "org/a", "c1", "build", "mvp", json.dumps(["metric"])))
    conn.commit()

    report = generate_weekly_report(conn, "2026-05-26")
    sections = json.loads(report["section_data_json"])

    assert report["report_week"] == week_key("2026-05-26") == "2026-05-25"
    assert sections["top5_trends"][0]["repo_full_name"] == "org/b"
    assert sections["planning_pool"][0]["brief_id"] == "b1"
    assert sections["top10_projects"][0]["repo_full_name"] == "org/a"
    assert "<html" in report["html"].lower()
