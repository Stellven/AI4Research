"""Tests for C2: collection, canonicalization, enrichment pipeline."""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib", "hf_paper_insight"))

from schema import PaperSnapshot, PaperCanonical, PaperEnrichment, WindowType, _title_hash, _gen_id, _utc_now
from storage import PaperStore
from collector import SnapshotCollector
from canonicalizer import Canonicalizer
from enricher import Enricher
from providers.base import BaseEnrichmentProvider, ProviderResult
from providers.hf_provider import HFProvider
from providers.arxiv_provider import ArxivProvider
from providers.hf_assets_provider import HFAssetsProvider


# ── Fixtures ──────────────────────────────────────────────────────

class MockSource:
    def __init__(self, papers: list[dict] | None = None, *, use_default: bool = True):
        if papers is not None:
            self._papers = papers
        elif use_default:
            self._papers = [
                {"paper_id": "2401.00001", "title": "Test Paper One", "upvotes": 10, "rank": 1},
                {"paper_id": "2401.00002", "title": "Test Paper Two", "upvotes": 5, "rank": 2},
            ]
        else:
            self._papers = []

    def fetch_papers(self, window_type: str, ws: str, we: str) -> list[dict]:
        return self._papers


class MockHTTPResponse:
    def __init__(self, data: dict, status_code: int = 200):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


def mock_client_factory(data: dict, status: int = 200):
    def client(url: str) -> MockHTTPResponse:
        return MockHTTPResponse(data, status)
    return client


class FailingProvider(BaseEnrichmentProvider):
    name = "failing"

    def _fetch(self, canonical):
        raise RuntimeError("provider_down")


class SuccessProvider(BaseEnrichmentProvider):
    name = "success_test"

    def _fetch(self, canonical):
        return {"key": "value", "paper_id": canonical.paper_id}


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(db):
    return PaperStore(db)


# ── Collector Tests ───────────────────────────────────────────────

class TestSnapshotCollector:
    def test_daily_snapshot(self, store):
        source = MockSource()
        collector = SnapshotCollector(source)
        snaps = collector.fetch_daily_snapshot(observed_at="2026-05-28")
        assert len(snaps) == 2
        assert snaps[0].window_type == WindowType.daily
        assert snaps[0].paper_id == "2401.00001"
        assert snaps[0].rank == 1

    def test_weekly_snapshot(self, store):
        source = MockSource()
        collector = SnapshotCollector(source)
        snaps = collector.fetch_weekly_snapshot(
            window_start="2026-05-26T00:00:00Z",
            window_end="2026-06-01T23:59:59Z",
        )
        assert len(snaps) == 2
        assert snaps[0].window_type == WindowType.weekly

    def test_monthly_snapshot(self, store):
        source = MockSource()
        collector = SnapshotCollector(source)
        snaps = collector.fetch_monthly_snapshot(
            window_start="2026-05-01T00:00:00Z",
            window_end="2026-05-31T23:59:59Z",
        )
        assert len(snaps) == 2
        assert snaps[0].window_type == WindowType.monthly

    def test_persist_batch(self, store):
        source = MockSource()
        collector = SnapshotCollector(source)
        snaps = collector.fetch_daily_snapshot()
        count = collector.persist_snapshot_batch(snaps, store)
        assert count == 2
        for snap in snaps:
            fetched = store.get(PaperSnapshot, snap.snapshot_id)
            assert fetched is not None

    def test_empty_source(self, store):
        source = MockSource([])
        collector = SnapshotCollector(source)
        snaps = collector.fetch_daily_snapshot()
        assert snaps == []


# ── Canonicalizer Tests ───────────────────────────────────────────

class TestCanonicalizer:
    def test_canonicalize_from_raw(self, store):
        can = Canonicalizer(store).canonicalize_from_raw(
            paper_id="2401.00001",
            title="Attention Is All You Need",
            hf_url="https://huggingface.co/papers/1706.03762",
            arxiv_abs_url="https://arxiv.org/abs/1706.03762",
        )
        assert can.paper_id == "2401.00001"
        assert can.title_hash == _title_hash("Attention Is All You Need")
        assert can.arxiv_id == "1706.03762"
        assert can.dedup_keys_json != ""

    def test_identity_stable_across_windows(self, store):
        canon = Canonicalizer(store)
        c1 = canon.canonicalize_from_raw(
            "p1", "Same Title", "https://hf.co/papers/1",
        )
        store.upsert(c1)

        is_dup, existing_id = canon.dedup_check(c1)
        assert is_dup is True
        assert existing_id == "p1"

        c2 = canon.canonicalize_from_raw(
            "p2", "Same Title", "https://hf.co/papers/1",
        )
        is_dup2, existing_id2 = canon.dedup_check(c2)
        assert is_dup2 is True
        assert existing_id2 == "p1"

    def test_dedup_by_arxiv_id(self, store):
        canon = Canonicalizer(store)
        c1 = canon.canonicalize_from_raw(
            "p1", "Title Alpha", "https://hf.co/papers/1",
            arxiv_abs_url="https://arxiv.org/abs/2301.00001",
        )
        store.upsert(c1)

        c2 = canon.canonicalize_from_raw(
            "p2", "Title Beta", "https://hf.co/papers/2",
            arxiv_abs_url="https://arxiv.org/abs/2301.00001",
        )
        is_dup, existing_id = canon.dedup_check(c2)
        assert is_dup is True
        assert existing_id == "p1"

    def test_no_dedup_different_papers(self, store):
        canon = Canonicalizer(store)
        c1 = canon.canonicalize_from_raw("p1", "Title A", "https://hf.co/papers/1")
        c2 = canon.canonicalize_from_raw("p2", "Title B", "https://hf.co/papers/2")
        is_dup, _ = canon.dedup_check(c1)
        assert is_dup is False
        store.upsert(c1)
        is_dup2, _ = canon.dedup_check(c2)
        assert is_dup2 is False

    def test_merge_seen_window(self, store):
        canon = Canonicalizer(store)
        c1 = canon.canonicalize_from_raw("p1", "Title", "https://hf.co/papers/1")
        store.upsert(c1)
        canon.merge_seen_window("p1", "daily", "2026-05-28T06:00:00Z")
        canon.merge_seen_window("p1", "weekly", "2026-05-26T00:00:00Z")
        fetched = store.get(PaperCanonical, "p1")
        windows = json.loads(fetched.seen_windows_json)
        assert len(windows) >= 2


# ── Provider Base Tests ───────────────────────────────────────────

class TestBaseProvider:
    def test_circuit_breaker_opens(self):
        p = FailingProvider(max_consecutive_failures=2, max_retries=1)
        assert p.is_available() is True
        p.enrich(PaperCanonical(paper_id="test"))
        assert p.is_available() is True
        p.enrich(PaperCanonical(paper_id="test"))
        assert p.is_available() is False

    def test_circuit_breaker_result(self):
        p = FailingProvider(max_consecutive_failures=3, max_retries=1)
        r = p.enrich(PaperCanonical(paper_id="test"))
        assert r.success is False
        assert "retries_failed" in r.error

    def test_backoff_calculation(self):
        p = SuccessProvider()
        assert p.backoff_delay(1) == 1.0
        assert p.backoff_delay(2) == 2.0
        assert p.backoff_delay(3) == 4.0
        assert p.backoff_delay(10) == 60.0

    def test_reset_clears_failures(self):
        p = FailingProvider(max_consecutive_failures=1, max_retries=1)
        p.enrich(PaperCanonical(paper_id="test"))
        assert p.is_available() is False
        p.reset()
        assert p.is_available() is True
        assert p.consecutive_failures == 0

    def test_success_provider(self):
        p = SuccessProvider()
        r = p.enrich(PaperCanonical(paper_id="p1"))
        assert r.success is True
        assert r.data["key"] == "value"

    def test_open_breaker_returns_immediately(self):
        p = FailingProvider(max_consecutive_failures=1, max_retries=1)
        p.enrich(PaperCanonical(paper_id="t"))
        assert p.is_available() is False
        r = p.enrich(PaperCanonical(paper_id="t"))
        assert "circuit_breaker_open" in r.error


# ── HF Provider Tests ─────────────────────────────────────────────

class TestHFProvider:
    def test_hf_enrich_success(self):
        mock_data = {
            "title": "Test Paper",
            "authors": [{"name": "Alice"}],
            "summary": "A test paper.",
            "tags": ["nlp"],
            "upvotes": 42,
            "publishedAt": "2026-05-01T00:00:00Z",
        }
        p = HFProvider(http_client=mock_client_factory(mock_data))
        r = p.enrich(PaperCanonical(paper_id="2401.00001"))
        assert r.success is True
        assert r.data["title"] == "Test Paper"
        assert r.data["upvotes"] == 42
        assert r.provider_name == "huggingface"

    def test_hf_enrich_api_error(self):
        p = HFProvider(http_client=mock_client_factory({}, status=500))
        r = p.enrich(PaperCanonical(paper_id="2401.00001"))
        assert r.success is False
        assert "500" in r.error


# ── Arxiv Provider Tests ──────────────────────────────────────────

class TestArxivProvider:
    ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Test Arxiv Paper</title>
    <summary>A test abstract.</summary>
    <published>2026-04-15T00:00:00Z</published>
    <author><name>Alice</name></author>
    <author><name>Bob</name></author>
    <category term="cs.AI"/>
  </entry>
</feed>"""

    def test_arxiv_enrich_success(self):
        def client(url):
            r = MockHTTPResponse({}, 200)
            r.text = self.ARXIV_XML
            return r

        p = ArxivProvider(http_client=client)
        c = PaperCanonical(
            paper_id="p1", title="T", title_hash="h",
            authors_json="[]", hf_url="", arxiv_id="2401.00001",
            first_seen_at="", last_seen_at="", dedup_keys_json="{}", updated_at="",
        )
        r = p.enrich(c)
        assert r.success is True
        assert r.data["arxiv_id"] == "2401.00001"
        assert r.data["title"] == "Test Arxiv Paper"
        assert "Alice" in r.data["authors"]
        assert "cs.AI" in r.data["categories"]

    def test_arxiv_no_id(self):
        p = ArxivProvider()
        c = PaperCanonical(
            paper_id="p1", title="T", title_hash="h",
            authors_json="[]", hf_url="", first_seen_at="", last_seen_at="",
            dedup_keys_json="{}", updated_at="",
        )
        r = p.enrich(c)
        assert r.success is False
        assert "no arxiv_id" in r.error


# ── HF Assets Provider Tests ──────────────────────────────────────

class TestHFAssetsProvider:
    def test_assets_enrich_success(self):
        mock_data = [
            {"type": "model", "id": "org/model-a", "likes": 100, "downloads": 5000},
            {"type": "dataset", "id": "org/data-b", "likes": 20, "downloads": 500},
            {"type": "space", "id": "org/demo-c", "likes": 5, "downloads": 0},
        ]
        p = HFAssetsProvider(http_client=mock_client_factory(mock_data))
        r = p.enrich(PaperCanonical(paper_id="2401.00001"))
        assert r.success is True
        assert len(r.data["models"]) == 1
        assert len(r.data["datasets"]) == 1
        assert len(r.data["spaces"]) == 1
        assert r.data["total_assets"] == 3

    def test_assets_empty(self):
        p = HFAssetsProvider(http_client=mock_client_factory([]))
        r = p.enrich(PaperCanonical(paper_id="2401.00001"))
        assert r.success is True
        assert r.data["total_assets"] == 0


# ── Enricher Tests ────────────────────────────────────────────────

class TestEnricher:
    def test_partial_provider_failure(self, store):
        ok_provider = SuccessProvider()
        fail_provider = FailingProvider(max_consecutive_failures=99, max_retries=1)

        enricher = Enricher(store)
        results = {
            "success_test": ok_provider.enrich(PaperCanonical(paper_id="p1")),
            "failing": fail_provider.enrich(PaperCanonical(paper_id="p1")),
        }
        enrichment = enricher.merge_provider_payloads("p1", results)

        assert "success_test" in json.loads(enrichment.provider_success_json)
        failures = json.loads(enrichment.provider_failures_json)
        assert "failing" in failures

    def test_all_providers_succeed(self, store):
        p1 = SuccessProvider()
        p2 = SuccessProvider()
        enricher = Enricher(store)
        enrichment = enricher.enrich_all(
            PaperCanonical(paper_id="p1"),
            providers={"a": p1, "b": p2},
        )
        success = json.loads(enrichment.provider_success_json)
        assert "a" in success and "b" in success
        failures = json.loads(enrichment.provider_failures_json)
        assert failures == {}

    def test_enrichment_ttl(self, store):
        enricher = Enricher(store)
        results = {"success_test": ProviderResult(success=True, data={}, provider_name="success_test")}
        enr = enricher.merge_provider_payloads("p1", results)
        assert enr.ttl_expires_at > _utc_now()


# ── End-to-End Pipeline Test ──────────────────────────────────────

class TestEndToEnd:
    def test_snapshot_to_enrichment(self, store):
        # 1. Collect snapshots
        source = MockSource([
            {"paper_id": "2401.00001", "title": "E2E Paper", "upvotes": 15},
        ])
        collector = SnapshotCollector(source)
        snaps = collector.fetch_daily_snapshot()
        assert len(snaps) == 1
        collector.persist_snapshot_batch(snaps, store)

        # 2. Canonicalize
        canon = Canonicalizer(store)
        canonical = canon.canonicalize_from_raw(
            "2401.00001", "E2E Paper", "https://hf.co/papers/2401.00001",
            arxiv_abs_url="https://arxiv.org/abs/2401.00001",
        )
        is_dup, _ = canon.dedup_check(canonical)
        assert is_dup is False
        store.upsert(canonical)

        # 3. Enrich with mock providers
        hf_data = {"title": "E2E Paper", "upvotes": 15}
        assets_data = [{"type": "model", "id": "org/e2e-model", "likes": 10, "downloads": 100}]
        enricher = Enricher(store)
        hf_p = HFProvider(http_client=mock_client_factory(hf_data))
        assets_p = HFAssetsProvider(http_client=mock_client_factory(assets_data))
        enrichment = enricher.enrich_all(canonical, {"huggingface": hf_p, "hf_assets": assets_p})

        assert enrichment.paper_id == "2401.00001"
        success = json.loads(enrichment.provider_success_json)
        assert "huggingface" in success
        assert "hf_assets" in success
        store.upsert(enrichment)

        # Verify persisted
        fetched_enr = store.get(PaperEnrichment, enrichment.enrichment_id)
        assert fetched_enr is not None
        assert fetched_enr.paper_id == "2401.00001"
