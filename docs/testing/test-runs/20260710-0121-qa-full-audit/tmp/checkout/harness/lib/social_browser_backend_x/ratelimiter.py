"""RateLimiter for the social_browser_backend_x package — 5 knobs per O3.

Per S02 design §A1 RateLimiter:
  1. per_account_cooldown_seconds: tier1=180, tier2=600
  2. global_concurrency: 1 (硬性)
  3. jitter_range_seconds: ±5..15
  4. exponential_backoff: base=2, max=300s
  5. tier_frequency_separation: tier1 every 6h, tier2 every 24h

Per S02 OQ-06: rate_429 backoff is per-account (failure isolation).
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Knob constants — exact values frozen by the architecture contract
# ---------------------------------------------------------------------------

# Knob 1 — per-account cooldown
TIER1_COOLDOWN_SECONDS: int = 180
TIER2_COOLDOWN_SECONDS: int = 600

# Knob 2 — global concurrency
GLOBAL_CONCURRENCY: int = 1

# Knob 3 — jitter range (seconds), uniform random within [JITTER_MIN, JITTER_MAX]
JITTER_MIN_SECONDS: int = 5
JITTER_MAX_SECONDS: int = 15

# Knob 4 — exponential backoff
BACKOFF_BASE: int = 2
BACKOFF_MAX_SECONDS: int = 300

# Knob 5 — tier scan frequency
TIER1_SCAN_INTERVAL_SECONDS: int = 6 * 3600   # 6 hours
TIER2_SCAN_INTERVAL_SECONDS: int = 24 * 3600  # 24 hours

# Failure trigger types (per O3 "on (login_fail/rate_429/parse_fail)")
FAILURE_TRIGGERS = frozenset({"login_fail", "rate_429", "parse_fail"})


class RateLimitExceeded(RuntimeError):
    """Raised when an acquire() is attempted while the account is in cooldown."""

    def __init__(self, account_id: str, wait_seconds: float, reason: str = "") -> None:
        self.account_id = account_id
        self.wait_seconds = wait_seconds
        self.reason = reason
        super().__init__(
            f"RateLimitExceeded(account={account_id!r}, "
            f"wait={wait_seconds:.1f}s, reason={reason!r})"
        )


@dataclass
class AccountState:
    """Per-account rate-limit bookkeeping (per OQ-06: isolation)."""

    last_acquired_at: float = 0.0
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    failure_reason: Optional[str] = None
    history: list = field(default_factory=list)


def tier_cooldown(tier: int) -> int:
    """Return per-account cooldown seconds for the tier (1 or 2)."""
    if tier == 1:
        return TIER1_COOLDOWN_SECONDS
    if tier == 2:
        return TIER2_COOLDOWN_SECONDS
    raise ValueError(f"tier must be 1 or 2, got {tier!r}")


def tier_scan_interval(tier: int) -> int:
    """Return the scan-frequency interval (seconds) for the tier."""
    if tier == 1:
        return TIER1_SCAN_INTERVAL_SECONDS
    if tier == 2:
        return TIER2_SCAN_INTERVAL_SECONDS
    raise ValueError(f"tier must be 1 or 2, got {tier!r}")


def jitter_seconds(rng: Optional[random.Random] = None) -> float:
    """Uniform random jitter in [JITTER_MIN_SECONDS, JITTER_MAX_SECONDS]."""
    r = rng if rng is not None else random
    return r.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)


def backoff_seconds(consecutive_failures: int) -> float:
    """Exponential backoff: min(BACKOFF_BASE ** failures, BACKOFF_MAX_SECONDS).

    failure 1 → 2s, failure 2 → 4s, … failure 8 → 256s, failure 9+ → 300s.
    """
    if consecutive_failures <= 0:
        return 0.0
    capped = min(BACKOFF_BASE ** consecutive_failures, BACKOFF_MAX_SECONDS)
    return float(capped)


class RateLimiter:
    """5-knob rate limiter for X profile scanning.

    Usage:
        rl = RateLimiter()
        with rl.acquire(account_id="karpathy", tier=1):
            ...  # do the scan
        rl.record_failure("karpathy", reason="rate_429")
    """

    def __init__(
        self,
        *,
        clock: Optional[callable] = None,
        rng: Optional[random.Random] = None,
        max_concurrent: int = GLOBAL_CONCURRENCY,
    ) -> None:
        self._clock = clock or time.monotonic
        self._rng = rng
        self._max_concurrent = max_concurrent
        self._semaphore = threading.BoundedSemaphore(value=max_concurrent)
        self._lock = threading.Lock()
        self._accounts: Dict[str, AccountState] = {}

    # -- introspection of knob values ------------------------------------

    @staticmethod
    def knobs() -> Dict[str, object]:
        """Return all 5 knobs in a dict for handoff evidence."""
        return {
            "per_account_cooldown_seconds": {
                "tier1": TIER1_COOLDOWN_SECONDS,
                "tier2": TIER2_COOLDOWN_SECONDS,
            },
            "global_concurrency": GLOBAL_CONCURRENCY,
            "jitter_range_seconds": [JITTER_MIN_SECONDS, JITTER_MAX_SECONDS],
            "exponential_backoff": {
                "base": BACKOFF_BASE,
                "max_seconds": BACKOFF_MAX_SECONDS,
            },
            "tier_frequency_separation": {
                "tier1_seconds": TIER1_SCAN_INTERVAL_SECONDS,
                "tier2_seconds": TIER2_SCAN_INTERVAL_SECONDS,
            },
        }

    # -- core API --------------------------------------------------------

    def time_until_ready(self, account_id: str, tier: int) -> float:
        """Return seconds the caller must wait before acquire() will succeed.

        Computes the maximum of:
          - cooldown_until - now (exponential backoff)
          - tier cooldown since last acquire
        Returns 0.0 if ready immediately.
        """
        with self._lock:
            now = self._clock()
            st = self._accounts.get(account_id)
            if st is None:
                return 0.0

            wait = 0.0
            if st.cooldown_until > now:
                wait = max(wait, st.cooldown_until - now)
            since_last = now - st.last_acquired_at
            tier_wait = tier_cooldown(tier) - since_last
            if tier_wait > 0:
                wait = max(wait, tier_wait)
            return float(wait)

    def acquire(self, account_id: str, tier: int, *, block: bool = True) -> "_AcquireGuard":
        """Reserve the global slot AND the per-account cooldown.

        Returns a context-manager guard that releases the global slot on exit.
        Per OQ-06 the per-account cooldown is independent.

        If `block=False` and the account is in cooldown, raises RateLimitExceeded
        immediately without acquiring the global semaphore.
        """
        if tier not in (1, 2):
            raise ValueError(f"tier must be 1 or 2, got {tier!r}")

        wait = self.time_until_ready(account_id, tier)
        if wait > 0:
            if not block:
                raise RateLimitExceeded(account_id, wait, reason="cooldown_active")
            # Sleep for the wait; tests can inject a fake clock to skip.
            # Note: we sleep BEFORE taking the global semaphore so we don't
            # hog concurrency while waiting on a single account's cooldown.
            time.sleep(wait)

        acquired = self._semaphore.acquire(blocking=block, timeout=None)
        if not acquired:
            raise RateLimitExceeded(account_id, 0.0, reason="global_concurrency")

        with self._lock:
            st = self._accounts.setdefault(account_id, AccountState())
            st.last_acquired_at = self._clock()
            st.history.append(("acquire", st.last_acquired_at, tier))
        return _AcquireGuard(self, account_id, tier)

    def record_success(self, account_id: str) -> None:
        """Reset the consecutive failure counter for the account."""
        with self._lock:
            st = self._accounts.setdefault(account_id, AccountState())
            st.consecutive_failures = 0
            st.failure_reason = None
            st.cooldown_until = 0.0
            st.history.append(("success", self._clock(), None))

    def record_failure(self, account_id: str, *, reason: str) -> float:
        """Record a failure and compute the new cooldown_until.

        Per O3, only login_fail / rate_429 / parse_fail trigger backoff.
        Other reasons are recorded but do not extend the cooldown.

        Returns the cooldown delay (seconds) applied to this account.
        """
        if reason not in FAILURE_TRIGGERS:
            raise ValueError(
                f"reason must be one of {sorted(FAILURE_TRIGGERS)}, got {reason!r}"
            )
        with self._lock:
            st = self._accounts.setdefault(account_id, AccountState())
            st.consecutive_failures += 1
            delay = backoff_seconds(st.consecutive_failures)
            delay += jitter_seconds(self._rng)
            now = self._clock()
            st.cooldown_until = now + delay
            st.failure_reason = reason
            st.history.append(("failure", now, reason))
            return delay

    # -- internal --------------------------------------------------------

    def _release_slot(self, account_id: str) -> None:
        with self._lock:
            st = self._accounts.get(account_id)
            if st is not None:
                st.history.append(("release", self._clock(), None))
        self._semaphore.release()

    # -- snapshot for tests / status surface ----------------------------

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        with self._lock:
            return {
                acct: {
                    "last_acquired_at": st.last_acquired_at,
                    "consecutive_failures": st.consecutive_failures,
                    "cooldown_until": st.cooldown_until,
                    "failure_reason": st.failure_reason,
                }
                for acct, st in self._accounts.items()
            }


class _AcquireGuard:
    """Context manager returned by RateLimiter.acquire()."""

    def __init__(self, limiter: RateLimiter, account_id: str, tier: int) -> None:
        self._limiter = limiter
        self._account_id = account_id
        self._tier = tier
        self._released = False

    def __enter__(self) -> "_AcquireGuard":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
        return None

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._limiter._release_slot(self._account_id)

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def tier(self) -> int:
        return self._tier
