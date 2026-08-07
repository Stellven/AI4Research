"""Convert AutoSci code evidence hints to `code_evidence_map.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    mappings = list(raw.get("mappings") or [{
        "mapping_id": "map-001",
        "claim_id": "claim-001",
        "repo_or_path": "tests/plugins/autosci/fixtures/sample_repo",
        "files": ["N/A"],
        "execution_entrypoint": "fixture-mode",
        "mapping_status": "unknown",
        "relevance_label": "unknown",
        "relevance_reason": "No code path was available to support this claim.",
        "evidence_ids": ["paper:sample#results"],
    }])
    return evidence_base(
        "code_evidence_map.v1",
        envelope,
        {"mappings": mappings},
        limitations=list(raw.get("limitations") or ["Fixture code mapping records explicit files when available; otherwise marks mappings unknown."]),
    )
