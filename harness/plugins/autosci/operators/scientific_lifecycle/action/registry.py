"""Package-local registration seam for action and delivery operators."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ...research_synthesis.base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    error_result,
)
from . import delivery, experiment, idea
from .common import IMPLEMENTATION_PACKAGE, OPERATOR_VERSION


Operator = Callable[[dict[str, Any], OperatorContext], dict[str, Any]]


_OPERATORS: dict[str, tuple[Operator, str]] = {
    "idea_generate": (idea.generate_ideas, idea.GENERATOR_ID),
    "idea_evaluate": (idea.evaluate_ideas, idea.EVALUATOR_ID),
    "experiment_design": (experiment.design_experiment, experiment.DESIGNER_ID),
    "experiment_approval_gate": (experiment.approve_experiment, experiment.APPROVAL_ID),
    "experiment_run": (experiment.run_experiment, experiment.RUNNER_ID),
    "experiment_monitor": (experiment.monitor_experiment, experiment.MONITOR_ID),
    "claim_verify": (delivery.verify_claim, delivery.CLAIM_VERIFIER_ID),
    "report_plan": (delivery.plan_report, delivery.REPORT_PLANNER_ID),
    "report_draft": (delivery.draft_report, delivery.REPORT_DRAFTER_ID),
    "artifact_review": (delivery.review_artifact, delivery.ARTIFACT_REVIEWER_ID),
    "publication_produce": (delivery.produce_publication, delivery.PUBLICATION_PRODUCER_ID),
    "workflow_evolve": (delivery.propose_workflow_evolution, delivery.WORKFLOW_EVOLVER_ID),
}


def registration_entries() -> tuple[dict[str, str], ...]:
    """Return immutable-by-convention metadata for the integration owner."""

    return tuple(
        {
            "node_id": node_id,
            "operator_id": operator_id,
            "operator_version": OPERATOR_VERSION,
            "implementation_package": IMPLEMENTATION_PACKAGE,
        }
        for node_id, (_operator, operator_id) in _OPERATORS.items()
    )


def get_operator(node_id: str) -> Operator:
    try:
        return _OPERATORS[node_id][0]
    except KeyError as exc:
        raise ResearchOperatorError(
            f"No action/delivery operator is registered for node_id={node_id}",
            error_type="unknown_node",
        ) from exc


def execute_operator(
    node_request: dict[str, Any],
    *,
    services: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    context = OperatorContext.from_request(
        node_request,
        services=services,
        workspace_root=workspace_root or Path.cwd(),
    )
    if not context.secret_verification_complete:
        result = build_node_result(
            context,
            status="failed",
            errors=[{
                "error_id": "operator.secret_verification_unavailable",
                "error_type": "secret_verification_unavailable",
                "message": "Authorized secret refs require matching in-memory secret values.",
            }],
            limitations=["No provider or execution service was invoked and no artifact was written."],
        )
        result["secret_redaction_assertion"] = {"no_secrets_observed": True, "redaction_review": "passed"}
        return result
    try:
        return get_operator(str(node_request.get("node_id") or ""))(node_request, context)
    except ResearchOperatorError as exc:
        return error_result(context, exc)
    except Exception as exc:  # fail closed at the package boundary
        return error_result(
            context,
            ResearchOperatorError(
                f"Unexpected operator failure: {type(exc).__name__}: {str(exc)[:300]}",
                error_type="operator_internal_error",
            ),
        )
