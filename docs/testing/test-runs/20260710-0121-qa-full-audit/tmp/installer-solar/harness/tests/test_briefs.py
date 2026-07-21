from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from github_intelligence.briefs import generate_planning_brief


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
            trend_implication TEXT NOT NULL DEFAULT '',
            risks_json TEXT NOT NULL DEFAULT '[]',
            watch_next TEXT NOT NULL DEFAULT '[]',
            evidence_ids_json TEXT NOT NULL DEFAULT '[]',
            risk_classification TEXT NOT NULL DEFAULT 'none',
            tier TEXT NOT NULL DEFAULT 'B',
            confidence REAL NOT NULL DEFAULT 0.5,
            model_used TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            verified INTEGER DEFAULT 0
        );
        CREATE TABLE repo_planning_briefs (
            brief_id TEXT PRIMARY KEY,
            repo_full_name TEXT NOT NULL,
            card_id TEXT NOT NULL,
            opportunity TEXT NOT NULL DEFAULT '',
            user_pain TEXT NOT NULL DEFAULT '',
            mvp_sketch TEXT NOT NULL DEFAULT '',
            architecture_hint TEXT NOT NULL DEFAULT '',
            go_to_market TEXT NOT NULL DEFAULT '',
            risks_json TEXT NOT NULL DEFAULT '[]',
            validation_metrics TEXT NOT NULL DEFAULT '[]',
            model_used TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        """
    )
    return conn


def insert_card(conn: sqlite3.Connection, verified: int) -> None:
    conn.execute(
        """INSERT INTO repo_analysis_cards
           (card_id, repo_full_name, positioning, what_it_does, target_users,
            core_technical_idea, why_hot_facts, scores_json, risks_json,
            watch_next, evidence_ids_json, model_used, created_at, updated_at, verified)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "card_1", "org/repo", "developer platform", "does useful work",
            json.dumps(["engineers", "researchers"]), "modular architecture",
            json.dumps(["fast growth", "strong releases"]), json.dumps({"heat_score": 88}),
            json.dumps([{"type":"adoption","severity":"medium"}]), json.dumps(["watch stars"]),
            json.dumps(["ev1", "ev2", "ev3"]), "test", "2026-05-26T00:00:00Z", "2026-05-26T00:00:00Z", verified,
        ),
    )
    conn.commit()


def test_generate_planning_brief_requires_verified_card():
    conn = make_conn()
    insert_card(conn, verified=0)
    with pytest.raises(ValueError, match="No verified analysis card"):
        generate_planning_brief(conn, "org/repo")


def test_generate_planning_brief_populates_required_fields_and_links_card():
    conn = make_conn()
    insert_card(conn, verified=1)

    brief = generate_planning_brief(conn, "org/repo", model_used="test-model")

    assert brief["card_id"] == "card_1"
    required = [
        "brief_id", "repo_full_name", "card_id", "opportunity", "user_pain",
        "mvp_sketch", "architecture_hint", "go_to_market", "risks_json",
        "validation_metrics", "model_used", "created_at",
    ]
    assert all(brief[key] for key in required)
    row = conn.execute("SELECT * FROM repo_planning_briefs WHERE brief_id=?", (brief["brief_id"],)).fetchone()
    assert row is not None
    assert row["card_id"] == "card_1"
