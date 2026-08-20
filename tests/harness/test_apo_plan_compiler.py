#!/usr/bin/env python3
"""Tests for explicit APO plan compilation stages."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = (Path(__file__).resolve().parents[2] / 'harness')
sys.path.insert(0, str(ROOT / "lib"))

import apo_plan_compiler as apo


def test_build_capsule_plan_node_inserts_guard_resource_and_verifier():
    node = {
        "id": "S2",
        "goal": "Implement the approved scope.",
        "logical_operator": "ImplementationWorker",
        "depends_on": ["S1"],
        "type": "implementation",
        "capability_native": True,
        "capability_capsule_id": "cap.requirement-compiler-implementation",
        "dispatch_task_type": "implementation",
        "capsule_plan": {
            "capability_native": True,
            "capability_capsule_id": "cap.requirement-compiler-implementation",
            "dispatch_task_type": "implementation",
            "logical_operator": "ImplementationWorker",
            "required_guard_capsules": ["guard.secret-leak-guard"],
            "required_resource_capsules": ["resource.repo-workspace"],
            "selected_skills": ["skill.multi-file-implementation"],
            "operator_constraints": {
                "preferred": ["mini-claude-sonnet-builder-2"],
                "forbidden": [],
                "default_operator_profile": "mini-claude-sonnet-builder-2",
            },
        },
    }
    plan = apo.build_capsule_plan_node(
        node,
        request_type="implementation",
        lane_hint="delivery",
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    assert [stage["stage_kind"] for stage in plan["stages"]] == [
        "guard",
        "resource",
        "capability",
        "verifier",
    ]
    assert plan["stages"][-1]["capability_capsule_id"] == "cap.requirement-compiler-verification"


def test_read_only_audit_plan_does_not_require_patch_diff():
    node = {
        "id": "A1",
        "goal": "Inventory backend entrypoints for packaging readiness without modifying source code.",
        "logical_operator": "ImplementationWorker",
        "depends_on": [],
        "type": "audit_inventory",
        "required_skills": ["documentation", "harness.reporting"],
        "write_scope": [
            "harness/sprints/sprint-x.audit-backend-entrypoints.md",
            "harness/sprints/sprint-x.audit-backend-entrypoints.json",
        ],
        "architecture_policy": {
            "package_boundary": "sprint-artifacts-only",
            "core_patch_allowed": False,
        },
    }
    plan = apo.build_capsule_plan_node(
        node,
        request_type="implementation",
        lane_hint="execution",
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    requirements = [item.get("requirement") for item in plan["proof_obligations"]]
    required_outputs = plan["artifact_types"]["required_outputs"]
    produced = plan["artifact_types"]["produces"]

    assert plan["capability_capsule_id"] == "cap.requirement-compiler-audit"
    assert "patch_diff exists" not in requirements
    assert not any(item.get("field") == "patch_diff" for item in plan["proof_obligations"])
    assert "diff" not in required_outputs
    assert "artifact.patch_diff" not in produced
    assert "handoff_md exists" in requirements


def test_empty_skill_bridge_falls_back_to_grounded_research_capsule():
    node = {
        "id": "R4",
        "goal": "Compile the grounded synthesis through the deterministic research compiler boundary.",
        "logical_operator": "GroundedResearchCompiler",
        "type": "research",
        "capability_capsule_id": "cap.skill-execution-bridge",
        "dispatch_task_type": "research",
        "selected_skills": [],
        "write_scope": ["workspace/research/report/"],
    }

    plan = apo.build_capsule_plan_node(
        node,
        request_type="research",
        lane_hint="research",
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )

    assert plan["capability_capsule_id"] == "cap.requirement-research-synthesizer"
    assert plan["dispatch_task_type"] == "research"
    assert plan["selected_skills"] == []
    capability_stages = [
        stage for stage in plan["stages"] if stage["stage_kind"] == "capability"
    ]
    assert len(capability_stages) == 1
    assert capability_stages[0]["capability_capsule_id"] == (
        "cap.requirement-research-synthesizer"
    )


def test_build_physical_plan_for_capsule_node_prefers_capsule_operator():
    capsule_plan_node = {
        "node_id": "S2",
        "logical_operator": "ImplementationWorker",
        "capability_capsule_id": "cap.requirement-compiler-implementation",
        "dispatch_task_type": "implementation",
        "role": "builder",
        "stages": [
            {
                "stage_id": "S2:capability",
                "stage_kind": "capability",
                "capability_capsule_id": "cap.requirement-compiler-implementation",
                "dispatch_mode": "execute",
                "role": "builder",
                "task_type": "implementation",
                "operator_constraints": {
                    "preferred": ["mini-claude-sonnet-builder-2"],
                    "forbidden": [],
                    "default_operator_profile": "mini-claude-sonnet-builder-2",
                },
            }
        ],
    }
    plan = apo.build_physical_plan_for_capsule_node(
        capsule_plan_node,
        require_dispatchable=False,
        operators_path=ROOT / "config" / "physical-operators.json",
    )
    assert plan["selected_operator_id"] == "mini-claude-sonnet-builder-2"
    assert plan["execution_candidates"][0]["operator_id"] == "mini-claude-sonnet-builder-2"
