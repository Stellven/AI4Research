"""Tests for P1 semantic viewpoint propagation engine.

Covers:
- social_compute_hot_score: viewpoint_strength, technical_depth, noise penalty,
  single_amplifier_risk
- social_cluster_posts: lifecycle, source_mix, summary, why_it_matters
- social_materialize_propagation_chains: single_amplifier detection
- schema migration: new columns present after ensure_social_columns
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "scripts" / "tech_hotspot_radar.py"


def _load_ns() -> dict:
    ns: dict = {"__file__": str(SCRIPT), "__name__": "tech_hotspot_radar_test"}
    code = compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec")
    exec(code, ns)
    return ns


@pytest.fixture(scope="module")
def ns():
    return _load_ns()


# ---------------------------------------------------------------------------
# social_compute_hot_score
# ---------------------------------------------------------------------------

class TestSocialHotScore:
    def test_viewpoint_strength_raises_score(self, ns):
        fn = ns["social_compute_hot_score"]
        base = fn(account_weight=0.5, semantic_importance=0.5, novelty=0.5)
        with_vp = fn(account_weight=0.5, semantic_importance=0.5, novelty=0.5,
                     viewpoint_strength=1.0)
        assert with_vp > base

    def test_technical_depth_raises_score(self, ns):
        fn = ns["social_compute_hot_score"]
        base = fn(account_weight=0.5, semantic_importance=0.5)
        with_depth = fn(account_weight=0.5, semantic_importance=0.5, technical_depth=1.0)
        assert with_depth > base

    def test_noise_signal_penalizes_score(self, ns):
        fn = ns["social_compute_hot_score"]
        normal = fn(account_weight=1.0, semantic_importance=0.8, engagement_velocity=0.9)
        noisy = fn(account_weight=1.0, semantic_importance=0.8, engagement_velocity=0.9,
                   noise_signal=True)
        assert noisy < normal
        assert noisy == pytest.approx(normal * 0.4, rel=1e-3)

    def test_single_amplifier_risk_penalizes_score(self, ns):
        fn = ns["social_compute_hot_score"]
        normal = fn(account_weight=1.0, semantic_importance=0.8, viewpoint_strength=0.9)
        risky = fn(account_weight=1.0, semantic_importance=0.8, viewpoint_strength=0.9,
                   single_amplifier_risk=True)
        assert risky < normal
        assert risky == pytest.approx(normal * 0.4, rel=1e-3)

    def test_both_penalties_applied_once(self, ns):
        """Both noise_signal AND single_amplifier_risk should still give 0.4x."""
        fn = ns["social_compute_hot_score"]
        normal = fn(account_weight=1.0, semantic_importance=0.6)
        both = fn(account_weight=1.0, semantic_importance=0.6,
                  noise_signal=True, single_amplifier_risk=True)
        assert both == pytest.approx(normal * 0.4, rel=1e-3)

    def test_all_weights_sum_without_penalty(self, ns):
        """Max inputs without penalty should give ≤ 1.0."""
        fn = ns["social_compute_hot_score"]
        score = fn(
            engagement_velocity=1.0, account_weight=1.0, semantic_importance=1.0,
            network_spread=1.0, novelty=1.0, cross_source_signal=1.0,
            viewpoint_strength=1.0, technical_depth=1.0,
        )
        assert 0.99 <= score <= 1.0

    def test_zero_account_weight_returns_zero(self, ns):
        """All explicit zeros should yield 0.0 (no default account_weight boost)."""
        fn = ns["social_compute_hot_score"]
        assert fn(account_weight=0.0) == 0.0


# ---------------------------------------------------------------------------
# social_cluster_posts: lifecycle, source_mix, summary, why_it_matters
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path, ns: dict) -> sqlite3.Connection:
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(ns["SCHEMA_SQL"])
    ns["ensure_social_columns"](conn)
    return conn


def _insert_account(conn, handle, tier="tier1", category="research", weight=1.5):
    conn.execute(
        "INSERT OR REPLACE INTO social_accounts "
        "(handle, raw_handle, account_id, platform, display_name, category, tier, "
        "enabled, weight, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (handle, handle, "", "x", handle, category, tier, 1, weight, "2026-05-30T00:00:00Z"),
    )
    conn.commit()


def _insert_post(conn, post_id, handle, text, urls="", tier="tier1", category="research"):
    conn.execute(
        "INSERT OR IGNORE INTO social_posts "
        "(post_id, author_handle, author_category, author_tier, post_url, text, "
        "created_at, lang, reply_count, repost_count, quote_count, like_count, "
        "view_count, bookmarks, media_urls, mentioned_handles, urls, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (post_id, handle, category, tier,
         f"https://x.com/{handle}/status/1", text,
         "2026-05-30T10:00:00Z", "en",
         5, 10, 2, 50, 1000, 3, "", "", urls,
         "2026-05-30T10:00:00Z"),
    )
    conn.commit()


class TestClusterLifecycle:
    def test_new_single_post_cluster_lifecycle(self, tmp_path, ns):
        """A single tier2 post with no tier1 actor should be 'emerging'."""
        conn = _make_db(tmp_path, ns)
        _insert_account(conn, "user_a", tier="tier2")
        _insert_post(conn, "p1", "user_a", "Check out https://github.com/openai/gpt5",
                     tier="tier2", category="community")
        created = ns["social_cluster_posts"](conn)
        assert created >= 1
        row = conn.execute(
            "SELECT lifecycle FROM social_clusters WHERE cluster_key LIKE '%openai/gpt5%'"
        ).fetchone()
        assert row is not None
        # tier2 single post → emerging; tier1 single post → heating (both valid)
        assert row["lifecycle"] in ("emerging", "heating")

    def test_multi_tier1_cluster_is_heating_or_peaking(self, tmp_path, ns):
        conn = _make_db(tmp_path, ns)
        for i in range(3):
            handle = f"expert_{i}"
            _insert_account(conn, handle, tier="tier1", category="ai_lab")
            _insert_post(conn, f"p{i}", handle,
                         "Amazing breakthrough https://github.com/deepmind/gemini-ultra")
        created = ns["social_cluster_posts"](conn)
        assert created >= 1
        row = conn.execute(
            "SELECT lifecycle FROM social_clusters WHERE cluster_key LIKE '%deepmind/gemini-ultra%'"
        ).fetchone()
        assert row is not None
        assert row["lifecycle"] in ("heating", "peaking")

    def test_source_mix_reflects_account_categories(self, tmp_path, ns):
        conn = _make_db(tmp_path, ns)
        _insert_account(conn, "researcher_1", category="paper_research")
        _insert_account(conn, "lab_1", category="ai_lab", tier="tier2")
        # Pass matching category to social_posts rows
        _insert_post(conn, "sm1", "researcher_1",
                     "Our new paper https://arxiv.org/abs/2501.12345",
                     category="paper_research")
        _insert_post(conn, "sm2", "lab_1",
                     "interesting paper https://arxiv.org/abs/2501.12345",
                     tier="tier2", category="ai_lab")
        ns["social_cluster_posts"](conn)
        row = conn.execute(
            "SELECT source_mix FROM social_clusters WHERE cluster_key LIKE '%2501.12345%'"
        ).fetchone()
        assert row is not None
        mix = row["source_mix"]
        assert "ai_lab" in mix or "paper_research" in mix

    def test_summary_and_why_it_matters_populated(self, tmp_path, ns):
        conn = _make_db(tmp_path, ns)
        _insert_account(conn, "big_name", tier="tier1", category="core_leader")
        _insert_post(conn, "bx1", "big_name",
                     "The future of agents https://github.com/microsoft/autogen")
        ns["social_cluster_posts"](conn)
        row = conn.execute(
            "SELECT summary, why_it_matters FROM social_clusters "
            "WHERE cluster_key LIKE '%microsoft/autogen%'"
        ).fetchone()
        assert row is not None
        assert len(row["summary"]) > 5
        assert len(row["why_it_matters"]) > 5

    def test_schema_has_new_columns(self, tmp_path, ns):
        conn = _make_db(tmp_path, ns)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(social_clusters)").fetchall()}
        assert "lifecycle" in cols
        assert "source_mix" in cols
        assert "summary" in cols
        assert "why_it_matters" in cols


# ---------------------------------------------------------------------------
# single_amplifier detection in propagation chains
# ---------------------------------------------------------------------------

class TestPropagationChains:
    def test_single_author_cluster_flagged_as_single_amplifier(self, tmp_path, ns):
        conn = _make_db(tmp_path, ns)
        _insert_account(conn, "solo_voice", tier="tier1")
        _insert_post(conn, "sa1", "solo_voice",
                     "New model https://github.com/solo/project breakthrough")
        ns["social_cluster_posts"](conn)
        ns["social_materialize_propagation_chains"](conn)
        row = conn.execute(
            "SELECT spread_pattern, hype_risk FROM propagation_chains "
            "JOIN social_clusters USING (cluster_id) "
            "WHERE social_clusters.cluster_key LIKE '%solo/project%'"
        ).fetchone()
        assert row is not None
        assert row["spread_pattern"] == "single_amplifier"
        # single_amplifier + tier1 → high hype_risk
        assert row["hype_risk"] == "high"

    def test_multi_source_cluster_gets_low_hype_risk(self, tmp_path, ns):
        conn = _make_db(tmp_path, ns)
        categories = ["research", "ai_lab", "open_source"]
        for i, cat in enumerate(categories):
            handle = f"voice_{i}"
            _insert_account(conn, handle, tier="tier2", category=cat)
            # Pass category to the post row so propagation_chains sees 3 distinct categories
            _insert_post(conn, f"mv{i}", handle,
                         f"Great work on https://github.com/multi/project from {cat}",
                         tier="tier2", category=cat)
        ns["social_cluster_posts"](conn)
        ns["social_materialize_propagation_chains"](conn)
        row = conn.execute(
            "SELECT spread_pattern, hype_risk FROM propagation_chains "
            "JOIN social_clusters USING (cluster_id) "
            "WHERE social_clusters.cluster_key LIKE '%multi/project%'"
        ).fetchone()
        assert row is not None
        assert row["spread_pattern"] == "multi_source_resonance"
        assert row["hype_risk"] == "low"


# ---------------------------------------------------------------------------
# Migration: existing DB gets new columns
# ---------------------------------------------------------------------------

class TestSchemaMigration:
    def test_migration_adds_lifecycle_to_existing_db(self, tmp_path, ns):
        db_path = tmp_path / "legacy.sqlite"
        conn_legacy = sqlite3.connect(str(db_path))
        # Create old-style social_clusters without new columns
        conn_legacy.executescript("""
            CREATE TABLE IF NOT EXISTS social_accounts (
                handle TEXT PRIMARY KEY, raw_handle TEXT NOT NULL DEFAULT '',
                account_id TEXT NOT NULL DEFAULT '', platform TEXT NOT NULL DEFAULT 'x',
                display_name TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
                tier TEXT NOT NULL DEFAULT 'tier2', enabled INTEGER NOT NULL DEFAULT 1,
                weight REAL NOT NULL DEFAULT 1.0, imported_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS social_post_snapshots (
                post_id TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS social_clusters (
                cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_key TEXT NOT NULL,
                cluster_type TEXT NOT NULL DEFAULT 'weak',
                window_start TEXT NOT NULL DEFAULT '',
                window_end TEXT NOT NULL DEFAULT '',
                post_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT ''
            );
        """)
        conn_legacy.commit()
        conn_legacy.close()

        conn = sqlite3.connect(str(db_path))
        ns["ensure_social_columns"](conn)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(social_clusters)").fetchall()}
        conn.close()

        assert "lifecycle" in cols
        assert "source_mix" in cols
        assert "summary" in cols
        assert "why_it_matters" in cols


# ---------------------------------------------------------------------------
# semantic extract completeness
# ---------------------------------------------------------------------------

class TestSemanticExtract:
    def test_extract_returns_all_required_fields(self, ns):
        fn = ns["social_semantic_extract_from_post"]
        result = fn(
            "Breakthrough: new agent framework https://github.com/openai/agents "
            "— replaces MCP memory inference triton",
            "https://github.com/openai/agents",
        )
        required = [
            "signal_type", "event_type", "stance", "claim_summary",
            "entities", "linked_assets", "technical_keywords",
            "local_importance_score", "novelty_score", "technical_depth_score",
        ]
        for field in required:
            assert field in result, f"missing field: {field}"

    def test_noise_post_gets_low_scores(self, ns):
        fn = ns["social_semantic_extract_from_post"]
        result = fn("Good morning! Hope everyone is having a great day 😊")
        assert result["signal_type"] in ("noise", "market_signal")
        assert result["local_importance_score"] <= 0.3

    def test_bullish_stance_detected(self, ns):
        fn = ns["social_semantic_extract_from_post"]
        result = fn("Huge breakthrough in LLM inference — this is really important!")
        assert result["stance"] == "bullish"

    def test_warning_stance_detected(self, ns):
        fn = ns["social_semantic_extract_from_post"]
        result = fn("Warning: this model has serious safety risks and dangers")
        assert result["stance"] == "warning"
