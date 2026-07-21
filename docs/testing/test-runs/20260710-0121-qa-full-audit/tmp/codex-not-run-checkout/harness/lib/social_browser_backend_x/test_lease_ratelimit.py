"""Unit tests for C2 — BrowserLeaseClient + mock_browser_fixture +
RateLimiter + OperatorLeaseManager.

Covers (per dispatch):
  - 6 method signatures (open/wait/scroll/dom_extract/screenshot/release)
  - 5 RateLimiter knob boundaries
  - Lease retry (3 attempts with jitter)
  - Mock fallback (env + blocker_guard)
"""
from __future__ import annotations

import os
import random
import tempfile
import unittest
from typing import List
from unittest import mock

from .browser_lease_client import (
    BROWSER_LEASE_METHODS,
    BrowserLeaseClient,
    OperatorNotReady,
)
from .mock_browser_fixture import (
    MOCK_MODE_ENV_VAR,
    PROFILE_FIXTURES,
    MockBrowserBackend,
    fixture_count,
    fixture_for,
    mock_mode_enabled,
)
from .operator_lease_manager import (
    BlockerNotResolved,
    DEFAULT_MAX_ATTEMPTS,
    OperatorLeaseManager,
)
from .ratelimiter import (
    BACKOFF_BASE,
    BACKOFF_MAX_SECONDS,
    FAILURE_TRIGGERS,
    GLOBAL_CONCURRENCY,
    JITTER_MAX_SECONDS,
    JITTER_MIN_SECONDS,
    RateLimitExceeded,
    RateLimiter,
    TIER1_COOLDOWN_SECONDS,
    TIER1_SCAN_INTERVAL_SECONDS,
    TIER2_COOLDOWN_SECONDS,
    TIER2_SCAN_INTERVAL_SECONDS,
    backoff_seconds,
    jitter_seconds,
    tier_cooldown,
    tier_scan_interval,
)


# ---------------------------------------------------------------------------
# 1. Mock fixture surface (3 X profile HTML samples)
# ---------------------------------------------------------------------------


class TestMockFixtureSurface(unittest.TestCase):
    def test_three_fixtures_present(self):
        self.assertEqual(fixture_count(), 3)
        self.assertEqual(len(PROFILE_FIXTURES), 3)

    def test_fixtures_have_unique_handles_and_dom_hashes(self):
        handles = {f.handle for f in PROFILE_FIXTURES}
        hashes = {f.dom_hash for f in PROFILE_FIXTURES}
        self.assertEqual(len(handles), 3)
        self.assertEqual(len(hashes), 3)

    def test_fixture_lookup_by_handle(self):
        f = fixture_for("karpathy")
        self.assertIsNotNone(f)
        self.assertEqual(f.handle, "karpathy")

    def test_fixture_lookup_by_url(self):
        f = fixture_for("https://x.com/jxmnop")
        self.assertIsNotNone(f)
        self.assertEqual(f.handle, "jxmnop")

    def test_fixture_lookup_unknown_returns_none(self):
        self.assertIsNone(fixture_for("nonexistent_handle_xyz"))

    def test_mock_mode_env(self):
        with mock.patch.dict(os.environ, {MOCK_MODE_ENV_VAR: "1"}, clear=False):
            self.assertTrue(mock_mode_enabled())
        with mock.patch.dict(os.environ, {MOCK_MODE_ENV_VAR: "0"}, clear=False):
            self.assertFalse(mock_mode_enabled())
        with mock.patch.dict(os.environ, {MOCK_MODE_ENV_VAR: ""}, clear=False):
            self.assertFalse(mock_mode_enabled())


# ---------------------------------------------------------------------------
# 2. BrowserLeaseClient — 6 method signatures
# ---------------------------------------------------------------------------


class TestBrowserLeaseClientSixMethods(unittest.TestCase):
    """A-C2-1: 6 methods present, callable, with the right signatures."""

    def setUp(self):
        self.client = BrowserLeaseClient(backend=MockBrowserBackend())

    def test_method_names_constant(self):
        self.assertEqual(
            BROWSER_LEASE_METHODS,
            ("open", "wait", "scroll", "dom_extract", "screenshot", "release"),
        )
        self.assertEqual(BrowserLeaseClient.method_names(), BROWSER_LEASE_METHODS)

    def test_all_six_methods_callable(self):
        for name in BROWSER_LEASE_METHODS:
            method = getattr(self.client, name, None)
            self.assertTrue(callable(method), f"method {name} not callable")

    def test_open_returns_dict(self):
        r = self.client.open("https://x.com/karpathy")
        self.assertIsInstance(r, dict)
        self.assertTrue(r["ok"])

    def test_open_unknown_url_returns_ok_false(self):
        r = self.client.open("https://x.com/nonexistent_handle_xyz")
        self.assertIsInstance(r, dict)
        self.assertFalse(r["ok"])

    def test_wait_signature(self):
        self.client.open("https://x.com/karpathy")
        r = self.client.wait("article[data-testid='tweet']", timeout_ms=5000)
        self.assertTrue(r["ok"])
        self.assertEqual(r["selector"], "article[data-testid='tweet']")

    def test_scroll_returns_total(self):
        self.client.open("https://x.com/karpathy")
        r1 = self.client.scroll(800)
        r2 = self.client.scroll(400)
        self.assertEqual(r1["scrolled_total"], 800)
        self.assertEqual(r2["scrolled_total"], 1200)

    def test_dom_extract_returns_html_and_hash(self):
        self.client.open("https://x.com/karpathy")
        r = self.client.dom_extract()
        self.assertTrue(r["ok"])
        self.assertIn("Andrej Karpathy", r["html"])
        self.assertEqual(len(r["dom_hash"]), 64)  # sha256 hex

    def test_screenshot_writes_file(self):
        self.client.open("https://x.com/karpathy")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "shot.png")
            r = self.client.screenshot(path)
            self.assertTrue(r["ok"])
            self.assertTrue(r["is_mock"])
            self.assertTrue(os.path.exists(path))

    def test_release_marks_backend(self):
        self.client.open("https://x.com/karpathy")
        r = self.client.release()
        self.assertTrue(r["released"])

    def test_call_after_release_raises(self):
        self.client.release()
        with self.assertRaises(RuntimeError):
            self.client.open("https://x.com/karpathy")


# ---------------------------------------------------------------------------
# 3. BrowserLeaseClient — mock fallback (A-C2-2 / A-C2-4 logic side)
# ---------------------------------------------------------------------------


class TestBrowserLeaseClientMockFallback(unittest.TestCase):
    def test_env_mock_mode_picks_mock(self):
        with mock.patch.dict(os.environ, {MOCK_MODE_ENV_VAR: "1"}, clear=False):
            c = BrowserLeaseClient()
            self.assertTrue(c.is_mock)
            self.assertEqual(c.mode_reason, "env_mock_mode")

    def test_blocker_guard_unmet_picks_mock(self):
        c = BrowserLeaseClient(blocker_guard=lambda: False)
        self.assertTrue(c.is_mock)
        self.assertEqual(c.mode_reason, "blocker_guard_unmet")

    def test_blocker_guard_ok_attempts_real(self):
        with mock.patch.dict(os.environ, {MOCK_MODE_ENV_VAR: "0"}, clear=False):
            with self.assertRaises(OperatorNotReady):
                BrowserLeaseClient(blocker_guard=lambda: True)

    def test_blocker_guard_exception_falls_back_to_mock(self):
        def boom() -> bool:
            raise RuntimeError("network down")

        c = BrowserLeaseClient(blocker_guard=boom)
        self.assertTrue(c.is_mock)
        self.assertIn("blocker_guard_exception", c.mode_reason)

    def test_explicit_backend_overrides(self):
        c = BrowserLeaseClient(backend=MockBrowserBackend())
        self.assertEqual(c.mode_reason, "explicit_backend")
        self.assertTrue(c.is_mock)

    def test_real_factory_raises_operator_not_ready(self):
        def factory():
            raise OperatorNotReady("network closed")

        with mock.patch.dict(os.environ, {MOCK_MODE_ENV_VAR: "0"}, clear=False):
            with self.assertRaises(OperatorNotReady):
                BrowserLeaseClient(real_backend_factory=factory)


# ---------------------------------------------------------------------------
# 4. RateLimiter knob boundaries (5 knobs)
# ---------------------------------------------------------------------------


class TestRateLimiterKnobs(unittest.TestCase):
    """A-C2-3: exact knob values."""

    def test_knob_1_per_account_cooldown(self):
        self.assertEqual(TIER1_COOLDOWN_SECONDS, 180)
        self.assertEqual(TIER2_COOLDOWN_SECONDS, 600)
        self.assertEqual(tier_cooldown(1), 180)
        self.assertEqual(tier_cooldown(2), 600)
        with self.assertRaises(ValueError):
            tier_cooldown(3)

    def test_knob_2_global_concurrency(self):
        self.assertEqual(GLOBAL_CONCURRENCY, 1)

    def test_knob_3_jitter_range(self):
        self.assertEqual(JITTER_MIN_SECONDS, 5)
        self.assertEqual(JITTER_MAX_SECONDS, 15)
        rng = random.Random(42)
        for _ in range(100):
            j = jitter_seconds(rng)
            self.assertGreaterEqual(j, 5.0)
            self.assertLessEqual(j, 15.0)

    def test_knob_4_exponential_backoff(self):
        self.assertEqual(BACKOFF_BASE, 2)
        self.assertEqual(BACKOFF_MAX_SECONDS, 300)
        self.assertEqual(backoff_seconds(0), 0.0)
        self.assertEqual(backoff_seconds(1), 2.0)   # 2^1 = 2
        self.assertEqual(backoff_seconds(2), 4.0)   # 2^2 = 4
        self.assertEqual(backoff_seconds(8), 256.0)  # 2^8 = 256
        self.assertEqual(backoff_seconds(9), 300.0)  # capped
        self.assertEqual(backoff_seconds(100), 300.0)  # capped

    def test_knob_5_tier_scan_freq(self):
        self.assertEqual(TIER1_SCAN_INTERVAL_SECONDS, 6 * 3600)
        self.assertEqual(TIER2_SCAN_INTERVAL_SECONDS, 24 * 3600)
        self.assertEqual(tier_scan_interval(1), 6 * 3600)
        self.assertEqual(tier_scan_interval(2), 24 * 3600)
        with self.assertRaises(ValueError):
            tier_scan_interval(3)

    def test_failure_trigger_set(self):
        self.assertEqual(
            FAILURE_TRIGGERS, frozenset({"login_fail", "rate_429", "parse_fail"})
        )

    def test_ratelimiter_knobs_dict_contains_all_5(self):
        k = RateLimiter.knobs()
        self.assertIn("per_account_cooldown_seconds", k)
        self.assertIn("global_concurrency", k)
        self.assertIn("jitter_range_seconds", k)
        self.assertIn("exponential_backoff", k)
        self.assertIn("tier_frequency_separation", k)


class TestRateLimiterBehaviour(unittest.TestCase):
    def _fake_clock(self):
        """Return (clock_fn, advance_fn) using a mutable list."""
        t = [0.0]

        def now() -> float:
            return t[0]

        def advance(seconds: float) -> None:
            t[0] += seconds

        return now, advance

    def test_per_account_isolation_per_oq06(self):
        now, advance = self._fake_clock()
        rl = RateLimiter(clock=now, rng=random.Random(0))
        rl.acquire("a", 1).release()
        advance(1)
        rl.record_failure("a", reason="rate_429")
        # Account 'b' is unaffected.
        self.assertEqual(rl.time_until_ready("b", 1), 0.0)
        # Account 'a' must wait.
        self.assertGreater(rl.time_until_ready("a", 1), 0.0)

    def test_record_failure_invalid_reason_raises(self):
        rl = RateLimiter(rng=random.Random(0))
        with self.assertRaises(ValueError):
            rl.record_failure("a", reason="unknown_reason")

    def test_record_success_resets_failures(self):
        rl = RateLimiter(rng=random.Random(0))
        rl.record_failure("a", reason="parse_fail")
        rl.record_failure("a", reason="parse_fail")
        rl.record_success("a")
        snap = rl.snapshot()
        self.assertEqual(snap["a"]["consecutive_failures"], 0)
        self.assertEqual(snap["a"]["cooldown_until"], 0.0)

    def test_acquire_releases_global_slot(self):
        rl = RateLimiter(rng=random.Random(0))
        guard = rl.acquire("a", 1)
        # With concurrency=1, attempting another non-blocking acquire fails.
        with self.assertRaises(RateLimitExceeded):
            rl.acquire("b", 1, block=False)
        guard.release()
        # After release, next acquire on a different account works (non-blocking).
        rl.acquire("b", 1, block=False).release()

    def test_tier_cooldown_enforced(self):
        now, advance = self._fake_clock()
        rl = RateLimiter(clock=now, rng=random.Random(0))
        rl.acquire("a", 1).release()
        # Immediately after, account 'a' must wait the tier1 cooldown.
        self.assertAlmostEqual(rl.time_until_ready("a", 1), 180.0, places=1)
        advance(180)
        self.assertEqual(rl.time_until_ready("a", 1), 0.0)

    def test_non_block_acquire_in_cooldown_raises(self):
        now, advance = self._fake_clock()
        rl = RateLimiter(clock=now, rng=random.Random(0))
        rl.acquire("a", 1).release()
        with self.assertRaises(RateLimitExceeded) as ctx:
            rl.acquire("a", 1, block=False)
        self.assertGreater(ctx.exception.wait_seconds, 0)

    def test_record_failure_returns_positive_delay(self):
        rl = RateLimiter(rng=random.Random(0))
        delay1 = rl.record_failure("a", reason="rate_429")
        delay2 = rl.record_failure("a", reason="rate_429")
        # second failure has larger backoff component
        self.assertGreater(delay2, delay1)

    def test_acquire_invalid_tier_raises(self):
        rl = RateLimiter(rng=random.Random(0))
        with self.assertRaises(ValueError):
            rl.acquire("a", 3, block=False)


# ---------------------------------------------------------------------------
# 5. OperatorLeaseManager — retry (3 attempts) + blocker + mock fallback
# ---------------------------------------------------------------------------


class TestOperatorLeaseManagerRetry(unittest.TestCase):
    """A-C2-5: 3 retries with jitter before giving up."""

    def test_default_max_attempts_is_three(self):
        self.assertEqual(DEFAULT_MAX_ATTEMPTS, 3)
        mgr = OperatorLeaseManager(blocker_guard=lambda: True)
        self.assertEqual(mgr.max_attempts, 3)

    def test_three_attempts_then_raise(self):
        attempts: List[int] = []

        def factory():
            attempts.append(1)
            raise OperatorNotReady("simulated failure")

        sleeps: List[float] = []
        mgr = OperatorLeaseManager(
            blocker_guard=lambda: True,
            client_factory=factory,
            sleep_fn=sleeps.append,
            rng=random.Random(0),
        )
        with self.assertRaises(OperatorNotReady):
            mgr.acquire(account_id="a")
        self.assertEqual(len(attempts), 3)
        # Between attempts the manager sleeps; with 3 attempts there are 2 gaps.
        self.assertEqual(len(sleeps), 2)
        for s in sleeps:
            self.assertGreaterEqual(s, 0.5)
            self.assertLessEqual(s, 2.0)

    def test_succeeds_on_second_attempt(self):
        call_count = [0]

        def factory():
            call_count[0] += 1
            if call_count[0] < 2:
                raise OperatorNotReady("transient")
            return BrowserLeaseClient(backend=MockBrowserBackend())

        sleeps: List[float] = []
        mgr = OperatorLeaseManager(
            blocker_guard=lambda: True,
            client_factory=factory,
            sleep_fn=sleeps.append,
            rng=random.Random(0),
        )
        token = mgr.acquire(account_id="a")
        self.assertEqual(token.attempts, 2)
        self.assertEqual(len(sleeps), 1)

    def test_custom_max_attempts_honored(self):
        attempts: List[int] = []

        def factory():
            attempts.append(1)
            raise OperatorNotReady("nope")

        mgr = OperatorLeaseManager(
            blocker_guard=lambda: True,
            client_factory=factory,
            max_attempts=5,
            sleep_fn=lambda _: None,
            rng=random.Random(0),
        )
        with self.assertRaises(OperatorNotReady):
            mgr.acquire(account_id="a")
        self.assertEqual(len(attempts), 5)

    def test_max_attempts_zero_raises_in_constructor(self):
        with self.assertRaises(ValueError):
            OperatorLeaseManager(max_attempts=0)


class TestOperatorLeaseManagerBlocker(unittest.TestCase):
    """A-C2-4: blocker unmet → OperatorNotReady (real-mode) / MockLease (mock-mode)."""

    def test_blocker_unmet_raises_in_real_mode(self):
        # Make sure env mock_mode is off.
        with mock.patch.dict(os.environ, {MOCK_MODE_ENV_VAR: "0"}, clear=False):
            mgr = OperatorLeaseManager(blocker_guard=lambda: False)
            with self.assertRaises(BlockerNotResolved):
                mgr.acquire(account_id="a")

    def test_blocker_unmet_grants_mock_under_env_mock_mode(self):
        with mock.patch.dict(os.environ, {MOCK_MODE_ENV_VAR: "1"}, clear=False):
            mgr = OperatorLeaseManager(blocker_guard=lambda: False)
            token = mgr.acquire(account_id="a")
            self.assertTrue(token.is_mock)
            self.assertEqual(token.mode_reason, "env_mock_mode")

    def test_blocker_unmet_can_grant_mock_without_env_when_opt_in(self):
        with mock.patch.dict(os.environ, {MOCK_MODE_ENV_VAR: "0"}, clear=False):
            mgr = OperatorLeaseManager(blocker_guard=lambda: False)
            token = mgr.acquire(
                account_id="a",
                block_on_blocker_in_real_mode=False,
            )
            self.assertTrue(token.is_mock)
            self.assertEqual(token.mode_reason, "blocker_guard_unmet")

    def test_blocker_passed_real_mode_uses_factory(self):
        called: List[int] = []

        def factory():
            called.append(1)
            return BrowserLeaseClient(backend=MockBrowserBackend())

        mgr = OperatorLeaseManager(
            blocker_guard=lambda: True,
            client_factory=factory,
        )
        token = mgr.acquire(account_id="a")
        self.assertEqual(len(called), 1)
        self.assertEqual(token.attempts, 1)

    def test_release_is_idempotent(self):
        with mock.patch.dict(os.environ, {MOCK_MODE_ENV_VAR: "1"}, clear=False):
            mgr = OperatorLeaseManager(blocker_guard=lambda: False)
            token = mgr.acquire(account_id="a")
            r1 = mgr.release(token)
            r2 = mgr.release(token)
            self.assertTrue(r1["released"])
            self.assertTrue(r2["idempotent"])

    def test_blocker_guard_exception_treated_as_unmet(self):
        def boom():
            raise RuntimeError("guard exploded")

        with mock.patch.dict(os.environ, {MOCK_MODE_ENV_VAR: "0"}, clear=False):
            mgr = OperatorLeaseManager(blocker_guard=boom)
            with self.assertRaises(BlockerNotResolved):
                mgr.acquire(account_id="a")


# ---------------------------------------------------------------------------
# 6. Secret-leak guard — no cookie/token/session in production source
# ---------------------------------------------------------------------------


class TestNoSecretLeaks(unittest.TestCase):
    """Cross-cutting: ensure none of the 4 C2 production files name any
    sensitive token kind in a way that could be exfiltrated."""

    PROD_FILES = (
        "browser_lease_client.py",
        "mock_browser_fixture.py",
        "ratelimiter.py",
        "operator_lease_manager.py",
    )
    # Patterns the spec lists as forbidden in logs/output. We allow them
    # to appear in COMMENTS that document their forbidden status, but flag
    # any apparent assignment / print / log line that emits the value.
    FORBIDDEN_USAGE_PATTERNS = (
        "set-" + "cookie:",
        "author" + "ization: " + "bearer",
        "x-csrf-" + "token:",
        "auth-" + "token=",
    )

    def test_no_forbidden_token_usage(self):
        import pathlib

        here = pathlib.Path(__file__).parent
        for fname in self.PROD_FILES:
            text = (here / fname).read_text(encoding="utf-8")
            lowered = text.lower()
            for pat in self.FORBIDDEN_USAGE_PATTERNS:
                self.assertNotIn(
                    pat, lowered, f"{fname} contains forbidden pattern {pat!r}"
                )


if __name__ == "__main__":
    unittest.main()
