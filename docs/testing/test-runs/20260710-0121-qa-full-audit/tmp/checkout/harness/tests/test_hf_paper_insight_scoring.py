"""Tests for HF Paper Insight collection, canonicalization, enrichment, taxonomy, scoring, packet.

Covers both C2 (collection/canonical/enrichment) and C3 (taxonomy/scoring/packet) acceptance.
"""
from __future__ import annotations

import json
import sys
import os
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib", "hf_paper_insight"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from schema import (
    PaperCanonical,
    PaperEnrichment,
    PaperEvidencePacket,
    PaperSignal,
    PaperSnapshot,
    PaperTaxonomy,
    WindowType,
    _gen_id,
    _title_hash,
    _utc_now,
)
from storage import PaperStore
from collector import SnapshotCollector
from canonicalizer import Canonicalizer
from providers.base import BaseEnrichmentProvider, ProviderResult
from taxonomy import PaperClassifier
from scoring import SignalScorer, ScoreProfile
from packet import PacketBuilder


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(tmp_db):
    s = PaperStore(tmp_db)
    yield s
    s.close()


class FakeSource:
    def __init__(self, papers):
        self._papers = papers

    def fetch_papers(self, window_type, window_start, window_end):
        return self._papers


@pytest.fixture
def sample_raw_papers():
    return [
        {
            "paper_id": "2401.12345",
            "rank": 1,
            "upvotes": 42,
            "hf_url": "https://huggingface.co/papers/2401.12345",
            "source": "huggingface_papers",
        },
        {
            "paper_id": "2401.67890",
            "rank": 2,
            "upvotes": 18,
            "hf_url": "https://huggingface.co/papers/2401.67890",
            "source": "huggingface_papers",
        },
    ]


@pytest.fixture
def sample_canonical():
    return PaperCanonical(
        paper_id="paper-abc123",
        title="Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
        hf_url="https://huggingface.co/papers/2312.00752",
        arxiv_id="2312.00752",
        arxiv_abs_url="https://arxiv.org/abs/2312.00752",
        authors_json=json.dumps([{"name": "Albert Gu"}, {"name": "Tri Dao"}]),
    )


@pytest.fixture
def sample_enrichment():
    return PaperEnrichment(
        enrichment_id="enr-test1",
        paper_id="paper-abc123",
        hf_metadata_json=json.dumps({
            "downloads": 50000,
            "likes": 200,
            "tags": ["mamba", "ssm", "sequence-modeling", "pytorch"],
            "pipeline_tag": "text-generation",
            "card_data": {"description": "Mamba model implementation"},
        }),
        arxiv_metadata_json=json.dumps({
            "arxiv_id": "2312.00752",
            "title": "Mamba: Linear-Time Sequence Modeling",
            "abstract": "We propose Mamba, a new architecture for sequence modeling.",
            "authors": ["Albert Gu", "Tri Dao"],
            "categories": ["cs.LG"],
            "published": "2023-12-01T00:00:00Z",
        }),
        hf_assets_json=json.dumps({
            "linked_models": ["state-spaces/mamba-130m"],
            "linked_datasets": [],
            "linked_spaces": ["state-spaces/mamba-demo"],
            "demo_urls": ["https://huggingface.co/spaces/state-spaces/mamba-demo"],
        }),
        provider_success_json=json.dumps({"hf_metadata": True, "arxiv_metadata": True, "hf_assets": True}),
        provider_failures_json="{}",
    )


# ── C2: Collection Tests ─────────────────────────────────────


class TestSnapshotCollector:
    def test_daily_snapshot(self, sample_raw_papers):
        source = FakeSource(sample_raw_papers)
        collector = SnapshotCollector(source)
        snapshots = collector.fetch_daily_snapshot(observed_at="2026-05-28T06:00:00Z")
        assert len(snapshots) == 2
        assert snapshots[0].window_type == WindowType.daily
        assert snapshots[0].rank == 1
        assert snapshots[0].upvotes == 42
        assert snapshots[0].paper_id == "2401.12345"

    def test_weekly_snapshot(self, sample_raw_papers):
        source = FakeSource(sample_raw_papers)
        collector = SnapshotCollector(source)
        snapshots = collector.fetch_weekly_snapshot(
            window_start="2026-05-26T00:00:00Z",
            window_end="2026-06-01T23:59:59Z",
        )
        assert len(snapshots) == 2
        assert snapshots[0].window_type == WindowType.weekly

    def test_persist_batch(self, sample_raw_papers, store):
        source = FakeSource(sample_raw_papers)
        collector = SnapshotCollector(source)
        snapshots = collector.fetch_daily_snapshot(observed_at="2026-05-28T06:00:00Z")
        count = collector.persist_snapshot_batch(snapshots, store)
        assert count == 2
        snap = store.get(PaperSnapshot, snapshots[0].snapshot_id)
        assert snap is not None

    def test_empty_source(self):
        source = FakeSource([])
        collector = SnapshotCollector(source)
        snapshots = collector.fetch_daily_snapshot(observed_at="2026-05-28T06:00:00Z")
        assert snapshots == []


# ── C2: Canonicalizer Tests ──────────────────────────────────


class TestCanonicalizer:
    def test_canonicalize_paper(self, store):
        snap = PaperSnapshot(
            paper_id="2401.12345",
            hf_url="https://huggingface.co/papers/2401.12345",
            window_type=WindowType.daily,
            window_start="2026-05-28",
            window_end="2026-05-29",
            observed_at="2026-05-28T06:00:00Z",
        )
        setattr(snap, "_raw_title", "Test Paper Title")
        setattr(snap, "_raw_arxiv_url", "https://arxiv.org/abs/2401.12345")

        canon = Canonicalizer(store)
        canonical = canon.canonicalize_paper(snap)
        assert canonical.paper_id == "2401.12345"
        assert canonical.title == "Test Paper Title"
        assert canonical.arxiv_id == "2401.12345"
        assert canonical.hf_url == "https://huggingface.co/papers/2401.12345"

    def test_dedup_by_arxiv_id(self, store, sample_canonical):
        store.upsert(sample_canonical)
        canon = Canonicalizer(store)
        is_dup, existing_id = canon.dedup_check(sample_canonical)
        assert is_dup is True
        assert existing_id == "paper-abc123"

    def test_dedup_by_title_hash(self, store):
        c1 = PaperCanonical(
            paper_id="paper-xyz",
            title="Same Title Different Source",
            title_hash=_title_hash("Same Title Different Source"),
            hf_url="https://huggingface.co/papers/1111.11111",
        )
        store.upsert(c1)

        c2 = PaperCanonical(
            paper_id="paper-new",
            title="Same Title Different Source",
            title_hash=_title_hash("Same Title Different Source"),
            hf_url="https://huggingface.co/papers/2222.22222",
        )

        canon = Canonicalizer(store)
        is_dup, existing_id = canon.dedup_check(c2)
        assert is_dup is True
        assert existing_id == "paper-xyz"

    def test_no_dedup_different_papers(self, store):
        c1 = PaperCanonical(
            paper_id="paper-a",
            title="Paper A",
            title_hash=_title_hash("Paper A"),
            hf_url="https://huggingface.co/papers/aaa",
        )
        store.upsert(c1)

        c2 = PaperCanonical(
            paper_id="paper-b",
            title="Paper B",
            title_hash=_title_hash("Paper B"),
            hf_url="https://huggingface.co/papers/bbb",
        )

        canon = Canonicalizer(store)
        is_dup, _ = canon.dedup_check(c2)
        assert is_dup is False

    def test_canonical_identity_stable_across_windows(self, store):
        snap1 = PaperSnapshot(
            paper_id="2401.12345",
            hf_url="https://huggingface.co/papers/2401.12345",
            window_type=WindowType.daily,
            window_start="2026-05-28",
            window_end="2026-05-29",
            observed_at="2026-05-28T06:00:00Z",
        )
        setattr(snap1, "_raw_title", "Test Paper")
        setattr(snap1, "_raw_arxiv_url", "https://arxiv.org/abs/2401.12345")

        canon = Canonicalizer(store)
        c1 = canon.canonicalize_paper(snap1)
        store.upsert(c1)

        # Same paper in next day's snapshot
        snap2 = PaperSnapshot(
            paper_id="2401.12345",
            hf_url="https://huggingface.co/papers/2401.12345",
            window_type=WindowType.daily,
            window_start="2026-05-29",
            window_end="2026-05-30",
            observed_at="2026-05-29T06:00:00Z",
        )
        setattr(snap2, "_raw_title", "Test Paper")
        setattr(snap2, "_raw_arxiv_url", "https://arxiv.org/abs/2401.12345")

        c2 = canon.canonicalize_paper(snap2)
        is_dup, _ = canon.dedup_check(c2)
        assert is_dup is True
        assert c2.arxiv_id == c1.arxiv_id

    def test_merge_seen_window(self, store, sample_canonical):
        store.upsert(sample_canonical)
        canon = Canonicalizer(store)
        canon.merge_seen_window(sample_canonical.paper_id, "weekly", "2026-05-28T06:00:00Z")

        updated = store.get(PaperCanonical, sample_canonical.paper_id)
        windows = json.loads(updated.seen_windows_json)
        assert len(windows) >= 1


# ── C2: Provider Tests ────────────────────────────────────────


class TestProviderCircuitBreaker:
    def test_provider_success(self):
        class OkProvider(BaseEnrichmentProvider):
            name = "test_ok"
            def _fetch(self, canonical):
                return {"status": "ok"}

        p = OkProvider()
        result = p.enrich(PaperCanonical())
        assert result.success is True
        assert result.data["status"] == "ok"

    def test_provider_failure_trips_breaker(self):
        class FailProvider(BaseEnrichmentProvider):
            name = "test_fail"
            def _fetch(self, canonical):
                raise ConnectionError("network down")

        p = FailProvider(max_consecutive_failures=3, max_retries=1)
        for _ in range(3):
            p.enrich(PaperCanonical())

        assert p.is_available() is False
        result = p.enrich(PaperCanonical())
        assert result.success is False
        assert "circuit_breaker_open" in result.error

    def test_provider_backoff(self):
        class FailProvider(BaseEnrichmentProvider):
            name = "test_backoff"
            def _fetch(self, canonical):
                raise RuntimeError("fail")

        p = FailProvider(max_retries=1)
        assert p.backoff_delay(1) == 1.0
        assert p.backoff_delay(2) == 2.0
        assert p.backoff_delay(3) == 4.0

    def test_single_provider_failure_no_block(self):
        """Single provider failure does not block other providers."""
        class FailProvider(BaseEnrichmentProvider):
            name = "fail_only"
            def _fetch(self, canonical):
                raise RuntimeError("fail")

        class OkProvider(BaseEnrichmentProvider):
            name = "ok_only"
            def _fetch(self, canonical):
                return {"status": "ok"}

        fail = FailProvider(max_retries=1)
        ok = OkProvider()

        fail_result = fail.enrich(PaperCanonical())
        ok_result = ok.enrich(PaperCanonical())

        assert fail_result.success is False
        assert ok_result.success is True


# ── C3: Taxonomy Tests ────────────────────────────────────────


class TestPaperClassifier:
    def test_classify_nlp_paper(self, sample_enrichment):
        classifier = PaperClassifier()
        taxonomy = classifier.classify_paper(sample_enrichment)
        assert taxonomy.paper_id == "paper-abc123"
        assert taxonomy.domain in ("nlp", "systems", "other")
        assert taxonomy.method != ""
        assert taxonomy.confidence > 0.0

    def test_infer_domain(self):
        classifier = PaperClassifier()
        assert classifier.infer_domain("Transformer architecture for NLP", "") == "nlp"
        assert classifier.infer_domain("Image segmentation with diffusion models", "") == "cv"
        assert classifier.infer_domain("Distributed training optimization", "") == "systems"

    def test_infer_research_route(self):
        classifier = PaperClassifier()
        tax = PaperTaxonomy(domain="systems", method="compression")
        assert classifier.infer_research_route(tax) == "engineering"

        tax2 = PaperTaxonomy(domain="safety", method="finetuning")
        assert classifier.infer_research_route(tax2) == "safety_alignment"

    def test_classify_outputs_paper_taxonomy(self, sample_enrichment):
        classifier = PaperClassifier()
        tax = classifier.classify_paper(sample_enrichment)
        assert isinstance(tax, PaperTaxonomy)
        assert tax.paper_id == sample_enrichment.paper_id
        assert tax.domain != ""
        assert tax.method != ""
        assert tax.task != ""
        assert tax.stack_layer != ""


# ── C3: Scoring Tests ─────────────────────────────────────────


class TestSignalScorer:
    def test_compute_scores(self, sample_canonical, sample_enrichment):
        classifier = PaperClassifier()
        taxonomy = classifier.classify_paper(sample_enrichment)

        scorer = SignalScorer()
        signal = scorer.compute_scores(sample_canonical, sample_enrichment, taxonomy, "default")

        assert isinstance(signal, PaperSignal)
        assert signal.paper_id == sample_canonical.paper_id
        assert 0.0 <= signal.research_signal_score <= 1.0
        assert 0.0 <= signal.insight_report_score <= 1.0
        assert 0.0 <= signal.experiment_score <= 1.0
        assert 0.0 <= signal.open_project_score <= 1.0
        assert 0.0 <= signal.deep_research_seed_score <= 1.0
        assert signal.attention_signal >= 0.0
        assert signal.novelty_signal >= 0.0
        assert signal.reproducibility_signal >= 0.0
        assert signal.industry_coupling_signal >= 0.0

    def test_packet_gate_pass(self, sample_canonical, sample_enrichment):
        classifier = PaperClassifier()
        taxonomy = classifier.classify_paper(sample_enrichment)
        scorer = SignalScorer()
        signal = scorer.compute_scores(sample_canonical, sample_enrichment, taxonomy, "default")

        gate = scorer.packet_gate_check(signal, sample_enrichment)
        assert gate["passed"] is True
        assert gate["checks"]["has_source"] is True
        assert gate["checks"]["has_metadata"] is True

    def test_packet_gate_fail_no_source(self, sample_canonical):
        empty_enrichment = PaperEnrichment(
            paper_id=sample_canonical.paper_id,
            provider_success_json="{}",
            provider_failures_json="{}",
        )
        signal = PaperSignal(
            paper_id=sample_canonical.paper_id,
            research_signal_score=0.5,
        )
        scorer = SignalScorer()
        gate = scorer.packet_gate_check(signal, empty_enrichment)
        assert gate["passed"] is False
        assert "no_provider_succeeded" in gate["reasons"]

    def test_score_inputs_recorded(self, sample_canonical, sample_enrichment):
        classifier = PaperClassifier()
        taxonomy = classifier.classify_paper(sample_enrichment)
        scorer = SignalScorer()
        signal = scorer.compute_scores(sample_canonical, sample_enrichment, taxonomy, "default")

        inputs = json.loads(signal.score_inputs_json)
        assert "attention_raw" in inputs
        assert "novelty_raw" in inputs
        assert "reproducibility_raw" in inputs
        assert "industry_raw" in inputs


# ── C3: Packet Tests ──────────────────────────────────────────


class TestPacketBuilder:
    def test_build_packet_v2(self, sample_canonical, sample_enrichment):
        classifier = PaperClassifier()
        taxonomy = classifier.classify_paper(sample_enrichment)
        scorer = SignalScorer()
        signal = scorer.compute_scores(sample_canonical, sample_enrichment, taxonomy, "default")
        gate = scorer.packet_gate_check(signal, sample_enrichment)

        builder = PacketBuilder()
        packet = builder.build_packet_v2(
            sample_canonical, sample_enrichment, taxonomy, signal,
            gate_result=gate,
        )

        assert isinstance(packet, PaperEvidencePacket)
        assert packet.packet_version == "v2"
        assert packet.paper_id == sample_canonical.paper_id
        assert packet.cache_expires_at != ""

        cs = json.loads(packet.canonical_summary_json)
        assert cs["title"] == sample_canonical.title

        gs = json.loads(packet.packet_gate_json)
        assert gs["passed"] is True

    def test_packet_with_failed_gate(self, sample_canonical):
        empty_enrichment = PaperEnrichment(paper_id=sample_canonical.paper_id)
        taxonomy = PaperTaxonomy(paper_id=sample_canonical.paper_id)
        signal = PaperSignal(paper_id=sample_canonical.paper_id)
        gate = {"passed": False, "checks": {"has_source": False}, "reasons": ["no_provider_succeeded"]}

        builder = PacketBuilder()
        packet = builder.build_packet_v2(
            sample_canonical, empty_enrichment, taxonomy, signal,
            gate_result=gate,
        )

        gs = json.loads(packet.packet_gate_json)
        assert gs["passed"] is False

    def test_only_gated_packets_proceed(self, sample_canonical, sample_enrichment):
        """AC: only packets passing Packet Gate go to high reasoning route."""
        classifier = PaperClassifier()
        taxonomy = classifier.classify_paper(sample_enrichment)
        scorer = SignalScorer()
        signal = scorer.compute_scores(sample_canonical, sample_enrichment, taxonomy, "default")
        gate = scorer.packet_gate_check(signal, sample_enrichment)

        builder = PacketBuilder()
        packet = builder.build_packet_v2(
            sample_canonical, sample_enrichment, taxonomy, signal,
            gate_result=gate,
        )

        gate_data = json.loads(packet.packet_gate_json)
        can_proceed = gate_data["passed"]
        assert can_proceed is True

        # Verify: a failed gate packet would NOT proceed
        fail_gate = {"passed": False, "checks": {"has_source": False}, "reasons": ["no_source"]}
        fail_packet = builder.build_packet_v2(
            sample_canonical, sample_enrichment, taxonomy, signal,
            gate_result=fail_gate,
        )
        fail_gate_data = json.loads(fail_packet.packet_gate_json)
        assert fail_gate_data["passed"] is False
