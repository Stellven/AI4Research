"""Convert bounded discovery hints to `literature_discovery.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    query = str(raw.get("query") or "solar-native scientific evidence adapters")
    candidates = list(raw.get("candidates") or [])
    if not candidates and raw.get("mode") == "fixture":
        candidates = [
        {
            "candidate_id": "candidate-autosci-fixture-paper",
            "title": "AutoSci Adapter Fixture Paper",
            "source_channels": ["local_fixture"],
            "ranking_score": 1.0,
            "ranking_rationale": "Fixture-mode candidate matches the requested Solar evidence adapter smoke test.",
            "dedup_status": "known",
            "fetch_status": "fetched",
            "source_ref": "plugins/autosci/tests/fixtures/sample_paper.md",
        }
        ]
    outputs: dict[str, Any] = {
        "query": query,
        "candidates": candidates,
        "mode": str(raw.get("mode") or "unknown"),
        "limit": int(raw.get("limit") or len(candidates) or 10),
    }
    for key in ("anchors", "negative_ids", "venue", "year", "source_fan_in", "source_provider_boundary"):
        if raw.get(key) not in (None, "", []):
            outputs[key] = raw[key]
    return evidence_base(
        "literature_discovery.v1",
        envelope,
        outputs,
        artifacts=list(raw.get("artifacts") or []),
        status=str(raw.get("status") or "completed"),
        limitations=list(raw.get("limitations") or ["Literature candidates require human review before ingest."]),
    )
