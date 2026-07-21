"""Tests for PaneLifecycleJobs — archive, TTL, backup."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from pane_lifecycle_jobs import PaneLifecycleJobs


@pytest.fixture
def jobs(tmp_path):
    hygiene = str(tmp_path / "pane-hygiene.json")
    ledger = str(tmp_path / "dispatch-ledger.jsonl")
    sqlite_db = str(tmp_path / "model_call_ledger.sqlite")
    archive = str(tmp_path / "archive")
    return PaneLifecycleJobs(
        hygiene_json_path=hygiene,
        ledger_jsonl_path=ledger,
        sqlite_db_path=sqlite_db,
        archive_dir=archive,
    )


def _write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _write_lines(path, lines):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for line in lines:
            f.write(line + "\n")


def _init_sqlite(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ledger_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pane_id TEXT NOT NULL,
            action TEXT NOT NULL,
            before_state TEXT,
            after_state TEXT,
            ts TEXT NOT NULL,
            reason TEXT,
            from_pane TEXT,
            to_pane TEXT,
            task_id TEXT,
            detector_id TEXT,
            sprint_id TEXT,
            attempt INTEGER,
            success INTEGER,
            extra TEXT,
            ledger_ts TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# --- archive_hygiene ---

class TestArchiveHygiene:
    def test_no_archive_when_small(self, jobs, tmp_path):
        _write_json(str(tmp_path / "pane-hygiene.json"), {"small": True})
        result = jobs.archive_hygiene()
        assert result is None

    def test_archive_when_large(self, jobs, tmp_path):
        large_data = {"data": "x" * 200_000}
        _write_json(str(tmp_path / "pane-hygiene.json"), large_data)
        result = jobs.archive_hygiene(max_size_kb=1)
        assert result is not None
        assert Path(result).exists()

    def test_no_file(self, jobs):
        result = jobs.archive_hygiene()
        assert result is None


# --- cleanup_hygiene_archives ---

class TestCleanupHygieneArchives:
    def test_removes_old_archives(self, jobs, tmp_path):
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir(parents=True)
        old_file = archive_dir / "pane-hygiene.20200101.json"
        old_file.write_text("{}")
        import os
        import datetime
        old_time = (datetime.datetime.now() - datetime.timedelta(days=60)).timestamp()
        os.utime(str(old_file), (old_time, old_time))

        removed = jobs.cleanup_hygiene_archives(retention_days=30)
        assert len(removed) == 1
        assert not old_file.exists()

    def test_keeps_recent(self, jobs, tmp_path):
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir(parents=True)
        recent = archive_dir / "pane-hygiene.20990101.json"
        recent.write_text("{}")
        removed = jobs.cleanup_hygiene_archives(retention_days=30)
        assert len(removed) == 0


# --- archive_ledger ---

class TestArchiveLedger:
    def test_no_archive_when_small(self, jobs, tmp_path):
        _write_lines(str(tmp_path / "dispatch-ledger.jsonl"), ['{"a":1}'])
        result = jobs.archive_ledger()
        assert result is None

    def test_archive_when_many_lines(self, jobs, tmp_path):
        lines = [json.dumps({"i": i}) for i in range(200)]
        _write_lines(str(tmp_path / "dispatch-ledger.jsonl"), lines)
        result = jobs.archive_ledger(max_lines=100)
        assert result is not None
        assert Path(result).exists()
        assert tmp_path.joinpath("dispatch-ledger.jsonl").exists()


# --- cleanup_ledger_archives ---

class TestCleanupLedgerArchives:
    def test_removes_old(self, jobs, tmp_path):
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir(parents=True)
        old = archive_dir / "dispatch-ledger.20200101.jsonl"
        old.write_text("line\n")
        import os, datetime
        old_time = (datetime.datetime.now() - datetime.timedelta(days=100)).timestamp()
        os.utime(str(old), (old_time, old_time))
        removed = jobs.cleanup_ledger_archives(retention_days=90)
        assert len(removed) == 1


# --- backup_sqlite ---

class TestBackupSqlite:
    def test_backup_creates_copy(self, jobs, tmp_path):
        db = str(tmp_path / "model_call_ledger.sqlite")
        _init_sqlite(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO ledger_events (pane_id, action, before_state, after_state, ts, reason, ledger_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     ("p", "clear", "dirty", "clean", "2026-01-01T00:00:00Z", "ok", "2026-01-01T00:00:00Z"))
        conn.commit()
        conn.close()
        result = jobs.backup_sqlite()
        assert result is not None
        assert Path(result).exists()

    def test_no_db(self, jobs):
        result = jobs.backup_sqlite()
        assert result is None


# --- ttl_sqlite ---

class TestTtlSqlite:
    def test_deletes_old_records(self, jobs, tmp_path):
        db = str(tmp_path / "model_call_ledger.sqlite")
        _init_sqlite(db)
        conn = sqlite3.connect(db)
        old_ts = "2020-01-01T00:00:00Z"
        new_ts = "2026-05-28T00:00:00Z"
        conn.execute("INSERT INTO ledger_events (pane_id, action, before_state, after_state, ts, reason, ledger_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     ("p1", "clear", "dirty", "clean", old_ts, "old", old_ts))
        conn.execute("INSERT INTO ledger_events (pane_id, action, before_state, after_state, ts, reason, ledger_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     ("p2", "clear", "dirty", "clean", new_ts, "new", new_ts))
        conn.commit()
        conn.close()
        deleted = jobs.ttl_sqlite(retention_days=90)
        assert deleted == 1
        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT COUNT(*) FROM ledger_events").fetchone()
        conn.close()
        assert rows[0] == 1


# --- run_daily ---

class TestRunDaily:
    def test_runs_all_jobs(self, jobs, tmp_path):
        _write_json(str(tmp_path / "pane-hygiene.json"), {"test": True})
        db = str(tmp_path / "model_call_ledger.sqlite")
        _init_sqlite(db)
        result = jobs.run_daily()
        assert "ts" in result
        assert "sqlite_ttl_deleted" in result
