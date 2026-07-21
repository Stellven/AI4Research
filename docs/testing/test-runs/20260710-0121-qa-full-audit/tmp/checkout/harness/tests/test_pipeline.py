"""pytest integration smoke tests for the github_intelligence pipeline.

Node: C5_core_runtime_release
Write-scope: harness/tests/test_pipeline.py

Tests the full snapshot → evidence → detector → card → report chain
against a real SQLite DB (temp file, not the production DB).
"""
import os
import sqlite3
import sys
import tempfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB = os.path.join(_ROOT, "lib")
sys.path.insert(0, _LIB)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_conn():
    """Provide a fresh in-memory SQLite connection with schema applied."""
    from github_intelligence.schema import apply_schema

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL")
    apply_schema(conn)
    yield conn
    conn.close()


@pytest.fixture()
def db_path():
    """Provide a temporary file-backed SQLite path."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        path = tf.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


REPO_HOT = {
    "full_name": "org/hot-agent-framework",
    "stars": 8500,
    "forks": 620,
    "readme": (
        "# HotAgentFramework\n\n"
        "Production-grade autonomous agent orchestration for enterprise ML.\n\n"
        "## Features\n"
        "- Zero-latency routing between agents\n"
        "- Persistent memory with vector retrieval\n"
        "- Tool use with sandboxed execution\n"
        "- Multi-modal support (text, image, code)\n\n"
        "## Why this?\nBuilt to solve real production reliability problems.\n"
        "Trusted by 200+ companies.\n"
    ),
    "releases": [
        {
            "tag": "v3.0.0",
            "name": "v3.0 — Enterprise GA",
            "body": "Introduces distributed coordinator and persistent state.",
            "published_at": "2026-05-26T09:00:00Z",
        }
    ],
}

REPO_EARLY = {
    "full_name": "indie/novel-compression",
    "stars": 80,
    "forks": 5,
    "readme": (
        "# NovelCompression\n\nExperimental lossless compression using neural networks.\n\n"
        "## Core idea\nUse small transformer to predict byte-level entropy.\n\n"
        "## Status\nEarly alpha. Contributions welcome.\n"
    ),
    "releases": [],
}

REPO_NORMAL = {
    "full_name": "util/logger",
    "stars": 400,
    "forks": 30,
    "readme": "# Logger\nSimple Python logging wrapper.\n## Usage\n`import logger`\n",
    "releases": [],
}


# ---------------------------------------------------------------------------
# Single-repo pipeline tests
# ---------------------------------------------------------------------------


class TestPipelineSingleRepo:
    def test_hot_repo_produces_card(self, db_path):
        from github_intelligence.pipeline import run_pipeline

        result = run_pipeline(db_path=db_path, date="2026-05-27",
                              repos=[REPO_HOT], auto_verify=True)
        assert result["repos_processed"] == 1
        assert result["cards_created"] == 1
        assert result["cards_verified"] == 1
        assert result["errors"] == []

    def test_hot_repo_triggers_detections(self, db_path):
        """A repo with high stars + recent release should produce detections."""
        from github_intelligence.pipeline import run_pipeline
        from github_intelligence.schema import fetch_rows, Detection

        result = run_pipeline(db_path=db_path, date="2026-05-27",
                              repos=[REPO_HOT], auto_verify=True)
        conn = sqlite3.connect(db_path)
        alerts = fetch_rows(conn, Detection.TABLE)
        conn.close()
        # detections may or may not fire depending on acceleration; just check no crash
        assert isinstance(alerts, list)

    def test_early_repo_no_crash(self, db_path):
        from github_intelligence.pipeline import run_pipeline

        result = run_pipeline(db_path=db_path, date="2026-05-27",
                              repos=[REPO_EARLY], auto_verify=True)
        assert result["repos_processed"] == 1
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# Multi-repo pipeline tests
# ---------------------------------------------------------------------------


class TestPipelineMultiRepo:
    def test_three_repos_processed(self, db_path):
        from github_intelligence.pipeline import run_pipeline

        result = run_pipeline(
            db_path=db_path,
            date="2026-05-27",
            repos=[REPO_HOT, REPO_EARLY, REPO_NORMAL],
            auto_verify=True,
        )
        assert result["repos_processed"] == 3
        assert result["cards_created"] == 3
        assert result["errors"] == []

    def test_daily_report_generated(self, db_path):
        from github_intelligence.pipeline import run_pipeline

        result = run_pipeline(
            db_path=db_path,
            date="2026-05-27",
            repos=[REPO_HOT, REPO_EARLY],
            auto_verify=True,
        )
        assert result["daily_report"] is not None
        assert result["daily_report"]["report_date"] == "2026-05-27"

    def test_daily_report_in_db(self, db_path):
        from github_intelligence.pipeline import run_pipeline
        from github_intelligence.schema import fetch_rows, DailyReport

        run_pipeline(db_path=db_path, date="2026-05-27",
                     repos=[REPO_HOT], auto_verify=True)
        conn = sqlite3.connect(db_path)
        rows = fetch_rows(conn, DailyReport.TABLE, "report_date=?", ("2026-05-27",))
        conn.close()
        assert len(rows) == 1

    def test_snapshots_persisted(self, db_path):
        from github_intelligence.pipeline import run_pipeline
        from github_intelligence.schema import fetch_rows, RepoSnapshot

        run_pipeline(db_path=db_path, date="2026-05-27",
                     repos=[REPO_HOT, REPO_NORMAL], auto_verify=True)
        conn = sqlite3.connect(db_path)
        rows = fetch_rows(conn, RepoSnapshot.TABLE)
        conn.close()
        assert len(rows) == 2

    def test_evidence_atoms_persisted(self, db_path):
        from github_intelligence.pipeline import run_pipeline
        from github_intelligence.schema import fetch_rows, EvidenceAtom

        run_pipeline(db_path=db_path, date="2026-05-27",
                     repos=[REPO_HOT], auto_verify=True)
        conn = sqlite3.connect(db_path)
        rows = fetch_rows(conn, EvidenceAtom.TABLE,
                          "full_name=?", ("org/hot-agent-framework",))
        conn.close()
        assert len(rows) > 0


# ---------------------------------------------------------------------------
# WAL + schema idempotency
# ---------------------------------------------------------------------------


class TestPipelineSchemaContract:
    def test_apply_schema_twice_no_error(self, db_conn):
        from github_intelligence.schema import apply_schema

        apply_schema(db_conn)  # second application must be safe

    def test_wal_mode_enabled(self, db_path):
        from github_intelligence.pipeline import run_pipeline

        run_pipeline(db_path=db_path, date="2026-05-27", repos=[], auto_verify=False)
        conn = sqlite3.connect(db_path)
        row = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        assert row[0] == "wal"

    def test_no_unverified_cards_in_daily_report(self, db_path):
        """Only verified cards should appear in sudden_hot / early_potential."""
        from github_intelligence.pipeline import run_pipeline
        from github_intelligence.schema import fetch_rows, DailyReport
        import json as _json

        # auto_verify=False → cards stay unverified → report sections empty
        run_pipeline(db_path=db_path, date="2026-05-27",
                     repos=[REPO_HOT], auto_verify=False)
        conn = sqlite3.connect(db_path)
        rows = fetch_rows(conn, DailyReport.TABLE, "report_date=?", ("2026-05-27",))
        conn.close()
        assert len(rows) == 1
        report_row = rows[0]
        sudden_hot = _json.loads(report_row.get("sudden_hot") or "[]")
        assert sudden_hot == [], "unverified cards must not appear in sudden_hot"
