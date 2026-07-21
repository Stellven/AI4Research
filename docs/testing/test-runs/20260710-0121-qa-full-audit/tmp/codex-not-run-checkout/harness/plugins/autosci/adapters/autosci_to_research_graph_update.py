"""Convert paper relationship hints to `research_graph_update.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    paper_id = str(raw.get("paper_id") or "paper-autosci-fixture")
    source_ref = str(raw.get("source_ref") or "plugins/autosci/tests/fixtures/sample_paper.md")
    evidence_ids = list(raw.get("evidence_ids") or [paper_id])
    edges = list(raw.get("edges") or [
        {
            "source": paper_id,
            "target": "concept.solar_evidence_abi",
            "relation": "describes",
            "operation": "propose",
            "evidence_ids": evidence_ids,
        },
        {
            "source": paper_id,
            "target": source_ref,
            "relation": "has_source",
            "operation": "confirm",
            "evidence_ids": evidence_ids,
        },
    ])
    return evidence_base(
        "research_graph_update.v1",
        envelope,
        {"edges": edges},
        artifacts=list(raw.get("artifacts") or []),
        status=str(raw.get("status") or "completed"),
        limitations=list(raw.get("limitations") or ["Fixture graph update records explicit proposed edges only."]),
    )
