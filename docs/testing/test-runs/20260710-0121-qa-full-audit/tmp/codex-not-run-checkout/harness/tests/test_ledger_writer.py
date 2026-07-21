"""Tests for LedgerWriter — dual-write JSONL + SQLite with fallback."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ledger_writer import LedgerWriter, LedgerRecord


@pytest.fixture
def ledger(tmp_path):
    jsonl = str(tmp_path / "test-ledger.jsonl")
    sqlite = str(tmp_path / "test-ledger.sqlite")
    fallback = str(tmp_path / "test-fallback.jsonl")
    return LedgerWriter(jsonl, sqlite, fallback_path=fallback)


def _read_jsonl(path: str) -> list[dict]:
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _read_sqlite(path: str) -> list[dict]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM ledger_events ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- record_recover ---

class TestRecordRecover:
    def test_dual_write(self, ledger, tmp_path):
        ledger.record_recover(
            "test:0.0", before_state="running", after_state="needs_recover",
            success=True, reason="proceed_detected",
        )
        jsonl_records = _read_jsonl(str(tmp_path / "test-ledger.jsonl"))
        sqlite_records = _read_sqlite(str(tmp_path / "test-ledger.sqlite"))
        assert len(jsonl_records) == 1
        assert len(sqlite_records) == 1
        assert jsonl_records[0]["action"] == "recover"
        assert sqlite_records[0]["action"] == "recover"

    def test_multiple_records(self, ledger, tmp_path):
        for i in range(5):
            ledger.record_recover(
                f"test:0.{i}", before_state="running", after_state="needs_recover",
                success=True, reason="test",
            )
        jsonl_records = _read_jsonl(str(tmp_path / "test-ledger.jsonl"))
        assert len(jsonl_records) == 5


# --- record_respawn ---

class TestRecordRespawn:
    def test_respawn_record(self, ledger, tmp_path):
        ledger.record_respawn(
            "test:0.2",
            before_state="needs_respawn",
            after_state="running",
            success=True,
            reason="worker_pane_recreated",
            sprint_id="sprint-123",
            task_id="task-123",
            extra={"active_respawns": 1},
        )
        records = _read_jsonl(str(tmp_path / "test-ledger.jsonl"))
        rows = _read_sqlite(str(tmp_path / "test-ledger.sqlite"))
        assert records[0]["action"] == "respawn"
        assert records[0]["task_id"] == "task-123"
        assert records[0]["extra"]["active_respawns"] == 1
        assert rows[0]["action"] == "respawn"

    def test_respawn_rejection_record(self, ledger, tmp_path):
        ledger.record_respawn(
            "test:0.2",
            before_state="needs_respawn",
            after_state="needs_respawn",
            success=False,
            reason="respawn_max_concurrent_reached",
        )
        records = _read_jsonl(str(tmp_path / "test-ledger.jsonl"))
        assert records[0]["success"] is False
        assert records[0]["reason"] == "respawn_max_concurrent_reached"


# --- record_clear ---

class TestRecordClear:
    def test_clear_record(self, ledger, tmp_path):
        ledger.record_clear(
            "test:0.0", before_state="dirty", after_state="clean",
            success=True, reason="clear_ok", attempt=1,
        )
        records = _read_jsonl(str(tmp_path / "test-ledger.jsonl"))
        assert len(records) == 1
        assert records[0]["action"] == "clear"
        assert records[0]["attempt"] == 1

    def test_clear_fail(self, ledger, tmp_path):
        ledger.record_clear(
            "test:0.0", before_state="dirty", after_state="dirty",
            success=False, reason="exhausted", attempt=4,
        )
        records = _read_jsonl(str(tmp_path / "test-ledger.jsonl"))
        assert records[0]["success"] is False


# --- record_reassign ---

class TestRecordReassign:
    def test_reassign_record(self, ledger, tmp_path):
        ledger.record_reassign(
            "test:0.0", "test:0.1",
            task_id="task-123", before_state="running",
            after_state="clean", reason="spillover",
        )
        records = _read_jsonl(str(tmp_path / "test-ledger.jsonl"))
        assert len(records) == 1
        assert records[0]["action"] == "reassign"
        assert records[0]["from_pane"] == "test:0.0"
        assert records[0]["to_pane"] == "test:0.1"
        assert records[0]["task_id"] == "task-123"

    def test_reassign_sqlite(self, ledger, tmp_path):
        ledger.record_reassign(
            "test:0.0", "test:0.1",
            task_id="task-456", before_state="running",
            after_state="clean", reason="reassign",
        )
        rows = _read_sqlite(str(tmp_path / "test-ledger.sqlite"))
        assert len(rows) == 1
        assert rows[0]["from_pane"] == "test:0.0"
        assert rows[0]["to_pane"] == "test:0.1"


# --- record_reinject ---

class TestRecordReinject:
    def test_reinject_success(self, ledger, tmp_path):
        ledger.record_reinject(
            "test:0.0", before_state="clean", after_state="running",
            success=True, reason="all_ok", sprint_id="sprint-123",
        )
        records = _read_jsonl(str(tmp_path / "test-ledger.jsonl"))
        assert records[0]["action"] == "reinject"
        assert records[0]["sprint_id"] == "sprint-123"


# --- query_history ---

class TestQueryHistory:
    def test_query_by_pane(self, ledger):
        ledger.record_clear("test:0.0", before_state="dirty", after_state="clean",
                            success=True, reason="ok")
        ledger.record_clear("test:0.1", before_state="dirty", after_state="clean",
                            success=True, reason="ok")
        results = ledger.query_history("test:0.0")
        assert len(results) == 1
        assert results[0].pane_id == "test:0.0"

    def test_query_by_action(self, ledger):
        ledger.record_recover("test:0.0", before_state="running",
                              after_state="needs_recover", success=True, reason="ok")
        ledger.record_clear("test:0.0", before_state="dirty",
                            after_state="clean", success=True, reason="ok")
        results = ledger.query_history("test:0.0", action="recover")
        assert len(results) == 1
        assert results[0].action == "recover"

    def test_query_limit(self, ledger):
        for i in range(10):
            ledger.record_clear("test:0.0", before_state="dirty",
                                after_state="clean", success=True, reason="ok")
        results = ledger.query_history("test:0.0", limit=3)
        assert len(results) == 3

    def test_query_empty(self, tmp_path):
        jsonl = str(tmp_path / "empty.jsonl")
        sqlite = str(tmp_path / "empty.sqlite")
        lw = LedgerWriter(jsonl, sqlite)
        results = lw.query_history("test:0.0")
        assert results == []


# --- dual-write failure fallback ---

class TestDualWriteFailure:
    def test_jsonl_failure_uses_fallback(self, tmp_path):
        jsonl = str(tmp_path / "readonly" / "ledger.jsonl")
        sqlite = str(tmp_path / "test.sqlite")
        fallback = str(tmp_path / "fallback.jsonl")
        readonly = tmp_path / "readonly"
        readonly.mkdir()
        readonly.chmod(0o500)
        try:
            lw = LedgerWriter(jsonl, sqlite, fallback_path=fallback)
            lw.record_clear("p", before_state="dirty", after_state="clean",
                            success=True, reason="test")
            assert (tmp_path / "fallback.jsonl").exists()
        finally:
            readonly.chmod(0o700)

    def test_sqlite_failure_continues(self, tmp_path):
        jsonl = str(tmp_path / "ledger.jsonl")
        sqlite = "/dev/null/impossible.sqlite"
        fallback = str(tmp_path / "fallback.jsonl")
        lw = LedgerWriter(jsonl, sqlite, fallback_path=fallback)
        lw.record_clear("p", before_state="dirty", after_state="clean",
                        success=True, reason="test")
        records = _read_jsonl(jsonl)
        assert len(records) == 1
