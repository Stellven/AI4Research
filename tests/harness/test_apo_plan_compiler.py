#!/usr/bin/env python3
"""Tests for explicit APO plan compilation stages."""

from __future__ import annotations

from pathlib import Path
import json
import sys
import yaml

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


def test_typed_composition_abi_is_executable_without_legacy_alias_adapter():
    request_envelope = "schema:request-envelope.schema.json"
    literature = "schema:schemas/evidence/literature_discovery.v1.schema.json"
    node = {
        "id": "discover",
        "goal": "Discover traceable scientific literature for the admitted request.",
        "logical_operator": "ScientificLiteratureDiscoverer",
        "type": "literature-discovery",
        "inputs": [request_envelope],
        "semantic_artifact_contract": {
            "consumes": [request_envelope],
            "produces": [{"artifact_type": literature}],
        },
        "capability_capsule_id": "cap.research-literature-discover",
        "dispatch_task_type": "scientific-research",
        "allowed_operators": {"role": "builder"},
    }

    plan = apo.build_capsule_plan_node(
        node,
        request_type="scientific-research",
        lane_hint="research",
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )

    assert [stage["stage_kind"] for stage in plan["stages"]] == ["capability"]
    assert plan["artifact_types"]["required_inputs"] == [request_envelope]
    assert plan["artifact_types"]["required_outputs"] == [literature]
    assert "artifact.discovery_query" not in plan["artifact_types"]["required_inputs"]


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


def test_physical_binding_excludes_fixture_operator_for_measured_capsule(tmp_path: Path):
    operators_path = tmp_path / "operators.json"
    operators_path.write_text(
        json.dumps(
            {
                "operators": {
                    "fixture-runner": {
                        "enabled": True,
                        "available": True,
                        "health_status": "ok",
                        "roles": ["builder"],
                        "execution_trust": "fixture_or_adapter_only",
                    },
                    "measured-runner": {
                        "enabled": True,
                        "available": True,
                        "health_status": "ok",
                        "roles": ["builder"],
                        "execution_trust": "measured_execution",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    capsule_plan_node = {
        "node_id": "run",
        "logical_operator": "ScientificExperimentRunner",
        "capability_capsule_id": "cap.real-experiment-run",
        "dispatch_task_type": "experiment-run",
        "role": "builder",
        "stages": [
            {
                "stage_id": "run:capability",
                "stage_kind": "capability",
                "dispatch_mode": "execute",
                "role": "builder",
                "task_type": "experiment-run",
                "operator_constraints": {},
                "required_execution_trust": "measured_execution",
            }
        ],
    }

    plan = apo.build_physical_plan_for_capsule_node(
        capsule_plan_node,
        operators_path=operators_path,
    )

    assert [row["operator_id"] for row in plan["execution_candidates"]] == [
        "measured-runner"
    ]
    fixture = next(
        row for row in plan["execution_excluded"] if row["operator_id"] == "fixture-runner"
    )
    assert fixture["reasons"] == ["EXECUTION_TRUST_UNSATISFIED"]


def test_registered_experiment_bridge_is_classified_fixture_only():
    node = {
        "id": "run",
        "goal": "Convert bounded fixture experiment evidence.",
        "logical_operator": "ScientificExperimentRunner",
        "type": "experiment-run",
        "capability_capsule_id": "cap.research-experiment-run",
        "dispatch_task_type": "experiment-run",
        "allowed_operators": {"role": "builder"},
    }

    capsule = apo.build_capsule_plan_node(
        node,
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    physical = apo.build_physical_plan_for_capsule_node(
        capsule,
        operators_path=ROOT / "config" / "physical-operators.json",
    )

    capability = next(
        stage for stage in capsule["stages"] if stage["stage_kind"] == "capability"
    )
    assert capability["required_execution_trust"] == "fixture_or_adapter_only"
    assert physical["selected_operator_id"] == "autosci-experiment-run-worker"


def test_native_idea_evaluation_and_experiment_design_bindings_are_exact():
    from plugins.autosci.operators.scientific_lifecycle.action import registry

    registrations = {
        row["node_id"]: row for row in registry.registration_entries()
    }
    operators = json.loads(
        (ROOT / "config" / "physical-operators.json").read_text(encoding="utf-8")
    )["operators"]
    expected = {
        "idea_evaluate": (
            "idea_evaluate_worker",
            "autosci-idea-evaluation-physical",
            "cap.research-idea-evaluate.yaml",
        ),
        "experiment_design": (
            "experiment_design_worker",
            "autosci-experiment-design-physical",
            "cap.research-experiment-design.yaml",
        ),
    }
    for node_id, (physical_id, implementation_id, manifest_name) in expected.items():
        assert registrations[node_id]["operator_id"] == implementation_id
        physical = operators[physical_id]
        assert physical["backend"] == "research_operator_registry"
        assert physical["execution_trust"] == "evidence_transform"
        assert physical["runtime_binding"] == {
            "registry": "plugins.autosci.operators.scientific_lifecycle.registry",
            "node_id": node_id,
            "implementation_operator_id": implementation_id,
        }
        manifest = yaml.safe_load(
            (ROOT / "capability-capsules" / manifest_name).read_text(encoding="utf-8")
        )
        assert manifest["operator_compatibility"]["preferred"] == [physical_id]
        assert manifest["implementation"]["trust_class"] == "evidence_transform"


def test_explicit_support_capsule_preference_wins_over_parent_logical_default():
    """Expanded support nodes keep the parent logical name but not its worker."""
    node = {
        "id": "design_support_paper",
        "goal": "Normalize the input paper for a later experiment design.",
        "logical_operator": "ScientificExperimentDesigner",
        "type": "paper-ingestion",
        "capability_capsule_id": "cap.research-paper-ingest",
        "dispatch_task_type": "paper-ingestion",
        "allowed_operators": {"role": "builder"},
    }

    capsule = apo.build_capsule_plan_node(
        node,
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
    )
    capability = next(
        stage for stage in capsule["stages"] if stage["stage_kind"] == "capability"
    )
    physical = apo.build_physical_plan_for_capsule_node(
        capsule,
        operators_path=ROOT / "config" / "physical-operators.json",
    )

    assert capability["operator_constraints"]["preferred"] == [
        "autosci-paper-ingest-worker"
    ]
    assert physical["selected_operator_id"] == "autosci-paper-ingest-worker"
