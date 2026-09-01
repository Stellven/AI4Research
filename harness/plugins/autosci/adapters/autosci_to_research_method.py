"""Convert AutoSci method data to `research_method.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    methods = list(raw.get("methods") or []) if "methods" in raw else [{
        "method_id": "method-001",
        "name": "Fixture evaluation protocol",
        "summary": "A bounded fixture protocol used to validate the adapter path.",
        "procedure": ["Load sample paper", "Extract a source-grounded claim", "Record fixture metrics"],
        "source_papers": ["paper-autosci-fixture"],
        "evidence_ids": ["paper:sample#method"],
    }]
    return evidence_base(
        "research_method.v1",
        envelope,
        {"methods": methods},
        limitations=list(raw.get("limitations") or ["Fixture method extraction uses local paper sections only."]),
    )
