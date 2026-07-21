"""Tests for HF Paper Insight schema, storage, state machine, compat."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "hf_paper_insight"))

from compat import CompatBridge, LegacyPaperFormat
from schema import (
    ALL_DDL,
    ENTITY_TABLE_MAP,
    PaperCanonical,
    PaperEnrichment,
    PaperEvidencePacket,
    PaperSignal,
    PaperSnapshot,
    PaperTaxonomy,
    WindowType,
    entity_to_row,
    _gen_id,
    _title_hash,
)
from state_machine import (
    IllegalTransitionError,
    PaperLifecycle,
    PaperStateMachine,
    PaperStateRecord,
)
from storage import PaperStore


# ── Schema Tests ───────────────────────────────────────────────────────


class TestPaperSnapshot:
    def test_default_values(self):
        s = PaperSnapshot(paper_id="p1")
        assert s.window_type == WindowType.daily
        assert s.source == "huggingface_papers"
        assert s.upvotes == 0
        assert s.first_seen_in_window == 1
        assert s.snapshot_id.startswith("snap-")

    def test_custom_values(self):
        s = PaperSnapshot(
            window_type=WindowType.weekly,
            window_start="2026-05-19",
            window_end="2026-05-25",
            paper_id="p2",
            rank=5,
            upvotes=42,
            hf_url="https://huggingface.co/papers/abc123",
        )
        assert s.window_type == WindowType.weekly
        assert s.rank == 5
        assert s.upvotes == 42


class TestPaperCanonical:
    def test_auto_title_hash(self):
        c = PaperCanonical(title="Attention Is All You Need")
        assert c.title_hash == _title_hash("Attention Is All You Need")
        assert len(c.title_hash) == 24

    def test_empty_title_no_hash(self):
        c = PaperCanonical()
        assert c.title_hash == ""

    def test_paper_id_prefix(self):
        c = PaperCanonical()
        assert c.paper_id.startswith("paper-")


class TestPaperEnrichment:
    def test_default_json_fields(self):
        e = PaperEnrichment(paper_id="p1")
        assert json.loads(e.hf_metadata_json) == {}
        assert json.loads(e.arxiv_metadata_json) == {}


class TestPaperTaxonomy:
    def test_fields(self):
        t = PaperTaxonomy(
            paper_id="p1",
            domain="nlp",
            method="transformer",
            task="translation",
            confidence=0.85,
        )
        assert t.domain == "nlp"
        assert t.confidence == 0.85


class TestPaperSignal:
    def test_default_scores_zero(self):
        s = PaperSignal(paper_id="p1")
        assert s.research_signal_score == 0.0
        assert s.score_profile == "ai-influence"


class TestPaperEvidencePacket:
    def test_version(self):
        p = PaperEvidencePacket(paper_id="p1")
        assert p.packet_version == "v2"


class TestEntityToRow:
    def test_enum_serialized(self):
        s = PaperSnapshot(paper_id="p1", window_type=WindowType.monthly)
        row = entity_to_row(s)
        assert row["window_type"] == "monthly"

    def test_all_fields_present(self):
        c = PaperCanonical(title="test")
        row = entity_to_row(c)
        assert "paper_id" in row
        assert "title_hash" in row


class TestEntityTableMap:
    def test_all_six_entities_mapped(self):
        assert len(ENTITY_TABLE_MAP) == 6
        assert ENTITY_TABLE_MAP["PaperSnapshot"] == "paper_snapshots"
        assert ENTITY_TABLE_MAP["PaperEvidencePacket"] == "paper_evidence_packets"


# ── Storage Tests ──────────────────────────────────────────────────────


class TestPaperStore:
    def test_init_creates_schema(self, tmp_path):
        db = str(tmp_path / "test.db")
        store = PaperStore(db)
        tables = [
            r[0]
            for r in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        store.close()
        assert "paper_snapshots" in tables
        assert "paper_canonical" in tables
        assert "paper_enrichment" in tables
        assert "_schema_meta" in tables

    def test_wal_mode(self, tmp_path):
        db = str(tmp_path / "test.db")
        store = PaperStore(db)
        mode = store.conn.execute("PRAGMA journal_mode").fetchone()[0]
        store.close()
        assert mode == "wal"

    def test_upsert_and_get_canonical(self, tmp_path):
        db = str(tmp_path / "test.db")
        store = PaperStore(db)
        c = PaperCanonical(
            paper_id="paper-test1",
            title="Test Paper",
            title_hash=_title_hash("Test Paper"),
            authors_json='["Author A"]',
            hf_url="https://huggingface.co/papers/test",
        )
        store.upsert(c)
        fetched = store.get(PaperCanonical, "paper-test1")
        store.close()
        assert fetched is not None
        assert fetched.title == "Test Paper"
        assert fetched.paper_id == "paper-test1"

    def test_upsert_update(self, tmp_path):
        db = str(tmp_path / "test.db")
        store = PaperStore(db)
        c = PaperCanonical(
            paper_id="paper-upd",
            title="V1",
            title_hash=_title_hash("V1"),
            authors_json="[]",
            hf_url="https://hf.co",
        )
        store.upsert(c)
        c.title = "V2"
        store.upsert(c)
        fetched = store.get(PaperCanonical, "paper-upd")
        store.close()
        assert fetched.title == "V2"

    def test_find_by_arxiv_id(self, tmp_path):
        db = str(tmp_path / "test.db")
        store = PaperStore(db)
        store.upsert(PaperCanonical(
            paper_id="paper-arxiv",
            title="ArXiv Paper",
            title_hash="x",
            authors_json="[]",
            hf_url="https://hf.co",
            arxiv_id="2401.12345",
        ))
        found = store.find_canonical_by_arxiv("2401.12345")
        store.close()
        assert found is not None
        assert found.paper_id == "paper-arxiv"

    def test_find_by_title_hash(self, tmp_path):
        db = str(tmp_path / "test.db")
        store = PaperStore(db)
        th = _title_hash("Unique Title")
        store.upsert(PaperCanonical(
            paper_id="paper-th",
            title="Unique Title",
            title_hash=th,
            authors_json="[]",
            hf_url="https://hf.co",
        ))
        found = store.find_canonical_by_title_hash(th)
        store.close()
        assert found is not None
        assert found.title == "Unique Title"

    def test_expired_enrichments(self, tmp_path):
        db = str(tmp_path / "test.db")
        store = PaperStore(db)
        store.upsert(PaperCanonical(
            paper_id="paper-exp",
            title="X",
            title_hash="x",
            authors_json="[]",
            hf_url="https://hf.co",
        ))
        store.upsert(PaperEnrichment(
            enrichment_id="enr-exp",
            paper_id="paper-exp",
            ttl_expires_at="2026-01-01T00:00:00Z",
        ))
        expired = store.get_expired_enrichments("2026-06-01T00:00:00Z")
        store.close()
        assert len(expired) == 1
        assert expired[0].enrichment_id == "enr-exp"

    def test_merge_seen_window(self, tmp_path):
        db = str(tmp_path / "test.db")
        store = PaperStore(db)
        store.upsert(PaperCanonical(
            paper_id="paper-merge",
            title="Merge Test",
            title_hash="m",
            authors_json="[]",
            hf_url="https://hf.co",
        ))
        store.merge_seen_window("paper-merge", "daily", "2026-05-28T12:00:00Z")
        c = store.get(PaperCanonical, "paper-merge")
        store.close()
        windows = json.loads(c.seen_windows_json)
        assert len(windows) == 1
        assert windows[0]["window_type"] == "daily"

    def test_query(self, tmp_path):
        db = str(tmp_path / "test.db")
        store = PaperStore(db)
        store.upsert(PaperCanonical(
            paper_id="paper-q1",
            title="Q1",
            title_hash="q1",
            authors_json="[]",
            hf_url="https://hf.co",
        ))
        store.upsert(PaperCanonical(
            paper_id="paper-q2",
            title="Q2",
            title_hash="q2",
            authors_json="[]",
            hf_url="https://hf.co",
        ))
        rows = store.query("paper_canonical")
        store.close()
        assert len(rows) == 2


# ── State Machine Tests ────────────────────────────────────────────────


class TestPaperStateMachine:
    def test_initialize(self):
        sm = PaperStateMachine()
        rec = sm.initialize("paper-1")
        assert rec.current_state == PaperLifecycle.collected
        assert rec.transition_count == 0

    def test_legal_transition(self):
        sm = PaperStateMachine()
        sm.initialize("paper-1")
        rec = sm.transition("paper-1", PaperLifecycle.canonicalized, trigger="canon")
        assert rec.current_state == PaperLifecycle.canonicalized
        assert rec.transition_count == 1

    def test_illegal_transition(self):
        sm = PaperStateMachine()
        sm.initialize("paper-1")
        with pytest.raises(IllegalTransitionError):
            sm.transition("paper-1", PaperLifecycle.stored)

    def test_unknown_paper(self):
        sm = PaperStateMachine()
        with pytest.raises(KeyError):
            sm.transition("ghost", PaperLifecycle.canonicalized)

    def test_full_pipeline(self):
        sm = PaperStateMachine()
        sm.initialize("paper-pipe")
        states = [
            PaperLifecycle.canonicalized,
            PaperLifecycle.enriching,
            PaperLifecycle.enriched,
            PaperLifecycle.classifying,
            PaperLifecycle.classified,
            PaperLifecycle.scoring,
            PaperLifecycle.scored,
            PaperLifecycle.packet_built,
            PaperLifecycle.resonating,
            PaperLifecycle.resonated,
            PaperLifecycle.reasoning,
            PaperLifecycle.compiled,
            PaperLifecycle.stored,
        ]
        for state in states:
            sm.transition("paper-pipe", state)
        rec = sm.get_state("paper-pipe")
        assert rec.current_state == PaperLifecycle.stored
        assert rec.transition_count == len(states)

    def test_event_log(self):
        sm = PaperStateMachine()
        sm.initialize("paper-ev")
        sm.transition("paper-ev", PaperLifecycle.canonicalized, trigger="test")
        rec = sm.get_state("paper-ev")
        events = json.loads(rec.event_log_json)
        assert len(events) == 2
        assert events[1]["to_state"] == "canonicalized"
        assert events[1]["trigger"] == "test"

    def test_rebuild_from_events(self):
        sm = PaperStateMachine()
        events = [
            {"to_state": "collected", "occurred_at": "2026-05-28T10:00:00Z", "trigger": "init"},
            {"to_state": "canonicalized", "occurred_at": "2026-05-28T10:01:00Z", "trigger": "canon"},
            {"to_state": "enriching", "occurred_at": "2026-05-28T10:02:00Z", "trigger": "enrich"},
        ]
        rec = sm.rebuild_from_events("paper-rebuild", events)
        assert rec.current_state == PaperLifecycle.enriching
        assert rec.transition_count == 3
        assert rec.last_trigger == "enrich"

    def test_rebuild_empty_events(self):
        sm = PaperStateMachine()
        with pytest.raises(ValueError):
            sm.rebuild_from_events("paper-empty", [])

    def test_metadata_in_transition(self):
        sm = PaperStateMachine()
        sm.initialize("paper-meta")
        sm.transition(
            "paper-meta",
            PaperLifecycle.canonicalized,
            trigger="canon",
            metadata={"source": "hf", "batch_id": "b1"},
        )
        rec = sm.get_state("paper-meta")
        events = json.loads(rec.event_log_json)
        meta = json.loads(events[1]["metadata_json"])
        assert meta["source"] == "hf"


# ── Compat Tests ───────────────────────────────────────────────────────


class TestLegacyPaperFormat:
    def test_from_jsonl(self):
        data = LegacyPaperFormat.from_legacy_jsonl('{"title": "Test"}')
        assert data["title"] == "Test"

    def test_from_jsonl_invalid(self):
        assert LegacyPaperFormat.from_legacy_jsonl("not json") is None

    def test_to_jsonl(self):
        c = PaperCanonical(
            paper_id="p1",
            title="Test",
            title_hash="x",
            authors_json="[]",
            hf_url="https://hf.co",
        )
        line = LegacyPaperFormat.to_legacy_jsonl(c)
        parsed = json.loads(line)
        assert parsed["title"] == "Test"

    def test_snapshot_to_canonical(self):
        snap = PaperSnapshot(
            paper_id="snap-p1",
            window_type=WindowType.daily,
            observed_at="2026-05-28T12:00:00Z",
            hf_url="https://hf.co/papers/abc",
        )
        canonical = LegacyPaperFormat.convert_snapshot_to_canonical(
            snap, title="My Paper"
        )
        assert canonical.title == "My Paper"
        windows = json.loads(canonical.seen_windows_json)
        assert len(windows) == 1


class TestCompatBridge:
    def test_ingest_legacy_batch(self, tmp_path):
        db = str(tmp_path / "compat.db")
        store = PaperStore(db)
        bridge = CompatBridge(store)

        jsonl = tmp_path / "legacy.jsonl"
        jsonl.write_text(
            '{"paper_id":"p1","title":"Paper One","title_hash":"h1","authors":[],"hf_url":"https://hf.co"}\n'
            '{"paper_id":"p2","title":"Paper Two","title_hash":"h2","authors":[],"hf_url":"https://hf.co"}\n'
        )
        result = bridge.ingest_legacy_batch(str(jsonl))
        store.close()
        assert result["converted"] == 2
        assert result["skipped"] == 0

    def test_ingest_skips_invalid(self, tmp_path):
        db = str(tmp_path / "compat2.db")
        store = PaperStore(db)
        bridge = CompatBridge(store)

        jsonl = tmp_path / "bad.jsonl"
        jsonl.write_text('{"title":"OK","authors":[]}\nnot-json\n')
        result = bridge.ingest_legacy_batch(str(jsonl))
        store.close()
        assert result["converted"] == 1
        assert result["skipped"] == 1

    def test_ingest_missing_file(self, tmp_path):
        db = str(tmp_path / "compat3.db")
        store = PaperStore(db)
        bridge = CompatBridge(store)
        result = bridge.ingest_legacy_batch(str(tmp_path / "nonexistent.jsonl"))
        store.close()
        assert len(result["errors"]) == 1

    def test_export_as_legacy(self, tmp_path):
        db = str(tmp_path / "compat4.db")
        store = PaperStore(db)
        store.upsert(PaperCanonical(
            paper_id="paper-exp",
            title="Export Test",
            title_hash="exp",
            authors_json="[]",
            hf_url="https://hf.co",
        ))
        bridge = CompatBridge(store)
        line = bridge.export_canonical_as_legacy("paper-exp")
        store.close()
        assert line is not None
        parsed = json.loads(line)
        assert parsed["title"] == "Export Test"

    def test_export_not_found(self, tmp_path):
        db = str(tmp_path / "compat5.db")
        store = PaperStore(db)
        bridge = CompatBridge(store)
        result = bridge.export_canonical_as_legacy("ghost")
        store.close()
        assert result is None
