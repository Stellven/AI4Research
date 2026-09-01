"""Experiment design, approval, bounded execution, and status operators."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...research_synthesis.base import build_node_result, stable_json_sha256
from .common import (
    OperatorContext,
    ResearchOperatorError,
    authorization,
    completed_result,
    load_documents,
    require_list,
    require_text,
    service_failure,
    write_evidence_artifact,
)


DESIGNER_ID = "autosci-experiment-design-physical"
APPROVAL_ID = "autosci-experiment-approval-gate-physical"
RUNNER_ID = "autosci-bounded-experiment-run-physical"
MONITOR_ID = "autosci-experiment-monitor-physical"
SANDBOX_MODES = {"isolated", "container", "process_restricted"}
DEFAULT_EXPERIMENT_RESULT_SCOPE = (
    "artifacts/scientific/scientific_research_lifecycle_full_v1/"
    "07_experiment_result/experiment_result.v1.json"
)


def _first_test_target(context: OperatorContext) -> dict[str, Any]:
    documents = load_documents(
        context,
        schemas=("idea_candidate.v1", "idea_evaluation.v1", "research_claims.v1"),
        payload_keys=("idea", "idea_candidate", "research_claims", "claims"),
    )
    requested_claim_id = str(context.payload.get("selected_claim_id") or "").strip()
    for document in documents:
        outputs = document.get("outputs") if isinstance(document.get("outputs"), dict) else document
        if isinstance(outputs, dict):
            if isinstance(outputs.get("idea"), dict):
                idea = outputs["idea"]
                return {
                    "target_id": require_text(idea.get("idea_id"), "idea.idea_id"),
                    "target_kind": "idea",
                    "hypothesis": require_text(idea.get("hypothesis"), "idea.hypothesis"),
                    "minimum_experiment": require_text(
                        idea.get("minimum_experiment"), "idea.minimum_experiment"
                    ),
                    "origin_evidence_ids": [
                        str(item) for item in idea.get("origin_evidence_ids") or []
                    ],
                }
            for item in outputs.get("ideas") or []:
                if isinstance(item, dict):
                    return {
                        "target_id": require_text(item.get("idea_id"), "idea.idea_id"),
                        "target_kind": "idea",
                        "hypothesis": require_text(item.get("hypothesis"), "idea.hypothesis"),
                        "minimum_experiment": require_text(
                            item.get("minimum_experiment"), "idea.minimum_experiment"
                        ),
                        "origin_evidence_ids": [
                            str(value) for value in item.get("origin_evidence_ids") or []
                        ],
                    }
            claims = [item for item in outputs.get("claims") or [] if isinstance(item, dict)]
            eligible = [
                item
                for item in claims
                if str(item.get("testability") or "unknown") in {"testable", "partially_testable"}
            ] or claims
            if requested_claim_id:
                eligible = [
                    item for item in eligible if str(item.get("claim_id") or "") == requested_claim_id
                ]
            if eligible:
                claim = eligible[0]
                claim_id = require_text(claim.get("claim_id"), "claim.claim_id")
                claim_text = require_text(claim.get("text"), "claim.text")
                criteria = [
                    str(item).strip()
                    for item in claim.get("acceptance_criteria") or []
                    if str(item).strip()
                ]
                minimum = str(context.payload.get("minimum_experiment") or "").strip()
                if not minimum:
                    minimum = (
                        "Measure the declared metrics for the supplied claim against the declared "
                        "baselines and evaluate its acceptance criteria."
                    )
                return {
                    "target_id": claim_id,
                    "target_kind": "claim",
                    "hypothesis": claim_text,
                    "minimum_experiment": minimum,
                    "origin_evidence_ids": [
                        str(item) for item in claim.get("evidence_ids") or [] if str(item).strip()
                    ],
                    "acceptance_criteria": criteria,
                }
    raise ResearchOperatorError(
        "No idea candidate or governed research claim was available",
        error_type="missing_input",
    )


def _dataset_manifest(context: OperatorContext) -> dict[str, Any]:
    documents = load_documents(
        context,
        schemas=("dataset_manifest.v1",),
        payload_keys=("dataset_manifest",),
        required=False,
    )
    if not documents:
        return {}
    document = documents[0]
    outputs = document.get("outputs") if isinstance(document.get("outputs"), dict) else document
    manifest = outputs.get("dataset_manifest") if isinstance(outputs, dict) else None
    if not isinstance(manifest, dict):
        raise ResearchOperatorError("Dataset manifest is malformed", error_type="invalid_input")
    return manifest


def design_experiment(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    target = _first_test_target(context)
    dataset_manifest = _dataset_manifest(context)
    hypothesis = target["hypothesis"]
    minimum = target["minimum_experiment"]
    requested_sandbox = context.payload.get("sandbox") if isinstance(context.payload.get("sandbox"), dict) else {}
    sandbox_write_scope = list(requested_sandbox.get("write_scope") or [])
    if not sandbox_write_scope:
        sandbox_write_scope = [DEFAULT_EXPERIMENT_RESULT_SCOPE]
    plan = {
        "experiment_id": str(
            context.payload.get("experiment_id") or f"exp-{target['target_id']}"
        ),
        "objective": str(context.payload.get("objective") or minimum),
        "hypothesis": hypothesis,
        "variables": [str(item) for item in context.payload.get("variables") or ["intervention", "outcome"]],
        "metrics": [str(item) for item in context.payload.get("metrics") or ["primary_outcome"]],
        "procedure": [str(item) for item in context.payload.get("procedure") or [minimum, "Record raw observations and metrics."]],
        "approval_required": True,
        "expected_artifacts": [str(item) for item in context.payload.get("expected_artifacts") or ["experiment_result.v1.json"]],
        "success_criteria": [str(item) for item in context.payload.get("success_criteria") or ["primary_outcome is recorded"]],
        "safety_checks": [str(item) for item in context.payload.get("safety_checks") or ["no undeclared network access", "writes remain in declared scope"]],
        "sandbox": {
            "mode": str(requested_sandbox.get("mode") or "isolated"),
            "network": bool(requested_sandbox.get("network", False)),
            "write_scope": sandbox_write_scope,
        },
        "resource_limits": {
            "timeout_seconds": min(
                int((context.payload.get("resource_limits") or {}).get("timeout_seconds") or 60),
                int((context.node_request.get("timeout_retry_policy") or {}).get("timeout_seconds") or 60),
            ),
            "max_output_bytes": int((context.payload.get("resource_limits") or {}).get("max_output_bytes") or 1_000_000),
        },
        "source_target_id": target["target_id"],
        "source_target_kind": target["target_kind"],
        "origin_evidence_ids": list(target["origin_evidence_ids"]),
    }
    if dataset_manifest:
        execution = dataset_manifest.get("execution")
        dataset = dataset_manifest.get("dataset")
        criteria = dataset_manifest.get("criteria_bindings")
        if not isinstance(execution, dict) or not isinstance(dataset, dict) or not isinstance(criteria, list):
            raise ResearchOperatorError(
                "Dataset manifest does not contain an executable package contract",
                error_type="invalid_input",
            )
        result_path = str(execution.get("result_path") or "").strip()
        if not result_path:
            raise ResearchOperatorError("Dataset manifest execution result_path is missing", error_type="invalid_input")
        plan.update(
            {
                "experiment_family": str(dataset_manifest.get("experiment_family") or ""),
                "dataset": dataset,
                "model": dataset_manifest.get("model") if isinstance(dataset_manifest.get("model"), dict) else {},
                "execution": execution,
                "criteria_bindings": criteria,
                "metrics": [
                    "memory_reduction_ratio_int8",
                    "memory_reduction_ratio_int4",
                    "mean_reconstruction_mse_int8",
                    "mean_reconstruction_mse_int4",
                    "mean_reconstruction_cosine_int8",
                    "mean_reconstruction_cosine_int4",
                    "mean_quantize_dequantize_ms_int8",
                    "mean_quantize_dequantize_ms_int4",
                ],
                "variables": ["cache_precision_bits", "context_tokens", "dataset_case_seed"],
                "procedure": [
                    "Load the exact hash-bound pretrained model state and retained public-dataset token cases.",
                    "Run a real cached forward pass for every retained context and collect its key/value tensors.",
                    "Quantize and dequantize every cache tensor at 8-bit and 4-bit precision.",
                    "Record cache bytes, reconstruction error, cosine similarity, and quantization time per case.",
                    "Recompute every acceptance criterion from the retained raw metrics.",
                ],
                "expected_artifacts": [
                    "raw_measurement.json",
                    "stdout.txt",
                    "stderr.txt",
                    "launch_receipt.json",
                    "experiment_result.v1.json",
                ],
                "sandbox": {
                    "mode": "process_restricted",
                    "network": False,
                    "write_scope": [str(Path(result_path).parent).replace("\\", "/")],
                },
            }
        )
    if target["target_kind"] == "idea":
        plan["source_idea_id"] = target["target_id"]
    else:
        plan["source_claim_id"] = target["target_id"]
        if target.get("acceptance_criteria"):
            plan["claim_acceptance_criteria"] = list(target["acceptance_criteria"])
    if not dataset_manifest and isinstance(context.payload.get("execution"), dict):
        plan["execution"] = dict(context.payload["execution"])
    if not dataset_manifest and isinstance(context.payload.get("criteria_bindings"), list):
        plan["criteria_bindings"] = list(context.payload["criteria_bindings"])
    if plan["sandbox"]["mode"] not in SANDBOX_MODES or plan["sandbox"]["network"]:
        raise ResearchOperatorError("Experiment plan must use an isolated no-network sandbox", error_type="safety_violation")
    require_list(plan["metrics"], "metrics")
    require_list(plan["procedure"], "procedure")
    return completed_result(
        context,
        operator_id=DESIGNER_ID,
        schema="experiment_plan.v1",
        outputs={"experiment_plan": plan},
        filename="experiment_plan.v1.json",
        artifact_id="experiment_plan",
    )


def _experiment_plan(context: OperatorContext) -> dict[str, Any]:
    documents = load_documents(context, schemas=("experiment_plan.v1",), payload_keys=("experiment_plan",))
    document = documents[0]
    outputs = document.get("outputs") if isinstance(document.get("outputs"), dict) else document
    plan = outputs.get("experiment_plan") if isinstance(outputs, dict) and isinstance(outputs.get("experiment_plan"), dict) else outputs
    if not isinstance(plan, dict):
        raise ResearchOperatorError("Experiment plan is malformed", error_type="invalid_input")
    return plan


def _approval_decision(context: OperatorContext, plan: dict[str, Any]) -> dict[str, Any]:
    auth = authorization(context)
    approved = {str(item) for item in auth.get("approved_capabilities") or []}
    approval_ref = str(auth.get("approval_ref") or "").strip()
    reasons: list[str] = []
    sandbox = plan.get("sandbox") if isinstance(plan.get("sandbox"), dict) else {}
    if str(sandbox.get("mode") or "") not in SANDBOX_MODES:
        reasons.append("sandbox mode is not isolated")
    if bool(sandbox.get("network", False)):
        reasons.append("experiment requests network access")
    approved_write_scope = auth.get("approved_write_scope") if isinstance(auth.get("approved_write_scope"), list) else context.write_scope
    declared_scopes = {str(item).replace("\\", "/").rstrip("/") for item in approved_write_scope}
    requested_scopes = {str(item).replace("\\", "/").rstrip("/") for item in sandbox.get("write_scope") or []}
    if not requested_scopes or not requested_scopes.issubset(declared_scopes):
        reasons.append("sandbox write scope exceeds the node request")
    if "execute_experiment" not in approved:
        reasons.append("execute_experiment capability is not approved")
    state = "approved"
    if reasons:
        state = "rejected"
    elif not approval_ref:
        state = "awaiting_human"
    return {
        "experiment_id": require_text(plan.get("experiment_id"), "experiment_id"),
        "decision": state,
        "approval_ref": approval_ref,
        "plan_sha256": stable_json_sha256(plan),
        "approved_capabilities": sorted(approved),
        "sandbox": sandbox,
        "reasons": reasons,
    }


def approve_experiment(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    plan = _experiment_plan(context)
    decision = _approval_decision(context, plan)
    artifact, ev, hashes = write_evidence_artifact(
        context,
        operator_id=APPROVAL_ID,
        schema="experiment_approval.v1",
        outputs={"approval": decision},
        filename="experiment_approval.v1.json",
        artifact_id="experiment_approval",
        status="completed" if decision["decision"] == "approved" else "inconclusive",
    )
    status = "completed" if decision["decision"] == "approved" else "awaiting_human" if decision["decision"] == "awaiting_human" else "blocked"
    return build_node_result(
        context,
        status=status,
        output_artifacts=[artifact],
        evidence=[ev],
        hashes=hashes,
        errors=[] if status != "blocked" else [{
            "error_id": "experiment.approval_rejected",
            "error_type": "safety_violation",
            "message": "; ".join(decision["reasons"])[:500],
        }],
        limitations=[] if status == "completed" else ["Experiment execution was not authorized."],
    )


def _approval_contract(context: OperatorContext) -> dict[str, Any]:
    documents = load_documents(
        context,
        schemas=("experiment_approval.v1",),
        payload_keys=("experiment_approval",),
        required=False,
    )
    for document in documents:
        outputs = document.get("outputs") if isinstance(document.get("outputs"), dict) else document
        approval = outputs.get("approval") if isinstance(outputs, dict) else None
        if isinstance(approval, dict):
            return approval
        if isinstance(document.get("approval"), dict):
            return document["approval"]
    return {}


def _allows_unavailable_as_inconclusive(context: OperatorContext) -> bool:
    task_contract = (
        context.payload.get("task_contract")
        if isinstance(context.payload.get("task_contract"), dict)
        else {}
    )
    request_text = " ".join(
        str(value or "")
        for value in (
            context.payload.get("availability_policy"),
            context.payload.get("objective"),
            task_contract.get("user_intent"),
        )
    ).casefold()
    return (
        bool(context.payload.get("inconclusive_when_unavailable"))
        or ("inconclusive" in request_text and "unavailable" in request_text)
    )


def _unavailable_experiment_result(
    context: OperatorContext,
    *,
    plan: dict[str, Any],
    approval: dict[str, Any],
    reason: str,
    unavailable_resource: str,
) -> dict[str, Any]:
    evidence_id = f"availability:{unavailable_resource}:unavailable"
    result = {
        "experiment_id": require_text(plan.get("experiment_id"), "experiment_id"),
        "outcome": "inconclusive",
        "metrics": [],
        "evidence_ids": [evidence_id],
        "approval_ref": approval["approval_ref"],
        "plan_sha256": approval["plan_sha256"],
        "sandbox_enforced": False,
        "execution_attempted": False,
        "availability": {
            "status": "unavailable",
            "resource": unavailable_resource,
            "reason": reason,
        },
    }
    limitation = (
        f"Experiment execution was not attempted because {unavailable_resource} was unavailable: {reason}"
    )
    artifact, evidence, hashes = write_evidence_artifact(
        context,
        operator_id=RUNNER_ID,
        schema="experiment_result.v1",
        outputs={"result": result},
        filename="experiment_result.v1.json",
        artifact_id="experiment_result",
        status="inconclusive",
        limitations=[limitation],
    )
    return build_node_result(
        context,
        status="completed",
        output_artifacts=[artifact],
        evidence=[evidence],
        hashes=hashes,
        limitations=[limitation],
    )


def run_experiment(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    plan = _experiment_plan(context)
    approval = _approval_contract(context)
    fresh_decision = _approval_decision(context, plan)
    if fresh_decision["decision"] != "approved":
        raise ResearchOperatorError("Experiment approval is absent or unsafe", error_type="approval_required")
    if approval:
        if approval.get("decision") != "approved" or approval.get("plan_sha256") != stable_json_sha256(plan):
            raise ResearchOperatorError("Approval does not authorize this exact plan", error_type="approval_mismatch")
        if approval.get("approval_ref") != fresh_decision.get("approval_ref"):
            raise ResearchOperatorError("Approval reference does not match authorization", error_type="approval_mismatch")
    else:
        raise ResearchOperatorError("Hash-bound approval evidence is required", error_type="approval_required")
    executor = context.services.get("experiment_executor")
    if not callable(executor):
        if _allows_unavailable_as_inconclusive(context):
            return _unavailable_experiment_result(
                context,
                plan=plan,
                approval=approval,
                reason="experiment_executor service is unavailable",
                unavailable_resource="executor",
            )
        raise ResearchOperatorError("experiment_executor service is unavailable", error_type="environment_unavailable")
    try:
        raw = executor(
            plan=plan,
            sandbox=dict(plan["sandbox"]),
            timeout_seconds=int(plan["resource_limits"]["timeout_seconds"]),
            max_output_bytes=int(plan["resource_limits"]["max_output_bytes"]),
        )
    except ResearchOperatorError as exc:
        if _allows_unavailable_as_inconclusive(context) and exc.error_type in {
            "environment_unavailable",
            "missing_input",
        }:
            unavailable_resource = "dataset" if exc.error_type == "missing_input" else "executor"
            return _unavailable_experiment_result(
                context,
                plan=plan,
                approval=approval,
                reason=str(exc),
                unavailable_resource=unavailable_resource,
            )
        raise
    except Exception as exc:
        raise service_failure("experiment_executor", exc) from exc
    if not isinstance(raw, dict):
        raise ResearchOperatorError("experiment_executor must return an object", error_type="provider_contract_failure")
    outcome = str(raw.get("outcome") or "")
    if outcome not in {"supports", "partially_supports", "refutes", "inconclusive", "failed"}:
        raise ResearchOperatorError("Experiment result has an invalid outcome", error_type="product_failure")
    metrics = raw.get("metrics")
    require_list(metrics, "experiment metrics")
    evidence_ids = [str(item) for item in require_list(raw.get("evidence_ids"), "experiment evidence_ids") if str(item).strip()]
    result = {
        "experiment_id": require_text(plan.get("experiment_id"), "experiment_id"),
        "outcome": outcome,
        "metrics": metrics,
        "evidence_ids": evidence_ids,
        "approval_ref": approval["approval_ref"],
        "plan_sha256": approval["plan_sha256"],
        "sandbox_enforced": True,
        "execution_attempted": True,
    }
    if isinstance(raw.get("criteria_results"), dict):
        result["criteria_results"] = {
            str(key): value for key, value in raw["criteria_results"].items() if isinstance(value, bool)
        }
    runtime = raw.get("runtime") if isinstance(raw.get("runtime"), dict) else {}
    if runtime:
        result["runtime"] = {
            key: value
            for key, value in runtime.items()
            if key != "artifacts"
        }
    extra_artifacts = [
        dict(item)
        for item in runtime.get("artifacts") or []
        if isinstance(item, dict)
        and item.get("artifact_id")
        and item.get("path")
        and item.get("sha256")
    ]
    extra_hashes = [
        {
            "hash_id": str(item["artifact_id"]),
            "algorithm": "sha256",
            "value": str(item["sha256"]),
        }
        for item in extra_artifacts
    ]
    return completed_result(
        context,
        operator_id=RUNNER_ID,
        schema="experiment_result.v1",
        outputs={"result": result},
        filename="experiment_result.v1.json",
        artifact_id="experiment_result",
        limitations=[str(item) for item in raw.get("limitations") or [] if str(item).strip()],
        extra_artifacts=extra_artifacts,
        extra_hashes=extra_hashes,
    )


def monitor_experiment(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    documents = load_documents(
        context,
        schemas=("experiment_result.v1", "experiment_plan.v1"),
        payload_keys=("experiment_result", "experiment_plan"),
    )
    experiment_id = ""
    state = "unknown"
    observations: list[str] = []
    evidence_ids: list[str] = []
    result_seen = False
    plan_seen = False
    for document in documents:
        outputs = document.get("outputs") if isinstance(document.get("outputs"), dict) else document
        result = outputs.get("result") if isinstance(outputs, dict) else None
        plan = outputs.get("experiment_plan") if isinstance(outputs, dict) else None
        if isinstance(result, dict):
            result_seen = True
            experiment_id = str(result.get("experiment_id") or experiment_id)
            state = "failed" if result.get("outcome") == "failed" else "completed"
            observations.append(f"Experiment outcome: {result.get('outcome', 'unknown')}")
            evidence_ids.extend(str(item) for item in result.get("evidence_ids") or [])
        elif isinstance(plan, dict):
            plan_seen = True
            if not result_seen:
                experiment_id = str(plan.get("experiment_id") or experiment_id)
                state = "planned"
    if plan_seen and not result_seen:
        observations.append("Experiment is designed but no result evidence is present.")
    status_provider = context.services.get("experiment_status_provider")
    if callable(status_provider) and state != "completed":
        try:
            remote = status_provider(experiment_id=experiment_id)
        except Exception as exc:
            raise service_failure("experiment_status_provider", exc) from exc
        if isinstance(remote, dict):
            state = str(remote.get("state") or state)
            observations.extend(str(item) for item in remote.get("observations") or [])
            evidence_ids.extend(str(item) for item in remote.get("evidence_ids") or [])
    if state not in {"planned", "running", "completed", "failed", "blocked", "unknown"}:
        raise ResearchOperatorError("Status provider returned an invalid state", error_type="provider_contract_failure")
    next_actions = [] if state == "completed" else ["Resume or collect bounded experiment evidence."]
    report = {
        "experiment_id": require_text(experiment_id, "experiment_id"),
        "state": state,
        "observations": observations or ["No experiment observations are available."],
        "next_actions": next_actions,
        "evidence_ids": sorted(set(evidence_ids)),
    }
    return completed_result(
        context,
        operator_id=MONITOR_ID,
        schema="experiment_status.v1",
        outputs={"status_report": report},
        filename="experiment_status.v1.json",
        artifact_id="experiment_status",
    )
