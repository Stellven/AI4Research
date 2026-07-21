"""Fallback level decision logic for DeepResearch token usage reporting.

Implements the 4-level degradation policy frozen in S02 fallback-policy.json:
  L1_FULL_REAL         — Serper + backend with real usage ledger
  L2_HYBRID            — Internal mirage + backend with real usage
  L3_FIXTURE           — Local-command JSON fixture, estimated tokens
  L4_TOKENIZER_DECLARED — Tokenizer estimate with explicit handoff declaration
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class FallbackLevel(Enum):
    L1_FULL_REAL = 1
    L2_HYBRID = 2
    L3_FIXTURE = 3
    L4_TOKENIZER_DECLARED = 4


_FALLBACK_METADATA: dict[FallbackLevel, dict[str, Any]] = {
    FallbackLevel.L1_FULL_REAL: {
        "usage_source": "provider_usage_ledger",
        "estimated": False,
        "fallback_reason": None,
    },
    FallbackLevel.L2_HYBRID: {
        "usage_source": "hybrid",
        "estimated": True,
        "fallback_reason": "serper_quota_or_timeout",
    },
    FallbackLevel.L3_FIXTURE: {
        "usage_source": "estimated",
        "estimated": True,
        "fallback_reason": "cli_no_usage_or_rate_limit",
    },
    FallbackLevel.L4_TOKENIZER_DECLARED: {
        "usage_source": "estimated",
        "estimated": True,
        "fallback_reason": "all_unavailable",
    },
}


def decide_fallback(
    serper_ok: bool,
    backend_returns_usage: bool,
    fixture_available: bool,
) -> FallbackLevel:
    if serper_ok and backend_returns_usage:
        return FallbackLevel.L1_FULL_REAL
    if backend_returns_usage:
        return FallbackLevel.L2_HYBRID
    if fixture_available:
        return FallbackLevel.L3_FIXTURE
    return FallbackLevel.L4_TOKENIZER_DECLARED


def fallback_metadata(level: FallbackLevel) -> dict[str, Any]:
    return dict(_FALLBACK_METADATA[level])
