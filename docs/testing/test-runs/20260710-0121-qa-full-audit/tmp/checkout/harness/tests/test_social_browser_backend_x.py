from __future__ import annotations

import random
import sqlite3

import pytest

from social_browser_backend_x.backend_selector import BackendSelector, ProbeResult, TIER_ORDER
from social_browser_backend_x.dedup_queue import DedupQueue
from social_browser_backend_x.hard_blocker_guard import CallableResolver, HardBlockerGuard
from social_browser_backend_x.post_extractor import POST_RECORD_FIELDS, PostExtractor
from social_browser_backend_x.ratelimiter import (
    FAILURE_TRIGGERS,
    RateLimitExceeded,
    RateLimiter,
    backoff_seconds,
    jitter_seconds,
    tier_cooldown,
    tier_scan_interval,
)
from social_browser_backend_x.schema import (
    BACKEND_BROWSER_AGENT,
    BACKEND_MANUAL_CURATED,
    BACKEND_RSS_PUBLIC,
    PostRecord,
    ensure_schema_safe,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE social_posts ("
        "post_id TEXT, author_handle TEXT, text TEXT, created_at TEXT, "
        "post_url TEXT, reply_count INTEGER, repost_count INTEGER, "
        "like_count INTEGER, view_count INTEGER, urls TEXT)"
    )
    ensure_schema_safe(conn)
    return conn


def test_cross_c1_c5_post_record_contract_has_11_business_fields() -> None:
    assert POST_RECORD_FIELDS == (
        "post_id",
        "author_handle",
        "text",
        "created_at",
        "post_url",
        "reply_count",
        "repost_count",
        "like_count",
        "view_count",
        "urls",
        "dom_hash",
    )
    rec = PostRecord(
        post_id="1790012345678901234",
        author_handle="karpathy",
        text="KV cache compression chapter draft",
        created_at="2026-05-28T16:42:11.000Z",
        post_url="https://x.com/karpathy/status/1790012345678901234",
        reply_count=312,
        repost_count=1240,
        like_count=9873,
        view_count=521004,
        urls="",
        dom_hash="abc123",
        collection_backend=BACKEND_BROWSER_AGENT,
    )
    assert set(POST_RECORD_FIELDS).issubset(rec.to_row())
    rec.validate_backend()


def test_cross_c1_c5_rate_limiter_exposes_all_5_knobs() -> None:
    knobs = RateLimiter.knobs()
    assert knobs["per_account_cooldown_seconds"] == {"tier1": 180, "tier2": 600}
    assert knobs["global_concurrency"] == 1
    assert knobs["jitter_range_seconds"] == [5, 15]
    assert knobs["exponential_backoff"] == {"base": 2, "max_seconds": 300}
    assert knobs["tier_frequency_separation"] == {
        "tier1_seconds": 6 * 3600,
        "tier2_seconds": 24 * 3600,
    }


def test_cross_c1_c5_failure_modes_are_explicit_and_isolated() -> None:
    assert FAILURE_TRIGGERS == {"login_fail", "rate_429", "parse_fail"}
    assert backoff_seconds(1) == 2.0
    assert backoff_seconds(9) == 300.0
    assert tier_cooldown(1) == 180
    assert tier_scan_interval(2) == 24 * 3600
    assert 5 <= jitter_seconds(random.Random(7)) <= 15

    limiter = RateLimiter(clock=lambda: 100.0)
    with limiter.acquire("acct-a", 1, block=False):
        pass
    with pytest.raises(RateLimitExceeded):
        limiter.acquire("acct-a", 1, block=False)

    extracted = PostExtractor().extract("")
    assert extracted.parse_ok is False
    assert "post_id" in extracted.missing_fields

    with pytest.raises(ValueError):
        PostRecord("1", "a", "t", None, "", collection_backend="bad").validate_backend()


def test_cross_c1_c5_dedup_and_schema_round_trip() -> None:
    conn = _conn()
    queue = DedupQueue(conn)
    rec = PostRecord(
        post_id="1790012345678901234",
        author_handle="karpathy",
        text="same text",
        created_at="2026-05-28T16:42:11+00:00",
        post_url="https://x.com/karpathy/status/1790012345678901234",
        collection_backend=BACKEND_BROWSER_AGENT,
    )
    first, _stored = queue.record_seen(rec, 1)
    second = queue.check(rec)
    assert first.is_duplicate is False
    assert second.is_duplicate is True
    assert second.key_kind == "url"


def test_cross_c1_c5_three_fallback_paths() -> None:
    guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: False,
    )
    auto_result = BackendSelector(guard=guard).select("auto")
    assert auto_result.selected == BACKEND_RSS_PUBLIC
    assert auto_result.walked[0].backend == BACKEND_BROWSER_AGENT
    assert auto_result.walked[0].reason == "hard_blocker_unmet"

    explicit_result = BackendSelector(guard=guard).select("browser")
    assert explicit_result.selected == BACKEND_RSS_PUBLIC
    assert explicit_result.fallback_from_explicit is True

    probes = {
        TIER_ORDER[0]: lambda: ProbeResult(TIER_ORDER[0], False, "disabled"),
        TIER_ORDER[1]: lambda: ProbeResult(TIER_ORDER[1], False, "feed_unavailable"),
        TIER_ORDER[2]: lambda: ProbeResult(TIER_ORDER[2], True, "manual_ready"),
        TIER_ORDER[3]: lambda: ProbeResult(TIER_ORDER[3], False, "not_enabled"),
    }
    manual_result = BackendSelector(guard=guard, probes=probes).select("auto")
    assert manual_result.selected == BACKEND_MANUAL_CURATED
