"""Experiment design, approval, bounded execution, and status operators."""

from __future__ import annotations

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


def _first_idea(context: OperatorContext) -> dict[str, Any]:
    documents = load_documents(
        context,
        schemas=("idea_candidate.v1", "idea_evaluation.v1"),
        payload_keys=("idea", "idea_candidate"),
    )
    for document in documents:
        outputs = document.get("outputs") if isinstance(document.get("outputs"), dict) else document
        if isinstance(outputs, dict):
            if isinstance(outputs.get("idea"), dict):
                return outputs["idea"]
            for item in outputs.get("ideas") or []:
                if isinstance(item, dict):
                    return item
    raise ResearchOperatorError("No idea candidate was available", error_type="missing_input")


def design_experiment(node_request: dict[str, Any], context: OperatorContext) -> dict[str, Any]:
    idea = _first_idea(context)
    hypothesis = require_text(idea.get("hypothesis"), "idea.hypothesis")
    minimum = require_text(idea.get("minimum_experiment"), "idea.minimum_experiment")
    requested_sandbox = context.payload.get("sandbox") if isinstance(context.payload.get("sandbox"), dict) else {}
    sandbox_write_scope = list(requested_sandbox.get("write_scope") or [])
    if not sandbox_write_scope:
        sandbox_write_scope = [DEFAULT_EXPERIMENT_RESULT_SCOPE]
    plan = {
        "experiment_id": str(context.payload.get("experiment_id") or f"exp-{idea.get('idea_id', 'candidate')}"),
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
        "source_idea_id": require_text(idea.get("idea_id"), "idea.idea_id"),
        "origin_evidence_ids": [str(item) for item in idea.get("origin_evidence_ids") or []],
    }
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
    declared_scopes = {str(item).replace("\\", "/").rstrip("/") for item in context.write_scope}
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
    documents = load_documents(context, schemas=("experiment_approval.v1",), required=False)
    for document in documents:
        outputs = document.get("outputs") if isinstance(document.get("outputs"), dict) else document
        approval = outputs.get("approval") if isinstance(outputs, dict) else None
        if isinstance(approval, dict):
            return approval
        if isinstance(document.get("approval"), dict):
            return document["approval"]
    return {}


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
        raise ResearchOperatorError("experiment_executor service is unavailable", error_type="environment_unavailable")
    try:
        raw = executor(
            plan=plan,
            sandbox=dict(plan["sandbox"]),
            timeout_seconds=int(plan["resource_limits"]["timeout_seconds"]),
            max_output_bytes=int(plan["resource_limits"]["max_output_bytes"]),
        )
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
    }
    if isinstance(raw.get("criteria_results"), dict):
        result["criteria_results"] = {
            str(key): value for key, value in raw["criteria_results"].items() if isinstance(value, bool)
        }
    return completed_result(
        context,
        operator_id=RUNNER_ID,
        schema="experiment_result.v1",
        outputs={"result": result},
        filename="experiment_result.v1.json",
        artifact_id="experiment_result",
        limitations=[str(item) for item in raw.get("limitations") or [] if str(item).strip()],
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
    for document in documents:
        outputs = document.get("outputs") if isinstance(document.get("outputs"), dict) else document
        result = outputs.get("result") if isinstance(outputs, dict) else None
        plan = outputs.get("experiment_plan") if isinstance(outputs, dict) else None
        if isinstance(result, dict):
            experiment_id = str(result.get("experiment_id") or experiment_id)
            state = "failed" if result.get("outcome") == "failed" else "completed"
            observations.append(f"Experiment outcome: {result.get('outcome', 'unknown')}")
            evidence_ids.extend(str(item) for item in result.get("evidence_ids") or [])
        elif isinstance(plan, dict):
            experiment_id = str(plan.get("experiment_id") or experiment_id)
            state = "planned"
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
