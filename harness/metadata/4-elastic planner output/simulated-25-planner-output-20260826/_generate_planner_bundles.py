#!/usr/bin/env python3
"""Create workflow-correct simulated planner bundles for the 25 live prompts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[2]
STAGE2 = HARNESS / "metadata" / "2-intent compiler output" / "live-25-prompt-pipeline-20260826"
STAGE3 = HARNESS / "metadata" / "3-requirements compiler output" / "live-25-prompt-pipeline-20260826"
STAGE4 = HERE
STAGE5 = HARNESS / "metadata" / "5-taskgraph compiler and validator output" / "simulated-25-planner-output-20260826"

BUILDER_FALLBACKS = [
    "mini-codex-gpt53-spark-builder-1",
    "mini-codex-gpt55-medium-builder-1",
]

RESEARCH_NODES = [
    (
        "seed_snapshot",
        "freeze_research_seed",
        "cap.research-seed-snapshot",
        ["autosci-research-synthesis-seed-fetch-worker", *BUILDER_FALLBACKS],
        [],
        ["solar.requirement_ir.v2"],
        ["research.seed_snapshot.v1"],
        "gate.seed_provenance.v1",
    ),
    (
        "source_discovery",
        "discover_public_sources",
        "cap.research-public-source-discovery",
        ["autosci-research-synthesis-source-discovery-worker", *BUILDER_FALLBACKS],
        ["seed_snapshot"],
        ["research.seed_snapshot.v1"],
        ["research.source_discovery.v1"],
        "gate.source_provenance.v1",
    ),
    (
        "source_validation",
        "validate_source_set",
        "cap.research-source-validation",
        ["autosci-research-synthesis-source-validation-worker", *BUILDER_FALLBACKS],
        ["source_discovery"],
        ["research.source_discovery.v1"],
        ["research.source_validation.v1"],
        "gate.source_validation.v1",
    ),
    (
        "evidence_synthesis",
        "synthesize_validated_evidence",
        "cap.research-evidence-synthesis",
        ["codex-research-evidence-synthesis-worker", *BUILDER_FALLBACKS],
        ["source_validation"],
        ["research.source_validation.v1", "research.seed_snapshot.v1"],
        ["research.evidence_synthesis.v1"],
        "gate.claim_grounding.v1",
    ),
    (
        "report_draft",
        "draft_requirement_complete_report",
        "cap.research-report-draft",
        ["codex-research-report-draft-worker", *BUILDER_FALLBACKS],
        ["evidence_synthesis"],
        ["research.evidence_synthesis.v1"],
        ["research.report.v1"],
        "gate.requirement_coverage.v1",
    ),
]

EXPERIMENT_NODES = [
    (
        "experiment_design",
        "design_bounded_experiment",
        "cap.research-experiment-design",
        ["autosci-experiment-design-worker", "autosci-exec-experiment-design-worker", *BUILDER_FALLBACKS],
        [],
        ["solar.requirement_ir.v2"],
        ["research.experiment_plan.v1"],
        "gate.experiment_design_complete.v1",
    ),
    (
        "experiment_run",
        "run_approved_bounded_experiment",
        "cap.research-experiment-run",
        ["autosci-experiment-run-worker", "autosci-exec-experiment-run-worker", *BUILDER_FALLBACKS],
        ["experiment_design"],
        ["research.experiment_plan.v1"],
        ["research.experiment_result.v1"],
        "gate.explicit_execution_approval.v1",
    ),
    (
        "claim_verification",
        "verify_experimental_claims",
        "cap.research-claim-verify",
        ["autosci-exec-claim-verification-worker", "autosci-research-poc-claim-verification-worker"],
        ["experiment_run"],
        ["research.experiment_result.v1"],
        ["research.claim_verdict.v1"],
        "gate.statistical_claim_support.v1",
    ),
    (
        "final_delivery",
        "deliver_requirement_complete_experiment_report",
        "cap.research-report-draft",
        ["autosci-exec-report-delivery-worker", "codex-research-report-draft-worker", *BUILDER_FALLBACKS],
        ["claim_verification"],
        ["research.experiment_result.v1", "research.claim_verdict.v1"],
        ["research.report.v1"],
        "gate.requirement_coverage.v1",
    ),
]

DIRECT_NODES = [
    (
        "direct_response",
        "compose_direct_user_response",
        "cap.unregistered.direct-response",
        BUILDER_FALLBACKS,
        [],
        ["solar.requirement_ir.v2"],
        ["solar.direct_response.v1"],
        "gate.requirement_coverage.v1",
    )
]


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_json_bytes(payload))
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _category(case_id: str) -> str:
    if "-experiment-" in case_id:
        return "experiment"
    if "-kid-" in case_id:
        return "direct_response"
    return "research"


def _node_payload(template: tuple[Any, ...], obligation_ids: list[str]) -> dict[str, Any]:
    node_id, logical, capsule, alternatives, dependencies, consumes, produces, gate = template
    return {
        "id": node_id,
        "logical_operator": logical,
        "capsule": capsule,
        "alternatives": alternatives,
        "depends_on": dependencies,
        "consumes": consumes,
        "produces": produces,
        "obligation_ids": obligation_ids,
        "gate": gate,
    }


def _catalog_snapshot() -> dict[str, Any]:
    capsules = []
    operators: dict[str, dict[str, Any]] = {}
    for template in [*RESEARCH_NODES, *EXPERIMENT_NODES, *DIRECT_NODES]:
        _, _, capsule, alternatives, _, consumes, produces, gate = template
        if not any(item["capsule_id"] == capsule for item in capsules):
            capsules.append(
                {
                    "capsule_id": capsule,
                    "inputs": consumes,
                    "outputs": produces,
                    "gate_id": gate,
                    "registered": not capsule.startswith("cap.unregistered."),
                }
            )
        for operator in alternatives:
            operators.setdefault(operator, {"operator_id": operator, "state": "CONFIGURED"})
    return {
        "schema_version": "solar.planning_catalog_snapshot.v1",
        "snapshot_id": "planning-catalog-live-25-20260826",
        "artifact_role": "control_or_support_artifact_not_planner_output",
        "capability_capsules": capsules,
        "physical_operators": list(operators.values()),
        "known_gaps": [
            {
                "capsule_id": "cap.unregistered.direct-response",
                "impact": "The five direct-answer plans are structurally complete but not capability-native dispatchable.",
            }
        ],
    }


def _accepted_bundle(case_id: str, requirement_path: Path, catalog_path: Path) -> dict[str, Any]:
    requirement = _read_json(requirement_path)
    obligation_ids = [str(item["requirement_id"]) for item in requirement["requirements"]]
    category = _category(case_id)
    templates = {
        "research": RESEARCH_NODES,
        "experiment": EXPERIMENT_NODES,
        "direct_response": DIRECT_NODES,
    }[category]
    strategy_id = f"strategy-{case_id}"
    strategy_path = STAGE4 / case_id / "strategy.json"
    plan_path = STAGE5 / case_id / "plan_ir.json"
    strategy = {
        "schema_version": "solar.workflow_strategy.v1",
        "strategy_id": strategy_id,
        "requirement_ir_ref": {
            "requirement_ir_id": requirement["requirement_ir_id"],
            "sha256": _sha256(requirement_path),
        },
        "strategy": "compose" if category != "direct_response" else "direct_response",
        "base_workflow": (
            "research.evidence_to_poc.v1" if category == "research" else
            "scientific_experiment_lifecycle_v1" if category == "experiment" else None
        ),
        "base_version": "1" if category != "direct_response" else None,
        "parameters": {
            "execution_mode": "approval_gated" if category == "experiment" else "bounded",
            "requirement_count": len(obligation_ids),
        },
        "topology_changes": [
            {
                "change": "Bind every requirement obligation to the final deliverable gate.",
                "required_by": obligation_ids,
            }
        ],
        "smallest_sufficient_reason": (
            "Use the smallest registered evidence workflow that discovers, validates, synthesizes, and reports sources."
            if category == "research"
            else "Use an approval-gated design, run, verification, and delivery chain."
            if category == "experiment"
            else "A one-node direct response is sufficient; no exact direct-response capability capsule is currently registered."
        ),
        "artifact_role": "simulated_planner_step_output",
    }
    _write_json(strategy_path, strategy)
    plan = {
        "schema_version": "solar.plan_ir.v1",
        "plan_ir_id": f"plan-ir-{case_id}",
        "strategy_ref": {"strategy_id": strategy_id, "sha256": _sha256(strategy_path)},
        "planning_catalog_ref": {
            "snapshot_id": "planning-catalog-live-25-20260826",
            "sha256": _sha256(catalog_path),
        },
        "nodes": [_node_payload(template, obligation_ids) for template in templates],
        "artifact_role": "simulated_planner_step_output_not_executed",
    }
    _write_json(plan_path, plan)
    manifest = {
        "case_id": case_id,
        "terminal_status": "planned",
        "artifacts": [
            {"path": str(strategy_path.relative_to(HARNESS)), "classification": "STEP_OUTPUT"},
            {"path": str(plan_path.relative_to(HARNESS)), "classification": "STEP_OUTPUT"},
        ],
        "dispatchable": category != "direct_response",
        "dispatch_blocker": (
            None if category != "direct_response" else "No registered direct-response capability capsule."
        ),
    }
    _write_json(STAGE4 / case_id / "bundle_manifest.json", manifest)
    return manifest


def _clarification_bundle(case_id: str) -> dict[str, Any]:
    acceptance_path = STAGE2 / case_id / "intent_acceptance.json"
    acceptance = _read_json(acceptance_path)
    halt_path = STAGE4 / case_id / "planning_halt.json"
    halt = {
        "schema_version": "solar.planning_halt.v1",
        "case_id": case_id,
        "reason": "requirement_compiler_handoff_not_allowed",
        "intent_acceptance_ref": {
            "acceptance_id": acceptance["acceptance_id"],
            "sha256": _sha256(acceptance_path),
        },
        "clarification_questions": acceptance.get("clarification_questions", []),
        "dispatch_allowed": False,
        "artifact_role": "control_or_support_artifact_not_planner_output",
    }
    _write_json(halt_path, halt)
    manifest = {
        "case_id": case_id,
        "terminal_status": "planning_not_entered",
        "artifacts": [
            {"path": str(halt_path.relative_to(HARNESS)), "classification": "CONTROL_OR_SUPPORT"}
        ],
        "dispatchable": False,
        "dispatch_blocker": "Intent acceptance requires clarification; no RequirementIR exists.",
    }
    _write_json(STAGE4 / case_id / "bundle_manifest.json", manifest)
    return manifest


def main() -> int:
    catalog_path = STAGE4 / "_support" / "planning_catalog_snapshot.json"
    _write_json(catalog_path, _catalog_snapshot())
    case_ids = sorted(
        path.name
        for path in STAGE2.iterdir()
        if path.is_dir() and (path / "pipeline_result.json").is_file()
    )
    manifests = []
    for case_id in case_ids:
        requirement_path = STAGE3 / case_id / "requirement_ir.json"
        if requirement_path.is_file():
            manifests.append(_accepted_bundle(case_id, requirement_path, catalog_path))
        else:
            manifests.append(_clarification_bundle(case_id))
    summary = {
        "schema_version": "solar.simulated_planner_bundle_run.v1",
        "case_count": len(manifests),
        "planner_output_count": sum(item["terminal_status"] == "planned" for item in manifests),
        "clarification_halt_count": sum(
            item["terminal_status"] == "planning_not_entered" for item in manifests
        ),
        "dispatchable_count": sum(bool(item["dispatchable"]) for item in manifests),
        "artifact_classification": {
            "planner_step_outputs": ["strategy.json", "plan_ir.json"],
            "support_outputs": ["planning_catalog_snapshot.json", "planning_halt.json", "bundle_manifest.json"],
            "evaluator_outputs_generated": [],
        },
        "cases": manifests,
    }
    _write_json(STAGE4 / "run_manifest.json", summary)
    _write_json(STAGE5 / "run_manifest.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if len(manifests) == 25 else 1


if __name__ == "__main__":
    raise SystemExit(main())
