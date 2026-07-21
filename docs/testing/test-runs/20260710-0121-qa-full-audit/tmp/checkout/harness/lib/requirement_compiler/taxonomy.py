"""Canonical taxonomy and legacy alias helpers for Requirement Compiler."""

from __future__ import annotations

IMPLEMENTATION = "implementation"
FULL_PRD = "full_prd"
RESEARCH = "research"

SHORT_IMPL = "short_impl"
FULL_SPEC = "full_spec"

LEGACY_TO_CANONICAL = {
    SHORT_IMPL: IMPLEMENTATION,
    FULL_SPEC: FULL_PRD,
    RESEARCH: RESEARCH,
    IMPLEMENTATION: IMPLEMENTATION,
    FULL_PRD: FULL_PRD,
}


def canonical_request_type(value: str) -> str:
    """Return the canonical request type for router/runtime consumers."""
    return LEGACY_TO_CANONICAL.get(value, value)


def classify_aliases(value: str) -> dict[str, str]:
    """Return both canonical and legacy labels for compatibility."""
    canonical = canonical_request_type(value)
    if canonical == IMPLEMENTATION:
        legacy = SHORT_IMPL
    elif canonical == FULL_PRD:
        legacy = FULL_SPEC
    else:
        legacy = RESEARCH
    return {
        "legacy_request_type": legacy,
        "canonical_request_type": canonical,
    }
