"""Registry for draft research_synthesis_v1 bounded operators."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import (
    evidence_synthesis,
    final_acceptance,
    independent_review,
    report_draft,
    report_revision,
    seed_fetch,
    source_discovery,
    source_validation,
)
from .base import OperatorContext, ResearchOperatorError, build_node_result, error_result


_OPERATORS = {
    "seed_fetch": seed_fetch,
    "source_discovery": source_discovery,
    "source_validation": source_validation,
    "evidence_synthesis": evidence_synthesis,
    "report_draft": report_draft,
    "independent_review": independent_review,
    "report_revision": report_revision,
    "final_acceptance": final_acceptance,
}


def get_operator(node_id: str):
    try:
        return _OPERATORS[node_id]
    except KeyError as exc:
        raise ResearchOperatorError(f"No research synthesis operator registered for node_id={node_id}", error_type="unknown_node") from exc


def execute_operator(
    node_request: dict,
    *,
    services: dict | None = None,
    workspace_root: Path | None = None,
) -> dict:
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
                "message": "Authorized secret refs require matching in-memory secret_values before bounded output can be verified.",
            }],
            limitations=[
                "No operator or provider was invoked and no output artifact was written.",
                "The redaction assertion applies only to this static preflight diagnostic; provider output was not reviewed.",
            ],
        )
        # This static result contains only fixed strings and request identity;
        # it never interpolates secret refs or values.  Claiming that this
        # constructed diagnostic contains no secrets is therefore truthful and
        # keeps the Phase 0 result contract valid without pretending that any
        # provider output was inspected.
        result["secret_redaction_assertion"] = {
            "no_secrets_observed": True,
            "redaction_review": "passed",
        }
        return result
    try:
        implementation_node_id = str(
            node_request.get("implementation_node_id")
            or node_request.get("node_id")
            or ""
        )
        operator = get_operator(implementation_node_id)
        return operator.execute(node_request, context)
    except ResearchOperatorError as exc:
        return error_result(context, exc)
