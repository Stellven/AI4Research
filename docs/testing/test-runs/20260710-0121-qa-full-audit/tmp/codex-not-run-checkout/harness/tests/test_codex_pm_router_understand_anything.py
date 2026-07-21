#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import codex_pm_router as router  # noqa: E402


def test_node_enrichment_promotes_understand_anything_to_code_understanding():
    node = {
        "id": "R1",
        "logical_operator": "ResearchScout",
        "goal": "Build codebase knowledge graph and onboarding architecture map for this repo",
    }
    enriched = router._node_enrichment("research", "delivery", node)
    assert enriched["capability_capsule_id"] == "cap.understand-anything-indexer"
    assert enriched["dispatch_task_type"] == "code-understanding"
    assert enriched["type"] == "code-understanding"
    assert "code-understanding" in enriched["signals"]
    assert "knowledge-graph" in enriched["signals"]
    assert enriched["outputs"] == ["knowledge-graph.json", "meta.json", "chunk-manifest.json", "resume-state.json"]
    assert enriched["validation"][0]["target"] == "knowledge-graph.json"
