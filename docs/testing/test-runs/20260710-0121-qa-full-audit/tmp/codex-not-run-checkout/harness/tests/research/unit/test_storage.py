"""Tests for research/storage.py: SQLite storage layer, JSONL helpers, feature flag.

Acceptance:
- init_db creates all 7 tables
- get_connection returns configured connection (foreign keys, WAL, Row factory)
- JSONL round-trip: append then read returns original data
- validate_jsonl reports errors for malformed lines
- feature_flag reads config or returns default
- SEVEN_TABLES constant matches actual table count
- span verification returns match/fuzzy_match/mismatch
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent.parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import pytest

from research.storage import (
    SEVEN_TABLES, append_jsonl, evidence_ledger_enabled, feature_flag,
    get_connection, init_db, read_jsonl, table_count, table_exists,
    validate_jsonl, verify_span,
)


class TestSevenTables:
    def test_count_is_7(self):
        assert len(SEVEN_TABLES) == 7

    def test_expected_table_names(self):
        assert "research_runs" in SEVEN_TABLES
        assert "research_sources" in SEVEN_TABLES
        assert "evidence_items" in SEVEN_TABLES
        assert "claims" in SEVEN_TABLES
        assert "claim_evidence" in SEVEN_TABLES
        assert "report_sections" in SEVEN_TABLES
        assert "section_checks" in SEVEN_TABLES


class TestInitDb:
    def test_creates_all_tables(self):
        conn = init_db(":memory:")
        for t in SEVEN_TABLES:
            assert table_exists(conn, t), f"missing table: {t}"
        conn.close()

    def test_idempotent(self):
        conn = init_db(":memory:")
        init_db_migrate = (Path(_LIB) / "research" / "migrations" / "001_init.sql").read_text()
        conn.executescript(init_db_migrate)
        for t in SEVEN_TABLES:
            assert table_exists(conn, t)
        conn.close()

    def test_foreign_keys_enabled(self):
        conn = init_db(":memory:")
        cur = conn.execute("PRAGMA foreign_keys")
        assert cur.fetchone()[0] == 1
        conn.close()

    def test_returns_connection_with_row_factory(self):
        conn = init_db(":memory:")
        conn.execute("INSERT INTO research_runs (topic) VALUES (?)", ("test",))
        row = conn.execute("SELECT * FROM research_runs LIMIT 1").fetchone()
        assert hasattr(row, "keys")
        conn.close()


class TestGetConnection:
    def test_in_memory(self):
        conn = get_connection(":memory:")
        conn.execute("SELECT 1")
        conn.close()

    def test_row_factory(self):
        conn = get_connection(":memory:")
        conn.execute("CREATE TABLE t(x)")
        conn.execute("INSERT INTO t VALUES (1)")
        row = conn.execute("SELECT x FROM t").fetchone()
        assert hasattr(row, "keys")
        conn.close()

    def test_wal_mode(self):
        conn = get_connection("/tmp/test_wal_mode.db")
        try:
            cur = conn.execute("PRAGMA journal_mode")
            assert cur.fetchone()[0].upper() == "WAL"
        finally:
            conn.close()
            os.unlink("/tmp/test_wal_mode.db")


class TestJsonlRoundTrip:
    def test_append_and_read(self, tmp_path):
        f = str(tmp_path / "test.jsonl")
        record = {"key": "value", "num": 42}
        append_jsonl(f, record)
        result = read_jsonl(f)
        assert len(result) == 1
        assert result[0] == record

    def test_multiple_records(self, tmp_path):
        f = str(tmp_path / "multi.jsonl")
        for i in range(5):
            append_jsonl(f, {"i": i})
        result = read_jsonl(f)
        assert len(result) == 5
        assert result[2]["i"] == 2

    def test_empty_file(self, tmp_path):
        f = str(tmp_path / "empty.jsonl")
        Path(f).touch()
        assert read_jsonl(f) == []

    def test_missing_file(self):
        assert read_jsonl("/nonexistent/path/file.jsonl") == []

    def test_creates_parent_dirs(self, tmp_path):
        f = str(tmp_path / "sub" / "dir" / "test.jsonl")
        append_jsonl(f, {"x": 1})
        assert os.path.exists(f)

    def test_unicode_content(self, tmp_path):
        f = str(tmp_path / "unicode.jsonl")
        append_jsonl(f, {"text": "你好世界 🧠"})
        result = read_jsonl(f)
        assert result[0]["text"] == "你好世界 🧠"


class TestValidateJsonl:
    def test_valid_file(self, tmp_path):
        f = str(tmp_path / "valid.jsonl")
        append_jsonl(f, {"a": 1})
        append_jsonl(f, {"b": 2})
        errors = validate_jsonl(f)
        assert errors == []

    def test_invalid_line(self, tmp_path):
        f = str(tmp_path / "bad.jsonl")
        Path(f).write_text('{"a":1}\nnot json\n{"b":2}', encoding="utf-8")
        errors = validate_jsonl(f)
        assert len(errors) == 1
        assert "line 2" in errors[0]

    def test_missing_file(self):
        assert validate_jsonl("/nonexistent.jsonl") == []


class TestFeatureFlag:
    def test_default_when_no_config(self, tmp_path, monkeypatch):
        fake_config = tmp_path / "nonexistent_config.json"
        monkeypatch.setattr("research.storage.CONFIG_PATH", fake_config)
        assert feature_flag("any_flag", default=True) is True
        assert feature_flag("any_flag", default=False) is False

    def test_reads_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.json"
        cfg.write_text('{"feature_flags":{"test_flag":true}}', encoding="utf-8")
        monkeypatch.setattr("research.storage.CONFIG_PATH", cfg)
        assert feature_flag("test_flag", default=False) is True

    def test_missing_flag_returns_default(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.json"
        cfg.write_text('{"feature_flags":{}}', encoding="utf-8")
        monkeypatch.setattr("research.storage.CONFIG_PATH", cfg)
        assert feature_flag("missing", default=True) is True

    def test_evidence_ledger_enabled_wrapper(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.json"
        cfg.write_text('{"feature_flags":{"research.evidence_ledger":true}}', encoding="utf-8")
        monkeypatch.setattr("research.storage.CONFIG_PATH", cfg)
        assert evidence_ledger_enabled() is True


class TestTableHelpers:
    def test_table_exists_false(self):
        conn = get_connection(":memory:")
        assert table_exists(conn, "nonexistent") is False
        conn.close()

    def test_table_count_empty(self):
        conn = init_db(":memory:")
        assert table_count(conn, "research_runs") == 0
        conn.close()

    def test_table_count_with_rows(self):
        conn = init_db(":memory:")
        conn.execute("INSERT INTO research_runs (topic) VALUES ('test')")
        assert table_count(conn, "research_runs") == 1
        conn.close()


class TestVerifySpan:
    def test_exact_match(self):
        source = "Hello world this is a test"
        evidence = "world this"
        start = len("Hello ".encode("utf-8"))
        end = start + len("world this".encode("utf-8"))
        result = verify_span(source, evidence, start, end)
        assert result["status"] == "match"

    def test_mismatch(self):
        result = verify_span("short", "totally different text", 0, 100)
        assert result["status"] == "mismatch"

    def test_fuzzy_match_whitespace(self):
        source = "  Hello world  "
        start = 0
        end = len(source.encode("utf-8"))
        result = verify_span(source, "Hello world", start, end)
        assert result["status"] in ("match", "fuzzy_match")

    def test_result_contains_span_bounds(self):
        result = verify_span("text", "text", 0, 4)
        assert "span_start" in result
        assert "span_end" in result
