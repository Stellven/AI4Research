from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib", "hf_paper_insight"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from compiler import Compiler
from knowledge_store import KnowledgeStore
from packet import PacketBuilder
from reasoning import HighReasoningEngine, ResonanceMatcher
from schema import PaperCanonical, PaperEnrichment, PaperTaxonomy
from scoring import SignalScorer
from watch import WatchTrigger


def _sample_canonical() -> PaperCanonical:
    return PaperCanonical(
        paper_id="paper-runtime-001",
        title="KV Cache Aware Inference Routing for Frontier Models",
        hf_url="https://huggingface.co/papers/2605.27001",
        arxiv_id="2605.27001",
        arxiv_abs_url="https://arxiv.org/abs/2605.27001",
        authors_json=json.dumps([{"name": "Alice"}, {"name": "Bob"}]),
        published_at="2026-05-27T00:00:00Z",
    )


def _sample_enrichment() -> PaperEnrichment:
    return PaperEnrichment(
        enrichment_id="enr-runtime-001",
        paper_id="paper-runtime-001",
        hf_metadata_json=json.dumps(
            {
                "downloads": 42000,
                "likes": 180,
                "tags": ["llm", "inference", "serving", "routing", "kv-cache", "systems"],
                "pipeline_tag": "text-generation",
                "card_data": {
                    "description": "Inference routing system for frontier model serving with KV cache locality.",
                },
            }
        ),
        arxiv_metadata_json=json.dumps(
            {
                "arxiv_id": "2605.27001",
                "title": "KV Cache Aware Inference Routing for Frontier Models",
                "abstract": "We study how KV cache placement and request routing interact in large-scale inference systems.",
                "authors": ["Alice", "Bob"],
                "categories": ["cs.LG", "cs.DC"],
                "published": "2026-05-27T00:00:00Z",
            }
        ),
        hf_assets_json=json.dumps(
            {
                "linked_models": ["org/kv-routing-8b"],
                "linked_datasets": ["org/inference-traffic-benchmark"],
                "linked_spaces": ["org/kv-routing-demo"],
                "demo_urls": ["https://huggingface.co/spaces/org/kv-routing-demo"],
            }
        ),
        github_repo_json=json.dumps({"url": "https://github.com/org/kv-routing", "stars": 2345}),
        provider_success_json=json.dumps(["huggingface", "arxiv", "hf_assets"]),
        provider_failures_json="{}",
    )


def _sample_taxonomy() -> PaperTaxonomy:
    return PaperTaxonomy(
        paper_id="paper-runtime-001",
        domain="systems",
        method="architecture",
        task="reasoning",
        asset="full_suite",
        stack_layer="inference",
        maturity="prototype",
        research_route="engineering",
        confidence=0.86,
    )


def test_hf_paper_insight_runtime_end_to_end(tmp_path):
    canonical = _sample_canonical()
    enrichment = _sample_enrichment()
    taxonomy = _sample_taxonomy()

    scorer = SignalScorer()
    signal = scorer.compute_scores(canonical, enrichment, taxonomy, profile_name="ai-influence")
    gate = scorer.packet_gate_check(signal, enrichment)
    assert gate["passed"] is True

    builder = PacketBuilder()
    packet = builder.build_packet_v2(canonical, enrichment, taxonomy, signal, gate_result=gate)

    matcher = ResonanceMatcher()
    resonance = matcher.match_resonance(packet)
    assert resonance["resonance_level"] in {"R2", "R3", "R4", "R5"}

    engine = HighReasoningEngine()
    reasoning = engine.call_high_model(packet, mode="browser_agent")
    assert reasoning["accepted"] is True
    assert engine.insight_gate_check(reasoning)["passed"] is True
    assert engine.resonance_gate_check(resonance)["passed"] is True

    compiler = Compiler()
    compiled = compiler.compile_outputs(packet, reasoning, resonance)
    assert sorted(compiled) == sorted(compiler.OUTPUT_KEYS)
    assert "Deep Research Seed Pack" in compiled["deep_research"]

    store = KnowledgeStore(tmp_path / "knowledge")
    fanout = store.fanout(
        canonical=canonical,
        enrichment=enrichment,
        packet=packet,
        resonance=resonance,
        compiled=compiled,
    )
    assert os.path.exists(fanout["raw"])
    assert len(fanout["extracted"]) == 7
    assert len(fanout["qmd"]) == 7
    assert len(fanout["graph"]) == 2

    watch = WatchTrigger(tmp_path / "knowledge")
    spec = watch.build_watch_spec(packet, resonance, reasoning)
    spec_path = watch.store_watch_spec(spec)
    queue_id = watch.trigger_watch(packet.paper_id, spec["priority"], spec["reason"])

    assert os.path.exists(spec_path)
    assert queue_id.startswith("watch-")
    assert spec["taxonomy"]["stack_layer"] == "inference"
