"""Abstract base class for DeepResearch source connectors.

Every connector implements search() and fetch(). No HTTP imports —
concrete connectors use subprocess calls to existing Solar-Harness
tools (mirage search, qmd-search, etc.) or read local files.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SearchResult:
    """Single hit from a source search."""
    source_id: str
    connector_id: str
    title: str
    url: Optional[str] = None
    snippet: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


@dataclass
class FetchResult:
    """Result of fetching a single source document."""
    source_id: str
    connector_id: str
    title: str
    raw_text: str
    content_length: int = 0
    source_url: Optional[str] = None
    fetch_status: str = "fetched"
    fetch_error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.content_length == 0 and self.raw_text:
            self.content_length = len(self.raw_text)
        if self.fetch_status == "failed" and not self.fetch_error:
            raise ValueError("FetchResult.fetch_error must be set when fetch_status='failed'")


class BaseSourceConnector(ABC):
    """Abstract source connector. Subclasses implement search() and fetch().

    No HTTP imports allowed — use subprocess, pathlib, or existing
    Solar-Harness CLI tools for data access.
    """

    connector_id: str
    connector_type: str
    source_tier: str
    display_name: str

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for attr in ("connector_id", "connector_type", "source_tier", "display_name"):
            if not hasattr(cls, attr):
                raise TypeError(f"SourceConnector subclass must define class attribute '{attr}'")

    @abstractmethod
    def search(self, query: str, max_hits: int = 10, **kwargs: Any) -> list[SearchResult]:
        """Search this source for hits matching query."""

    @abstractmethod
    def fetch(self, source_id: str) -> FetchResult:
        """Fetch full content for a single source_id."""

    def health_check(self) -> dict[str, Any]:
        """Return connector health status. Default: healthy."""
        return {
            "connector_id": self.connector_id,
            "status": "active",
            "message": "ok",
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.connector_id}>"
