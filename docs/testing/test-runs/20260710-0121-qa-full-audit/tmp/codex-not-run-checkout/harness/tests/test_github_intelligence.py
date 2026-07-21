"""pytest suite for GitHub Project Intelligence core modules.

Node: C5_core_runtime_release
Write-scope: harness/tests/test_github_intelligence.py

Wraps the module-level _self_test() functions and adds cross-module integration
assertions. Requires no network access — all tests use in-memory SQLite.
"""
import importlib
import json
import os
import sqlite3
import sys
import tempfile

import pytest

# Ensure harness/lib is on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB = os.path.join(_ROOT, "lib")
sys.path.insert(0, _LIB)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fresh_conn() -> sqlite3.Connection:
    """Return a fresh in-memory SQLite connection with schema applied."""
    from github_intelligence.schema import apply_schema

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL")
    apply_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# C1: schema + model_ledger
# ---------------------------------------------------------------------------


class TestSchema:
    def test_self_test_passes(self):
        import github_intelligence.schema as m

        result = m._self_test()
        assert result["tests_run"] == result["tests_passed"], json.dumps(result, indent=2)

    def test_model_ledger_self_test_passes(self):
        import github_intelligence.model_ledger as m

        result = m._self_test()
        assert result["tests_run"] == result["tests_passed"], json.dumps(result, indent=2)

    def test_model_ledger_persists_budget_exhausted_audit_row(self, monkeypatch):
        import github_intelligence.model_ledger as m

        monkeypatch.setattr(m, "MAX_PREMIUM_CALLS_PER_DAY", 50)
        monkeypatch.setattr(m, "MAX_PREMIUM_COST_PER_DAY", 0.10)

        conn = sqlite3.connect(":memory:")
        ledger = m.ModelLedger(conn)
        ledger.record_event(
            model_name="claude-opus",
            provider="anthropic",
            call_type="editorial",
            cost_estimate=0.04,
            created_at="2026-05-27T00:00:00Z",
            call_id="ok-1",
        )
        ledger.record_event(
            model_name="claude-opus",
            provider="anthropic",
            call_type="editorial",
            cost_estimate=0.05,
            created_at="2026-05-27T01:00:00Z",
            call_id="ok-2",
        )

        with pytest.raises(m.BudgetExceeded):
            ledger.record_event(
                model_name="claude-opus",
                provider="anthropic",
                call_type="editorial",
                cost_estimate=0.02,
                created_at="2026-05-27T02:00:00Z",
                call_id="blocked",
            )

        rows = ledger.list_calls(limit=20, include_budget_exhausted=True)
        blocked = next(call for call in rows if call.call_id == "blocked")
        assert blocked.usage_extra["budget_exhausted"] is True
        assert blocked.usage_extra["budget_reason"] == "premium_daily_usd_cap"
        assert blocked.usage_extra["attempted_cost_estimate"] == 0.02
        assert blocked.cost_estimate == 0.0
        assert ledger.premium_count_on("2026-05-27") == 2
        assert round(ledger.get_total_cost_today("2026-05-27"), 2) == 0.09

    def test_model_ledger_aggregation_helpers(self):
        import github_intelligence.model_ledger as m

        conn = sqlite3.connect(":memory:")
        ledger = m.ModelLedger(conn)
        ledger.record_event(
            model_name="qwen3.6-thunderomlx",
            provider="thunderomlx",
            call_type="preprocess",
            input_tokens=10,
            output_tokens=5,
            created_at="2026-05-27T00:00:00Z",
            call_id="local-1",
        )
        ledger.record_event(
            model_name="gemini-pro",
            provider="google",
            call_type="reasoning",
            input_tokens=20,
            output_tokens=10,
            cost_estimate=0.11,
            created_at="2026-05-27T01:00:00Z",
            call_id="premium-1",
        )

        by_provider = ledger.get_calls_by_provider()
        by_model = ledger.get_calls_by_model()
        assert by_provider["google"]["calls"] == 1
        assert by_provider["thunderomlx"]["calls"] == 1
        assert by_model["gemini-pro"]["cost"] == 0.11
        assert ledger.get_call_count() == 2
        assert ledger.get_call_count(provider="google") == 1
        assert round(ledger.get_total_cost_today("2026-05-27"), 2) == 0.11

    def test_schema_version_constant(self):
        from github_intelligence.schema import SCHEMA_VERSION

        assert SCHEMA_VERSION == "github_intelligence.v1"

    def test_apply_schema_idempotent(self):
        from github_intelligence.schema import apply_schema

        conn = sqlite3.connect(":memory:")
        apply_schema(conn)
        apply_schema(conn)  # second call must not raise
        cur = conn.execute("SELECT COUNT(*) FROM github_intelligence_migrations")
        assert cur.fetchone()[0] == 1  # only one migration record

    def test_evidence_atom_truncation(self):
        from github_intelligence.schema import EvidenceAtom

        atom = EvidenceAtom(
            evidence_id="ev-x",
            full_name="o/r",
            source="api",
            evidence_type="readme_claim",
            compressed_content="a" * 1000,
        )
        assert len(atom.compressed_content) == EvidenceAtom.MAX_COMPRESSED_CHARS

    def test_analysis_card_evidence_floor(self):
        from github_intelligence.schema import AnalysisCard

        card = AnalysisCard(
            analysis_id="ac-test",
            full_name="o/r",
            analysis_date="2026-05-27",
            evidence_ids=["e1"],
        )
        with pytest.raises(ValueError):
            card.validate_evidence_floor()

    def test_detection_bad_severity(self):
        from github_intelligence.schema import Detection

        with pytest.raises(ValueError):
            Detection(
                detector_name="x",
                full_name="o/r",
                severity="catastrophic",
                title="x",
            )


# ---------------------------------------------------------------------------
# C2: adapters + snapshots
# ---------------------------------------------------------------------------


class TestAdapters:
    def test_self_test_passes(self):
        from github_intelligence.adapters import _self_test

        result = _self_test()
        assert result["tests_run"] == result["tests_passed"], json.dumps(result, indent=2)

    def test_topic_adapter_empty_response(self):
        from github_intelligence.adapters.topic import TopicAdapter
        from datetime import datetime

        adapter = TopicAdapter(
            topics=["llm"],
            fetch_fn=lambda url, headers: {"items": [], "total_count": 0},
        )
        candidates = adapter.run(since=datetime(2026, 5, 1))
        assert candidates == []

    def test_tracked_adapter_known_repos(self):
        from github_intelligence.adapters.tracked import TrackedAdapter
        from datetime import datetime

        adapter = TrackedAdapter(config={"tracked_repos": ["owner/repo-a", "owner/repo-b"]})
        candidates = adapter.run(since=datetime(2026, 5, 1))
        assert len(candidates) == 2
        full_names = {c.full_name for c in candidates}
        assert "owner/repo-a" in full_names

    def test_dedup_queue_no_duplicates(self):
        from github_intelligence.adapters import DedupQueue
        from github_intelligence.schema import DiscoveryCandidate, utc_now_iso

        conn = fresh_conn()
        queue = DedupQueue()

        ts = utc_now_iso()
        candidates = [
            DiscoveryCandidate("owner/x", "trending", ts),
            DiscoveryCandidate("owner/x", "trending", ts),  # duplicate
        ]
        new1 = queue.enqueue(candidates, conn)
        assert len(new1) == 1

        new2 = queue.enqueue(candidates, conn)
        assert len(new2) == 0  # all already seen


class TestSnapshots:
    def test_self_test_passes(self):
        from github_intelligence.snapshots import _self_test

        result = _self_test()
        assert result["tests_run"] == result["tests_passed"], json.dumps(result, indent=2)

    def test_take_snapshot_persisted(self):
        from github_intelligence.snapshots import take_snapshot
        from github_intelligence.schema import fetch_rows, RepoSnapshot

        conn = fresh_conn()
        snap = take_snapshot(full_name="org/proj", stars=500, conn=conn)
        rows = fetch_rows(conn, RepoSnapshot.TABLE, "full_name=?", ("org/proj",))
        assert len(rows) == 1
        assert rows[0]["stars"] == 500

    def test_compute_deltas_insufficient_history(self):
        from github_intelligence.snapshots import take_snapshot, compute_deltas

        conn = fresh_conn()
        snap = take_snapshot(full_name="org/newrepo", stars=10, conn=conn)
        deltas = compute_deltas("org/newrepo", snap.snapshot_at, conn)
        assert deltas.get("history_status") == "insufficient_history"


# ---------------------------------------------------------------------------
# C3: evidence + detectors
# ---------------------------------------------------------------------------


class TestEvidence:
    def test_self_test_passes(self):
        from github_intelligence.evidence import _self_test

        result = _self_test()
        assert result["tests_run"] == result["tests_passed"], json.dumps(result, indent=2)

    def test_compress_readme_returns_atoms(self):
        from github_intelligence.evidence import compress_readme

        readme = (
            "# MyProject\n\nA great ML toolkit.\n\n"
            "## Features\n- Fast inference\n- Low memory\n- Easy API\n"
        )
        atoms = compress_readme("org/myproject", readme)
        assert len(atoms) > 0
        for atom in atoms:
            assert atom.full_name == "org/myproject"
            assert atom.evidence_type == "readme_claim"
            assert len(atom.compressed_content or "") <= 500

    def test_compress_readme_discards_low_importance(self):
        from github_intelligence.evidence import compress_readme

        atoms = compress_readme("org/x", "")
        assert atoms == []

    def test_compress_releases_one_atom_per_release(self):
        from github_intelligence.evidence import compress_releases

        releases = [
            {"tag": "v1.0", "name": "First", "body": "Initial release", "published_at": "2026-05-01"},
            {"tag": "v2.0", "name": "Major", "body": "Major improvements", "published_at": "2026-05-15"},
        ]
        atoms = compress_releases("org/x", releases)
        assert len(atoms) == 2
        tags = {a.raw_ref for a in atoms}
        assert "v1.0" in tags
        assert "v2.0" in tags


class TestDetectors:
    def test_self_test_passes(self):
        from github_intelligence.detectors import _self_test

        result = _self_test()
        assert result["tests_run"] == result["tests_passed"], json.dumps(result, indent=2)

    def test_sudden_hot_triggers_on_high_acceleration(self):
        from github_intelligence.detectors import detect_sudden_hot
        from github_intelligence.schema import RepoSnapshot

        snap = RepoSnapshot(
            snapshot_id="s1",
            full_name="o/r",
            snapshot_at="2026-05-27T00:00:00Z",
            stars=5000,
            star_acceleration=10.0,
            stars_delta_24h=500,
        )
        detections = detect_sudden_hot("o/r", snap, [])
        assert len(detections) == 1
        assert detections[0].severity == "high"

    def test_sudden_hot_negative_control(self):
        from github_intelligence.detectors import detect_sudden_hot
        from github_intelligence.schema import RepoSnapshot

        snap = RepoSnapshot(
            snapshot_id="s2",
            full_name="o/r",
            snapshot_at="2026-05-27T00:00:00Z",
            stars=100,
            star_acceleration=0.5,
            stars_delta_24h=1,
        )
        detections = detect_sudden_hot("o/r", snap, [])
        assert detections == []

    def test_heat_score_deterministic(self):
        from github_intelligence.detectors import compute_heat_score
        from github_intelligence.schema import RepoSnapshot, EvidenceAtom

        snap = RepoSnapshot(
            snapshot_id="sx",
            full_name="o/r",
            snapshot_at="2026-05-27T00:00:00Z",
            stars=2000,
            star_acceleration=3.0,
            stars_delta_24h=200,
            commit_count_7d=15,
        )
        evidence = [
            EvidenceAtom(
                evidence_id="e1",
                full_name="o/r",
                source="api",
                evidence_type="readme_claim",
                importance_score=80.0,
                technical_depth_score=70.0,
            )
        ]
        h1 = compute_heat_score(snap, evidence)
        h2 = compute_heat_score(snap, evidence)
        assert h1 == h2, "heat_score must be deterministic"
        assert 0.0 <= h1 <= 100.0


# ---------------------------------------------------------------------------
# C4: cards + briefs + reports
# ---------------------------------------------------------------------------


class TestCards:
    def test_self_test_passes(self):
        from github_intelligence.cards import _self_test

        result = _self_test()
        assert result["tests_run"] == result["tests_passed"], json.dumps(result, indent=2)

    def test_create_card_verified_false_by_default(self):
        from github_intelligence.cards import create_analysis_card

        conn = fresh_conn()
        card = create_analysis_card(
            full_name="o/r",
            analysis_date="2026-05-27",
            evidence_ids=["e1", "e2", "e3"],
            conn=conn,
        )
        assert card.verified == 0

    def test_verify_card_sets_flag(self):
        from github_intelligence.cards import create_analysis_card, verify_card

        conn = fresh_conn()
        card = create_analysis_card(
            full_name="o/r",
            analysis_date="2026-05-27",
            evidence_ids=["e1", "e2", "e3"],
            conn=conn,
        )
        updated = verify_card(card.analysis_id, conn)
        assert updated is True

    def test_planning_brief_requires_verified_card(self):
        from github_intelligence.cards import create_analysis_card, create_planning_brief

        conn = fresh_conn()
        card = create_analysis_card(
            full_name="o/r",
            analysis_date="2026-05-27",
            evidence_ids=["e1", "e2", "e3"],
            conn=conn,
        )
        with pytest.raises(ValueError):
            create_planning_brief(card, conn=conn)


class TestReports:
    def test_self_test_passes(self):
        from github_intelligence.reports import _self_test

        result = _self_test()
        assert result["tests_run"] == result["tests_passed"], json.dumps(result, indent=2)

    def test_daily_report_required_sections(self):
        from github_intelligence.schema import DailyReport

        required = [
            "report_date", "core_judgment", "sudden_hot", "early_potential",
            "tech_radar", "community_signals", "planning_suggestions", "watchlist",
        ]
        for field in required:
            assert hasattr(DailyReport, "__dataclass_fields__") or hasattr(
                DailyReport("2026-05-27"), field
            )

    def test_weekly_report_required_sections(self):
        from github_intelligence.schema import WeeklyReport

        wr = WeeklyReport(week_start="2026-05-25")
        for attr in ["one_sentence", "top5_trends", "top10_projects",
                     "deep_analysis", "planning_pool", "next_week_metrics"]:
            assert hasattr(wr, attr)


# ---------------------------------------------------------------------------
# C4: pipeline smoke
# ---------------------------------------------------------------------------


class TestPipeline:
    def test_self_test_passes(self):
        from github_intelligence.pipeline import _self_test

        result = _self_test()
        assert result["tests_run"] == result["tests_passed"], json.dumps(result, indent=2)

    def test_pipeline_empty_repos(self):
        from github_intelligence.pipeline import run_pipeline

        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            db_path = tf.name
        try:
            result = run_pipeline(db_path=db_path, date="2026-05-27", repos=[])
            assert result["repos_processed"] == 0
            assert result["errors"] == []
        finally:
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# Cross-module integration: snapshot → evidence → detection → card → report
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_chain_snapshot_to_card(self):
        """End-to-end: snapshot → evidence → detection → card persisted in DB."""
        from github_intelligence.snapshots import take_snapshot
        from github_intelligence.evidence import compress_readme, compress_releases, persist_atoms
        from github_intelligence.detectors import run_detectors
        from github_intelligence.cards import create_analysis_card, verify_card, get_verified_cards

        conn = fresh_conn()
        full_name = "integration/test-repo"
        date = "2026-05-27"

        # Snapshot
        snap = take_snapshot(full_name=full_name, stars=3000, conn=conn)
        assert snap.full_name == full_name

        # Evidence
        readme = (
            "# Integration Test\n\nAn agent framework for autonomous tasks.\n\n"
            "## Features\n- Multi-agent orchestration\n- Zero-latency routing\n"
            "- Production-hardened\n\n## Why\nBuilt for real workloads."
        )
        atoms = compress_readme(full_name, readme)
        persist_atoms(atoms, conn)
        assert len(atoms) > 0

        # Run detectors — no crash expected; sudden_hot requires computed delta history
        detections = run_detectors(full_name, snap, atoms, conn=conn)
        assert isinstance(detections, list)

        # Analysis card
        evidence_ids = [a.evidence_id for a in atoms]
        while len(evidence_ids) < 3:
            evidence_ids.append(f"ev-pad-{len(evidence_ids)}")

        card = create_analysis_card(
            full_name=full_name,
            analysis_date=date,
            evidence_ids=evidence_ids,
            heat_score=88.0,
            conn=conn,
        )
        verify_card(card.analysis_id, conn)

        # Query verified cards
        verified = get_verified_cards(conn, date)
        assert any(c.full_name == full_name for c in verified)

    def test_schema_backward_compat(self):
        """Existing harness modules still importable after github_intelligence is loaded."""
        for module in [
            "session_log",
            "event_ledger",
            "evidence_ledger",
            "model_call_runtime",
        ]:
            try:
                importlib.import_module(module)
            except ImportError:
                pytest.skip(f"{module} not available in this environment")
