"""OperatorLeaseManager — acquire/release the browser operator lease.

Per S02 A1 §1: "申请/释放 Browser lease via
`solar.physical_operator.browser.lease(...)`; 上游 hard_blocker 未 PASS →
manager 立即 raise `OperatorNotReady`."

Per dispatch C2 acceptance:
  - OperatorLeaseManager raises OperatorNotReady when blocker unmet;
    auto-switches to MockLease in mock-mode.
  - Lease retry behavior: 3 retries with jitter before giving up.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .browser_lease_client import BrowserLeaseClient, OperatorNotReady
from .mock_browser_fixture import MockBrowserBackend, mock_mode_enabled

logger = logging.getLogger(__name__)

# Retry policy — 3 retries means 1 initial + 2 retry attempts = 3 total attempts.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_JITTER_MIN_S = 0.5
DEFAULT_RETRY_JITTER_MAX_S = 2.0


class BlockerNotResolved(OperatorNotReady):
    """Specialisation of OperatorNotReady when HardBlockerGuard refuses.

    Subclasses `OperatorNotReady` so callers that catch the parent still
    work, while tests can distinguish "blocker unmet" from "lease layer
    unavailable" via this subtype.
    """

    def __init__(self, blocker_id: str) -> None:
        self.blocker_id = blocker_id
        super().__init__(f"hard_blocker '{blocker_id}' not resolved")


@dataclass
class LeaseToken:
    """Token returned by `OperatorLeaseManager.acquire()`.

    Holds the live `BrowserLeaseClient` and metadata used by the caller
    to drive the 6-method surface and to surface diagnostics in the
    handoff / status surface.
    """

    client: BrowserLeaseClient
    is_mock: bool
    mode_reason: str
    attempts: int
    acquired_at: float
    account_id: Optional[str] = None
    history: List[str] = field(default_factory=list)
    released: bool = False


@dataclass
class _LeaseAttempt:
    attempt: int
    error: Optional[str]
    is_mock: bool
    timestamp: float


class OperatorLeaseManager:
    """Acquire/release wrapper around `BrowserLeaseClient` with retry + guard.

    Constructor parameters:
        blocker_guard: optional zero-arg callable that returns True iff
                       the upstream hard_blocker is resolved. When the
                       guard returns False AND mock-mode is off, the
                       manager raises BlockerNotResolved on acquire().
                       When the guard returns False AND mock-mode is on,
                       a MockLease is granted instead.
        blocker_id:    string identifier for diagnostics
                       (defaults to the cutover sprint id).
        max_attempts:  retry budget for acquire() (default 3).
        client_factory: zero-arg callable returning a BrowserLeaseClient.
                       Default constructs one wired with the same blocker
                       guard so the client picks the right backend.
        sleep_fn:      injection point for tests to skip real sleeping.
        rng:           injection point for deterministic jitter.
    """

    DEFAULT_BLOCKER_ID = "sprint-20260525-browser-agent-global-operator-cutover"

    def __init__(
        self,
        *,
        blocker_guard: Optional[Callable[[], bool]] = None,
        blocker_id: str = DEFAULT_BLOCKER_ID,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        client_factory: Optional[Callable[[], BrowserLeaseClient]] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        rng: Optional[random.Random] = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {max_attempts!r}")
        self._blocker_guard = blocker_guard
        self._blocker_id = blocker_id
        self._max_attempts = max_attempts
        self._sleep = sleep_fn
        self._rng = rng if rng is not None else random.Random()
        self._client_factory = client_factory or self._default_client_factory
        self._attempts_log: List[_LeaseAttempt] = []

    def _default_client_factory(self) -> BrowserLeaseClient:
        return BrowserLeaseClient(blocker_guard=self._blocker_guard)

    # ---- blocker check ------------------------------------------------

    def _blocker_passed(self) -> bool:
        if self._blocker_guard is None:
            return True
        try:
            return bool(self._blocker_guard())
        except Exception as exc:  # noqa: BLE001
            logger.warning("blocker_guard raised %s — treating as unmet", exc)
            return False

    # ---- public API ---------------------------------------------------

    def acquire(
        self,
        *,
        account_id: Optional[str] = None,
        block_on_blocker_in_real_mode: bool = True,
    ) -> LeaseToken:
        """Acquire a browser lease.

        Behaviour:
          - mock-mode (BROWSER_AGENT_MOCK_MODE=1): always returns a MockLease,
            even if blocker_guard fails. mode_reason='env_mock_mode'.
          - real-mode + blocker_guard returns False + block_on_blocker_in_real_mode=True:
            raises BlockerNotResolved.
          - real-mode + blocker_guard ok (or absent): asks client_factory for
            a real client. If the factory raises OperatorNotReady, retries
            up to max_attempts with jitter before re-raising the last error.
        """
        # Branch 1 — explicit env mock-mode dominates.
        if mock_mode_enabled():
            return self._grant_mock_lease(
                account_id=account_id, mode_reason="env_mock_mode", attempts=1
            )

        # Branch 2 — blocker check.
        if not self._blocker_passed():
            if block_on_blocker_in_real_mode:
                raise BlockerNotResolved(self._blocker_id)
            return self._grant_mock_lease(
                account_id=account_id,
                mode_reason="blocker_guard_unmet",
                attempts=1,
            )

        # Branch 3 — try real client with retries.
        last_error: Optional[OperatorNotReady] = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                client = self._client_factory()
            except OperatorNotReady as exc:
                self._attempts_log.append(
                    _LeaseAttempt(
                        attempt=attempt,
                        error=str(exc),
                        is_mock=False,
                        timestamp=time.time(),
                    )
                )
                last_error = exc
                if attempt < self._max_attempts:
                    self._sleep(self._jitter_delay())
                continue

            self._attempts_log.append(
                _LeaseAttempt(
                    attempt=attempt,
                    error=None,
                    is_mock=client.is_mock,
                    timestamp=time.time(),
                )
            )
            return LeaseToken(
                client=client,
                is_mock=client.is_mock,
                mode_reason=client.mode_reason,
                attempts=attempt,
                acquired_at=time.time(),
                account_id=account_id,
                history=[
                    f"attempt={a.attempt} ok={a.error is None} mock={a.is_mock}"
                    for a in self._attempts_log
                ],
            )

        # Exhausted retries — re-raise last error.
        assert last_error is not None
        raise last_error

    def release(self, token: LeaseToken) -> Dict[str, object]:
        """Release the underlying lease. Idempotent."""
        if token.released:
            return {"ok": True, "released": True, "idempotent": True}
        result = token.client.release()
        token.released = True
        token.history.append("released")
        return result

    # ---- helpers ------------------------------------------------------

    def _grant_mock_lease(
        self,
        *,
        account_id: Optional[str],
        mode_reason: str,
        attempts: int,
    ) -> LeaseToken:
        client = BrowserLeaseClient(backend=MockBrowserBackend())
        self._attempts_log.append(
            _LeaseAttempt(
                attempt=attempts,
                error=None,
                is_mock=True,
                timestamp=time.time(),
            )
        )
        return LeaseToken(
            client=client,
            is_mock=True,
            mode_reason=mode_reason,
            attempts=attempts,
            acquired_at=time.time(),
            account_id=account_id,
            history=[f"mock_lease:{mode_reason}"],
        )

    def _jitter_delay(self) -> float:
        return self._rng.uniform(
            DEFAULT_RETRY_JITTER_MIN_S, DEFAULT_RETRY_JITTER_MAX_S
        )

    # ---- introspection -----------------------------------------------

    @property
    def attempts_log(self) -> List[_LeaseAttempt]:
        return list(self._attempts_log)

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def blocker_id(self) -> str:
        return self._blocker_id


class MockLease:
    """Sentinel marker — `LeaseToken.is_mock` is True iff this would apply.

    Kept as a class for callers that wish to use `isinstance` against the
    token's backend object: `isinstance(token.client.backend, MockLease)`.
    Effectively an alias of `MockBrowserBackend` for naming clarity.
    """

    def __new__(cls, *args, **kwargs):  # noqa: D401 — factory
        return MockBrowserBackend(*args, **kwargs)
