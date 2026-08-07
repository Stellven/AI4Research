#!/usr/bin/env python3
"""Run a small scheduler-dispatched scientific lifecycle smoke."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_HARNESS_DIR = Path(__file__).resolve().parents[1]
if str(REPO_HARNESS_DIR / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_HARNESS_DIR / "tools"))

import run_scientific_node_smoke as node_smoke  # noqa: E402


DEFAULT_PAPER = "tests/plugins/autosci/fixtures/sample_paper.md"
DEFAULT_WORKFLOW_ID = "scientific_research_lifecycle_full_v1"
DEFAULT_WORKFLOW_CONFIG = REPO_HARNESS_DIR / "workflows" / f"{DEFAULT_WORKFLOW_ID}.json"
NODE_SPECS = [
    {
        "node_id": "literature_discover",
        "logical_operator": "ScientificLiteratureDiscoverer",
        "operator_id": "autosci-literature-discover-worker",
        "action": "discover_literature",
        "gate": "G_LITERATURE_DISCOVER",
        "evidence_name": "literature_discovery.json",
    },
    {
        "node_id": "paper_ingest",
        "logical_operator": "ScientificPaperIngestor",
        "operator_id": "autosci-paper-ingest-worker",
        "action": "ingest_paper",
        "gate": "G_PAPER_INGEST",
        "evidence_name": "research_paper.json",
    },
    {
        "node_id": "paper_analyze",
        "logical_operator": "ScientificPaperAnalyzer",
        "operator_id": "autosci-paper-analyze-worker",
        "action": "analyze_paper",
        "gate": "G_PAPER_ANALYZE",
        "evidence_name": "research_paper_analysis.json",
    },
    {
        "node_id": "memory_update_initial",
        "logical_operator": "ScientificMemoryUpdater",
        "operator_id": "autosci-memory-update-worker",
        "action": "update_memory",
        "gate": "G_MEMORY_UPDATE_INITIAL",
        "evidence_name": "research_memory_update.json",
    },
    {
        "node_id": "graph_update",
        "logical_operator": "ScientificGraphUpdater",
        "operator_id": "autosci-graph-update-worker",
        "action": "update_graph",
        "gate": "G_GRAPH_UPDATE",
        "evidence_name": "research_graph_update.json",
    },
    {
        "node_id": "claim_extract",
        "logical_operator": "ScientificClaimExtractor",
        "operator_id": "autosci-claim-extract-worker",
        "action": "extract_claims",
        "gate": "G_CLAIM_EXTRACT",
        "evidence_name": "research_claims.json",
    },
    {
        "node_id": "method_extract",
        "logical_operator": "ScientificMethodExtractor",
        "operator_id": "autosci-method-extract-worker",
        "action": "extract_methods",
        "gate": "G_METHOD_EXTRACT",
        "evidence_name": "research_method.json",
    },
    {
        "node_id": "code_evidence_map",
        "logical_operator": "ScientificCodeEvidenceMapper",
        "operator_id": "autosci-code-evidence-map-worker",
        "action": "map_code_evidence",
        "gate": "G_CODE_EVIDENCE_MAP",
        "evidence_name": "code_evidence_map.json",
    },
    {
        "node_id": "idea_generate",
        "logical_operator": "ScientificIdeaGenerator",
        "operator_id": "autosci-idea-worker",
        "action": "generate_ideas",
        "gate": "G_IDEA_GENERATE",
        "evidence_name": "idea_candidate.json",
    },
    {
        "node_id": "idea_evaluate",
        "logical_operator": "ScientificIdeaEvaluator",
        "operator_id": "autosci-idea-evaluate-worker",
        "action": "evaluate_ideas",
        "gate": "G_IDEA_EVALUATE",
        "evidence_name": "idea_evaluation.json",
    },
    {
        "node_id": "experiment_design",
        "logical_operator": "ScientificExperimentDesigner",
        "operator_id": "autosci-experiment-design-worker",
        "action": "design_experiment",
        "gate": "G_EXPERIMENT_DESIGN",
        "evidence_name": "experiment_plan.json",
    },
    {
        "node_id": "experiment_run",
        "logical_operator": "ScientificExperimentRunner",
        "operator_id": "autosci-experiment-run-worker",
        "action": "run_experiment",
        "gate": "G_EXPERIMENT_RUN",
        "evidence_name": "experiment_result.json",
    },
    {
        "node_id": "experiment_monitor",
        "logical_operator": "ScientificExperimentMonitor",
        "operator_id": "autosci-experiment-monitor-worker",
        "action": "monitor_experiment",
        "gate": "G_EXPERIMENT_MONITOR",
        "evidence_name": "experiment_status.json",
    },
    {
        "node_id": "claim_verify",
        "logical_operator": "ScientificClaimVerifier",
        "operator_id": "autosci-claim-verify-worker",
        "action": "verify_claim",
        "gate": "G_CLAIM_VERIFY",
        "evidence_name": "claim_verdict.json",
    },
    {
        "node_id": "report_draft",
        "logical_operator": "ScientificReportDrafter",
        "operator_id": "autosci-report-worker",
        "action": "write_report",
        "gate": "G_REPORT_DRAFT",
        "evidence_name": "scientific_report.json",
    },
    {
        "node_id": "artifact_review",
        "logical_operator": "ScientificArtifactReviewer",
        "operator_id": "autosci-artifact-review-worker",
        "action": "review_artifact",
        "gate": "G_ARTIFACT_REVIEW",
        "evidence_name": "artifact_review.json",
    },
    {
        "node_id": "memory_update_final",
        "logical_operator": "ScientificMemoryUpdater",
        "operator_id": "autosci-memory-update-worker",
        "action": "update_memory",
        "gate": "G_MEMORY_UPDATE_FINAL",
        "evidence_name": "final_research_memory_update.json",
    },
    {
        "node_id": "workflow_evolve",
        "logical_operator": "ScientificWorkflowEvolver",
        "operator_id": "autosci-workflow-evolve-worker",
        "action": "evolve_workflow",
        "gate": "G_WORKFLOW_EVOLVE",
        "evidence_name": "workflow_evolution.json",
    },
]
EXTERNAL_NODE_SPECS = [
    {
        "node_id": "report_plan",
        "logical_operator": "ScientificReportPlanner",
        "operator_id": "autosci-report-plan-worker",
        "action": "plan_report",
        "gate": "G_REPORT_PLAN",
        "evidence_name": "scientific_report_plan.json",
    },
    {
        "node_id": "publication_produce",
        "logical_operator": "ScientificPublicationProducer",
        "operator_id": "autosci-publication-compile-worker",
        "action": "compile_paper",
        "gate": "G_PUBLICATION_PRODUCE",
        "evidence_name": "publication_bundle.json",
    },
]
EXTERNAL_NODE_BY_ID = {spec["node_id"]: spec for spec in EXTERNAL_NODE_SPECS}
TAIL_NODE_IDS = {"report_draft", "artifact_review", "memory_update_final", "workflow_evolve"}
NODE_SPEC_BY_ID = {spec["node_id"]: spec for spec in NODE_SPECS}
BASE_NODE_SPECS = [spec for spec in NODE_SPECS if spec["node_id"] not in TAIL_NODE_IDS]
CONFIGURED_TAIL_NODE_IDS = [
    "report_plan",
    "report_draft",
    "artifact_review",
    "publication_produce",
    "memory_update_final",
    "workflow_evolve",
]
CONFIGURED_TAIL_NODE_SPECS = [
    EXTERNAL_NODE_BY_ID.get(node_id) or NODE_SPEC_BY_ID[node_id]
    for node_id in CONFIGURED_TAIL_NODE_IDS
]
BLOCKED_EXTERNAL_NODE_DETAILS = {
    "report_plan": {
        "node_id": "report_plan",
        "logical_operator": "ScientificReportPlanner",
        "operator_id": "autosci-report-plan-worker",
        "action": "plan_report",
        "gate": "G_REPORT_PLAN",
        "status": "blocked",
        "reason": "Waiting for completed Review LLM artifact_review.v1 evidence.",
        "required_evidence": ["artifact_review.v1 with review_mode=review_llm and review_llm.status=completed"],
        "unblock_condition": "Provide completed Review LLM-backed artifact_review.v1 evidence, then dispatch report_plan.",
    },
    "publication_produce": {
        "node_id": "publication_produce",
        "logical_operator": "ScientificPublicationProducer",
        "operator_id": "autosci-publication-compile-worker",
        "action": "compile_paper",
        "gate": "G_PUBLICATION_PRODUCE",
        "status": "blocked",
        "reason": "Waiting for LaTeX/PDF compile evidence or approved compile runtime evidence.",
        "required_evidence": ["publication_bundle.v1 with existing files and compile/PDF evidence"],
        "unblock_condition": "Provide a compile target with LaTeX/PDF artifacts or approved runtime evidence, then dispatch publication_produce.",
    },
}
HUMAN_GATE_SPECS = [
    {
        "node_id": "idea_acceptance_gate",
        "logical_operator": "ScientificWorkflowEvolver",
        "operator_id": "human-approval-gate",
        "action": "approve_idea_selection",
        "gate": "G_HUMAN_IDEA_ACCEPTANCE",
        "evidence_name": "idea_acceptance_gate.json",
    },
    {
        "node_id": "results_acceptance_gate",
        "logical_operator": "ScientificWorkflowEvolver",
        "operator_id": "human-approval-gate",
        "action": "approve_results_acceptance",
        "gate": "G_HUMAN_RESULTS_ACCEPTANCE",
        "evidence_name": "results_acceptance_gate.json",
    },
]
HUMAN_GATE_BY_ID = {spec["node_id"]: spec for spec in HUMAN_GATE_SPECS}
HUMAN_GATE_AFTER_NODE = {
    "idea_evaluate": "idea_acceptance_gate",
    "claim_verify": "results_acceptance_gate",
}
HUMAN_GATE_APPROVAL_ATTR = {
    "idea_acceptance_gate": "idea_approval_ref",
    "results_acceptance_gate": "results_approval_ref",
}
HUMAN_GATE_BLOCKED_DETAILS = {
    "idea_acceptance_gate": {
        "reason": "Waiting for durable human approval of the selected idea before experiment design.",
        "required_evidence": ["Human approval evidence for accepted/rejected idea IDs"],
        "unblock_condition": "Provide --idea-approval-ref or resume with recorded idea approval evidence.",
    },
    "results_acceptance_gate": {
        "reason": "Waiting for durable human approval of experiment results before publication planning.",
        "required_evidence": ["Human approval evidence for accepted/rejected experiment verdict"],
        "unblock_condition": "Provide --results-approval-ref or resume with recorded results approval evidence.",
    },
}


def _utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def _resolve_harness_path(root: Path, raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else root / path


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contains_fixture_reference(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        return "fixtures/" in normalized or "/fixtures/" in normalized
    if isinstance(value, list):
        return any(_contains_fixture_reference(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_fixture_reference(item) for item in value.values())
    return False


def _dispatch_input_profile(spec: dict[str, str], node_args: argparse.Namespace) -> dict[str, Any]:
    extra_inputs = node_args.extra_inputs if isinstance(getattr(node_args, "extra_inputs", None), dict) else {}
    markers: list[str] = []
    if extra_inputs.get("smoke_mode") is True:
        markers.append("smoke_mode=true")
    if extra_inputs.get("fixture_fallback") is True:
        markers.append("fixture_fallback=true")
    execution_mode = str(extra_inputs.get("execution_mode") or "").strip().lower()
    if execution_mode == "fixture":
        markers.append("execution_mode=fixture")
    if _contains_fixture_reference(extra_inputs):
        markers.append("fixture_reference_in_inputs")
    if _contains_fixture_reference(getattr(node_args, "paper", "")):
        markers.append("fixture_reference_in_paper")
    return {
        "node_id": spec["node_id"],
        "logical_operator": spec["logical_operator"],
        "operator_id": spec["operator_id"],
        "action": spec["action"],
        "runner_mode": "bounded_runtime_smoke",
        "smoke_mode": extra_inputs.get("smoke_mode") is True,
        "execution_mode": str(extra_inputs.get("execution_mode") or "N/A"),
        "fixture_markers": _unique_list(markers),
        "uses_fixture_or_smoke_input": bool(markers),
    }


def _unique_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _load_configured_workflow_nodes(workflow_config: Path) -> list[dict[str, str]]:
    payload = json.loads(workflow_config.read_text(encoding="utf-8"))
    nodes = payload.get("nodes") if isinstance(payload, dict) else None
    if not isinstance(nodes, list):
        raise ValueError(f"Workflow config must contain a nodes array: {workflow_config}")
    configured: list[dict[str, str]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        configured.append({
            "node_id": str(node.get("id") or ""),
            "logical_operator": str(node.get("logical_operator") or ""),
            "gate": str(node.get("gate") or ""),
        })
    return [node for node in configured if node["node_id"]]


def _workflow_config_alignment(
    *,
    workflow_config: Path,
    required_nodes: list[str],
    available_specs: list[dict[str, str]],
) -> dict[str, Any]:
    configured_nodes = _load_configured_workflow_nodes(workflow_config)
    configured_ids = [node["node_id"] for node in configured_nodes]
    available_ids = [spec["node_id"] for spec in available_specs]
    configured_set = set(configured_ids)
    available_set = set(available_ids)
    required_set = set(required_nodes)
    missing_available = [node_id for node_id in configured_ids if node_id not in available_set]
    extra_available = [node_id for node_id in available_ids if node_id not in configured_set]
    missing_required = [node_id for node_id in configured_ids if node_id not in required_set]
    extra_required = [node_id for node_id in required_nodes if node_id not in configured_set]
    configured_required_order = [node_id for node_id in configured_ids if node_id in required_set]
    runner_configured_order = [node_id for node_id in required_nodes if node_id in configured_set]
    order_matches = runner_configured_order == configured_required_order
    issues: list[str] = []
    if missing_available:
        issues.append("configured_nodes_missing_from_runner")
    if extra_available:
        issues.append("runner_nodes_not_declared_in_config")
    if missing_required:
        issues.append("configured_nodes_not_required_by_run")
    if extra_required:
        issues.append("required_run_nodes_not_declared_in_config")
    if not order_matches:
        issues.append("required_node_order_drift")
    return {
        "ok": not issues,
        "status": "aligned" if not issues else "drift",
        "workflow_config_path": _rel(workflow_config, REPO_HARNESS_DIR),
        "configured_nodes": configured_ids,
        "runner_available_nodes": available_ids,
        "required_nodes": required_nodes,
        "configured_nodes_missing_from_runner": missing_available,
        "runner_nodes_not_declared_in_config": extra_available,
        "configured_nodes_not_required_by_run": missing_required,
        "required_run_nodes_not_declared_in_config": extra_required,
        "configured_required_order": configured_required_order,
        "runner_configured_order": runner_configured_order,
        "order_matches": order_matches,
        "issues": issues,
    }


def _record_workflow_config_alignment(
    lifecycle: dict[str, Any],
    args: argparse.Namespace,
    *,
    required_nodes: list[str],
    checks: list[dict[str, str]],
) -> None:
    workflow_config = _resolve_harness_path(Path(args.harness_dir).expanduser().resolve(), args.workflow_config)
    alignment = _workflow_config_alignment(
        workflow_config=workflow_config,
        required_nodes=required_nodes,
        available_specs=[*NODE_SPECS, *EXTERNAL_NODE_SPECS],
    )
    lifecycle["workflow_config_alignment"] = alignment
    if bool(getattr(args, "require_workflow_config_alignment", False)) and not alignment["ok"]:
        checks.append({
            "check": "workflow_config_alignment",
            "status": "error",
            "detail": ",".join(alignment["issues"]),
        })


def _scheduler_dispatch_boundary(
    args: argparse.Namespace,
    *,
    required_nodes: list[str],
    dispatch_input_profiles: dict[str, Any],
) -> dict[str, Any]:
    harness_dir = Path(args.harness_dir).expanduser().resolve()
    workflow_config = _resolve_harness_path(harness_dir, args.workflow_config)
    fixture_nodes = [
        node_id
        for node_id, profile in sorted(dispatch_input_profiles.items())
        if isinstance(profile, dict) and profile.get("uses_fixture_or_smoke_input")
    ]
    smoke_nodes = [
        node_id
        for node_id, profile in sorted(dispatch_input_profiles.items())
        if isinstance(profile, dict) and profile.get("smoke_mode") is True
    ]
    blocking_reasons = [
        "runner_contract=bounded_smoke_runner",
    ]
    if smoke_nodes:
        blocking_reasons.append("node_inputs_include_smoke_mode")
    if fixture_nodes:
        blocking_reasons.append("node_inputs_include_fixture_or_fixture_fallback")
    workflow_hash = _sha256(workflow_config) if workflow_config.exists() and workflow_config.is_file() else ""
    return {
        "schema": "autosci_scheduler_dispatch_boundary.v1",
        "status": "bounded_smoke",
        "production_ready": False,
        "runner": _rel(Path(__file__).resolve(), REPO_HARNESS_DIR),
        "runner_contract": "bounded_smoke_runner",
        "workflow_id": DEFAULT_WORKFLOW_ID,
        "workflow_config_path": _rel(workflow_config, REPO_HARNESS_DIR),
        "workflow_config_sha256": workflow_hash,
        "required_nodes": list(required_nodes),
        "profiled_nodes": sorted(dispatch_input_profiles),
        "smoke_nodes": smoke_nodes,
        "fixture_nodes": fixture_nodes,
        "blocking_reasons": _unique_list(blocking_reasons),
        "limitations": [
            "This lifecycle is dispatched through the bounded smoke runner, not a generic production scheduler.",
            "Production parity requires a non-smoke workflow dispatcher with no fixture/smoke input markers and durable resume/runtime proof.",
        ],
    }


def _gate_lifecycle(summary_path: Path, harness_dir: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(harness_dir)
    proc = subprocess.run(
        [sys.executable, str(REPO_HARNESS_DIR / "evaluators/scientific/lifecycle_runtime_gate.py"), str(summary_path)],
        cwd=str(REPO_HARNESS_DIR),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "status": "failed",
            "reasons": [f"lifecycle_runtime_gate emitted non-json output: {proc.stdout.strip()}"],
            "warnings": [proc.stderr.strip()] if proc.stderr.strip() else [],
        }
    payload["exit_code"] = proc.returncode
    if proc.stderr.strip():
        payload.setdefault("warnings", []).append(proc.stderr.strip())
    return payload


def _blocked_external_node(job_id: str, node_id: str) -> dict[str, Any]:
    node = {"job_id": job_id, **BLOCKED_EXTERNAL_NODE_DETAILS[node_id]}
    request = _legacy_authorization_request(job_id, node)
    node["authorization_request"] = request
    node["continuation"] = request["continuation"]
    return node


def _blocked_human_gate(job_id: str, node_id: str) -> dict[str, Any]:
    spec = HUMAN_GATE_BY_ID[node_id]
    detail = HUMAN_GATE_BLOCKED_DETAILS[node_id]
    node = {
        "job_id": job_id,
        "node_id": node_id,
        "logical_operator": spec["logical_operator"],
        "operator_id": spec["operator_id"],
        "action": spec["action"],
        "gate": spec["gate"],
        "status": "blocked",
        **detail,
    }
    request = _legacy_authorization_request(job_id, node)
    node["authorization_request"] = request
    node["continuation"] = request["continuation"]
    return node


def _legacy_authorization_request(job_id: str, node: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node.get("node_id") or "")
    if node_id == "report_plan":
        requested_side_effects = ["review_llm"]
        required_inputs = ["review_llm_evidence"]
        resume_args_patch = ["--review-llm-evidence", "<review-llm-evidence.json>"]
    elif node_id == "publication_produce":
        requested_side_effects = ["tex_compile", "publication_runtime"]
        required_inputs = ["compile_target", "compile_runtime_evidence", "compile_approval_ref"]
        resume_args_patch = [
            "--compile-target",
            "<paper-or-tex-target>",
            "--compile-runtime-evidence",
            "<compile-runtime-evidence.json>",
            "--compile-approval-ref",
            "<approval-ref>",
        ]
    elif node_id == "idea_acceptance_gate":
        requested_side_effects = ["human_approval"]
        required_inputs = ["idea_approval_ref"]
        resume_args_patch = ["--idea-approval-ref", "<approval-ref>"]
    elif node_id == "results_acceptance_gate":
        requested_side_effects = ["human_approval"]
        required_inputs = ["results_approval_ref"]
        resume_args_patch = ["--results-approval-ref", "<approval-ref>"]
    else:
        requested_side_effects = ["approval_or_runtime_evidence"]
        required_inputs = list(node.get("required_evidence") or [])
        resume_args_patch = ["--allow-existing-result"]
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "job_id": job_id,
                "node_id": node_id,
                "reason": node.get("reason"),
                "required_inputs": required_inputs,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "scientific_workflow_gate_authorization_request.v1",
        "status": "awaiting_authorization",
        "job_id": job_id,
        "node_id": node_id,
        "native_skill": node.get("action", "N/A"),
        "reason": str(node.get("reason") or ""),
        "requested_side_effects": requested_side_effects,
        "required_inputs": required_inputs,
        "prompt": (
            "This legacy lifecycle gate is waiting for approval or runtime evidence. "
            "Supply the requested inputs, then resume the lifecycle."
        ),
        "continuation": {
            "schema": "scientific_workflow_gate_continuation.v1",
            "status": "awaiting_authorization",
            "retriable": True,
            "same_workflow_supported": True,
            "request_fingerprint": fingerprint,
            "resume_strategy": "resume_legacy_lifecycle_with_authorization_patch",
            "resume_args_patch": resume_args_patch,
            "resume_node_id": node_id,
        },
        "non_error_contract": {
            "blocked_runs_exit_successfully": True,
            "lifecycle_status": "blocked",
        },
    }


def _authorization_requests_from_blocked(blocked_nodes: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        node["authorization_request"]
        for node in blocked_nodes.values()
        if isinstance(node, dict) and isinstance(node.get("authorization_request"), dict)
    ]


def _human_gate_approval_result(
    *,
    harness_dir: Path,
    job_id: str,
    spec: dict[str, str],
    approval_ref: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    node_id = spec["node_id"]
    task_id = f"task-{job_id}-{node_id}"
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    output_dir = _resolve_harness_path(
        harness_dir,
        f"artifacts/scientific/scheduler-lifecycle-smoke/{job_id}/{node_id}",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / spec["evidence_name"]
    bridge_result_path = output_dir / f"{spec['action']}.result.json"
    operator_result_dir = _resolve_harness_path(
        harness_dir,
        f"run/operator-results/{spec['operator_id']}/{task_id}",
    )
    operator_result_dir.mkdir(parents=True, exist_ok=True)
    operator_result_path = operator_result_dir / "result.json"
    payload = {
        "schema": "workflow_evolution.v1",
        "task_id": task_id,
        "sprint_id": job_id,
        "node_id": node_id,
        "status": "completed",
        "inputs": {"approval_ref": approval_ref, "gate": spec["gate"]},
        "outputs": {
            "evolution": {
                "proposal_id": f"{node_id}-{approval_ref}",
                "scope": "scientific research lifecycle human gate",
                "change_type": "gate",
                "rationale": f"Human approval `{approval_ref}` was recorded as scheduler-visible lifecycle state.",
                "expected_effect": "Allow the scientific lifecycle to advance past a human approval pause without losing auditability.",
                "approval_state": "approved",
                "evidence_ids": [f"human-approval:{approval_ref}", node_id],
                "collected": {
                    "failed_nodes": [],
                    "gate_rejection_reasons": [],
                    "ambiguous_manuals_or_prompts": [],
                    "insufficient_schemas": [],
                    "poor_operator_bindings": [],
                    "human_intervention_points": [
                        {
                            "id": node_id,
                            "description": f"Approval ref `{approval_ref}` recorded for {node_id}.",
                        }
                    ],
                    "runtime_errors": [],
                },
                "review": {
                    "human_accept_reject_required": True,
                    "protected_core_edits_applied": False,
                    "application_state": "not_applied",
                    "approval_ref": approval_ref,
                },
            }
        },
        "artifacts": [],
        "provenance": {
            "operator_id": spec["operator_id"],
            "implementation_package": "harness.tools.run_scientific_lifecycle_smoke",
            "timestamp": timestamp,
        },
        "limitations": ["Approval ref was supplied explicitly; no external side effect was executed by this gate."],
    }
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_hash = _sha256(artifact_path)
    bridge_result = {
        "action": spec["action"],
        "approval_ref": approval_ref,
        "artifact_sha256": artifact_hash,
        "evidence_path": _rel(artifact_path, harness_dir),
        "gate": spec["gate"],
        "job_id": job_id,
        "node_id": node_id,
        "ok": True,
        "result_path": _rel(bridge_result_path, harness_dir),
        "schema": "workflow_evolution.v1",
        "status": "completed",
        "task_id": task_id,
    }
    bridge_result_path.write_text(json.dumps(bridge_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    operator_result = {
        "action": spec["action"],
        "approval_ref": approval_ref,
        "bridge_result_path": _rel(bridge_result_path, harness_dir),
        "effective_model": "human-approval-ref",
        "effective_provider": "human",
        "exit_code": 0,
        "finished_at": timestamp,
        "node_id": node_id,
        "operator_id": spec["operator_id"],
        "requested_model": "human-approval-ref",
        "routing_model": "human-approval-ref",
        "sprint_id": job_id,
        "started_at": timestamp,
        "status": "completed",
        "task_id": task_id,
    }
    operator_result_path.write_text(json.dumps(operator_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    node_result = {
        "job_id": job_id,
        "node_id": node_id,
        "logical_operator": spec["logical_operator"],
        "operator_id": spec["operator_id"],
        "action": spec["action"],
        "status": "passed",
        "artifact_path": _rel(artifact_path, harness_dir),
        "artifact_sha256": artifact_hash,
        "bridge_result_path": _rel(bridge_result_path, harness_dir),
        "expected_schema": "workflow_evolution.v1",
        "gate": spec["gate"],
        "operator_result_path": _rel(operator_result_path, harness_dir),
        "approval_ref": approval_ref,
    }
    gate_result = {
        "job_id": job_id,
        "node_id": node_id,
        "gate": spec["gate"],
        "status": "passed",
        "ok": True,
        "reasons": [],
        "warnings": [],
        "approval_ref": approval_ref,
    }
    return node_result, gate_result


def _extra_inputs_for(
    spec: dict[str, str],
    node_results: dict[str, Any],
    args: argparse.Namespace | None = None,
) -> dict[str, Any]:
    node_id = spec["node_id"]
    inputs: dict[str, Any] = {"smoke_mode": True}
    discovery_path = (node_results.get("literature_discover") or {}).get("artifact_path")
    paper_path = (node_results.get("paper_ingest") or {}).get("artifact_path")
    claims_path = (node_results.get("claim_extract") or {}).get("artifact_path")
    method_path = (node_results.get("method_extract") or {}).get("artifact_path")
    code_path = (node_results.get("code_evidence_map") or {}).get("artifact_path")
    idea_path = (node_results.get("idea_generate") or {}).get("artifact_path")
    idea_eval_path = (node_results.get("idea_evaluate") or {}).get("artifact_path")
    experiment_plan_path = (node_results.get("experiment_design") or {}).get("artifact_path")
    experiment_result_path = (node_results.get("experiment_run") or {}).get("artifact_path")
    claim_verdict_path = (node_results.get("claim_verify") or {}).get("artifact_path")
    report_path = (node_results.get("report_draft") or {}).get("artifact_path")
    report_plan_path = (node_results.get("report_plan") or {}).get("artifact_path")
    review_llm_evidence = list(getattr(args, "review_llm_evidence", None) or []) if args else []
    compile_target = str(getattr(args, "compile_target", "") or "") if args else ""
    experiment_approval_ref = str(getattr(args, "experiment_approval_ref", "") or "") if args else ""
    experiment_runtime_evidence = list(getattr(args, "experiment_runtime_evidence", None) or []) if args else []
    experiment_allowlist = list(getattr(args, "experiment_allowlist_evidence", None) or []) if args else []
    experiment_before = list(getattr(args, "experiment_before_artifact", None) or []) if args else []
    experiment_after = list(getattr(args, "experiment_after_artifact", None) or []) if args else []
    experiment_execute_approved = bool(getattr(args, "experiment_execute_approved", False)) if args else False
    experiment_executor_timeout = int(getattr(args, "experiment_executor_timeout_seconds", 120) or 120) if args else 120
    compile_approval_ref = str(getattr(args, "compile_approval_ref", "") or "") if args else ""
    compile_runtime_evidence = list(getattr(args, "compile_runtime_evidence", None) or []) if args else []
    compile_allowlist = list(getattr(args, "compile_allowlist_evidence", None) or []) if args else []
    compile_before = list(getattr(args, "compile_before_artifact", None) or []) if args else []
    compile_after = list(getattr(args, "compile_after_artifact", None) or []) if args else []
    compile_execute_approved = bool(getattr(args, "compile_execute_approved", False)) if args else False
    compile_executor_timeout = int(getattr(args, "compile_executor_timeout_seconds", 120) or 120) if args else 120
    has_experiment_runtime_contract = bool(
        experiment_approval_ref
        or experiment_runtime_evidence
        or experiment_allowlist
        or experiment_before
        or experiment_after
        or experiment_execute_approved
    )

    if node_id in {"memory_update_initial", "graph_update", "method_extract"} and paper_path:
        inputs["source_evidence"] = paper_path
    if node_id == "literature_discover":
        allow_network_fetch = bool(getattr(args, "allow_network_fetch", False)) if args else False
        require_online = bool(getattr(args, "require_online_source_evidence", False)) if args else False
        disable_fixture_fallback = bool(getattr(args, "disable_fixture_fallback", False)) if args else False
        discovery_query = str(getattr(args, "discovery_query", "") or "scheduler lifecycle smoke") if args else "scheduler lifecycle smoke"
        discovery_mode = str(getattr(args, "discovery_mode", "") or "") if args else ""
        discovery_limit = int(getattr(args, "discovery_limit", 3) or 3) if args else 3
        min_online_channels = int(getattr(args, "min_online_source_channels", 1) or 1) if args else 1
        source_runtime_evidence = list(getattr(args, "source_runtime_evidence", None) or []) if args else []
        source_allowlist = list(getattr(args, "source_allowlist_evidence", None) or []) if args else []
        source_before = list(getattr(args, "source_before_artifact", None) or []) if args else []
        source_after = list(getattr(args, "source_after_artifact", None) or []) if args else []
        source_approval_ref = str(getattr(args, "source_approval_ref", "") or "") if args else ""
        inputs.update({
            "query": discovery_query,
            "topic": discovery_query,
            "limit": discovery_limit,
            "allow_network_fetch": allow_network_fetch,
            "fixture_fallback": not (disable_fixture_fallback or require_online),
            "require_online_source_evidence": require_online,
            "min_online_source_channels": min_online_channels,
        })
        if discovery_mode:
            inputs["discover_mode"] = discovery_mode
        if source_approval_ref:
            inputs["approval_ref"] = source_approval_ref
        if source_runtime_evidence:
            inputs["runtime_evidence"] = source_runtime_evidence
        if source_allowlist:
            inputs["allowlist_evidence"] = source_allowlist
        if source_before:
            inputs["before_artifacts"] = source_before
        if source_after:
            inputs["after_artifacts"] = source_after
    if node_id in {"code_evidence_map", "idea_generate", "idea_evaluate"}:
        if claims_path:
            inputs["claims_evidence"] = claims_path
        if method_path:
            inputs["method_evidence"] = method_path
    if node_id == "code_evidence_map":
        inputs["repo_path"] = "tests/plugins/autosci/fixtures/sample_repo"
    if node_id in {"idea_generate", "idea_evaluate"}:
        if paper_path:
            inputs["paper_evidence"] = paper_path
        if idea_path:
            inputs["ideas_evidence"] = idea_path
    if node_id == "claim_verify":
        if claims_path:
            inputs["claims_evidence"] = claims_path
        if code_path:
            inputs["code_evidence"] = code_path
        if experiment_result_path:
            inputs["experiment_result_evidence"] = experiment_result_path
        inputs["claim_id"] = "claim-001"
    if node_id == "experiment_design":
        inputs.update({
            "claim_id": "claim-001",
            "execution_mode": "fixture",
        })
        if idea_eval_path:
            inputs["idea_evaluation_evidence"] = idea_eval_path
    if node_id == "experiment_run":
        inputs["execution_mode"] = "human_approved" if has_experiment_runtime_contract else "fixture"
        if experiment_plan_path:
            inputs["experiment_plan_evidence"] = experiment_plan_path
        if has_experiment_runtime_contract:
            if experiment_approval_ref:
                inputs["approval_ref"] = experiment_approval_ref
            if experiment_runtime_evidence:
                inputs["runtime_evidence"] = experiment_runtime_evidence
            if experiment_allowlist:
                inputs["allowlist_evidence"] = experiment_allowlist
            if experiment_before:
                inputs["before_artifacts"] = experiment_before
            if experiment_after:
                inputs["after_artifacts"] = experiment_after
            if experiment_execute_approved:
                inputs["execute_approved_side_effect"] = True
                inputs["executor_timeout_seconds"] = experiment_executor_timeout
        else:
            inputs["experiment_result"] = "tests/plugins/autosci/fixtures/sample_autosci_raw_experiment_result.json"
    if node_id == "experiment_monitor":
        inputs["execution_mode"] = "human_approved" if has_experiment_runtime_contract else "fixture"
        if experiment_plan_path:
            inputs["experiment_plan_evidence"] = experiment_plan_path
        if has_experiment_runtime_contract and experiment_runtime_evidence:
            inputs["collect"] = True
            if experiment_approval_ref:
                inputs["approval_ref"] = experiment_approval_ref
            if experiment_runtime_evidence:
                inputs["runtime_evidence"] = experiment_runtime_evidence
            if experiment_allowlist:
                inputs["allowlist_evidence"] = experiment_allowlist
            if experiment_before:
                inputs["before_artifacts"] = experiment_before
            if experiment_after:
                inputs["after_artifacts"] = experiment_after
        elif experiment_result_path:
            inputs["experiment_result_evidence"] = experiment_result_path
    if node_id == "report_draft":
        inputs.update({
            "claim_id": "claim-001",
            "experiment_id": "exp-supported-001",
            "report_id": "report-scheduler-lifecycle-smoke",
            "report_title": "Scheduler Lifecycle Smoke Report",
            "paper_draft": True,
            "target": "scheduler-lifecycle-draft",
        })
        if discovery_path:
            inputs["discovery_evidence"] = discovery_path
        if claims_path:
            inputs["claims_evidence"] = claims_path
        if claim_verdict_path:
            inputs["claim_verdict_evidence"] = claim_verdict_path
        if experiment_result_path:
            inputs["experiment_result"] = experiment_result_path
        if code_path:
            inputs["code_evidence"] = code_path
        if method_path:
            inputs["method_evidence"] = method_path
        if idea_eval_path:
            inputs["idea_evaluation_evidence"] = idea_eval_path
        if paper_path:
            inputs["paper_evidence"] = paper_path
        if report_plan_path:
            inputs["report_plan_evidence"] = report_plan_path
        _attach_review_llm_inputs(inputs, args)
        _attach_compile_handoff_inputs(inputs, args)
    if node_id == "memory_update_final" and report_path:
        inputs["source_evidence"] = report_path
    if node_id == "artifact_review":
        if report_path:
            inputs["target"] = report_path
            inputs["artifact_path"] = report_path
        inputs["difficulty"] = "standard"
        inputs["focus"] = "completeness"
    if node_id == "workflow_evolve":
        inputs["failed_run"] = {
            "workflow_id": DEFAULT_WORKFLOW_ID,
            "sprint_id": "scheduler-lifecycle-smoke-synthetic-failed-run",
            "nodes": [
                {
                    "id": "publication_produce",
                    "logical_operator": "ScientificPublicationProducer",
                    "gate": "G_PUBLICATION_PRODUCE",
                    "status": "failed",
                }
            ],
            "gate_results": {
                "G_PUBLICATION_PRODUCE": {
                    "status": "failed",
                    "reasons": [
                        "publication_produce currently lacks a scheduler-bound publication_bundle.v1 action"
                    ],
                }
            },
            "ambiguous_manuals_or_prompts": [
                {
                    "manual_id": "scientific-publication-produce.dispatch",
                    "description": "Scheduler publication dispatch does not yet distinguish report drafting from publication bundle compilation."
                }
            ],
            "insufficient_schemas": [],
            "poor_operator_bindings": [
                {
                    "logical_operator": "ScientificPublicationProducer",
                    "physical_operator": "autosci-report-worker",
                    "description": "Current report worker emits scientific_report.v1 as the primary evidence."
                }
            ],
            "human_intervention_points": [
                {
                    "point": "publication_compile_approval",
                    "description": "Compiled publication output requires explicit bounded compile or human-approved external execution."
                }
            ],
            "runtime_errors": [
                {
                    "error_id": "runtime.publication-bundle-action-missing",
                    "message": "No dedicated scheduler physical operator currently emits publication_bundle.v1."
                }
            ],
        }
    if node_id == "report_plan":
        inputs.update({
            "claim_id": "claim-001",
            "experiment_id": "exp-supported-001",
            "report_id": "report-scheduler-lifecycle-resume-plan",
            "report_title": "Scheduler Lifecycle Resumed Paper Plan",
            "target": "scheduler-lifecycle-resume",
        })
        if discovery_path:
            inputs["discovery_evidence"] = discovery_path
        if paper_path:
            inputs["paper_evidence"] = paper_path
        if claims_path:
            inputs["claims_evidence"] = claims_path
        if claim_verdict_path:
            inputs["claim_verdict_evidence"] = claim_verdict_path
        if experiment_result_path:
            inputs["experiment_result"] = experiment_result_path
        if code_path:
            inputs["code_evidence"] = code_path
        if method_path:
            inputs["method_evidence"] = method_path
        if idea_eval_path:
            inputs["idea_evaluation_evidence"] = idea_eval_path
        _attach_review_llm_inputs(inputs, args)
        _attach_compile_handoff_inputs(inputs, args)
    if node_id == "publication_produce":
        inputs.update({
            "checklist": True,
            "title": "Scheduler Lifecycle Resumed Publication",
        })
        if compile_target:
            inputs["target"] = compile_target
        _attach_compile_handoff_inputs(inputs, args)
    return inputs


def _node_args(
    args: argparse.Namespace,
    harness_dir: Path,
    job_id: str,
    spec: dict[str, str],
    node_results: dict[str, Any],
) -> argparse.Namespace:
    task_id = f"task-{job_id}-{spec['node_id']}"
    return argparse.Namespace(
        harness_dir=str(harness_dir),
        operator_id=spec["operator_id"],
        node_id=spec["node_id"],
        action=spec["action"],
        logical_operator=spec["logical_operator"],
        expected_schema=None,
        evidence_name=spec["evidence_name"],
        task_id=task_id,
        sprint_id=job_id,
        paper=args.paper,
        paper_id=f"paper-{job_id}",
        input_json=None,
        extra_inputs=_extra_inputs_for(spec, node_results, args),
        output_dir=f"artifacts/scientific/scheduler-lifecycle-smoke/{job_id}/{spec['node_id']}",
        out=None,
        timeout_seconds=float(args.timeout_seconds),
        lease_ttl_seconds=int(args.lease_ttl_seconds),
        allow_existing_result=bool(args.allow_existing_result),
    )


def _run_scheduler_node(
    args: argparse.Namespace,
    harness_dir: Path,
    job_id: str,
    spec: dict[str, str],
    node_results: dict[str, Any],
    dispatch_input_profiles: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    node_args = _node_args(args, harness_dir, job_id, spec, node_results)
    dispatch_input_profiles[spec["node_id"]] = _dispatch_input_profile(spec, node_args)
    return node_smoke.run(node_args)


def _node_result_from_summary(
    *,
    node_summary: dict[str, Any],
    harness_dir: Path,
    job_id: str,
    gate_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence_path = _resolve_harness_path(harness_dir, str(node_summary["evidence_path"]))
    artifact_hash = _sha256(evidence_path)
    bridge_result = node_summary.get("bridge_result") if isinstance(node_summary.get("bridge_result"), dict) else {}
    expected_schema = str(bridge_result.get("schema") or "research_paper.v1")
    node_result = {
        "job_id": job_id,
        "node_id": node_summary["node_id"],
        "logical_operator": node_summary["logical_operator"],
        "operator_id": node_summary["operator_id"],
        "action": node_summary["action"],
        "status": "passed" if node_summary.get("status") == "passed" else "failed",
        "artifact_path": node_summary["evidence_path"],
        "artifact_sha256": artifact_hash,
        "expected_schema": expected_schema,
        "gate": gate_name,
        "operator_result_path": node_summary["operator_result_path"],
        "bridge_result_path": node_summary["bridge_result_path"],
    }
    raw_gate = node_summary.get("gate_result") if isinstance(node_summary.get("gate_result"), dict) else {}
    gate_result = {
        "job_id": job_id,
        "node_id": node_summary["node_id"],
        "gate": gate_name,
        "status": str(raw_gate.get("status") or "failed"),
        "ok": bool(raw_gate.get("ok")),
        "reasons": raw_gate.get("reasons") or [],
        "warnings": raw_gate.get("warnings") or [],
    }
    return node_result, gate_result


def _resume_node_fingerprint(node_result: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "status",
        "artifact_path",
        "artifact_sha256",
        "operator_result_path",
        "bridge_result_path",
        "gate",
    )
    return {field: node_result.get(field) for field in fields if field in node_result}


def _scheduler_resume_boundary(
    *,
    resume_audit: dict[str, Any],
    changed_reused_nodes: list[str],
) -> dict[str, Any]:
    reused_nodes = resume_audit.get("reused_nodes") if isinstance(resume_audit.get("reused_nodes"), dict) else {}
    dispatched_nodes = resume_audit.get("dispatched_nodes") if isinstance(resume_audit.get("dispatched_nodes"), list) else []
    approved_human_gates = (
        resume_audit.get("approved_human_gates")
        if isinstance(resume_audit.get("approved_human_gates"), list)
        else []
    )
    source_summary_path = str(resume_audit.get("source_summary_path") or "").strip()
    no_rerun_verified = bool(source_summary_path and reused_nodes and not changed_reused_nodes)
    blocking_reasons: list[str] = []
    if not source_summary_path:
        blocking_reasons.append("missing_resume_source_summary")
    if not reused_nodes:
        blocking_reasons.append("no_reused_node_fingerprints")
    if changed_reused_nodes:
        blocking_reasons.append("reused_node_fingerprint_changed")
    return {
        "schema": "autosci_scheduler_resume_boundary.v1",
        "status": "resume_no_rerun_verified" if no_rerun_verified else "incomplete",
        "no_rerun_verified": no_rerun_verified,
        "source_summary_path": source_summary_path,
        "reused_node_count": len(reused_nodes),
        "reused_nodes": reused_nodes,
        "changed_reused_nodes": list(changed_reused_nodes),
        "dispatched_nodes": list(dispatched_nodes),
        "dispatched_node_count": len(dispatched_nodes),
        "approved_human_gates": list(approved_human_gates),
        "blocking_reasons": _unique_list(blocking_reasons),
        "limitations": [] if no_rerun_verified else [
            "Scheduler resume did not prove that prior node artifacts were reused without rerun."
        ],
    }


def _scheduler_lease_boundary(
    *,
    harness_dir: Path,
    job_id: str,
    required_nodes: list[str],
    lease_dir: Path,
    resume: bool,
) -> dict[str, Any]:
    lease_dir.mkdir(parents=True, exist_ok=True)
    lease_path = lease_dir / "scheduler_lease.json"
    lease_id = hashlib.sha1(
        json.dumps(
            {"job_id": job_id, "required_nodes": required_nodes, "resume": resume},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lease = {
        "schema": "autosci_scheduler_lease.v1",
        "lease_id": lease_id,
        "job_id": job_id,
        "scope": "local_smoke_runner_resume" if resume else "local_smoke_runner",
        "owner": "harness.tools.run_scientific_lifecycle_smoke",
        "acquired_at": timestamp,
        "required_nodes": list(required_nodes),
        "distributed": False,
        "production_ready": False,
        "limitations": [
            "This is a local smoke-run lease record, not a distributed scheduler lease.",
        ],
    }
    lease_path.write_text(json.dumps(lease, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "schema": "autosci_scheduler_lease_boundary.v1",
        "status": "local_smoke_lease",
        "local_lease_recorded": True,
        "distributed_lease_verified": False,
        "production_ready": False,
        "lease_id": lease_id,
        "lease_path": _rel(lease_path, harness_dir),
        "lease_scope": lease["scope"],
        "required_nodes": list(required_nodes),
        "blocking_reasons": ["lease_scope=local_smoke_runner", "distributed_lease_not_verified"],
        "limitations": [
            "Scheduler lease ownership is recorded locally for auditability; production parity requires a distributed lease/quota manager.",
        ],
    }


def _ensure_lifecycle_node(lifecycle: dict[str, Any], spec: dict[str, str]) -> None:
    required_nodes = lifecycle.setdefault("required_nodes", [])
    if isinstance(required_nodes, list) and spec["node_id"] not in required_nodes:
        required_nodes.append(spec["node_id"])
    nodes = lifecycle.setdefault("nodes", [])
    if isinstance(nodes, list) and not any(
        isinstance(node, dict) and node.get("id") == spec["node_id"]
        for node in nodes
    ):
        nodes.append({
            "id": spec["node_id"],
            "logical_operator": spec["logical_operator"],
            "operator_id": spec["operator_id"],
            "action": spec["action"],
            "gate": spec["gate"],
        })


def _append_required_node(
    required_nodes: list[str],
    nodes: list[dict[str, str]],
    spec: dict[str, str],
) -> None:
    node_id = spec["node_id"]
    if node_id not in required_nodes:
        required_nodes.append(node_id)
    if not any(node.get("id") == node_id for node in nodes):
        nodes.append({
            "id": node_id,
            "logical_operator": spec["logical_operator"],
            "operator_id": spec["operator_id"],
            "action": spec["action"],
            "gate": spec["gate"],
        })


def _record_unsupplied_external_tail_blockers(
    *,
    lifecycle: dict[str, Any],
    args: argparse.Namespace,
    job_id: str,
    node_results: dict[str, Any],
    blocked_nodes: dict[str, Any],
    checks: list[dict[str, str]],
    start_index: int,
) -> None:
    for pending_spec in CONFIGURED_TAIL_NODE_SPECS[start_index:]:
        pending_id = pending_spec["node_id"]
        if pending_id not in EXTERNAL_NODE_BY_ID or pending_id in node_results:
            continue
        if _resume_evidence_supplied(args, pending_id):
            continue
        _ensure_lifecycle_node(lifecycle, pending_spec)
        blocked_nodes[pending_id] = _blocked_external_node(job_id, pending_id)
        checks.append({
            "check": f"{pending_id}_resume_waiting",
            "status": "ok",
            "detail": "required external evidence was not supplied",
        })


def _resume_evidence_supplied(args: argparse.Namespace, node_id: str) -> bool:
    if node_id == "report_plan":
        return bool(getattr(args, "review_llm_evidence", None))
    if node_id == "publication_produce":
        return bool(str(getattr(args, "compile_target", "") or "").strip())
    return False


def _attach_review_llm_inputs(inputs: dict[str, Any], args: argparse.Namespace | None) -> None:
    review_llm_evidence = list(getattr(args, "review_llm_evidence", None) or []) if args else []
    if review_llm_evidence:
        inputs["review_llm_evidence"] = review_llm_evidence
        inputs["artifact_review_evidence"] = review_llm_evidence


def _attach_compile_handoff_inputs(inputs: dict[str, Any], args: argparse.Namespace | None) -> None:
    if args is None:
        return
    compile_target = str(getattr(args, "compile_target", "") or "").strip()
    compile_approval_ref = str(getattr(args, "compile_approval_ref", "") or "").strip()
    compile_runtime_evidence = list(getattr(args, "compile_runtime_evidence", None) or [])
    compile_allowlist = list(getattr(args, "compile_allowlist_evidence", None) or [])
    compile_before = list(getattr(args, "compile_before_artifact", None) or [])
    compile_after = list(getattr(args, "compile_after_artifact", None) or [])
    compile_execute_approved = bool(getattr(args, "compile_execute_approved", False))
    compile_executor_timeout = int(getattr(args, "compile_executor_timeout_seconds", 120) or 120)
    if compile_target:
        inputs["paper_path"] = compile_target
        inputs["supplied_compile_target_evidence"] = True
    if compile_approval_ref:
        inputs["approval_ref"] = compile_approval_ref
    if compile_runtime_evidence:
        inputs["runtime_evidence"] = compile_runtime_evidence
    if compile_allowlist:
        inputs["allowlist_evidence"] = compile_allowlist
    if compile_before:
        inputs["before_artifacts"] = compile_before
    if compile_after:
        inputs["after_artifacts"] = compile_after
    if compile_execute_approved:
        inputs["execute_approved_side_effect"] = True
        inputs["executor_timeout_seconds"] = compile_executor_timeout


def _write_and_gate_lifecycle(
    lifecycle: dict[str, Any],
    summary_path: Path,
    harness_dir: Path,
    *,
    blocked_nodes: dict[str, Any],
    checks: list[dict[str, str]],
    gate_check_name: str = "lifecycle_runtime_gate_passed",
    authorization_blocked_exit_zero: bool = False,
) -> tuple[int, dict[str, Any]]:
    authorization_requests = _authorization_requests_from_blocked(blocked_nodes)
    lifecycle["authorization_required"] = bool(authorization_requests)
    lifecycle["authorization_requests"] = authorization_requests
    lifecycle["authorization_prompt"] = (
        "One or more legacy lifecycle gates are waiting for authorization or runtime evidence; "
        "supply the requested access patch and resume the lifecycle."
        if authorization_requests
        else ""
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    lifecycle["summary_path"] = _rel(summary_path, harness_dir)
    summary_path.write_text(json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lifecycle_gate = _gate_lifecycle(summary_path, harness_dir)
    lifecycle["lifecycle_gate_result"] = lifecycle_gate
    lifecycle_gate_ok = lifecycle_gate.get("ok") is True or (
        bool(blocked_nodes) and str(lifecycle_gate.get("status") or "") == "inconclusive"
    )
    checks.append({
        "check": gate_check_name,
        "status": "ok" if lifecycle_gate_ok else "error",
        "detail": str(lifecycle_gate.get("status")),
    })
    if all(item["status"] == "ok" for item in checks):
        lifecycle["lifecycle_status"] = "blocked" if blocked_nodes else "passed"
    else:
        lifecycle["lifecycle_status"] = "failed"
    lifecycle["summary_path"] = _rel(summary_path, harness_dir)
    summary_path.write_text(json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if lifecycle["lifecycle_status"] == "passed":
        return 0, lifecycle
    if lifecycle["lifecycle_status"] == "blocked":
        return (0 if authorization_blocked_exit_zero else 3), lifecycle
    return 1, lifecycle


def run_resume(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    harness_dir = Path(args.harness_dir).expanduser().resolve()
    resume_summary_path = _resolve_harness_path(harness_dir, str(args.resume_summary))
    base = json.loads(resume_summary_path.read_text(encoding="utf-8"))
    if not isinstance(base, dict):
        raise ValueError(f"Lifecycle summary must be a JSON object: {resume_summary_path}")

    lifecycle = copy.deepcopy(base)
    job_id = str(lifecycle.get("job_id") or lifecycle.get("sprint_id") or args.job_id or f"job-scientific-lifecycle-resume-{_utc_stamp()}")
    lifecycle["job_id"] = job_id
    lifecycle["sprint_id"] = job_id
    lifecycle["execution_owner"] = "solar.operator_runtime.scheduler_lifecycle_resume"
    lifecycle["resume_source_summary_path"] = _rel(resume_summary_path, harness_dir)

    node_summaries = lifecycle.setdefault("node_summaries", {})
    node_results = lifecycle.setdefault("node_results", {})
    gate_results = lifecycle.setdefault("gate_results", {})
    blocked_nodes = lifecycle.setdefault("blocked_nodes", {})
    checks = lifecycle.setdefault("checks", [])
    dispatch_input_profiles = lifecycle.setdefault("dispatch_input_profiles", {})
    if not isinstance(node_summaries, dict):
        node_summaries = lifecycle["node_summaries"] = {}
    if not isinstance(node_results, dict):
        node_results = lifecycle["node_results"] = {}
    if not isinstance(gate_results, dict):
        gate_results = lifecycle["gate_results"] = {}
    if not isinstance(blocked_nodes, dict):
        blocked_nodes = lifecycle["blocked_nodes"] = {}
    if not isinstance(checks, list):
        checks = lifecycle["checks"] = []
    if not isinstance(dispatch_input_profiles, dict):
        dispatch_input_profiles = lifecycle["dispatch_input_profiles"] = {}
    reused_node_fingerprints = {
        node_id: _resume_node_fingerprint(result)
        for node_id, result in sorted(node_results.items())
        if isinstance(result, dict) and node_id not in blocked_nodes
    }
    resume_audit = {
        "source_summary_path": _rel(resume_summary_path, harness_dir),
        "blocked_nodes_before": sorted(blocked_nodes),
        "reused_nodes": reused_node_fingerprints,
        "dispatched_nodes": [],
        "approved_human_gates": [],
    }
    lifecycle["resume_audit"] = resume_audit

    stopped_for_human_gate = False
    resume_after_node: str | None = None
    human_gate_mode = bool(args.include_human_gates) or any(
        gate_id in blocked_nodes or gate_id in node_results for gate_id in HUMAN_GATE_BY_ID
    )
    for gate_node_id in ("idea_acceptance_gate", "results_acceptance_gate"):
        if gate_node_id not in blocked_nodes:
            continue
        gate_spec = HUMAN_GATE_BY_ID[gate_node_id]
        _ensure_lifecycle_node(lifecycle, gate_spec)
        approval_ref = str(getattr(args, HUMAN_GATE_APPROVAL_ATTR[gate_node_id]) or "").strip()
        if not approval_ref:
            checks.append({
                "check": f"{gate_node_id}_resume_waiting",
                "status": "ok",
                "detail": "required human approval evidence was not supplied",
            })
            stopped_for_human_gate = True
            continue
        node_result, gate_result = _human_gate_approval_result(
            harness_dir=harness_dir,
            job_id=job_id,
            spec=gate_spec,
            approval_ref=approval_ref,
        )
        node_results[gate_node_id] = node_result
        gate_results[gate_node_id] = gate_result
        resume_audit["approved_human_gates"].append(gate_node_id)
        blocked_nodes.pop(gate_node_id, None)
        checks.append({
            "check": f"{gate_node_id}_resumed_approved",
            "status": "ok",
            "detail": approval_ref,
        })
        resume_after_node = "idea_evaluate" if gate_node_id == "idea_acceptance_gate" else "claim_verify"
        stopped_for_human_gate = False

    if resume_after_node:
        start_index = next(
            (index + 1 for index, spec in enumerate(BASE_NODE_SPECS) if spec["node_id"] == resume_after_node),
            len(BASE_NODE_SPECS),
        )
        for spec in BASE_NODE_SPECS[start_index:]:
            node_id = spec["node_id"]
            if node_id in node_results:
                continue
            _ensure_lifecycle_node(lifecycle, spec)
            code, node_summary = _run_scheduler_node(args, harness_dir, job_id, spec, node_results, dispatch_input_profiles)
            resume_audit["dispatched_nodes"].append(node_id)
            node_summaries[node_id] = node_summary
            node_ok = code == 0 and node_summary.get("status") == "passed"
            checks.append({
                "check": f"{node_id}_resumed_dispatched",
                "status": "ok" if node_ok else "error",
                "detail": str(node_summary.get("status")),
            })
            if node_ok:
                node_result, gate_result = _node_result_from_summary(
                    node_summary=node_summary,
                    harness_dir=harness_dir,
                    job_id=job_id,
                    gate_name=spec["gate"],
                )
                node_results[node_id] = node_result
                gate_results[node_id] = gate_result
            else:
                break
            if human_gate_mode and node_id in HUMAN_GATE_AFTER_NODE:
                gate_node_id = HUMAN_GATE_AFTER_NODE[node_id]
                if gate_node_id in node_results:
                    continue
                gate_spec = HUMAN_GATE_BY_ID[gate_node_id]
                _ensure_lifecycle_node(lifecycle, gate_spec)
                approval_ref = str(getattr(args, HUMAN_GATE_APPROVAL_ATTR[gate_node_id]) or "").strip()
                if approval_ref:
                    node_result, gate_result = _human_gate_approval_result(
                        harness_dir=harness_dir,
                        job_id=job_id,
                        spec=gate_spec,
                        approval_ref=approval_ref,
                    )
                    node_results[gate_node_id] = node_result
                    gate_results[gate_node_id] = gate_result
                    resume_audit["approved_human_gates"].append(gate_node_id)
                    checks.append({
                        "check": f"{gate_node_id}_resumed_approved",
                        "status": "ok",
                        "detail": approval_ref,
                    })
                else:
                    blocked_nodes[gate_node_id] = _blocked_human_gate(job_id, gate_node_id)
                    checks.append({
                        "check": f"{gate_node_id}_resume_blocked",
                        "status": "ok",
                        "detail": "waiting for durable human approval evidence",
                    })
                    stopped_for_human_gate = True
                    break

    for tail_index, spec in enumerate(CONFIGURED_TAIL_NODE_SPECS):
        if stopped_for_human_gate:
            break
        node_id = spec["node_id"]
        _ensure_lifecycle_node(lifecycle, spec)
        if node_id in node_results:
            continue
        if node_id in EXTERNAL_NODE_BY_ID and node_id not in blocked_nodes:
            blocked_nodes[node_id] = _blocked_external_node(job_id, node_id)

        if node_id in EXTERNAL_NODE_BY_ID and node_id in blocked_nodes and not _resume_evidence_supplied(args, node_id):
            _record_unsupplied_external_tail_blockers(
                lifecycle=lifecycle,
                args=args,
                job_id=job_id,
                node_results=node_results,
                blocked_nodes=blocked_nodes,
                checks=checks,
                start_index=tail_index,
            )
            break

        code, node_summary = _run_scheduler_node(args, harness_dir, job_id, spec, node_results, dispatch_input_profiles)
        resume_audit["dispatched_nodes"].append(node_id)
        node_summaries[node_id] = node_summary
        node_ok = code == 0 and node_summary.get("status") == "passed"
        checks.append({
            "check": f"{node_id}_resumed_dispatched",
            "status": "ok" if node_ok else "error",
            "detail": str(node_summary.get("status")),
        })
        if node_ok:
            node_result, gate_result = _node_result_from_summary(
                node_summary=node_summary,
                harness_dir=harness_dir,
                job_id=job_id,
                gate_name=spec["gate"],
            )
            node_results[node_id] = node_result
            gate_results[node_id] = gate_result
            blocked_nodes.pop(node_id, None)
        else:
            break

    output_root = _resolve_harness_path(
        harness_dir,
        args.output_dir or resume_summary_path.parent,
    )
    summary_path = _resolve_harness_path(
        harness_dir,
        args.out or output_root / "scientific_lifecycle_runtime.resumed.json",
    )
    changed_reused_nodes = [
        node_id
        for node_id, fingerprint in reused_node_fingerprints.items()
        if _resume_node_fingerprint(node_results.get(node_id) or {}) != fingerprint
    ]
    lifecycle["resume_boundary"] = _scheduler_resume_boundary(
        resume_audit=resume_audit,
        changed_reused_nodes=changed_reused_nodes,
    )
    checks.append({
        "check": "resume_reused_nodes_preserved",
        "status": "error" if changed_reused_nodes else "ok",
        "detail": ",".join(changed_reused_nodes) if changed_reused_nodes else f"{len(reused_node_fingerprints)} reused nodes",
    })
    checks.append({
        "check": "scheduler_resume_no_rerun_boundary",
        "status": "ok" if lifecycle["resume_boundary"]["no_rerun_verified"] else "error",
        "detail": ",".join(lifecycle["resume_boundary"]["blocking_reasons"])
        if lifecycle["resume_boundary"]["blocking_reasons"]
        else f"{lifecycle['resume_boundary']['reused_node_count']} reused nodes",
    })
    required_nodes_for_alignment = [
        str(node_id)
        for node_id in lifecycle.get("required_nodes", [])
        if isinstance(node_id, str)
    ]
    _record_workflow_config_alignment(
        lifecycle,
        args,
        required_nodes=required_nodes_for_alignment,
        checks=checks,
    )
    lifecycle["lease_boundary"] = _scheduler_lease_boundary(
        harness_dir=harness_dir,
        job_id=job_id,
        required_nodes=required_nodes_for_alignment,
        lease_dir=summary_path.parent,
        resume=True,
    )
    checks.append({
        "check": "scheduler_local_lease_boundary",
        "status": "ok" if lifecycle["lease_boundary"]["local_lease_recorded"] else "error",
        "detail": lifecycle["lease_boundary"]["lease_path"],
    })
    lifecycle["dispatch_boundary"] = _scheduler_dispatch_boundary(
        args,
        required_nodes=required_nodes_for_alignment,
        dispatch_input_profiles=dispatch_input_profiles,
    )
    if bool(getattr(args, "require_production_dispatch", False)) and not lifecycle["dispatch_boundary"]["production_ready"]:
        checks.append({
            "check": "production_dispatch_boundary",
            "status": "error",
            "detail": ",".join(lifecycle["dispatch_boundary"]["blocking_reasons"]),
        })
    lifecycle["lifecycle_status"] = "blocked" if blocked_nodes else "passed"
    return _write_and_gate_lifecycle(
        lifecycle,
        summary_path,
        harness_dir,
        blocked_nodes=blocked_nodes,
        checks=checks,
        gate_check_name="resume_lifecycle_runtime_gate_passed",
        authorization_blocked_exit_zero=bool(getattr(args, "authorization_blocked_exit_zero", False)),
    )


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    if args.resume_summary:
        return run_resume(args)

    harness_dir = Path(args.harness_dir).expanduser().resolve()
    job_id = args.job_id or f"job-scientific-lifecycle-smoke-{_utc_stamp()}"
    lifecycle_dir = _resolve_harness_path(
        harness_dir,
        args.output_dir or f"artifacts/scientific/scheduler-lifecycle-smoke/{job_id}",
    )
    summary_path = _resolve_harness_path(
        harness_dir,
        args.out or lifecycle_dir / "scientific_lifecycle_runtime.json",
    )

    node_summaries: dict[str, Any] = {}
    node_results: dict[str, Any] = {}
    gate_results: dict[str, Any] = {}
    blocked_nodes: dict[str, Any] = {}
    checks: list[dict[str, str]] = []
    executed_specs: list[dict[str, str]] = []
    human_gate_specs: list[dict[str, str]] = []
    dispatch_input_profiles: dict[str, Any] = {}
    stopped_for_human_gate = False

    for spec in BASE_NODE_SPECS:
        code, node_summary = _run_scheduler_node(args, harness_dir, job_id, spec, node_results, dispatch_input_profiles)
        executed_specs.append(spec)
        node_summaries[spec["node_id"]] = node_summary
        node_ok = code == 0 and node_summary.get("status") == "passed"
        checks.append({
            "check": f"{spec['node_id']}_dispatched",
            "status": "ok" if node_ok else "error",
            "detail": str(node_summary.get("status")),
        })
        if node_ok:
            node_result, gate_result = _node_result_from_summary(
                node_summary=node_summary,
                harness_dir=harness_dir,
                job_id=job_id,
                gate_name=spec["gate"],
            )
            node_results[spec["node_id"]] = node_result
            gate_results[spec["node_id"]] = gate_result
        else:
            break
        if args.include_human_gates and spec["node_id"] in HUMAN_GATE_AFTER_NODE:
            gate_node_id = HUMAN_GATE_AFTER_NODE[spec["node_id"]]
            gate_spec = HUMAN_GATE_BY_ID[gate_node_id]
            human_gate_specs.append(gate_spec)
            approval_ref = str(getattr(args, HUMAN_GATE_APPROVAL_ATTR[gate_node_id]) or "").strip()
            if approval_ref:
                node_result, gate_result = _human_gate_approval_result(
                    harness_dir=harness_dir,
                    job_id=job_id,
                    spec=gate_spec,
                    approval_ref=approval_ref,
                )
                node_results[gate_node_id] = node_result
                gate_results[gate_node_id] = gate_result
                checks.append({
                    "check": f"{gate_node_id}_approved",
                    "status": "ok",
                    "detail": approval_ref,
                })
            else:
                blocked_nodes[gate_node_id] = _blocked_human_gate(job_id, gate_node_id)
                checks.append({
                    "check": f"{gate_node_id}_blocked",
                    "status": "ok",
                    "detail": "waiting for durable human approval evidence",
                })
                stopped_for_human_gate = True
                break

    lifecycle_specs = [*executed_specs, *human_gate_specs] if args.include_human_gates else BASE_NODE_SPECS
    required_nodes = [spec["node_id"] for spec in lifecycle_specs]
    nodes = [
        {
            "id": spec["node_id"],
            "logical_operator": spec["logical_operator"],
            "operator_id": spec["operator_id"],
            "action": spec["action"],
            "gate": spec["gate"],
        }
        for spec in lifecycle_specs
    ]
    if args.dispatch_external_evidence and not stopped_for_human_gate and len(node_results) >= len(BASE_NODE_SPECS):
        for spec in CONFIGURED_TAIL_NODE_SPECS:
            node_id = spec["node_id"]
            _append_required_node(required_nodes, nodes, spec)
            if node_id in EXTERNAL_NODE_BY_ID and not _resume_evidence_supplied(args, node_id):
                blocked_nodes[node_id] = _blocked_external_node(job_id, node_id)
                checks.append({
                    "check": f"{node_id}_external_evidence_supplied",
                    "status": "error",
                    "detail": "required external evidence was not supplied",
                })
                break
            code, node_summary = _run_scheduler_node(args, harness_dir, job_id, spec, node_results, dispatch_input_profiles)
            node_summaries[node_id] = node_summary
            node_ok = code == 0 and node_summary.get("status") == "passed"
            checks.append({
                "check": f"{node_id}_dispatched",
                "status": "ok" if node_ok else "error",
                "detail": str(node_summary.get("status")),
            })
            if node_ok:
                node_result, gate_result = _node_result_from_summary(
                    node_summary=node_summary,
                    harness_dir=harness_dir,
                    job_id=job_id,
                    gate_name=spec["gate"],
                )
                node_results[node_id] = node_result
                gate_results[node_id] = gate_result
            else:
                break

    if not args.dispatch_external_evidence and not stopped_for_human_gate and len(node_results) >= len(BASE_NODE_SPECS):
        for node_id in EXTERNAL_NODE_BY_ID:
            if node_id in node_results or node_id in blocked_nodes:
                continue
            blocked = _blocked_external_node(job_id, node_id)
            _append_required_node(required_nodes, nodes, EXTERNAL_NODE_BY_ID[node_id])
            blocked_nodes[node_id] = blocked
        checks.append({
            "check": "external_blocked_nodes_recorded",
            "status": "ok",
            "detail": ",".join(sorted(blocked_nodes)),
        })

    unblocked_required_nodes = [node_id for node_id in required_nodes if node_id not in blocked_nodes]
    nodes_ok = all(node_id in node_results for node_id in unblocked_required_nodes) and all(
        item["status"] == "ok" for item in checks
    )
    lifecycle_status = "passed" if nodes_ok and not blocked_nodes else "blocked" if nodes_ok else "failed"
    lifecycle = {
        "schema": "scientific_lifecycle.v1",
        "workflow_id": DEFAULT_WORKFLOW_ID,
        "job_id": job_id,
        "sprint_id": job_id,
        "lifecycle_status": lifecycle_status,
        "execution_owner": "solar.operator_runtime.scheduler_lifecycle_smoke",
        "required_nodes": required_nodes,
        "nodes": nodes,
        "node_results": node_results,
        "gate_results": gate_results,
        "blocked_nodes": blocked_nodes,
        "node_summaries": node_summaries,
        "dispatch_input_profiles": dispatch_input_profiles,
        "checks": checks,
    }
    authorization_requests = _authorization_requests_from_blocked(blocked_nodes)
    lifecycle["authorization_required"] = bool(authorization_requests)
    lifecycle["authorization_requests"] = authorization_requests
    lifecycle["authorization_prompt"] = (
        "One or more legacy lifecycle gates are waiting for authorization or runtime evidence; "
        "supply the requested access patch and resume the lifecycle."
        if authorization_requests
        else ""
    )
    _record_workflow_config_alignment(
        lifecycle,
        args,
        required_nodes=required_nodes,
        checks=checks,
    )
    lifecycle["lease_boundary"] = _scheduler_lease_boundary(
        harness_dir=harness_dir,
        job_id=job_id,
        required_nodes=required_nodes,
        lease_dir=summary_path.parent,
        resume=False,
    )
    checks.append({
        "check": "scheduler_local_lease_boundary",
        "status": "ok" if lifecycle["lease_boundary"]["local_lease_recorded"] else "error",
        "detail": lifecycle["lease_boundary"]["lease_path"],
    })
    lifecycle["dispatch_boundary"] = _scheduler_dispatch_boundary(
        args,
        required_nodes=required_nodes,
        dispatch_input_profiles=dispatch_input_profiles,
    )
    if bool(getattr(args, "require_production_dispatch", False)) and not lifecycle["dispatch_boundary"]["production_ready"]:
        checks.append({
            "check": "production_dispatch_boundary",
            "status": "error",
            "detail": ",".join(lifecycle["dispatch_boundary"]["blocking_reasons"]),
        })
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lifecycle_gate = _gate_lifecycle(summary_path, harness_dir)
    lifecycle["lifecycle_gate_result"] = lifecycle_gate
    lifecycle_gate_ok = lifecycle_gate.get("ok") is True or (
        bool(blocked_nodes) and str(lifecycle_gate.get("status") or "") == "inconclusive"
    )
    checks.append({
        "check": "lifecycle_runtime_gate_passed",
        "status": "ok" if lifecycle_gate_ok else "error",
        "detail": str(lifecycle_gate.get("status")),
    })
    if all(item["status"] == "ok" for item in checks):
        lifecycle["lifecycle_status"] = "blocked" if blocked_nodes else "passed"
    else:
        lifecycle["lifecycle_status"] = "failed"
    lifecycle["summary_path"] = _rel(summary_path, harness_dir)
    summary_path.write_text(json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if lifecycle["lifecycle_status"] == "passed":
        return 0, lifecycle
    if lifecycle["lifecycle_status"] == "blocked":
        return (0 if bool(getattr(args, "authorization_blocked_exit_zero", False)) else 3), lifecycle
    return 1, lifecycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness-dir", default=str(Path(os.environ.get("HARNESS_DIR", REPO_HARNESS_DIR))))
    parser.add_argument("--job-id")
    parser.add_argument("--paper", default=DEFAULT_PAPER)
    parser.add_argument("--output-dir")
    parser.add_argument("--out", help="Optional lifecycle summary JSON path, relative to --harness-dir.")
    parser.add_argument("--workflow-config", default=str(DEFAULT_WORKFLOW_CONFIG), help="Declared workflow config used for scheduler drift detection.")
    parser.add_argument(
        "--require-workflow-config-alignment",
        action="store_true",
        help="Fail when the smoke runner's required nodes or order diverge from the declared workflow config.",
    )
    parser.add_argument(
        "--require-production-dispatch",
        action="store_true",
        help="Fail when the lifecycle is still backed by the bounded smoke runner or fixture/smoke inputs.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--lease-ttl-seconds", type=int, default=120)
    parser.add_argument("--allow-existing-result", action="store_true")
    parser.add_argument("--include-blocked-external", action="store_true")
    parser.add_argument("--include-human-gates", action="store_true", help="Record native AutoSci human approval gates as scheduler-visible blocked/passed nodes.")
    parser.add_argument(
        "--authorization-blocked-exit-zero",
        action="store_true",
        help="Return exit code 0 for authorization-blocked lifecycle runs while preserving lifecycle_status=blocked.",
    )
    parser.add_argument("--idea-approval-ref", help="Durable approval reference for the idea acceptance human gate.")
    parser.add_argument("--results-approval-ref", help="Durable approval reference for the results acceptance human gate.")
    parser.add_argument("--resume-summary", help="Blocked lifecycle summary JSON to resume, relative to --harness-dir.")
    parser.add_argument(
        "--review-llm-evidence",
        action="append",
        help="Completed artifact_review.v1 Review LLM evidence path used to unblock report_plan.",
    )
    parser.add_argument("--compile-target", help="LaTeX/PDF target path used to unblock publication_produce.")
    parser.add_argument("--compile-approval-ref", help="Approval reference for supplied or executed publication compile evidence.")
    parser.add_argument("--compile-runtime-evidence", action="append", help="Approved paper compile runtime evidence JSON.")
    parser.add_argument("--compile-allowlist-evidence", action="append", help="Allowlist evidence for publication compile runtime.")
    parser.add_argument("--compile-before-artifact", action="append", help="Before artifact for publication compile runtime.")
    parser.add_argument("--compile-after-artifact", action="append", help="After artifact for publication compile runtime.")
    parser.add_argument("--compile-execute-approved", action="store_true", help="Execute the approved allowlisted TeX command during publication_produce.")
    parser.add_argument("--compile-executor-timeout-seconds", type=int, default=120, help="Timeout for an approved publication compile command.")
    parser.add_argument("--allow-network-fetch", action="store_true", help="Allow discovery actions to call configured online sources.")
    parser.add_argument("--disable-fixture-fallback", action="store_true", help="Prevent discovery from using local fixture candidates.")
    parser.add_argument(
        "--require-online-source-evidence",
        action="store_true",
        help="Require completed non-fixture online literature discovery evidence.",
    )
    parser.add_argument("--min-online-source-channels", type=int, default=1)
    parser.add_argument("--discovery-query", help="Query for the literature discovery node.")
    parser.add_argument("--discovery-mode", help="Explicit discovery mode such as topic, anchors, wiki, or venue.")
    parser.add_argument("--discovery-limit", type=int, default=3)
    parser.add_argument("--source-approval-ref", help="Approval reference for supplied online source runtime evidence.")
    parser.add_argument("--source-runtime-evidence", action="append", help="Approved source-fetch runtime evidence JSON.")
    parser.add_argument("--source-allowlist-evidence", action="append", help="Allowlist evidence for source-fetch runtime.")
    parser.add_argument("--source-before-artifact", action="append", help="Before artifact for source-fetch runtime.")
    parser.add_argument("--source-after-artifact", action="append", help="After artifact for source-fetch runtime.")
    parser.add_argument("--experiment-approval-ref", help="Approval reference for supplied experiment runtime evidence.")
    parser.add_argument("--experiment-runtime-evidence", action="append", help="Approved experiment runtime/result evidence JSON.")
    parser.add_argument("--experiment-allowlist-evidence", action="append", help="Allowlist evidence for experiment runtime.")
    parser.add_argument("--experiment-before-artifact", action="append", help="Before artifact for experiment runtime.")
    parser.add_argument("--experiment-after-artifact", action="append", help="After artifact for experiment runtime.")
    parser.add_argument("--experiment-execute-approved", action="store_true", help="Execute the approved allowlisted experiment command during experiment_run.")
    parser.add_argument("--experiment-executor-timeout-seconds", type=int, default=120, help="Timeout for an approved experiment executor command.")
    parser.add_argument(
        "--dispatch-external-evidence",
        action="store_true",
        help="Dispatch report_plan and publication_produce in the same lifecycle run when their evidence is supplied.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    code, summary = run(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
