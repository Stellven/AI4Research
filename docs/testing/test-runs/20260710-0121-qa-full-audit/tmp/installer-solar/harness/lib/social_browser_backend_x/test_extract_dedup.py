"""Unit tests for C3 — PostExtractor + DedupQueue.

Acceptance map:
  - A-C3-1 PostExtractor extracts all 11 post_record fields from DOM
  - A-C3-2 Missing fields filled with N/A placeholder (not None / empty string)
  - A-C3-3 DedupQueue 24h window uses canonical URL when available
  - A-C3-4 DedupQueue falls back to sha256(handle+text+time) when no URL
  - A-C3-5 URL conflict: sha256 same but URL different -> sha256 wins,
            URL takes latest

The tests use the C2 mock_browser_fixture so the extractor exercises
the exact DOM shape the production lease will deliver.
"""
from __future__ import annotations

import re
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from .dedup_keys_table import lookup_dedup_key
from .dedup_queue import (
    DEFAULT_WINDOW,
    DEFAULT_WINDOW_HOURS,
    DedupQueue,
    DedupVerdict,
    canonical_url,
    derive_keys,
    sha256_fallback_key,
)
from .mock_browser_fixture import PROFILE_FIXTURES, MockBrowserBackend
from .post_extractor import (
    N_A,
    POST_RECORD_FIELDS,
    ExtractionResult,
    PostExtractor,
)
from .schema import PostRecord


def _bootstrap_social_posts(conn: sqlite3.Connection) -> None:
    """Minimal social_posts table so dedup_key FK has a target."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS social_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT,
            author_handle TEXT,
            text TEXT,
            created_at TEXT,
            post_url TEXT
        );
        """
    )


# ---------------------------------------------------------------------------
# 1. PostExtractor — 11-field extraction (A-C3-1)
# ---------------------------------------------------------------------------


class TestPostExtractorFullExtraction(unittest.TestCase):
    """A-C3-1 — every fixture should yield all 11 business fields."""

    def setUp(self):
        self.extractor = PostExtractor()

    def test_field_names_count(self):
        # 11 business field names per S02 A2.
        self.assertEqual(len(POST_RECORD_FIELDS), 11)
        self.assertEqual(POST_RECORD_FIELDS[0], "post_id")
        self.assertEqual(POST_RECORD_FIELDS[-1], "dom_hash")

    def test_three_fixtures_all_extract_cleanly(self):
        for fixture in PROFILE_FIXTURES:
            with self.subTest(handle=fixture.handle):
                result = self.extractor.extract(fixture.html)
                self.assertTrue(result.parse_ok, fixture.handle)
                self.assertEqual(result.missing_fields, ())
                rec = result.record
                self.assertEqual(rec.author_handle, fixture.handle)
                self.assertTrue(rec.post_id.isdigit())
                self.assertIn("https://x.com/", rec.post_url)
                self.assertIn(rec.post_id, rec.post_url)
                self.assertEqual(rec.dom_hash, PostExtractor._hash_html(fixture.html))
                # All 13 record fields populated (11 business + 2 meta).
                self.assertEqual(rec.collection_backend, "browser_agent")
                self.assertIsNone(rec.screenshot_path)

    def test_karpathy_concrete_values(self):
        sample = next(f for f in PROFILE_FIXTURES if f.handle == "karpathy")
        rec = self.extractor.extract(sample.html).record
        self.assertEqual(rec.post_id, "1790012345678901234")
        self.assertEqual(rec.author_handle, "karpathy")
        self.assertIn("KV cache compression", rec.text)
        self.assertEqual(rec.created_at, "2026-05-28T16:42:11.000Z")
        self.assertEqual(rec.reply_count, 312)
        self.assertEqual(rec.repost_count, 1240)
        self.assertEqual(rec.like_count, 9873)
        self.assertEqual(rec.view_count, 521004)
        self.assertEqual(rec.urls, "")

    def test_unreasonable_metric_noise_is_ignored(self):
        html = """
        <article data-testid="tweet" data-tweet-id="1770123596121432351">
          <div data-testid="User-Name"><a href="/mustafasuleyman">@mustafasuleyman</a></div>
          <time datetime="2024-03-19T16:22:07.000Z"></time>
          <div data-testid="tweetText">Joining Microsoft AI.</div>
          <div data-testid="reply">9661736813914265</div>
          <div data-testid="retweet">2</div>
          <div data-testid="like">14</div>
        </article>
        """
        rec = self.extractor.extract(html, author_handle_hint="mustafasuleyman").record
        self.assertEqual(rec.reply_count, 0)
        self.assertEqual(rec.repost_count, 2)
        self.assertEqual(rec.like_count, 14)

    def test_links_extracted_from_tweet_text(self):
        sample = next(f for f in PROFILE_FIXTURES if f.handle == "jxmnop")
        rec = self.extractor.extract(sample.html).record
        self.assertIn("arxiv.org/abs/2603.21567", rec.urls)
        self.assertIn("github.com/jxmnop/repe-notes", rec.urls)

    def test_anthropic_single_link(self):
        sample = next(f for f in PROFILE_FIXTURES if f.handle == "AnthropicAI")
        rec = self.extractor.extract(sample.html).record
        self.assertIn("anthropic.com/research/prompt-cache-reliability", rec.urls)

    def test_extract_via_mock_backend_round_trip(self):
        """PostExtractor accepts the exact payload MockBrowserBackend yields."""
        backend = MockBrowserBackend()
        backend.open("https://x.com/karpathy")
        payload = backend.dom_extract()
        result = self.extractor.extract(payload["html"])
        self.assertTrue(result.parse_ok)
        self.assertEqual(result.record.dom_hash, payload["dom_hash"])


# ---------------------------------------------------------------------------
# 2. PostExtractor — missing fields → N/A placeholders (A-C3-2)
# ---------------------------------------------------------------------------


class TestPostExtractorPlaceholders(unittest.TestCase):
    """A-C3-2 — missing fields surface as N/A (not None / empty)."""

    def setUp(self):
        self.extractor = PostExtractor()

    def test_empty_html_returns_all_placeholders(self):
        result = self.extractor.extract("")
        self.assertFalse(result.parse_ok)
        rec = result.record
        self.assertEqual(rec.post_id, N_A)
        self.assertEqual(rec.author_handle, N_A)
        self.assertEqual(rec.text, N_A)
        self.assertEqual(rec.post_url, N_A)
        # All 10 string/optional business fields should be in missing_fields
        # (dom_hash is always computed → not missing).
        for name in POST_RECORD_FIELDS:
            if name == "dom_hash":
                self.assertNotIn(name, result.missing_fields)

    def test_partial_article_missing_metrics_sets_zero_and_no_placeholder_for_ints(self):
        """Metrics absent in DOM map to 0 (not 'N/A') because the schema
        types are int — see schema.PostRecord. The placeholder is for
        string-typed fields only."""
        html = (
            "<article data-testid='tweet' data-tweet-id='999'>"
            "<div data-testid='User-Name'><a href='/foo'><span>@foo</span></a></div>"
            "<div data-testid='tweetText'>Hello world</div>"
            "<time datetime='2026-05-28T10:00:00.000Z'>x</time>"
            "<a href='/foo/status/999'><time>10:00</time></a>"
            "</article>"
        )
        rec = self.extractor.extract(html).record
        self.assertEqual(rec.reply_count, 0)
        self.assertEqual(rec.repost_count, 0)
        self.assertEqual(rec.like_count, 0)
        self.assertIsNone(rec.view_count)  # nullable per schema
        self.assertEqual(rec.author_handle, "foo")

    def test_missing_handle_uses_hint(self):
        html = (
            "<article data-testid='tweet' data-tweet-id='42'>"
            "<div data-testid='tweetText'>orphan tweet</div>"
            "</article>"
        )
        rec = self.extractor.extract(html, author_handle_hint="@injected").record
        self.assertEqual(rec.author_handle, "injected")

    def test_missing_url_falls_back_to_na(self):
        html = (
            "<article data-testid='tweet'>"
            "<div data-testid='tweetText'>no id no url</div>"
            "</article>"
        )
        result = self.extractor.extract(html)
        self.assertFalse(result.parse_ok)
        self.assertEqual(result.record.post_url, N_A)
        self.assertEqual(result.record.post_id, N_A)
        self.assertIn("post_id", result.missing_fields)
        self.assertIn("post_url", result.missing_fields)

    def test_na_constant_is_string(self):
        # A-C3-2: must be string "N/A", never None or empty.
        self.assertEqual(N_A, "N/A")
        self.assertIsInstance(N_A, str)


# ---------------------------------------------------------------------------
# 3. DedupQueue — canonical URL wins (A-C3-3)
# ---------------------------------------------------------------------------


class TestDedupQueueCanonicalUrl(unittest.TestCase):
    """A-C3-3 — canonical URL is the primary dedup key inside the 24h window."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        _bootstrap_social_posts(self.conn)
        self.queue = DedupQueue(self.conn)

    def tearDown(self):
        self.conn.close()

    def _record(self, **overrides) -> PostRecord:
        defaults = dict(
            post_id="1790012345678901234",
            author_handle="karpathy",
            text="KV cache compression chapter draft",
            created_at="2026-05-28T16:42:11+00:00",
            post_url="https://x.com/karpathy/status/1790012345678901234",
            reply_count=312,
            repost_count=1240,
            like_count=9873,
            view_count=521004,
            urls="",
            dom_hash="deadbeef",
            screenshot_path=None,
            collection_backend="browser_agent",
        )
        defaults.update(overrides)
        return PostRecord(**defaults)

    def test_default_window_is_24h(self):
        self.assertEqual(DEFAULT_WINDOW_HOURS, 24)
        self.assertEqual(DEFAULT_WINDOW, timedelta(hours=24))
        self.assertEqual(self.queue.window, DEFAULT_WINDOW)

    def test_first_record_is_not_duplicate(self):
        record = self._record()
        verdict = self.queue.check(record)
        self.assertFalse(verdict.is_duplicate)
        self.assertEqual(verdict.key_kind, "url")
        self.assertEqual(verdict.key, "https://x.com/karpathy/status/1790012345678901234")

    def test_second_seen_within_window_is_duplicate_by_url(self):
        record = self._record()
        first_verdict, _ = self.queue.record_seen(record, post_pk=1)
        self.assertFalse(first_verdict.is_duplicate)
        second_verdict, _ = self.queue.record_seen(record, post_pk=1)
        self.assertTrue(second_verdict.is_duplicate)
        self.assertEqual(second_verdict.key_kind, "url")

    def test_record_outside_window_is_not_duplicate(self):
        now = datetime(2026, 5, 28, 16, 42, 11, tzinfo=timezone.utc)
        later = now + timedelta(hours=DEFAULT_WINDOW_HOURS + 1)

        clock = {"t": now}
        queue = DedupQueue(self.conn, clock=lambda: clock["t"])
        record = self._record()
        queue.record_seen(record, post_pk=1)

        clock["t"] = later
        verdict, _ = queue.record_seen(record, post_pk=2)
        self.assertFalse(verdict.is_duplicate)

    def test_canonical_url_helper(self):
        url = canonical_url(self._record())
        self.assertEqual(url, "https://x.com/karpathy/status/1790012345678901234")

    def test_canonical_url_none_when_handle_missing(self):
        url = canonical_url(self._record(author_handle="N/A"))
        self.assertIsNone(url)


# ---------------------------------------------------------------------------
# 4. DedupQueue — sha256 fallback when URL missing (A-C3-4)
# ---------------------------------------------------------------------------


class TestDedupQueueSha256Fallback(unittest.TestCase):
    """A-C3-4 — sha256(handle+text+time) is used when canonical URL absent."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        _bootstrap_social_posts(self.conn)
        self.queue = DedupQueue(self.conn)

    def tearDown(self):
        self.conn.close()

    def _orphan_record(self, **overrides) -> PostRecord:
        defaults = dict(
            post_id="N/A",
            author_handle="ghost",
            text="manually curated post with no permalink",
            created_at="2026-05-28T12:00:00+00:00",
            post_url="N/A",
            reply_count=0,
            repost_count=0,
            like_count=0,
            view_count=None,
            urls="",
            dom_hash="cafebabe",
            screenshot_path=None,
            collection_backend="manual_curated",
        )
        defaults.update(overrides)
        return PostRecord(**defaults)

    def test_check_uses_sha256_when_url_unavailable(self):
        record = self._orphan_record()
        verdict = self.queue.check(record)
        self.assertEqual(verdict.key_kind, "sha256")
        self.assertTrue(verdict.key.startswith("sha256:"))
        self.assertIsNone(verdict.canonical_url)

    def test_sha256_deterministic_with_same_inputs(self):
        record = self._orphan_record()
        key_a = sha256_fallback_key(record)
        key_b = sha256_fallback_key(record)
        self.assertEqual(key_a, key_b)

    def test_sha256_changes_when_text_changes(self):
        a = self._orphan_record()
        b = self._orphan_record(text="totally different content")
        self.assertNotEqual(sha256_fallback_key(a), sha256_fallback_key(b))

    def test_second_orphan_is_duplicate_by_sha256(self):
        record = self._orphan_record()
        self.queue.record_seen(record, post_pk=1)
        verdict, _ = self.queue.record_seen(record, post_pk=1)
        self.assertTrue(verdict.is_duplicate)
        self.assertEqual(verdict.key_kind, "sha256")

    def test_whitespace_normalised_text_dedups(self):
        a = self._orphan_record(text="hello   world")
        b = self._orphan_record(text="hello world")
        self.queue.record_seen(a, post_pk=1)
        verdict, _ = self.queue.record_seen(b, post_pk=1)
        self.assertTrue(verdict.is_duplicate)


# ---------------------------------------------------------------------------
# 5. DedupQueue — URL conflict policy (A-C3-5)
# ---------------------------------------------------------------------------


class TestDedupQueueUrlConflict(unittest.TestCase):
    """A-C3-5 — sha256 same + URL different → sha256 wins; URL refreshed."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        _bootstrap_social_posts(self.conn)
        self.queue = DedupQueue(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_sha256_collision_with_url_mismatch_dedups(self):
        # First record was collected without a URL (manual_curated), so
        # the sha256 fallback became its primary key.
        first = PostRecord(
            post_id="N/A",
            author_handle="ghost",
            text="shared body text shared body text",
            created_at="2026-05-28T12:00:00+00:00",
            post_url="N/A",
            reply_count=0,
            repost_count=0,
            like_count=0,
            view_count=None,
            urls="",
            dom_hash="aa",
            collection_backend="manual_curated",
        )
        self.queue.record_seen(first, post_pk=1)

        # Same text + same handle + same window arrive now with a URL.
        second = PostRecord(
            post_id="1790009999999999999",
            author_handle="ghost",
            text="shared body text shared body text",
            created_at="2026-05-28T12:00:30+00:00",
            post_url="https://x.com/ghost/status/1790009999999999999",
            reply_count=1,
            repost_count=0,
            like_count=2,
            view_count=42,
            urls="",
            dom_hash="bb",
            collection_backend="browser_agent",
        )

        verdict, stored = self.queue.record_seen(second, post_pk=2)
        self.assertTrue(verdict.is_duplicate)
        # sha256 wins per OQ-04 — the verdict key kind reflects this.
        self.assertEqual(verdict.key_kind, "sha256")

        # The URL key is also written as an alias so a later URL-keyed
        # lookup finds the same post_pk.
        alias = lookup_dedup_key(
            self.conn, "https://x.com/ghost/status/1790009999999999999"
        )
        self.assertIsNotNone(alias)
        self.assertEqual(alias.post_pk, 2)

    def test_derive_keys_returns_both_when_url_available(self):
        rec = PostRecord(
            post_id="1",
            author_handle="x",
            text="hi",
            created_at="2026-05-28T12:00:00+00:00",
            post_url="https://x.com/x/status/1",
            reply_count=0,
            repost_count=0,
            like_count=0,
            view_count=None,
            urls="",
            dom_hash="",
            collection_backend="browser_agent",
        )
        keys = derive_keys(rec)
        self.assertIsNotNone(keys.url_key)
        self.assertTrue(keys.sha256_key.startswith("sha256:"))
        self.assertEqual(keys.primary_kind, "url")

    def test_alias_persistence_round_trip(self):
        rec = PostRecord(
            post_id="1",
            author_handle="x",
            text="alias smoke",
            created_at="2026-05-28T12:00:00+00:00",
            post_url="https://x.com/x/status/1",
            reply_count=0,
            repost_count=0,
            like_count=0,
            view_count=None,
            urls="",
            dom_hash="",
            collection_backend="browser_agent",
        )
        self.queue.record_seen(rec, post_pk=7)
        # Both URL and sha256 keys should resolve to post_pk=7.
        keys = derive_keys(rec)
        url_row = lookup_dedup_key(self.conn, keys.url_key)
        sha_row = lookup_dedup_key(self.conn, keys.sha256_key)
        self.assertEqual(url_row.post_pk, 7)
        self.assertEqual(sha_row.post_pk, 7)


# ---------------------------------------------------------------------------
# 6. Cross-module — no secret leakage in extractor / dedup
# ---------------------------------------------------------------------------


class TestNoSecretLeaksC3(unittest.TestCase):
    """Same secret-scan style as C2 — guarantees the extractor / dedup
    modules never embed or print cookies / tokens / session strings."""

    SECRET_RX = re.compile(
        "(" + "set-" + "cookie:|bearer" + r"\s+[a-z0-9]|x-csrf-" + "token:|" + "session=" + r"[a-z0-9]+|auth-" + "token=" + ")",
        re.IGNORECASE,
    )

    def test_no_forbidden_tokens_in_module_sources(self):
        import importlib.resources as resources

        pkg = "social_browser_backend_x"
        for name in ("post_extractor", "dedup_queue"):
            with self.subTest(module=name):
                source = resources.files(pkg).joinpath(f"{name}.py").read_text()
                matches = list(self.SECRET_RX.finditer(source))
                self.assertEqual(matches, [], f"secret hit in {name}: {matches}")


if __name__ == "__main__":
    unittest.main()
