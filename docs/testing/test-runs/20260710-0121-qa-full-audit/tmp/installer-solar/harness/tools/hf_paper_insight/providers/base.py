"""Base enrichment provider with per-provider circuit breaker + exponential backoff.

Per design D2: per-provider breaker, no shared throttle.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol


class PaperCanonicalProto(Protocol):
    paper_id: str
    title: str
    hf_url: str
    arxiv_abs_url: Optional[str]
    arxiv_id: Optional[str]


@dataclass
class ProviderResult:
    success: bool
    data: dict = field(default_factory=dict)
    error: str = ""
    fetched_at: str = ""
    provider_name: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BaseEnrichmentProvider(ABC):
    """Abstract base with circuit breaker + exponential backoff."""

    name: str = "base"

    def __init__(
        self,
        *,
        max_consecutive_failures: int = 5,
        base_delay_s: float = 1.0,
        max_delay_s: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self._max_failures = max_consecutive_failures
        self._base_delay = base_delay_s
        self._max_delay = max_delay_s
        self._max_retries = max_retries
        self._consecutive_failures: int = 0
        self._last_failure_at: Optional[str] = None

    @abstractmethod
    def _fetch(self, canonical: PaperCanonicalProto) -> dict:
        """Subclass implements actual fetch logic. Returns parsed dict."""
        ...

    def enrich(self, canonical: PaperCanonicalProto) -> ProviderResult:
        if not self.is_available():
            return ProviderResult(
                success=False,
                error=f"circuit_breaker_open:{self._consecutive_failures}_failures",
                fetched_at=_utc_now(),
                provider_name=self.name,
            )

        last_error = ""
        for attempt in range(1, self._max_retries + 1):
            try:
                data = self._fetch(canonical)
                self._consecutive_failures = 0
                self._last_failure_at = None
                return ProviderResult(
                    success=True,
                    data=data,
                    fetched_at=_utc_now(),
                    provider_name=self.name,
                )
            except Exception as exc:
                last_error = str(exc)
                self._record_failure()

        return ProviderResult(
            success=False,
            error=f"all_{self._max_retries}_retries_failed:{last_error}",
            fetched_at=_utc_now(),
            provider_name=self.name,
        )

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        self._last_failure_at = _utc_now()

    def is_available(self) -> bool:
        return self._consecutive_failures < self._max_failures

    def backoff_delay(self, attempt: int) -> float:
        delay = self._base_delay * (2 ** (attempt - 1))
        return min(delay, self._max_delay)

    def reset(self) -> None:
        self._consecutive_failures = 0
        self._last_failure_at = None

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def last_failure_at(self) -> Optional[str]:
        return self._last_failure_at
