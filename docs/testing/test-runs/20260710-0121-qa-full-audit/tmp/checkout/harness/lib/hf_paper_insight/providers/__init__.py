"""Provider adapters for HF Paper Insight enrichment."""
from .base import BaseEnrichmentProvider, ProviderResult
from .hf_provider import HFProvider
from .arxiv_provider import ArxivProvider
from .hf_assets_provider import HFAssetsProvider

__all__ = [
    "BaseEnrichmentProvider",
    "ProviderResult",
    "HFProvider",
    "ArxivProvider",
    "HFAssetsProvider",
]
