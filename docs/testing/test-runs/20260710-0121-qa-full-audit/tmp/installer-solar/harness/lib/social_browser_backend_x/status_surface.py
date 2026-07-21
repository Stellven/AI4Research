"""StatusSurface — 7 indicators emitted as JSON per S03 design §C5 + O8.

Per S03 design §C5 acceptance:
  - 7 indicators total:
      1. total            : configured account count (across all backends)
      2. enabled          : currently enabled / not paused
      3. scanned_today    : accounts whose `last_scan_at` falls inside the
                            current UTC day
      4. browser_ready    : 1 iff the browser-agent lease is wired and the
                            hard_blocker reports PASS (0 otherwise)
      5. scan_state       : `running` | `paused` | `failed` | `idle`
      6. parse_fail       : count of `parse_ok=False` records in the
                            current day (rolling 24h optional)
      7. fallback_count   : count of records collected via a non-primary
                            backend (i.e. anything other than
                            `browser_agent`) in the current day
   plus an auxiliary `by_backend_count` map for visibility — the map is
   *derived* from the 7 indicators and is NOT counted as an 8th indicator.

The surface accepts a single `StatusInput` payload (the pipeline owns
data collection) and returns a `dict` ready for `json.dumps(...)`. It
deliberately does not query the database itself — the CLI and the
dashboard supply pre-aggregated counters.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Tuple

# Single source of truth for indicator names. Mirrors S03 design §C5.
STATUS_INDICATORS: Tuple[str, ...] = (
    "total",
    "enabled",
    "scanned_today",
    "browser_ready",
    "scan_state",
    "parse_fail",
    "fallback_count",
)

VALID_SCAN_STATES: Tuple[str, ...] = ("running", "paused", "failed", "idle")

# Backend names align with `schema.VALID_BACKENDS` plus the implicit
# "unknown" fallback used by legacy rows.
DEFAULT_BACKEND_KEYS: Tuple[str, ...] = (
    "browser_agent",
    "rss_public",
    "manual_curated",
    "x_api",
)

PRIMARY_BACKEND = "browser_agent"


@dataclass
class StatusInput:
    """Aggregated counters the pipeline supplies to StatusSurface."""

    total_accounts: int
    enabled_accounts: int
    scanned_today: int
    browser_ready: bool
    scan_state: str
    parse_fail_count: int
    by_backend_count: Mapping[str, int] = field(default_factory=dict)

    def validate(self) -> None:
        if self.total_accounts < 0:
            raise ValueError("total_accounts must be >= 0")
        if self.enabled_accounts < 0 or self.enabled_accounts > self.total_accounts:
            raise ValueError("enabled_accounts must be in [0, total_accounts]")
        if self.scanned_today < 0:
            raise ValueError("scanned_today must be >= 0")
        if self.parse_fail_count < 0:
            raise ValueError("parse_fail_count must be >= 0")
        if self.scan_state not in VALID_SCAN_STATES:
            raise ValueError(
                f"scan_state must be one of {VALID_SCAN_STATES}, got {self.scan_state!r}"
            )
        for backend, count in self.by_backend_count.items():
            if count < 0:
                raise ValueError(f"by_backend_count[{backend!r}] must be >= 0")


class StatusSurface:
    """Render a StatusInput → 7-indicator JSON payload."""

    def __init__(self, *, backend_keys: Iterable[str] = DEFAULT_BACKEND_KEYS) -> None:
        self._backend_keys = tuple(backend_keys)

    @classmethod
    def indicator_names(cls) -> Tuple[str, ...]:
        return STATUS_INDICATORS

    @staticmethod
    def fallback_count(by_backend_count: Mapping[str, int]) -> int:
        """Sum of all non-`browser_agent` collections."""
        return sum(
            count
            for backend, count in by_backend_count.items()
            if backend != PRIMARY_BACKEND
        )

    def render(self, payload: StatusInput) -> Dict[str, object]:
        """Return a JSON-serialisable dict with the 7 indicators + map."""
        payload.validate()

        backend_map: Dict[str, int] = {key: 0 for key in self._backend_keys}
        for backend, count in payload.by_backend_count.items():
            backend_map[backend] = backend_map.get(backend, 0) + count

        fallback = self.fallback_count(backend_map)

        indicators: Dict[str, object] = {
            "total": payload.total_accounts,
            "enabled": payload.enabled_accounts,
            "scanned_today": payload.scanned_today,
            "browser_ready": 1 if payload.browser_ready else 0,
            "scan_state": payload.scan_state,
            "parse_fail": payload.parse_fail_count,
            "fallback_count": fallback,
        }
        # Aux map — informational only; not one of the 7 indicators.
        indicators["by_backend_count"] = backend_map
        return indicators

    def render_json(self, payload: StatusInput, *, indent: int = 2) -> str:
        return json.dumps(self.render(payload), indent=indent, sort_keys=False)
