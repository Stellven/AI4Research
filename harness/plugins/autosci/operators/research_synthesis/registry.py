"""Registry for draft research_synthesis_v1 bounded operators."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import (
    evidence_synthesis,
    final_acceptance,
    independent_review,
    report_draft,
    seed_fetch,
    source_discovery,
    source_validation,
)
from .base import OperatorContext, ResearchOperatorError, error_result


_OPERATORS = {
    "seed_fetch": seed_fetch,
    "source_discovery": source_discovery,
    "source_validation": source_validation,
    "evidence_synthesis": evidence_synthesis,
    "report_draft": report_draft,
    "independent_review": independent_review,
    "final_acceptance": final_acceptance,
}


def get_operator(node_id: str):
    try:
        return _OPERATORS[node_id]
    except KeyError as exc:
        raise ResearchOperatorError(f"No research synthesis operator registered for node_id={node_id}", error_type="unknown_node") from exc


def execute_operator(node_request: dict, *, services: dict | None = None) -> dict:
    context = OperatorContext.from_request(node_request, services=services, workspace_root=Path.cwd())
    try:
        operator = get_operator(str(node_request.get("node_id") or ""))
        return operator.execute(node_request, context)
    except ResearchOperatorError as exc:
        return error_result(context, exc)
