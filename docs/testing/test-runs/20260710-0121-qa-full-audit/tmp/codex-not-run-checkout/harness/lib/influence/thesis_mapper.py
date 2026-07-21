"""L3 ThesisMappingOperator — reverse-map a Thesis to evidence sources.

Wires through to existing signal sources (e.g. ``scripts/tech_hotspot_radar.py``
for code/event signals, HF Paper Insight Flow connectors for papers). For MVP,
connectors that are not available emit empty buckets plus an explicit
``coverage_gap`` entry rather than failing (S1-design §11 risk 2). The radar call
is injectable so tests run without spawning subprocesses.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from .models import Thesis, empty_mapped_evidence

# A connector takes a Thesis and returns a list of evidence dicts for one bucket.
Connector = Callable[[Thesis], list[dict[str, Any]]]


def map_thesis(
    thesis: Thesis,
    connectors: Optional[dict[str, Connector]] = None,
) -> dict[str, Any]:
    """Build a mapped_evidence block for one thesis.

    ``connectors`` maps a bucket name (e.g. ``github_repos``) to a callable. Any
    bucket without a connector is left empty and recorded in ``coverage_gap``.
    """
    connectors = connectors or {}
    block = empty_mapped_evidence()
    for bucket in list(block.keys()):
        if bucket == "coverage_gap":
            continue
        connector = connectors.get(bucket)
        if connector is None:
            block["coverage_gap"].append(f"{bucket}_connector_missing")
            continue
        try:
            block[bucket] = list(connector(thesis))
        except Exception as exc:  # connector failures degrade, not crash
            block["coverage_gap"].append(f"{bucket}_connector_error:{type(exc).__name__}")
    return block


def has_any_evidence(block: dict[str, Any]) -> bool:
    return any(block.get(b) for b in block if b != "coverage_gap")
