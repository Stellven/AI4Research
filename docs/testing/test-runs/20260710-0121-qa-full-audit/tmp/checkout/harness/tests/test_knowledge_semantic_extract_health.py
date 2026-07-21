#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "lib" / "knowledge-semantic-extract.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("knowledge_semantic_extract", MODULE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_thunderomlx_health_resolves_legacy_mini_alias_to_loaded_qwen(monkeypatch) -> None:
    mod = _load_module()

    def fake_request_json(url, args, timeout_s=5.0):
        if url.endswith("/health"):
            return {
                "status": "healthy",
                "engine_pool": {
                    "models": [
                        {"id": "Qwen3.6-35b-a3b", "loaded": True},
                        {"id": "gemma-4-31B", "loaded": False},
                    ]
                },
            }
        if url.endswith("/v1/models"):
            return {
                "data": [
                    {"id": "Qwen3.6-35b-a3b"},
                    {"id": "gemma-4-31B"},
                ]
            }
        raise AssertionError(url)

    monkeypatch.setattr(mod, "_request_json", fake_request_json)
    args = argparse.Namespace(
        endpoint="http://127.0.0.1:8002",
        proxy_model="mini-thunderomlx-qwen36-knowledge",
        local_model="Qwen3.6-35b-a3b",
    )

    assert mod.thunderomlx_healthy(args) is True
    assert args.proxy_model == "Qwen3.6-35b-a3b"


def test_thunderomlx_health_rejects_unknown_alias_without_qwen(monkeypatch) -> None:
    mod = _load_module()

    def fake_request_json(url, args, timeout_s=5.0):
        if url.endswith("/health"):
            return {"status": "healthy", "engine_pool": {"models": [{"id": "gemma-4-31B", "loaded": True}]}}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "gemma-4-31B"}]}
        raise AssertionError(url)

    monkeypatch.setattr(mod, "_request_json", fake_request_json)
    args = argparse.Namespace(
        endpoint="http://127.0.0.1:8002",
        proxy_model="mini-thunderomlx-qwen36-knowledge",
        local_model="Qwen3.6-35b-a3b",
    )

    assert mod.thunderomlx_healthy(args) is False
    assert args.proxy_model == "mini-thunderomlx-qwen36-knowledge"


def test_registry_query_indexes_created() -> None:
    mod = _load_module()
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE extract_jobs(job_id TEXT, doc_id TEXT, state TEXT);
        CREATE TABLE validation_results(result_id TEXT, job_id TEXT, passed INTEGER);
        CREATE TABLE documents(doc_id TEXT, source_path TEXT, current_state TEXT, extract_policy TEXT, updated_at TEXT);
        """
    )

    mod.ensure_registry_query_indexes(conn)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}

    assert "idx_extract_jobs_doc_state" in names
    assert "idx_validation_results_job_passed" in names
    assert "idx_documents_state_extract_updated" in names
    assert "idx_documents_source_path" in names


def test_registry_doc_id_prefers_duplicate_path_with_completed_extract() -> None:
    mod = _load_module()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE documents(doc_id TEXT, source_path TEXT, current_state TEXT, updated_at TEXT);
        CREATE TABLE extract_jobs(job_id TEXT, doc_id TEXT, state TEXT);
        CREATE TABLE ingest_events(event_id TEXT, doc_id TEXT, event_kind TEXT, from_state TEXT, to_state TEXT, source_adapter TEXT, payload_json TEXT, ts TEXT);
        CREATE TABLE spans(doc_id TEXT, span_id TEXT, start_line INTEGER, end_line INTEGER, text_sha256 TEXT);
        """
    )
    source = Path("/tmp/source.md")
    conn.execute(
        "INSERT INTO documents(doc_id, source_path, current_state, updated_at) VALUES (?,?,?,?)",
        ("raw:duplicate", str(source), "RAW_MATERIALIZED", "2026-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO documents(doc_id, source_path, current_state, updated_at) VALUES (?,?,?,?)",
        ("raw_chatgpt:canonical", str(source), "EXTRACTED_QMD_INDEX_PENDING", "2026-01-02T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO extract_jobs(job_id, doc_id, state) VALUES (?,?,?)",
        ("job1", "raw_chatgpt:canonical", "extract_indexed"),
    )

    assert mod.registry_doc_id(conn, source, "sha", Path("/tmp")) == "raw_chatgpt:canonical"
