"""Artifact builders for the Requirement Compiler."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sprint_handoff_artifacts(sprint_id: str, target: str) -> list[str]:
    if sprint_id and sprint_id != "N/A":
        artifacts = [
            f"{sprint_id}.request_envelope.json",
            f"{sprint_id}.requirement_ir.json",
            f"{sprint_id}.prd.md",
            f"{sprint_id}.Contracts.yaml",
            f"{sprint_id}.task_graph.json",
            f"{sprint_id}.task_dag.state.json",
        ]
        if target == "solar_harness":
            artifacts.append(f"{sprint_id}.handoff.md")
        return artifacts
    artifacts = [
        ".pm/request_envelope.json",
        ".pm/requirement_ir.json",
        ".pm/prd.md",
        ".pm/Contracts.yaml",
        ".pm/task_dag.json",
        ".pm/task_dag.state.json",
    ]
    if target == "solar_harness":
        artifacts.append(".pm/handoff/solar_harness_handoff.md")
    return artifacts


def make_artifact_refs(sprint_id: str) -> dict[str, str]:
    if sprint_id and sprint_id != "N/A":
        prefix = sprint_id
        return {
            "request_envelope": f"{prefix}.request_envelope.json",
            "requirement_ir": f"{prefix}.requirement_ir.json",
            "prd": f"{prefix}.prd.md",
            "contracts_manifest": f"{prefix}.Contracts.yaml",
            "task_dag": f"{prefix}.task_graph.json",
            "task_dag_state": f"{prefix}.task_dag.state.json",
            "closure": f"{prefix}.closure.json",
            "codex_handoff": f"{prefix}.codex_handoff.md",
            "solar_harness_handoff": f"{prefix}.handoff.md",
        }
    return {
        "request_envelope": ".pm/request_envelope.json",
        "requirement_ir": ".pm/requirement_ir.json",
        "prd": ".pm/prd.md",
        "contracts_manifest": ".pm/Contracts.yaml",
        "task_dag": ".pm/task_dag.json",
        "task_dag_state": ".pm/task_dag.state.json",
        "closure": ".pm/closure.json",
        "codex_handoff": ".pm/handoff/codex_handoff.md",
        "solar_harness_handoff": ".pm/handoff/solar_harness_handoff.md",
    }


def build_request_envelope(
    *,
    request_id: str,
    raw_text: str,
    classification: dict[str, str],
    repo_context: list[str],
    papers: list[str],
    logs: list[str],
    created_at: str,
    sprint_id: str,
    target_system: str,
) -> dict[str, Any]:
    return {
        "schema_version": "solar.request_envelope.v1",
        "request_id": request_id,
        "raw_text": raw_text,
        "source": "codex_pm_router",
        "classification": classification,
        "attachments": {
            "papers": papers,
            "logs": logs,
        },
        "repo_context": {
            "paths": repo_context,
            "target_system": target_system,
            "sprint_id": sprint_id or "N/A",
        },
        "created_at": created_at,
    }


def build_contract_manifest(
    *,
    sprint_id: str,
    requirement_ir_ref: str,
    product: dict[str, Any],
    interface: dict[str, Any],
    agent_execution: dict[str, Any],
    research: dict[str, Any],
) -> dict[str, Any]:
    def _entry(path: str, payload: dict[str, Any]) -> dict[str, str]:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return {
            "path": path,
            "digest": digest_text(serialized),
        }

    return {
        "schema_version": "solar.contract_manifest.v1",
        "sprint_id": sprint_id or "N/A",
        "requirement_ir_ref": requirement_ir_ref,
        "contracts": {
            "product": _entry("contracts/product.yaml", product),
            "interface": _entry("contracts/interface.yaml", interface),
            "agent_execution": _entry("contracts/agent_execution.yaml", agent_execution),
            "research": _entry("contracts/research.yaml", research),
        },
    }


def build_task_graph_state(
    *,
    sprint_id: str,
    graph: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "solar.task_graph_state.v1",
        "sprint_id": sprint_id or str(graph.get("sprint_id") or "N/A"),
        "graph_ref": f"{sprint_id}.task_graph.json" if sprint_id and sprint_id != "N/A" else ".pm/task_dag.json",
        "node_results": {},
        "gate_results": {},
        "leases": {},
        "dispatch_ids": {},
        "events": [],
    }


def build_closure_record(
    *,
    sprint_id: str,
    requirement_ir_ref: str,
    contracts_manifest_ref: str,
    graph_ref: str,
) -> dict[str, Any]:
    return {
        "schema_version": "solar.closure_record.v1",
        "sprint_id": sprint_id or "N/A",
        "status": "pending",
        "requirement_ir_ref": requirement_ir_ref,
        "contracts_manifest_ref": contracts_manifest_ref,
        "graph_ref": graph_ref,
        "all_nodes_passed": False,
        "all_required_gates_passed": False,
        "acceptance_traceability_coverage": 0,
        "tests": [],
        "evals": [],
        "changed_files": [],
        "residual_risks": [],
    }
