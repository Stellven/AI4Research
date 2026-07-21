"""Enricher — multi-provider enrichment with failure isolation.

Per interfaces.md §3 + design D2: per-provider breaker, single failure doesn't block others.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Protocol

from schema import PaperCanonical, PaperEnrichment, _gen_id, _utc_now
from providers.base import BaseEnrichmentProvider, ProviderResult


class StoreProto(Protocol):
    def upsert(self, entity: object) -> None: ...
    def get(self, table: str, pk_value: str) -> Optional[object]: ...


_ENRICHMENT_TTL_DAYS = 30


def _ttl_expiry() -> str:
    expiry = datetime.now(timezone.utc) + timedelta(days=_ENRICHMENT_TTL_DAYS)
    return expiry.strftime("%Y-%m-%dT%H:%M:%SZ")


class Enricher:
    def __init__(self, store: StoreProto) -> None:
        self._store = store

    def enrich_hf(self, canonical: PaperCanonical, provider: BaseEnrichmentProvider) -> ProviderResult:
        return provider.enrich(canonical)

    def enrich_arxiv(self, canonical: PaperCanonical, provider: BaseEnrichmentProvider) -> ProviderResult:
        return provider.enrich(canonical)

    def enrich_hf_assets(self, canonical: PaperCanonical, provider: BaseEnrichmentProvider) -> ProviderResult:
        return provider.enrich(canonical)

    def enrich_all(self, canonical: PaperCanonical,
                   providers: dict[str, BaseEnrichmentProvider]) -> PaperEnrichment:
        results: dict[str, ProviderResult] = {}
        for name, provider in providers.items():
            results[name] = provider.enrich(canonical)

        return self.merge_provider_payloads(canonical.paper_id, results)

    def merge_provider_payloads(self, paper_id: str,
                                results: dict[str, ProviderResult]) -> PaperEnrichment:
        success_data: dict[str, dict] = {}
        failures: dict[str, str] = {}
        hf_metadata: dict = {}
        arxiv_metadata: dict = {}
        hf_assets: dict = {}

        for name, result in results.items():
            if result.success:
                success_data[name] = result.data
                if name == "huggingface":
                    hf_metadata = result.data
                elif name == "arxiv":
                    arxiv_metadata = result.data
                elif name == "hf_assets":
                    hf_assets = result.data
            else:
                failures[name] = result.error

        now = _utc_now()
        enrichment = PaperEnrichment(
            enrichment_id=_gen_id("enr-"),
            paper_id=paper_id,
            hf_metadata_json=json.dumps(hf_metadata),
            arxiv_metadata_json=json.dumps(arxiv_metadata),
            hf_assets_json=json.dumps(hf_assets),
            github_repo_json="{}",
            semantic_scholar_json="{}",
            provider_success_json=json.dumps(list(success_data.keys())),
            provider_failures_json=json.dumps(failures),
            fetched_at=now,
            ttl_expires_at=_ttl_expiry(),
        )
        return enrichment
