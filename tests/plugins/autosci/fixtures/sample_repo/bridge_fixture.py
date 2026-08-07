"""Fixture code path for Phase 10 code evidence mapping."""

from __future__ import annotations


def run_fixture_bridge() -> dict[str, str]:
    """Return a deterministic marker used by code evidence mapping tests."""
    return {
        "status": "completed",
        "artifact": "solar_evidence_abi",
    }
