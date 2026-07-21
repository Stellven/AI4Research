"""Unit tests for fallback_policy.py — L1-L4 decision table.

Covers decide_fallback() with all 8 input combinations and
fallback_metadata() for each level.
"""

from harness.lib.research.fallback_policy import (
    FallbackLevel,
    decide_fallback,
    fallback_metadata,
)


class TestDecideFallback:
    """Decision table: (serper_ok, backend_returns_usage, fixture_available) -> level."""

    def test_l1_full_real(self):
        result = decide_fallback(serper_ok=True, backend_returns_usage=True, fixture_available=True)
        assert result is FallbackLevel.L1_FULL_REAL

    def test_l1_full_real_no_fixture(self):
        result = decide_fallback(serper_ok=True, backend_returns_usage=True, fixture_available=False)
        assert result is FallbackLevel.L1_FULL_REAL

    def test_l2_hybrid(self):
        result = decide_fallback(serper_ok=False, backend_returns_usage=True, fixture_available=True)
        assert result is FallbackLevel.L2_HYBRID

    def test_l2_hybrid_no_fixture(self):
        result = decide_fallback(serper_ok=False, backend_returns_usage=True, fixture_available=False)
        assert result is FallbackLevel.L2_HYBRID

    def test_l3_fixture(self):
        result = decide_fallback(serper_ok=False, backend_returns_usage=False, fixture_available=True)
        assert result is FallbackLevel.L3_FIXTURE

    def test_l4_tokenizer_declared(self):
        result = decide_fallback(serper_ok=False, backend_returns_usage=False, fixture_available=False)
        assert result is FallbackLevel.L4_TOKENIZER_DECLARED

    def test_serper_ok_but_no_usage_goes_l2(self):
        """serper_ok=True alone is not enough — backend must also return usage for L1."""
        result = decide_fallback(serper_ok=True, backend_returns_usage=False, fixture_available=True)
        assert result is FallbackLevel.L3_FIXTURE

    def test_serper_ok_no_usage_no_fixture(self):
        result = decide_fallback(serper_ok=True, backend_returns_usage=False, fixture_available=False)
        assert result is FallbackLevel.L4_TOKENIZER_DECLARED


class TestFallbackMetadata:
    """Each level must return correct metadata dict."""

    def test_l1_metadata(self):
        meta = fallback_metadata(FallbackLevel.L1_FULL_REAL)
        assert meta["usage_source"] == "provider_usage_ledger"
        assert meta["estimated"] is False
        assert meta["fallback_reason"] is None

    def test_l2_metadata(self):
        meta = fallback_metadata(FallbackLevel.L2_HYBRID)
        assert meta["usage_source"] == "hybrid"
        assert meta["estimated"] is True
        assert meta["fallback_reason"] == "serper_quota_or_timeout"

    def test_l3_metadata(self):
        meta = fallback_metadata(FallbackLevel.L3_FIXTURE)
        assert meta["usage_source"] == "estimated"
        assert meta["estimated"] is True

    def test_l4_metadata(self):
        meta = fallback_metadata(FallbackLevel.L4_TOKENIZER_DECLARED)
        assert meta["usage_source"] == "estimated"
        assert meta["estimated"] is True
        assert meta["fallback_reason"] == "all_unavailable"

    def test_returns_copy(self):
        m1 = fallback_metadata(FallbackLevel.L1_FULL_REAL)
        m1["usage_source"] = "tampered"
        m2 = fallback_metadata(FallbackLevel.L1_FULL_REAL)
        assert m2["usage_source"] == "provider_usage_ledger"
