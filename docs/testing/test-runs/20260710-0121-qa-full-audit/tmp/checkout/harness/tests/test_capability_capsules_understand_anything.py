#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import capability_capsules as cc  # noqa: E402


def test_understand_anything_default_plan_for_codebase_understanding_goal():
    plan = cc.default_capability_plan_for_logical_operator(
        "ResearchScout",
        request_type="research",
        lane_hint="delivery",
        node={"goal": "Build codebase knowledge graph and onboarding architecture map for this repo"},
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    assert plan["capability_capsule_id"] == "cap.understand-anything-indexer"
    assert plan["dispatch_task_type"] == "code-understanding"


def test_skill_driven_override_maps_knowledge_graph_builder(monkeypatch):
    monkeypatch.setenv("SOLAR_SKILL_OPERATOR_REGISTRY", str(ROOT / "config" / "skill-operator-bindings.yaml"))
    plan = cc.default_capability_plan_for_logical_operator(
        "KnowledgeGraphBuilder",
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    assert plan["capability_capsule_id"] == "cap.understand-anything-knowledge-graph-builder"
    assert plan["skill_driven_override"] is True
    assert plan["semantic_backend"] == "ThunderOMLX"
