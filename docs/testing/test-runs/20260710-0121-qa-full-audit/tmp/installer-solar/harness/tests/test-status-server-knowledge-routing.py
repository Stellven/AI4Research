#!/usr/bin/env python3
"""Regression tests for Tech Hotspot Radar reasoning packet routing summary."""

import importlib.util
import json
import sqlite3
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "lib" / "symphony" / "status-server.py"
spec = importlib.util.spec_from_file_location("status_server", MODULE)
status_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(status_server)


def test_tech_hotspot_reasoning_policy_summary_reads_packet_policy_json(tmp_path, monkeypatch):
    db_path = tmp_path / "tech-hotspot-radar.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE reasoning_packets (
                packet_id TEXT PRIMARY KEY,
                packet_type TEXT NOT NULL,
                evidence_atom_count INTEGER NOT NULL DEFAULT 0,
                token_budget INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                model_policy_json TEXT NOT NULL DEFAULT '{}',
                premium_escalation_json TEXT NOT NULL DEFAULT '{}',
                embedding_policy_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            "INSERT INTO reasoning_packets VALUES (?,?,?,?,?,?,?,?)",
            (
                "pkt-1",
                "trend_synthesis",
                3,
                2000,
                "2026-05-23T23:00:00Z",
                json.dumps({
                    "route": "premium_reasoner",
                    "default_model_family": "claude_opus_like",
                }),
                json.dumps({
                    "allowed": True,
                    "reason": "cross-source synthesis",
                }),
                json.dumps({
                    "route": "embedding_unchanged",
                }),
            ),
        )

    monkeypatch.setenv("TECH_HOTSPOT_RADAR_DB", str(db_path))

    summary = status_server._tech_hotspot_reasoning_policy_summary()

    assert summary["status"] == "ok"
    assert summary["total_packets"] == 1
    assert summary["premium_allowed"] == 1
    assert summary["embedding_unchanged"] == 1
    assert summary["items"][0]["route"] == "premium_reasoner"
    assert summary["items"][0]["default_model_family"] == "claude_opus_like"
