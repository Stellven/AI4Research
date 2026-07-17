#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import codex_pm_router as router  # noqa: E402


def test_node_enrichment_does_not_promote_draft_understand_anything_surface():
    node = {
        "id": "R1",
        "logical_operator": "ResearchScout",
        "goal": "Build codebase knowledge graph and onboarding architecture map for this repo",
    }
    enriched = router._node_enrichment("research", "delivery", node)
    assert "capability_capsule_id" not in enriched
    assert "dispatch_task_type" not in enriched
    assert enriched["type"] == "research"
    assert enriched["outputs"] == ["source_manifest.json"]
