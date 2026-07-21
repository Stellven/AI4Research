"""HardBlockerGuard — gate the pipeline behind an upstream sprint PASS.

Per S03 design §C4 + dispatch C4 acceptance:
  - `HardBlockerGuard.check(blocker_id='browser-agent-global-operator-cutover') -> bool`
  - Mandatory at sprint dispatch — the pipeline calls `assert_ready()`
    before any real lease acquisition.
  - mock-mode (BROWSER_AGENT_MOCK_MODE=1): the guard reports
    `mock_ready=True` so the pipeline can proceed against the mock
    fixture. The blocker still gets logged in the resolution payload
    so handoff evidence captures which path was taken.
  - real-mode + blocker unmet: `assert_ready()` raises
    `BlockerNotResolved` so the call site never silently degrades.

Resolution backends:
  - `FileLookupResolver` — reads `~/.solar/harness/sprints/<id>.status.json`
    (the canonical sprint-status file) and returns True iff the
    document's `status` field is `"passed"`. This is the default.
  - `CallableResolver` — wraps any zero-arg callable returning bool, for
    tests and future remote lookups.

The guard purposefully does NOT consult external network resources —
S03 stop rule "不真跑 browser_agent" forbids it.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol

from .mock_browser_fixture import MOCK_MODE_ENV_VAR, mock_mode_enabled
from .operator_lease_manager import BlockerNotResolved

logger = logging.getLogger(__name__)

# The single upstream sprint the entire epic depends on. Encoded here so
# every collaborator that reads the guard sees the same id.
DEFAULT_BLOCKER_ID = "sprint-20260525-browser-agent-global-operator-cutover"

# Default location for the status sidecar the file resolver consults.
DEFAULT_SPRINT_DIR = Path.home() / ".solar" / "harness" / "sprints"


class BlockerResolver(Protocol):
    """Probes a blocker id and returns True iff the upstream is PASSED."""

    def resolve(self, blocker_id: str) -> bool: ...


@dataclass
class BlockerStatus:
    """Outcome of one `HardBlockerGuard.check` call."""

    blocker_id: str
    resolved: bool
    mock_ready: bool
    mode: str  # "mock" | "real"
    reason: str
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, object]:
        return {
            "blocker_id": self.blocker_id,
            "resolved": self.resolved,
            "mock_ready": self.mock_ready,
            "mode": self.mode,
            "reason": self.reason,
            "checked_at": self.checked_at,
        }


class FileLookupResolver:
    """Reads `<sprint_dir>/<blocker_id>.status.json` for `status == 'passed'`.

    The sprint-status sidecar is written by the coordinator when a
    sprint transitions to `passed`. Until the file exists the resolver
    returns False (= upstream not yet PASSED).
    """

    STATUS_PASSED = "passed"

    def __init__(self, sprint_dir: Path = DEFAULT_SPRINT_DIR) -> None:
        self._sprint_dir = Path(sprint_dir)

    def resolve(self, blocker_id: str) -> bool:
        path = self._sprint_dir / f"{blocker_id}.status.json"
        if not path.exists():
            return False
        try:
            with path.open("r", encoding="utf-8") as fp:
                doc = json.load(fp)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("blocker status file unreadable: %s (%s)", path, exc)
            return False
        return str(doc.get("status", "")).lower() == self.STATUS_PASSED


class CallableResolver:
    """Wraps a `Callable[[], bool]` as a `BlockerResolver`.

    Useful for tests (`CallableResolver(lambda: True)`) and for future
    swaps to a remote lookup.
    """

    def __init__(self, fn: Callable[[], bool]) -> None:
        self._fn = fn

    def resolve(self, blocker_id: str) -> bool:  # noqa: ARG002 — blocker id ignored
        try:
            return bool(self._fn())
        except Exception as exc:  # noqa: BLE001 — defensive: resolver is external
            logger.warning("CallableResolver raised %s — treating as unmet", exc)
            return False


class HardBlockerGuard:
    """Sprint-dispatch mandatory guard for the upstream blocker.

    Parameters:
        resolver: any `BlockerResolver`. Defaults to `FileLookupResolver`
                  reading the local harness sprint dir.
        blocker_id: the upstream sprint id to probe. Defaults to the
                    epic-level cutover sprint encoded above.
        mock_mode_probe: zero-arg callable returning True iff mock-mode
                         is enabled. Defaults to `mock_mode_enabled`
                         (which honours BROWSER_AGENT_MOCK_MODE).
    """

    def __init__(
        self,
        resolver: Optional[BlockerResolver] = None,
        *,
        blocker_id: str = DEFAULT_BLOCKER_ID,
        mock_mode_probe: Callable[[], bool] = mock_mode_enabled,
    ) -> None:
        self._resolver = resolver or FileLookupResolver()
        self._blocker_id = blocker_id
        self._mock_mode_probe = mock_mode_probe
        self._history: List[BlockerStatus] = []

    # ---- public API ---------------------------------------------------

    def check(self, blocker_id: Optional[str] = None) -> BlockerStatus:
        """Probe the blocker. Never raises — see `assert_ready` for that.

        Returns a `BlockerStatus` with mode = `"mock"` or `"real"`.
        """
        bid = blocker_id or self._blocker_id

        if self._mock_mode_probe():
            status = BlockerStatus(
                blocker_id=bid,
                resolved=False,
                mock_ready=True,
                mode="mock",
                reason=f"{MOCK_MODE_ENV_VAR}=1 — mock fixture path",
            )
            self._history.append(status)
            return status

        resolved = self._resolver.resolve(bid)
        status = BlockerStatus(
            blocker_id=bid,
            resolved=resolved,
            mock_ready=False,
            mode="real",
            reason=(
                "upstream sprint PASSED"
                if resolved
                else "upstream sprint not yet PASSED — real-mode forbidden"
            ),
        )
        self._history.append(status)
        return status

    def assert_ready(self, blocker_id: Optional[str] = None) -> BlockerStatus:
        """Mandatory call at dispatch time.

        - mock-mode: returns the mock_ready status (caller must use mock lease).
        - real-mode + resolved: returns the resolved status.
        - real-mode + unresolved: raises `BlockerNotResolved`.
        """
        status = self.check(blocker_id)
        if status.mode == "mock":
            return status  # mock_ready=True signals "use mock"
        if not status.resolved:
            raise BlockerNotResolved(status.blocker_id)
        return status

    # ---- accessors ----------------------------------------------------

    @property
    def blocker_id(self) -> str:
        return self._blocker_id

    @property
    def history(self) -> List[BlockerStatus]:
        return list(self._history)

    def as_lease_guard(self) -> Callable[[], bool]:
        """Adapter so `OperatorLeaseManager` / `BrowserLeaseClient` can
        consume the guard via their `blocker_guard` constructor arg
        (which expects a `Callable[[], bool]`)."""
        def _probe() -> bool:
            try:
                status = self.check()
            except Exception as exc:  # noqa: BLE001 — never propagate to lease
                logger.warning("guard probe raised %s — treating as unmet", exc)
                return False
            if status.mode == "mock":
                # mock_ready: tell the lease layer the blocker is "good"
                # so it picks the mock backend deliberately, not because
                # of guard exception fallback.
                return True
            return status.resolved
        return _probe


__all__ = [
    "DEFAULT_BLOCKER_ID",
    "DEFAULT_SPRINT_DIR",
    "BlockerStatus",
    "BlockerResolver",
    "FileLookupResolver",
    "CallableResolver",
    "HardBlockerGuard",
    "BlockerNotResolved",
]
