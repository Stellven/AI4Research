#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import GateResult, run_cli
from evaluators.scientific.lifecycle_runtime_gate import evaluate as evaluate_runtime

SCHEMA = "scientific_lifecycle.v1"

FULL_LIFECYCLE_OPERATORS = [
    "ScientificLiteratureDiscoverer",
    "ScientificPaperIngestor",
    "ScientificPaperAnalyzer",
    "ScientificMemoryUpdater",
    "ScientificGraphUpdater",
    "ScientificClaimExtractor",
    "ScientificMethodExtractor",
    "ScientificCodeEvidenceMapper",
    "ScientificIdeaGenerator",
    "ScientificIdeaEvaluator",
    "ScientificExperimentDesigner",
    "ScientificExperimentRunner",
    "ScientificExperimentMonitor",
    "ScientificClaimVerifier",
    "ScientificReportPlanner",
    "ScientificReportDrafter",
    "ScientificArtifactReviewer",
    "ScientificPublicationProducer",
    "ScientificMemoryUpdater",
    "ScientificWorkflowEvolver",
]

RESUME_LIFECYCLE_OPERATORS = [
    "ScientificLiteratureDiscoverer",
    "ScientificClaimExtractor",
    "ScientificMethodExtractor",
    "ScientificExperimentDesigner",
    "ScientificClaimVerifier",
    "ScientificReportDrafter",
    "ScientificMemoryUpdater",
    "ScientificWorkflowEvolver",
]

EXPECTED_ARTIFACT_ENTRIES = {
    "01_paper/",
    "02_claims/",
    "03_methods/",
    "04_code_evidence/",
    "05_ideas/",
    "06_experiment_plan/",
    "07_experiment_result/",
    "08_verdict/",
    "09_report/",
    "10_memory_update/",
    "lifecycle_summary.json",
    "evidence.jsonl",
}

EXPECTED_ARTIFACT_SLOTS = {
    entry.rstrip("/") for entry in EXPECTED_ARTIFACT_ENTRIES if entry.endswith("/")
}

BOUNDED_EXECUTION_OPERATORS = {
    "ScientificExperimentRunner",
    "ScientificExperimentMonitor",
}


def _is_runtime_summary(payload: dict[str, Any]) -> bool:
    return payload.get("schema") == SCHEMA and "artifact_contract" not in payload


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons: list[str] = []
    warnings: list[str] = []
    schema = payload.get("schema")
    if schema is not None and schema != SCHEMA:
        reasons.append(f"schema must be {SCHEMA}")
    is_summary = _is_runtime_summary(payload)
    if is_summary:
        return evaluate_runtime(payload, path)

    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        reasons.append("lifecycle graph must contain nodes")
        return _finish(payload, reasons, warnings, path)

    expected_operators = _expected_operator_sequence(payload, nodes)
    if expected_operators is None:
        reasons.append(
            "lifecycle graph must match scientific_research_lifecycle_full_v1 "
            "or scientific_research_resume_v1 operator sequence"
        )
    else:
        _validate_operator_sequence(nodes, expected_operators, reasons)

    ids = {str(node.get("id") or "") for node in nodes if isinstance(node, dict)}
    if len(ids) != len(nodes):
        reasons.append("lifecycle graph node ids must be unique and present")

    required_gates = _string_set(payload.get("required_gates"))
    parent_gate = _validate_parent_gate(payload, required_gates, reasons, is_summary=is_summary)
    artifact_contract = _validate_artifact_contract(payload, nodes, reasons, is_summary=is_summary)
    resume_contract = _validate_resume_contract(payload, reasons, is_summary=is_summary)
    _validate_lifecycle_artifacts(payload, artifact_contract, reasons, is_summary=is_summary)

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            reasons.append(f"nodes[{index}] must be an object")
            continue
        node_id = str(node.get("id") or f"nodes[{index}]")
        _validate_no_black_box(node, node_id, reasons, is_summary=is_summary)
        required_fields = ("logical_operator", "gate") if is_summary else (
            "logical_operator",
            "required_capabilities",
            "read_scope",
            "write_scope",
            "gate",
        )
        for field in required_fields:
            if not node.get(field):
                reasons.append(f"{node_id}.{field} is required")
        gate = str(node.get("gate") or "")
        if gate and required_gates and gate not in required_gates:
            reasons.append(f"{node_id}.gate must be listed in required_gates")
        _validate_capabilities(node, node_id, reasons, is_summary=is_summary)
        _validate_evidence_policy(node, node_id, reasons)
        _validate_artifact_binding(
            node,
            node_id,
            artifact_contract,
            parent_gate,
            resume_contract,
            reasons,
        )
        for dep in node.get("depends_on") or []:
            if dep not in ids:
                reasons.append(f"{node_id} depends on missing node {dep}")
        if not is_summary and node.get("logical_operator") in BOUNDED_EXECUTION_OPERATORS:
            bounded = (node.get("execution_policy") or {}).get("mode") == "fixture_or_human_approved"
            if not bounded and not node.get("approval_gate"):
                reasons.append(f"{node_id} requires bounded execution mode or approval_gate")

    if expected_operators is not None:
        _validate_linear_dependencies(nodes, reasons, require_declared=not is_summary)

    return _finish(payload, reasons, warnings, path)


def _expected_operator_sequence(payload: dict[str, Any], nodes: list[Any]) -> list[str] | None:
    workflow_id = str(payload.get("workflow_id") or "")
    operators = [
        str(node.get("logical_operator") or "")
        for node in nodes
        if isinstance(node, dict)
    ]
    if workflow_id == "scientific_research_lifecycle_full_v1":
        return FULL_LIFECYCLE_OPERATORS
    if workflow_id == "scientific_research_resume_v1":
        return RESUME_LIFECYCLE_OPERATORS
    if operators == FULL_LIFECYCLE_OPERATORS:
        return FULL_LIFECYCLE_OPERATORS
    if operators == RESUME_LIFECYCLE_OPERATORS:
        return RESUME_LIFECYCLE_OPERATORS
    return None


def _validate_operator_sequence(
    nodes: list[Any],
    expected_operators: list[str],
    reasons: list[str],
) -> None:
    actual = [
        str(node.get("logical_operator") or "")
        for node in nodes
        if isinstance(node, dict)
    ]
    if actual != expected_operators:
        reasons.append(
            "lifecycle operator sequence mismatch: "
            f"expected {expected_operators}, got {actual}"
        )


def _validate_linear_dependencies(
    nodes: list[Any],
    reasons: list[str],
    *,
    require_declared: bool = True,
) -> None:
    valid_nodes = [node for node in nodes if isinstance(node, dict)]
    for index, node in enumerate(valid_nodes):
        node_id = str(node.get("id") or f"nodes[{index}]")
        depends_on = node.get("depends_on") or []
        if index == 0:
            if require_declared and depends_on:
                reasons.append(f"{node_id}.depends_on must be empty for the first lifecycle node")
            continue
        previous_id = str(valid_nodes[index - 1].get("id") or "")
        if not require_declared and "depends_on" not in node:
            continue
        if depends_on != [previous_id]:
            reasons.append(f"{node_id}.depends_on must be [{previous_id!r}]")
        required_node_id = node.get("required_node_id")
        if required_node_id is not None and required_node_id != previous_id:
            reasons.append(f"{node_id}.required_node_id must be {previous_id}")
        required_status = node.get("required_node_status")
        if required_status is not None and required_status != "passed":
            reasons.append(f"{node_id}.required_node_status must be passed")


def _validate_parent_gate(
    payload: dict[str, Any],
    required_gates: set[str],
    reasons: list[str],
    *,
    is_summary: bool = False,
) -> dict[str, Any]:
    parent_gate = payload.get("parent_gate")
    if not isinstance(parent_gate, dict):
        if is_summary:
            evidence_log = str(payload.get("evidence_log") or "").strip()
            summary_artifact = str(payload.get("summary_artifact") or "").strip()
            if not evidence_log:
                reasons.append("evidence_log is required for lifecycle summary")
            if not summary_artifact:
                reasons.append("summary_artifact is required for lifecycle summary")
            return {
                "id": str(payload.get("parent_gate_id") or "G_SCIENTIFIC_LIFECYCLE"),
                "evidence_log": evidence_log,
                "summary_artifact": summary_artifact,
            }
        reasons.append("parent_gate must be declared for lifecycle summary")
        return {}
    gate_id = str(parent_gate.get("id") or "")
    if not gate_id:
        reasons.append("parent_gate.id is required")
    elif required_gates and gate_id not in required_gates:
        reasons.append("parent_gate.id must be listed in required_gates")
    evaluator = str(parent_gate.get("evaluator") or "")
    if not evaluator.endswith("evaluators/scientific/lifecycle_gate.py"):
        reasons.append("parent_gate.evaluator must point to lifecycle_gate.py")
    for field in ("summary_artifact", "evidence_log"):
        if not str(parent_gate.get(field) or "").strip():
            reasons.append(f"parent_gate.{field} is required")
    if parent_gate.get("requires_node_gates") is not True:
        reasons.append("parent_gate.requires_node_gates must be true")
    if parent_gate.get("requires_inspectable_artifact_tree") is not True:
        reasons.append("parent_gate.requires_inspectable_artifact_tree must be true")
    return parent_gate


def _validate_artifact_contract(
    payload: dict[str, Any],
    nodes: list[Any],
    reasons: list[str],
    *,
    is_summary: bool = False,
) -> dict[str, Any]:
    artifact_contract = payload.get("artifact_contract")
    if not isinstance(artifact_contract, dict):
        if is_summary:
            root = str(payload.get("artifact_root") or "").strip()
            if not root:
                reasons.append("artifact_root is required for lifecycle summary")
            node_artifacts: dict[str, dict[str, str]] = {}
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_id = str(node.get("id") or "")
                artifact = str(node.get("artifact") or "").strip()
                expected_schema = str(node.get("expected_schema") or "").strip()
                if node_id and artifact:
                    node_artifacts[node_id] = {
                        "slot": _slot_for_artifact(root, artifact),
                        "path": artifact,
                        "schema": expected_schema,
                    }
            return {
                "root": root,
                "summary_artifact": str(payload.get("summary_artifact") or ""),
                "evidence_log": str(payload.get("evidence_log") or ""),
                "node_artifacts": node_artifacts,
            }
        reasons.append("artifact_contract must be declared")
        return {}
    root = str(artifact_contract.get("root") or "")
    if not root.startswith("artifacts/scientific/"):
        reasons.append("artifact_contract.root must be under artifacts/scientific/<job_id>")
    required_entries = set(_string_list(artifact_contract.get("required_entries")))
    missing_entries = sorted(EXPECTED_ARTIFACT_ENTRIES - required_entries)
    if missing_entries:
        reasons.append(f"artifact_contract.required_entries missing {missing_entries}")
    if str(artifact_contract.get("summary_artifact") or "") != f"{root}/lifecycle_summary.json":
        reasons.append("artifact_contract.summary_artifact must be <root>/lifecycle_summary.json")
    if str(artifact_contract.get("evidence_log") or "") != f"{root}/evidence.jsonl":
        reasons.append("artifact_contract.evidence_log must be <root>/evidence.jsonl")

    node_artifacts = artifact_contract.get("node_artifacts")
    if not isinstance(node_artifacts, dict):
        reasons.append("artifact_contract.node_artifacts must map node ids to typed artifacts")
    else:
        node_ids = {
            str(node.get("id") or "")
            for node in nodes
            if isinstance(node, dict)
        }
        missing_nodes = sorted(node_ids - set(node_artifacts))
        if missing_nodes:
            reasons.append(f"artifact_contract.node_artifacts missing {missing_nodes}")
    return artifact_contract


def _validate_resume_contract(
    payload: dict[str, Any],
    reasons: list[str],
    *,
    is_summary: bool = False,
) -> dict[str, Any]:
    resume_contract = payload.get("resume_contract")
    if not isinstance(resume_contract, dict):
        if is_summary:
            return {}
        reasons.append("resume_contract must be declared")
        return {}
    workflow_id = str(payload.get("workflow_id") or "")
    mode = str(resume_contract.get("mode") or "")
    if workflow_id == "scientific_research_resume_v1":
        if mode != "resume_from_existing_artifact_tree":
            reasons.append("resume workflow must declare resume_from_existing_artifact_tree mode")
    elif workflow_id == "scientific_research_lifecycle_full_v1":
        if mode != "resume_from_state_or_artifacts":
            reasons.append("full lifecycle must declare resume_from_state_or_artifacts mode")
    elif not mode:
        reasons.append("resume_contract.mode is required")
    if resume_contract.get("skip_completed_nodes") is not True:
        reasons.append("resume_contract.skip_completed_nodes must be true")
    if resume_contract.get("do_not_rerun_completed_nodes") is not True:
        reasons.append("resume_contract.do_not_rerun_completed_nodes must be true")
    completed_statuses = set(_string_list(resume_contract.get("completed_statuses")))
    if "passed" not in completed_statuses:
        reasons.append("resume_contract.completed_statuses must include passed")
    rerun_statuses = set(_string_list(resume_contract.get("rerun_statuses")))
    required_reruns = {"failed", "inconclusive", "missing_artifact", "schema_invalid"}
    missing_reruns = sorted(required_reruns - rerun_statuses)
    if missing_reruns:
        reasons.append(f"resume_contract.rerun_statuses missing {missing_reruns}")
    state_sources = set(_string_list(resume_contract.get("state_sources")))
    for required in ("task_dag.state.json", "lifecycle_summary.json", "evidence.jsonl"):
        if required not in state_sources:
            reasons.append(f"resume_contract.state_sources must include {required}")
    return resume_contract


def _validate_lifecycle_artifacts(
    payload: dict[str, Any],
    artifact_contract: dict[str, Any],
    reasons: list[str],
    *,
    is_summary: bool = False,
) -> None:
    lifecycle_artifacts = payload.get("lifecycle_artifacts")
    if not isinstance(lifecycle_artifacts, dict):
        if is_summary:
            root = str(artifact_contract.get("root") or "")
            summary_artifact = str(artifact_contract.get("summary_artifact") or "")
            evidence_log = str(artifact_contract.get("evidence_log") or "")
            if root and summary_artifact != f"{root}/lifecycle_summary.json":
                reasons.append("summary_artifact must be <artifact_root>/lifecycle_summary.json")
            if root and evidence_log != f"{root}/evidence.jsonl":
                reasons.append("evidence_log must be <artifact_root>/evidence.jsonl")
            return
        reasons.append("lifecycle_artifacts must be declared")
        return
    root = str(artifact_contract.get("root") or "")
    expected_tree = set(_string_list(lifecycle_artifacts.get("expected_tree")))
    required_paths = {f"{root}/{entry}" for entry in EXPECTED_ARTIFACT_ENTRIES}
    missing_paths = sorted(required_paths - expected_tree)
    if missing_paths:
        reasons.append(f"lifecycle_artifacts.expected_tree missing {missing_paths}")
    if str(lifecycle_artifacts.get("human_inspection_root") or "") != root:
        reasons.append("lifecycle_artifacts.human_inspection_root must match artifact_contract.root")


def _validate_no_black_box(
    node: dict[str, Any],
    node_id: str,
    reasons: list[str],
    *,
    is_summary: bool = False,
) -> None:
    black_box_operators = {"AutoSciRunner", "BackendFullWorkflowRunner"}
    logical_operator = str(node.get("logical_operator") or "")
    if logical_operator in black_box_operators:
        reasons.append(f"{node_id} must not use black-box workflow runner {logical_operator}")
    architecture_policy = node.get("architecture_policy")
    if not isinstance(architecture_policy, dict):
        if is_summary:
            return
        reasons.append(f"{node_id}.architecture_policy is required")
        return
    forbidden = set(_string_list(architecture_policy.get("forbidden")))
    if "hidden-backend-full-workflow" not in forbidden:
        reasons.append(f"{node_id}.architecture_policy must forbid hidden-backend-full-workflow")
    if "backend-black-box-runner" not in forbidden:
        reasons.append(f"{node_id}.architecture_policy must forbid backend-black-box-runner")
    backend_contract = str(architecture_policy.get("backend_contract") or "")
    if backend_contract != "single_bounded_action_or_solar_gate":
        reasons.append(f"{node_id}.architecture_policy.backend_contract must be single_bounded_action_or_solar_gate")


def _validate_capabilities(
    node: dict[str, Any],
    node_id: str,
    reasons: list[str],
    *,
    is_summary: bool = False,
) -> None:
    capabilities = _string_list(node.get("required_capabilities"))
    if is_summary and not capabilities:
        return
    if not any(item.startswith("cap.research-") for item in capabilities):
        reasons.append(f"{node_id}.required_capabilities must include a cap.research-* capsule")


def _validate_evidence_policy(node: dict[str, Any], node_id: str, reasons: list[str]) -> None:
    evidence_policy = node.get("evidence_policy")
    if not isinstance(evidence_policy, dict):
        expected_schema = str(node.get("expected_schema") or "")
        if not expected_schema.endswith(".v1"):
            reasons.append(f"{node_id}.expected_schema must name a v1 evidence ABI")
        return
    expected_schema = str(evidence_policy.get("expected_schema") or "")
    if not expected_schema.endswith(".v1"):
        reasons.append(f"{node_id}.evidence_policy.expected_schema must name a v1 evidence ABI")
    if evidence_policy.get("allow_failed") is not True:
        reasons.append(f"{node_id}.evidence_policy.allow_failed must be true")
    if evidence_policy.get("allow_inconclusive") is not True:
        reasons.append(f"{node_id}.evidence_policy.allow_inconclusive must be true")
    if evidence_policy.get("forbid_overclaiming") is not True:
        reasons.append(f"{node_id}.evidence_policy.forbid_overclaiming must be true")


def _validate_artifact_binding(
    node: dict[str, Any],
    node_id: str,
    artifact_contract: dict[str, Any],
    parent_gate: dict[str, Any],
    resume_contract: dict[str, Any],
    reasons: list[str],
) -> None:
    root = str(artifact_contract.get("root") or "")
    expected_schema = str(
        (node.get("evidence_policy") or {}).get("expected_schema")
        or node.get("expected_schema")
        or ""
    )
    declared_artifact = str(node.get("artifact") or "").strip()
    slot = str(node.get("lifecycle_artifact_slot") or "") or _slot_for_artifact(root, declared_artifact)
    if slot not in EXPECTED_ARTIFACT_SLOTS:
        reasons.append(f"{node_id}.lifecycle_artifact_slot must be one of {sorted(EXPECTED_ARTIFACT_SLOTS)}")
    write_scope = _string_list(node.get("write_scope"))
    if declared_artifact and declared_artifact not in write_scope:
        write_scope.append(declared_artifact)
    slot_prefix = f"{root}/{slot}/" if root and slot else ""
    write_artifacts = [
        item for item in write_scope
        if item.startswith(slot_prefix) and item.endswith(".json")
    ]
    if not write_artifacts:
        reasons.append(f"{node_id}.write_scope must include a typed artifact under {slot_prefix}")
        return
    primary_artifact = write_artifacts[0]

    expected_evidence_log = str(parent_gate.get("evidence_log") or artifact_contract.get("evidence_log") or "")
    if expected_evidence_log and node.get("evidence_log") and str(node.get("evidence_log") or "") != expected_evidence_log:
        reasons.append(f"{node_id}.evidence_log must match parent lifecycle evidence log")

    resume_policy = node.get("resume_policy")
    if not isinstance(resume_policy, dict):
        if not declared_artifact:
            reasons.append(f"{node_id}.resume_policy is required")
    else:
        if resume_policy.get("mode") != "skip_if_completed_evidence_exists":
            reasons.append(f"{node_id}.resume_policy.mode must be skip_if_completed_evidence_exists")
        if resume_policy.get("artifact") != primary_artifact:
            reasons.append(f"{node_id}.resume_policy.artifact must match write_scope typed artifact")
        if resume_policy.get("expected_schema") != expected_schema:
            reasons.append(f"{node_id}.resume_policy.expected_schema must match evidence_policy.expected_schema")
        if expected_evidence_log and resume_policy.get("evidence_log") != expected_evidence_log:
            reasons.append(f"{node_id}.resume_policy.evidence_log must match parent lifecycle evidence log")
        if resume_policy.get("do_not_rerun_completed_nodes") is not True:
            reasons.append(f"{node_id}.resume_policy.do_not_rerun_completed_nodes must be true")
        if "passed" not in set(_string_list(resume_policy.get("completed_statuses"))):
            reasons.append(f"{node_id}.resume_policy.completed_statuses must include passed")

    node_artifacts = artifact_contract.get("node_artifacts")
    if isinstance(node_artifacts, dict) and isinstance(node_artifacts.get(node_id), dict):
        declared = node_artifacts[node_id]
        if declared.get("slot") != slot:
            reasons.append(f"artifact_contract.node_artifacts.{node_id}.slot must match node slot")
        if declared.get("path") != primary_artifact:
            reasons.append(f"artifact_contract.node_artifacts.{node_id}.path must match node write_scope")
        if declared.get("schema") != expected_schema:
            reasons.append(f"artifact_contract.node_artifacts.{node_id}.schema must match node expected schema")

    if resume_contract:
        summary_artifact = str(resume_contract.get("summary_artifact") or "")
        evidence_log = str(resume_contract.get("evidence_log") or "")
        if summary_artifact and summary_artifact != f"{root}/lifecycle_summary.json":
            reasons.append("resume_contract.summary_artifact must match artifact_contract root")
        if evidence_log and evidence_log != expected_evidence_log:
            reasons.append("resume_contract.evidence_log must match parent lifecycle evidence log")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _string_set(value: Any) -> set[str]:
    return set(_string_list(value))


def _slot_for_artifact(root: str, artifact: str) -> str:
    prefix = f"{root}/" if root else ""
    if not prefix or not artifact.startswith(prefix):
        return ""
    remainder = artifact[len(prefix):]
    return remainder.split("/", 1)[0] if "/" in remainder else ""


def _finish(
    payload: dict[str, Any],
    reasons: list[str],
    warnings: list[str],
    path: str | Path | None,
):
    status = "failed" if reasons else _runtime_status(payload)
    evidence_status = {
        "passed": "completed",
        "failed": "failed",
        "inconclusive": "inconclusive",
    }[status]
    return GateResult(
        ok=status == "passed",
        status=status,
        reasons=reasons,
        warnings=warnings,
        schema=SCHEMA,
        path=str(path) if path else None,
        evidence_status=evidence_status,
    )


def _runtime_status(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("lifecycle_status") or payload.get("verdict") or "").lower()
    if explicit in {"passed", "failed", "inconclusive"}:
        return explicit

    statuses: list[str] = []
    for key in ("node_results", "gate_results"):
        result_map = payload.get(key)
        if not isinstance(result_map, dict):
            continue
        for result in result_map.values():
            if isinstance(result, dict):
                status = str(result.get("status") or "").lower()
                if status:
                    statuses.append(status)

    if any(status in {"failed", "error"} for status in statuses):
        return "failed"
    if any(status == "inconclusive" for status in statuses):
        return "inconclusive"
    return "passed"


if __name__ == "__main__":
    raise SystemExit(run_cli(evaluate, SCHEMA))
