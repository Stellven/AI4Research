"""BackendSelector — 4-tier fallback chain per S03 design §C4 + O1.

Order (per O1):
    1. browser_agent   (primary — requires HardBlockerGuard PASS or mock-mode)
    2. rss_public      (degraded)
    3. manual_curated  (manual fallback)
    4. x_api_optional  (optional last resort — only when explicitly enabled)

Selection policy:
  - CLI `--backend <name>` is the request. `auto` defers to this selector.
  - The selector probes each tier via a `BackendProbe`. The first probe
    that reports `available=True` wins.
  - `auto` mode walks the 4-tier list in order; any explicit (non-auto)
    backend must match a probe whose `available=True`. If the explicit
    backend is unavailable, the selector emits a `SelectionResult` with
    `fallback_from_explicit=True` and the next available tier.

The selector never raises — it always returns a `SelectionResult` (which
may carry `selected=None` if no tier is available, so the pipeline can
exit with `EXIT_LEASE_FALLBACK` and a clear status payload).

Per S03 design §C4 acceptance:
  - A-C4-1 4-tier fallback chain present.
  - A-C4-6 When hard_blocker unmet (and not mock-mode), the selector
    auto-falls back to rss; the lease is NOT called in real mode.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from .cli import (
    BACKEND_AUTO,
    BACKEND_BROWSER,
    BACKEND_CHOICES,
    BACKEND_MANUAL,
    BACKEND_RSS,
    BACKEND_X_API,
    CLI_TO_SCHEMA_BACKEND,
)
from .hard_blocker_guard import BlockerStatus, HardBlockerGuard
from .mock_browser_fixture import mock_mode_enabled
from .schema import (
    BACKEND_BROWSER_AGENT,
    BACKEND_MANUAL_CURATED,
    BACKEND_RSS_PUBLIC,
    BACKEND_X_API as SCHEMA_BACKEND_X_API,
)

logger = logging.getLogger(__name__)

# 4-tier order per O1. Names are schema-level (matching `PostRecord.collection_backend`).
TIER_ORDER: Tuple[str, ...] = (
    BACKEND_BROWSER_AGENT,
    BACKEND_RSS_PUBLIC,
    BACKEND_MANUAL_CURATED,
    SCHEMA_BACKEND_X_API,
)

# CLI alias → schema name. Mirrors `cli.CLI_TO_SCHEMA_BACKEND` for clarity.
_CLI_ALIAS = dict(CLI_TO_SCHEMA_BACKEND)
# Auto request — resolved by walking TIER_ORDER.
_AUTO = BACKEND_AUTO


# ---------------------------------------------------------------------------
# Probe protocol
# ---------------------------------------------------------------------------


@dataclass
class ProbeResult:
    """One probe outcome — does this backend have capacity right now?"""

    backend: str
    available: bool
    reason: str
    details: Mapping[str, object] = field(default_factory=dict)


ProbeFn = Callable[[], ProbeResult]


# ---------------------------------------------------------------------------
# Selection result
# ---------------------------------------------------------------------------


@dataclass
class SelectionResult:
    """Final selector verdict surfaced to the pipeline.

    `selected` is the schema-level backend name (e.g. `browser_agent`) or
    `None` if every tier failed. `walked` lists the probes in order so
    the handoff evidence can show "browser_agent unavailable: reason X,
    fell through to rss_public".
    """

    requested: str
    selected: Optional[str]
    fallback_from_explicit: bool
    walked: List[ProbeResult]
    blocker_status: Optional[BlockerStatus] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "requested": self.requested,
            "selected": self.selected,
            "fallback_from_explicit": self.fallback_from_explicit,
            "walked": [
                {
                    "backend": p.backend,
                    "available": p.available,
                    "reason": p.reason,
                }
                for p in self.walked
            ],
            "blocker_status": (
                self.blocker_status.to_dict() if self.blocker_status else None
            ),
        }


# ---------------------------------------------------------------------------
# BackendSelector
# ---------------------------------------------------------------------------


class BackendSelector:
    """4-tier backend selector with HardBlockerGuard integration.

    Constructor parameters:
        guard: `HardBlockerGuard`. When the guard reports the upstream
               unmet AND mock-mode is off, the `browser_agent` probe
               returns `available=False, reason="hard_blocker_unmet"`
               and the selector falls through to RSS/manual.
        probes: optional mapping of schema-backend → `ProbeFn`. Probes
                that return `available=True` win. Defaults to a set of
                conservative probes:
                    - browser_agent: requires guard.check().mock_ready
                                      or guard.check().resolved.
                    - rss_public: always available (it is a public feed).
                    - manual_curated: available iff `manual_enabled=True`
                                      was passed to the constructor.
                    - x_api: available iff `x_api_enabled=True` was passed.
        manual_enabled: opt-in flag for the manual tier (default False).
        x_api_enabled: opt-in flag for the x_api tier (default False).
    """

    def __init__(
        self,
        guard: Optional[HardBlockerGuard] = None,
        *,
        probes: Optional[Mapping[str, ProbeFn]] = None,
        manual_enabled: bool = False,
        x_api_enabled: bool = False,
    ) -> None:
        self._guard = guard or HardBlockerGuard()
        self._manual_enabled = manual_enabled
        self._x_api_enabled = x_api_enabled
        self._probes: Dict[str, ProbeFn] = (
            dict(probes) if probes is not None else self._default_probes()
        )

    # ---- public API ---------------------------------------------------

    def select(self, requested: str = _AUTO) -> SelectionResult:
        """Return the SelectionResult for the requested CLI backend."""
        if requested not in BACKEND_CHOICES:
            return SelectionResult(
                requested=requested,
                selected=None,
                fallback_from_explicit=False,
                walked=[
                    ProbeResult(
                        backend=requested,
                        available=False,
                        reason=f"unknown_backend:{requested!r}",
                    )
                ],
            )

        schema_explicit: Optional[str]
        if requested == _AUTO:
            schema_explicit = None
        else:
            schema_explicit = _CLI_ALIAS[requested]

        walked: List[ProbeResult] = []
        # Probe in TIER_ORDER. Stop at the first available tier.
        # For explicit (non-auto) requests, we still walk the whole list
        # so the caller can see why the requested backend was rejected.
        chosen: Optional[str] = None
        for backend in TIER_ORDER:
            probe = self._probes.get(backend, self._unavailable(backend, "no_probe"))
            result = probe()
            walked.append(result)
            if chosen is None and result.available:
                # auto: take the first available
                # explicit: must match requested
                if schema_explicit is None or backend == schema_explicit:
                    chosen = backend

        fallback_from_explicit = (
            schema_explicit is not None
            and chosen is not None
            and chosen != schema_explicit
        )

        # If explicit backend was requested but rejected, walk again for
        # the next available tier after the requested one.
        if schema_explicit is not None and chosen is None:
            for backend in TIER_ORDER:
                if backend == schema_explicit:
                    continue
                # Look up the probe result we already collected.
                cached = next(
                    (p for p in walked if p.backend == backend and p.available), None
                )
                if cached is not None:
                    chosen = backend
                    fallback_from_explicit = True
                    break

        return SelectionResult(
            requested=requested,
            selected=chosen,
            fallback_from_explicit=fallback_from_explicit,
            walked=walked,
            blocker_status=self._guard.check(),
        )

    # ---- introspection ------------------------------------------------

    @property
    def guard(self) -> HardBlockerGuard:
        return self._guard

    @property
    def probes(self) -> Mapping[str, ProbeFn]:
        return dict(self._probes)

    # ---- default probes ----------------------------------------------

    def _default_probes(self) -> Dict[str, ProbeFn]:
        return {
            BACKEND_BROWSER_AGENT: self._probe_browser_agent,
            BACKEND_RSS_PUBLIC: self._probe_rss,
            BACKEND_MANUAL_CURATED: self._probe_manual,
            SCHEMA_BACKEND_X_API: self._probe_x_api,
        }

    def _probe_browser_agent(self) -> ProbeResult:
        status = self._guard.check()
        if status.mode == "mock":
            return ProbeResult(
                backend=BACKEND_BROWSER_AGENT,
                available=True,
                reason="mock_mode",
                details={"blocker_status": status.to_dict()},
            )
        if status.resolved:
            return ProbeResult(
                backend=BACKEND_BROWSER_AGENT,
                available=True,
                reason="hard_blocker_passed",
                details={"blocker_status": status.to_dict()},
            )
        return ProbeResult(
            backend=BACKEND_BROWSER_AGENT,
            available=False,
            reason="hard_blocker_unmet",
            details={"blocker_status": status.to_dict()},
        )

    def _probe_rss(self) -> ProbeResult:
        # RSS uses public feed shapes (Nitter mirrors / X RSS bridge).
        # It needs no credentials and is treated as always available in
        # this layer; the pipeline is responsible for handling fetch
        # errors at runtime.
        return ProbeResult(
            backend=BACKEND_RSS_PUBLIC,
            available=True,
            reason="public_feed_default",
        )

    def _probe_manual(self) -> ProbeResult:
        if not self._manual_enabled:
            return ProbeResult(
                backend=BACKEND_MANUAL_CURATED,
                available=False,
                reason="manual_disabled",
            )
        return ProbeResult(
            backend=BACKEND_MANUAL_CURATED,
            available=True,
            reason="manual_enabled",
        )

    def _probe_x_api(self) -> ProbeResult:
        if not self._x_api_enabled:
            return ProbeResult(
                backend=SCHEMA_BACKEND_X_API,
                available=False,
                reason="x_api_disabled",
            )
        return ProbeResult(
            backend=SCHEMA_BACKEND_X_API,
            available=True,
            reason="x_api_enabled",
        )

    @staticmethod
    def _unavailable(backend: str, reason: str) -> ProbeFn:
        def _probe() -> ProbeResult:
            return ProbeResult(backend=backend, available=False, reason=reason)
        return _probe


__all__ = [
    "BackendSelector",
    "SelectionResult",
    "ProbeResult",
    "ProbeFn",
    "TIER_ORDER",
]
