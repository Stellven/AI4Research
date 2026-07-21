"""Source connector registry — unified provider resolution seam.

Provides a single entry point for resolving search providers to their
connector implementations.  Replaces the hardcoded provider cascade in
cli.py:web_search() with a pluggable registry pattern.

Usage::

    from research.sources.registry import ConnectorRegistry

    registry = ConnectorRegistry.default()
    hits, errors = registry.search("query", max_results=10, provider="auto")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .base import BaseSourceConnector, FetchResult, SearchResult


# Type alias for lightweight search functions (serper_search, google_cse_search, etc.)
# These return (list[hit_dicts], list[error_strings]) — the legacy cli.py contract.
SearchFn = Callable[[str, int], tuple[list[dict], list[str]]]


@dataclass
class ProviderEntry:
    """A registered search provider with metadata and optional connector."""

    provider_id: str
    search_fn: SearchFn
    connector: Optional[BaseSourceConnector] = None
    priority: int = 0
    tags: list[str] = field(default_factory=list)


class ConnectorRegistry:
    """Pluggable registry for search providers.

    Providers are registered with a ``provider_id``, a ``search_fn``,
    and an optional ``BaseSourceConnector`` instance.  The ``search()``
    method resolves a provider name (or ``"auto"`` for cascade) and
    delegates to the registered function.
    """

    def __init__(self) -> None:
        self._providers: dict[str, ProviderEntry] = {}

    def register(
        self,
        provider_id: str,
        search_fn: SearchFn,
        *,
        connector: BaseSourceConnector | None = None,
        priority: int = 0,
        tags: list[str] | None = None,
    ) -> None:
        """Register a search provider."""
        self._providers[provider_id] = ProviderEntry(
            provider_id=provider_id,
            search_fn=search_fn,
            connector=connector,
            priority=priority,
            tags=tags or [],
        )

    def search(
        self,
        query: str,
        max_results: int,
        provider: str = "auto",
    ) -> tuple[list[dict], list[str]]:
        """Execute a search through the resolved provider.

        When *provider* is ``"auto"``, providers are tried in priority
        order until one returns hits.
        """
        if provider != "auto":
            entry = self._providers.get(provider)
            if entry is None:
                return [], [f"unknown search provider: {provider}"]
            return entry.search_fn(query, max_results)

        errors: list[str] = []
        for entry in self._sorted_providers():
            hits, provider_errors = entry.search_fn(query, max_results)
            errors.extend(provider_errors)
            if hits:
                return hits, errors
        return [], errors

    def fetch(self, source_id: str, provider_hint: str = "") -> FetchResult | None:
        """Fetch a source through its connector, if one is registered."""
        if provider_hint:
            entry = self._providers.get(provider_hint)
            if entry and entry.connector:
                return entry.connector.fetch(source_id)
        for entry in self._providers.values():
            if entry.connector:
                try:
                    result = entry.connector.fetch(source_id)
                    if result.fetch_status != "failed":
                        return result
                except Exception:
                    continue
        return None

    def get_connector(self, provider_id: str) -> BaseSourceConnector | None:
        """Return the connector for a provider, if registered."""
        entry = self._providers.get(provider_id)
        return entry.connector if entry else None

    def list_providers(self) -> list[dict[str, Any]]:
        """Return metadata for all registered providers."""
        return [
            {
                "provider_id": e.provider_id,
                "priority": e.priority,
                "tags": e.tags,
                "has_connector": e.connector is not None,
            }
            for e in self._sorted_providers()
        ]

    def _sorted_providers(self) -> list[ProviderEntry]:
        """Return providers sorted by priority (highest first)."""
        return sorted(self._providers.values(), key=lambda e: -e.priority)


def build_default_registry(
    serper_fn: SearchFn | None = None,
    google_cse_fn: SearchFn | None = None,
    google_cse_oauth_fn: SearchFn | None = None,
    google_cse_element_fn: SearchFn | None = None,
    arxiv_fn: SearchFn | None = None,
    browser_use_fn: SearchFn | None = None,
    http_fn: SearchFn | None = None,
) -> ConnectorRegistry:
    """Build a ConnectorRegistry with standard providers and priorities.

    Each ``*_fn`` argument is a ``(query, max_results) -> (hits, errors)``
    callable.  When *None*, that provider slot is skipped.
    """
    registry = ConnectorRegistry()

    if serper_fn:
        registry.register("serper", serper_fn, priority=100, tags=["web", "google"])
    if google_cse_fn:
        registry.register("google-cse", google_cse_fn, priority=90, tags=["web", "google"])
    if google_cse_oauth_fn:
        registry.register("google-cse-oauth", google_cse_oauth_fn, priority=85, tags=["web", "google"])
    if google_cse_element_fn:
        registry.register("google-cse-element", google_cse_element_fn, priority=80, tags=["web", "google"])
    if arxiv_fn:
        registry.register("arxiv", arxiv_fn, priority=70, tags=["academic", "paper"])
    if browser_use_fn:
        registry.register("browser-use", browser_use_fn, priority=50, tags=["web", "browser"])
    if http_fn:
        registry.register("http", http_fn, priority=10, tags=["web", "fallback"])

    return registry
