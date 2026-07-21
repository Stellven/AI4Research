"""Convert paper/memory hints to `research_memory_update.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    paper_id = str(raw.get("paper_id") or "paper-autosci-fixture")
    title = str(raw.get("title") or "AutoSci Fixture Paper")
    memory_path = str(raw.get("memory_path") or f"knowledge/research/papers/{paper_id}.md")
    evidence_ids = list(raw.get("evidence_ids") or [paper_id])
    changes = list(raw.get("changes") or [
        {
            "entity_type": "paper",
            "entity_id": paper_id,
            "operation": "propose",
            "path": memory_path,
            "evidence_ids": evidence_ids,
            "confidence": float(raw.get("confidence") or 0.9),
            "summary": f"Propose recording normalized metadata for {title}.",
        }
    ])
    return evidence_base(
        "research_memory_update.v1",
        envelope,
        {"changes": changes},
        artifacts=list(raw.get("artifacts") or []),
        status=str(raw.get("status") or "completed"),
        limitations=list(raw.get("limitations") or ["Fixture proposes a memory update; it does not mutate wiki state."]),
    )
