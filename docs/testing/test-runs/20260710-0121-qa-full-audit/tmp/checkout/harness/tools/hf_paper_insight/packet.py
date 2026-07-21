"""PacketBuilder — assemble evidence packets with gate enforcement.

Per interfaces §5: build_packet_v2.
Only packets passing packet_gate_check proceed to high reasoning.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from schema import (
    PaperCanonical,
    PaperEnrichment,
    PaperEvidencePacket,
    PaperSignal,
    PaperTaxonomy,
    _gen_id,
    _utc_now,
)


def _packet_ttl_days() -> int:
    return 7


def _expires_at() -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=_packet_ttl_days())
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class PacketBuilder:
    """Assembles PaperEvidencePacket v2 from upstream entities.

    Gate enforcement: ``build_packet_v2`` accepts a gate_result dict.
    If gate_result["passed"] is False, returns a packet with
    packet_gate_json documenting the rejection (not sent to high reasoning).
    """

    def build_packet_v2(
        self,
        canonical: PaperCanonical,
        enrichment: PaperEnrichment,
        taxonomy: PaperTaxonomy,
        signal: PaperSignal,
        *,
        gate_result: Optional[dict] = None,
    ) -> PaperEvidencePacket:
        gate = gate_result or {"passed": True, "checks": {}, "reasons": []}

        canonical_summary = {
            "paper_id": canonical.paper_id,
            "title": canonical.title,
            "arxiv_id": canonical.arxiv_id,
            "hf_url": canonical.hf_url,
            "authors": json.loads(canonical.authors_json),
            "published_at": canonical.published_at,
        }

        enrichment_summary = self._summarize_enrichment(enrichment)

        taxonomy_summary = {
            "domain": taxonomy.domain,
            "method": taxonomy.method,
            "task": taxonomy.task,
            "stack_layer": taxonomy.stack_layer,
            "maturity": taxonomy.maturity,
            "research_route": taxonomy.research_route,
            "confidence": taxonomy.confidence,
        }

        score_summary = {
            "research_signal": signal.research_signal_score,
            "insight_report": signal.insight_report_score,
            "experiment": signal.experiment_score,
            "open_project": signal.open_project_score,
            "deep_research_seed": signal.deep_research_seed_score,
            "attention": signal.attention_signal,
            "novelty": signal.novelty_signal,
            "reproducibility": signal.reproducibility_signal,
            "industry_coupling": signal.industry_coupling_signal,
            "profile": signal.score_profile,
        }

        provenance = {
            "canonical_id": canonical.paper_id,
            "enrichment_id": enrichment.enrichment_id,
            "taxonomy_id": taxonomy.taxonomy_id,
            "signal_id": signal.signal_id,
            "snapshot_source": enrichment.hf_metadata_json and "hf_api" or "unknown",
        }

        return PaperEvidencePacket(
            packet_id=_gen_id("pkt-"),
            paper_id=canonical.paper_id,
            packet_version="v2",
            canonical_summary_json=json.dumps(canonical_summary),
            enrichment_summary_json=json.dumps(enrichment_summary),
            taxonomy_summary_json=json.dumps(taxonomy_summary),
            score_summary_json=json.dumps(score_summary),
            provenance_json=json.dumps(provenance),
            packet_gate_json=json.dumps(gate),
            cache_expires_at=_expires_at(),
        )

    def _summarize_enrichment(self, enrichment: PaperEnrichment) -> dict:
        hf_meta = json.loads(enrichment.hf_metadata_json)
        arxiv = json.loads(enrichment.arxiv_metadata_json)
        assets = json.loads(enrichment.hf_assets_json)

        return {
            "has_hf_metadata": bool(hf_meta),
            "has_arxiv_metadata": bool(arxiv),
            "has_hf_assets": bool(assets),
            "arxiv_title": arxiv.get("title", ""),
            "abstract_length": len(arxiv.get("abstract", "")),
            "linked_models_count": len(assets.get("linked_models", [])),
            "linked_datasets_count": len(assets.get("linked_datasets", [])),
            "has_demo": bool(assets.get("demo_urls")),
            "provider_success": json.loads(enrichment.provider_success_json),
        }
