"""Tests for social_account_registry.py

Covers:
  - normalize_handle: @-strip, URL extraction, case folding
  - ensure_registry_columns: adds 'status' idempotently
  - compute_snapshot_deltas: 1h/6h/24h delta + velocity_score
  - social_link_type: product detection + existing types
  - social_materialize_links: regex correctly extracts URLs from text
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "harness" / "lib"
SCRIPTS = ROOT / "harness" / "scripts"
for p in (str(LIB), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from social_account_registry import (
    SocialAccountRegistry,
    compute_snapshot_deltas,
    ensure_registry_columns,
    normalize_handle,
)


# ---------------------------------------------------------------------------
# normalize_handle
# ---------------------------------------------------------------------------


def test_normalize_handle_strips_at():
    assert normalize_handle("@karpathy") == "karpathy"


def test_normalize_handle_lowercases():
    assert normalize_handle("KARPATHY") == "karpathy"


def test_normalize_handle_at_and_case():
    assert normalize_handle("@KARPATHY") == "karpathy"


def test_normalize_handle_x_url():
    assert normalize_handle("https://x.com/karpathy") == "karpathy"


def test_normalize_handle_x_url_with_path():
    assert normalize_handle("https://x.com/karpathy/status/123") == "karpathy"


def test_normalize_handle_twitter_url():
    assert normalize_handle("https://twitter.com/ylecun?lang=en") == "ylecun"


def test_normalize_handle_www_prefix():
    assert normalize_handle("https://www.x.com/sama") == "sama"


def test_normalize_handle_plain():
    assert normalize_handle("karpathy") == "karpathy"


def test_normalize_handle_whitespace():
    assert normalize_handle("  lecun  ") == "lecun"


def test_normalize_handle_empty():
    assert normalize_handle("") == ""


def test_normalize_handle_url_case_folded():
    assert normalize_handle("https://x.com/SAMA") == "sama"


# ---------------------------------------------------------------------------
# ensure_registry_columns
# ---------------------------------------------------------------------------


def _make_accounts_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE social_accounts (
            handle TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            imported_at TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO social_accounts (handle) VALUES ('karpathy');
    """)
    conn.commit()
    return conn


def test_ensure_registry_columns_adds_status():
    conn = _make_accounts_db()
    cols_before = {r[1] for r in conn.execute("PRAGMA table_info(social_accounts)").fetchall()}
    assert "status" not in cols_before

    ensure_registry_columns(conn)

    cols_after = {r[1] for r in conn.execute("PRAGMA table_info(social_accounts)").fetchall()}
    assert "status" in cols_after


def test_ensure_registry_columns_idempotent():
    conn = _make_accounts_db()
    ensure_registry_columns(conn)
    # Must not raise on second call
    ensure_registry_columns(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(social_accounts)").fetchall()}
    assert "status" in cols


def test_ensure_registry_columns_default_active():
    conn = _make_accounts_db()
    ensure_registry_columns(conn)
    row = conn.execute("SELECT status FROM social_accounts WHERE handle='karpathy'").fetchone()
    assert row[0] == "active"


def test_ensure_registry_columns_no_table_is_noop():
    conn = sqlite3.connect(":memory:")
    # Should not raise even if table absent
    ensure_registry_columns(conn)


# ---------------------------------------------------------------------------
# compute_snapshot_deltas
# ---------------------------------------------------------------------------

_SNAPSHOT_SCHEMA = """
CREATE TABLE social_post_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    reply_count INTEGER NOT NULL DEFAULT 0,
    repost_count INTEGER NOT NULL DEFAULT 0,
    like_count INTEGER NOT NULL DEFAULT 0,
    view_count INTEGER,
    engagement_delta_1h INTEGER NOT NULL DEFAULT 0,
    engagement_delta_6h INTEGER NOT NULL DEFAULT 0,
    engagement_delta_24h INTEGER NOT NULL DEFAULT 0,
    velocity_score REAL NOT NULL DEFAULT 0.0,
    snapshot_at TEXT NOT NULL,
    UNIQUE(post_id, snapshot_at)
);
"""


def _ts(hours_ago: float, base: str = "2026-05-30T12:00:00Z") -> str:
    base_dt = dt.datetime.fromisoformat(base.replace("Z", "+00:00"))
    return (base_dt - dt.timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


NOW = "2026-05-30T12:00:00Z"


def test_compute_snapshot_deltas_no_history():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SNAPSHOT_SCHEMA)
    d1h, d6h, d24h, vel = compute_snapshot_deltas(conn, "post1", 10, 5, 20, None, NOW)
    assert d1h == 0
    assert d6h == 0
    assert d24h == 0
    assert vel == 0.0


def test_compute_snapshot_deltas_1h_delta():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SNAPSHOT_SCHEMA)
    # insert a snapshot from 2h ago (so it's within 6h and 24h windows but not in 1h)
    conn.execute(
        "INSERT INTO social_post_snapshots "
        "(post_id, reply_count, repost_count, like_count, view_count, snapshot_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("post1", 5, 2, 10, None, _ts(2.0)),
    )
    conn.commit()
    # current: 10+5+20 = 35, old (2h ago): 5+2+10 = 17
    d1h, d6h, d24h, vel = compute_snapshot_deltas(conn, "post1", 10, 5, 20, None, NOW)
    assert d1h == 0, "2h-old snapshot shouldn't count for 1h delta"
    assert d6h == 35 - 17  # 18
    assert d24h == 35 - 17  # 18


def test_compute_snapshot_deltas_with_view_count():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SNAPSHOT_SCHEMA)
    # old snapshot 0.5h ago: reply=5, repost=2, like=10, view=100
    # eng_old = 5+2+10 + floor(100*0.05) = 17+5 = 22
    conn.execute(
        "INSERT INTO social_post_snapshots "
        "(post_id, reply_count, repost_count, like_count, view_count, snapshot_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("post2", 5, 2, 10, 100, _ts(0.5)),
    )
    conn.commit()
    # current: reply=10, repost=5, like=20, view=200
    # eng_cur = 10+5+20+10 = 45
    d1h, _d6h, _d24h, vel = compute_snapshot_deltas(conn, "post2", 10, 5, 20, 200, NOW)
    assert d1h == 45 - 22  # 23
    assert vel > 0.0


def test_compute_snapshot_deltas_velocity_capped_at_1():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SNAPSHOT_SCHEMA)
    # tiny old, large current → velocity should cap at 1.0
    conn.execute(
        "INSERT INTO social_post_snapshots "
        "(post_id, reply_count, repost_count, like_count, view_count, snapshot_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("post3", 0, 0, 0, None, _ts(0.5)),
    )
    conn.commit()
    _d1h, _d6h, _d24h, vel = compute_snapshot_deltas(conn, "post3", 1000, 500, 2000, None, NOW)
    assert vel <= 1.0


def test_compute_snapshot_deltas_delta_never_negative():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SNAPSHOT_SCHEMA)
    # old snapshot has MORE engagement (edge case: metrics went down)
    conn.execute(
        "INSERT INTO social_post_snapshots "
        "(post_id, reply_count, repost_count, like_count, view_count, snapshot_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("post4", 100, 50, 200, None, _ts(0.5)),
    )
    conn.commit()
    d1h, _d6h, _d24h, _vel = compute_snapshot_deltas(conn, "post4", 5, 2, 10, None, NOW)
    assert d1h == 0, "delta must not be negative"


# ---------------------------------------------------------------------------
# social_link_type (imported from tech_hotspot_radar)
# ---------------------------------------------------------------------------


def _load_radar():
    import importlib.util, types
    spec = importlib.util.spec_from_file_location(
        "tech_hotspot_radar_test",
        str(SCRIPTS / "tech_hotspot_radar.py"),
    )
    mod = types.ModuleType("tech_hotspot_radar_test")
    mod.__file__ = str(SCRIPTS / "tech_hotspot_radar.py")
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_social_link_type_github():
    mod = _load_radar()
    assert mod.social_link_type("https://github.com/vllm-project/vllm") == "github_repo"


def test_social_link_type_arxiv():
    mod = _load_radar()
    assert mod.social_link_type("https://arxiv.org/abs/2406.12345") == "arxiv"


def test_social_link_type_youtube():
    mod = _load_radar()
    assert mod.social_link_type("https://youtube.com/watch?v=abc123") == "youtube"


def test_social_link_type_model_card():
    mod = _load_radar()
    assert mod.social_link_type("https://huggingface.co/meta-llama/Llama-3") == "model_card"


def test_social_link_type_product_openai_api():
    mod = _load_radar()
    assert mod.social_link_type("https://openai.com/api") == "product"


def test_social_link_type_product_anthropic_claude():
    mod = _load_radar()
    assert mod.social_link_type("https://anthropic.com/claude") == "product"


def test_social_link_type_product_replicate():
    mod = _load_radar()
    assert mod.social_link_type("https://replicate.com/stability-ai/sdxl") == "product"


def test_social_link_type_blog():
    mod = _load_radar()
    assert mod.social_link_type("https://karpathy.medium.com/some-post") == "blog"


def test_social_link_type_paper_pdf():
    mod = _load_radar()
    assert mod.social_link_type("https://some.edu/paper.pdf") == "paper"


def test_social_link_type_unknown():
    mod = _load_radar()
    assert mod.social_link_type("https://example.com/random") == "unknown"


# ---------------------------------------------------------------------------
# social_materialize_links: regex extracts URLs from text correctly
# ---------------------------------------------------------------------------


def test_social_materialize_links_extracts_github_url(tmp_path):
    """social_materialize_links must extract URLs from post text and tag them."""
    mod = _load_radar()
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(mod.SCHEMA_SQL)
    conn.execute(
        "INSERT INTO social_accounts (handle, tier, imported_at) VALUES ('testuser','tier1','2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO social_posts "
        "(post_id, author_handle, text, post_url, urls, fetched_at) "
        "VALUES ('p1', 'testuser', 'Check out https://github.com/huggingface/transformers great lib', "
        "'https://x.com/testuser/status/1', '', '2026-05-30T00:00:00Z')"
    )
    conn.commit()
    inserted = mod.social_materialize_links(conn)
    assert inserted >= 1
    row = conn.execute("SELECT link_type, dispatch_status FROM social_links WHERE post_id='p1'").fetchone()
    assert row is not None
    assert row[0] == "github_repo"
    assert row[1] == "pending"
    conn.close()


def test_social_materialize_links_extracts_arxiv_from_text(tmp_path):
    mod = _load_radar()
    db = tmp_path / "test2.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(mod.SCHEMA_SQL)
    conn.execute(
        "INSERT INTO social_accounts (handle, tier, imported_at) VALUES ('testuser','tier1','2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO social_posts "
        "(post_id, author_handle, text, post_url, urls, fetched_at) "
        "VALUES ('p2', 'testuser', 'New paper https://arxiv.org/abs/2406.99999 on agents', "
        "'https://x.com/testuser/status/2', '', '2026-05-30T00:00:00Z')"
    )
    conn.commit()
    mod.social_materialize_links(conn)
    row = conn.execute("SELECT link_type FROM social_links WHERE post_id='p2'").fetchone()
    assert row is not None
    assert row[0] == "arxiv"
    conn.close()


# ---------------------------------------------------------------------------
# SocialAccountRegistry
# ---------------------------------------------------------------------------


def _make_registry() -> tuple[sqlite3.Connection, SocialAccountRegistry]:
    conn = sqlite3.connect(":memory:")
    reg = SocialAccountRegistry(conn)
    reg.ensure_schema()
    return conn, reg


def test_registry_upsert_normalize_handle():
    _, reg = _make_registry()
    h = reg.upsert("@Karpathy", category="research", tier="tier1")
    assert h == "karpathy"
    acct = reg.get("karpathy")
    assert acct is not None
    assert acct["handle"] == "karpathy"
    assert acct["category"] == "research"
    assert acct["tier"] == "tier1"


def test_registry_upsert_url_handle():
    _, reg = _make_registry()
    h = reg.upsert("https://x.com/ylecun", tier="tier1", weight=1.5)
    assert h == "ylecun"
    acct = reg.get("ylecun")
    assert acct["weight"] == 1.5


def test_registry_upsert_updates_existing():
    _, reg = _make_registry()
    reg.upsert("sama", category="ai_lab", tier="tier1")
    reg.upsert("sama", category="research", tier="tier2")
    acct = reg.get("sama")
    assert acct["category"] == "research"
    assert acct["tier"] == "tier2"


def test_registry_upsert_role_profile_scan_policy():
    _, reg = _make_registry()
    reg.upsert(
        "karpathy",
        role_profile={"focus": "ml_research"},
        scan_policy={"max_posts": 5, "freq_hours": 6},
    )
    import json
    acct = reg.get("karpathy")
    assert json.loads(acct["role_profile_json"]) == {"focus": "ml_research"}
    assert json.loads(acct["scan_policy_json"])["max_posts"] == 5


def test_registry_upsert_status():
    _, reg = _make_registry()
    reg.upsert("karpathy", status="active")
    assert reg.get("karpathy")["status"] == "active"


def test_registry_set_status():
    _, reg = _make_registry()
    reg.upsert("karpathy")
    reg.set_status("karpathy", "suspended")
    assert reg.get("karpathy")["status"] == "suspended"


def test_registry_get_returns_none_for_missing():
    _, reg = _make_registry()
    assert reg.get("nonexistent_user_xyz") is None


def test_registry_list_enabled():
    _, reg = _make_registry()
    reg.upsert("user_a", tier="tier1", enabled=True)
    reg.upsert("user_b", tier="tier2", enabled=True)
    reg.upsert("user_c", tier="tier1", enabled=False)
    enabled = reg.list_enabled()
    handles = {a["handle"] for a in enabled}
    assert "user_a" in handles
    assert "user_b" in handles
    assert "user_c" not in handles


def test_registry_list_enabled_filter_tier():
    _, reg = _make_registry()
    reg.upsert("t1_a", tier="tier1")
    reg.upsert("t1_b", tier="tier1")
    reg.upsert("t2_a", tier="tier2")
    tier1 = reg.list_enabled(tier="tier1")
    assert all(a["tier"] == "tier1" for a in tier1)
    assert len(tier1) == 2


def test_registry_list_enabled_filter_category():
    _, reg = _make_registry()
    reg.upsert("researcher", category="research")
    reg.upsert("founder", category="founder")
    research = reg.list_enabled(category="research")
    assert len(research) == 1
    assert research[0]["handle"] == "researcher"


def test_registry_ensure_schema_idempotent():
    conn, reg = _make_registry()
    reg.ensure_schema()  # second call must not raise
    cols = {r[1] for r in conn.execute("PRAGMA table_info(social_accounts)").fetchall()}
    for required in ("handle", "category", "tier", "weight", "role_profile_json",
                     "scan_policy_json", "status", "enabled"):
        assert required in cols, f"column {required!r} missing"


def test_registry_import_manual_string_handles():
    _, reg = _make_registry()
    imported = reg.import_manual(
        ["@Karpathy", "https://x.com/ylecun", "  sama  "],
        category="research",
        tier="tier1",
        collection_backend="manual_curated",
    )
    assert sorted(imported) == ["karpathy", "sama", "ylecun"]
    assert reg.get("karpathy")["collection_backend"] == "manual_curated"
    assert reg.get("ylecun")["category"] == "research"


def test_registry_import_manual_dict_entries():
    _, reg = _make_registry()
    entries = [
        {"handle": "yann", "category": "ai_lab", "tier": "tier1", "weight": 2.0},
        {"handle": "@sama", "tier": "tier1"},
    ]
    imported = reg.import_manual(entries)
    assert "yann" in imported
    assert "sama" in imported
    assert reg.get("yann")["weight"] == 2.0
    assert reg.get("yann")["category"] == "ai_lab"


def test_registry_import_manual_empty():
    _, reg = _make_registry()
    assert reg.import_manual([]) == []


def test_registry_import_manual_deduplicates_normalized():
    _, reg = _make_registry()
    reg.import_manual(["@KARPATHY", "karpathy", "https://x.com/karpathy"])
    rows = reg.list_enabled()
    handles = [r["handle"] for r in rows]
    assert handles.count("karpathy") == 1
