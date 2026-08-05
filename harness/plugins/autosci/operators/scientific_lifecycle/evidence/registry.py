"""Package-local registry seam for evidence physical operators.

The integration owner can merge :func:`registration_entries` into the shared
resolver without this worker editing shared registry or workflow files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...research_synthesis.base import ResearchOperatorError
from . import operators
from .base import OperatorSpec, execute_spec


_VERSION = "1.1.0"


def _spec(
    node_id: str,
    operator_id: str,
    schema: str,
    filename: str,
    handler,
    *,
    version: str = _VERSION,
) -> OperatorSpec:
    return OperatorSpec(
        node_id=node_id,
        operator_id=operator_id,
        version=version,
        output_schema=schema,
        output_filename=filename,
        handler=handler,
    )


OPERATOR_SPECS: dict[str, OperatorSpec] = {
    "evidence_import": _spec(
        "evidence_import", "autosci-evidence-import", "research_evidence_import.v1", "research_evidence_import.v1.json", operators.import_existing_evidence
    ),
    "literature_discover": _spec(
        "literature_discover", "autosci-evidence-literature-discover", "literature_discovery.v1", "literature_discovery.v1.json", operators.literature_discovery
    ),
    "paper_ingest": _spec(
        "paper_ingest", "autosci-evidence-paper-ingest", "research_paper.v1", "research_paper.v1.json", operators.ingest_source
    ),
    "material_ingest": _spec(
        "material_ingest", "autosci-evidence-material-ingest", "research_paper.v1", "research_material.v1.json", operators.ingest_source
    ),
    "paper_analyze": _spec(
        "paper_analyze", "autosci-evidence-paper-analyze", "research_paper.v1", "research_paper_analysis.v1.json", operators.analyze_content
    ),
    "content_analyze": _spec(
        "content_analyze", "autosci-evidence-content-analyze", "research_paper.v1", "research_content_analysis.v1.json", operators.analyze_content
    ),
    "memory_update_initial": _spec(
        "memory_update_initial", "autosci-evidence-memory-update-initial", "research_memory_update.v1", "initial_research_memory_update.v1.json", operators.memory_update
    ),
    "memory_update_final": _spec(
        "memory_update_final", "autosci-evidence-memory-update-final", "research_memory_update.v1", "final_research_memory_update.v1.json", operators.memory_update
    ),
    "graph_update": _spec(
        "graph_update", "autosci-evidence-graph-update", "research_graph_update.v1", "research_graph_update.v1.json", operators.graph_update
    ),
    "claim_extract": _spec(
        "claim_extract",
        "autosci-evidence-claim-extract",
        "research_claims.v1",
        "research_claims.v1.json",
        operators.extract_claims,
        version="1.2.0",
    ),
    "method_extract": _spec(
        "method_extract",
        "autosci-evidence-method-extract",
        "research_method.v1",
        "research_method.v1.json",
        operators.extract_methods,
        version="1.3.0",
    ),
    "code_evidence_map": _spec(
        "code_evidence_map", "autosci-evidence-code-evidence-map", "code_evidence_map.v1", "code_evidence_map.v1.json", operators.map_code_evidence
    ),
}


def get_operator_spec(node_id: str) -> OperatorSpec:
    try:
        return OPERATOR_SPECS[node_id]
    except KeyError as exc:
        raise ResearchOperatorError(
            f"No evidence physical operator registered for node_id={node_id}", error_type="unknown_node"
        ) from exc


def resolve_entrypoint(node_id: str):
    """Resolve an executable callable, failing closed for unknown node IDs."""

    get_operator_spec(node_id)

    def resolved(
        node_request: dict[str, Any],
        *,
        services: dict[str, Any] | None = None,
        workspace_root: Path | None = None,
    ) -> dict[str, Any]:
        return execute_operator(node_request, services=services, workspace_root=workspace_root)

    resolved.operator_spec = OPERATOR_SPECS[node_id]  # type: ignore[attr-defined]
    return resolved


def execute_operator(
    node_request: dict[str, Any],
    *,
    services: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    spec = get_operator_spec(str(node_request.get("node_id") or ""))
    return execute_spec(spec, node_request, services=services, workspace_root=workspace_root)


def registration_entries() -> list[dict[str, Any]]:
    """Return deterministic declarations for integration into a shared resolver."""

    return [
        {
            "node_id": spec.node_id,
            "operator_id": spec.operator_id,
            "operator_version": spec.version,
            "entrypoint": spec.entrypoint,
            "input_contract": "research_node_request.v1 + explicit typed inputs",
            "output_contract": "research_node_result.v1",
            "evidence_schema": spec.output_schema,
            "mutates_global_state": False,
        }
        for spec in OPERATOR_SPECS.values()
    ]


def _execute_named(
    node_id: str,
    node_request: dict[str, Any],
    *,
    services: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    if str(node_request.get("node_id") or "") != node_id:
        request = dict(node_request)
        request.setdefault("node_id", node_id)
        node_request = request
    return execute_spec(get_operator_spec(node_id), node_request, services=services, workspace_root=workspace_root)


def execute_literature_discover(node_request, *, services=None, workspace_root=None):
    return _execute_named("literature_discover", node_request, services=services, workspace_root=workspace_root)


def execute_evidence_import(node_request, *, services=None, workspace_root=None):
    return _execute_named("evidence_import", node_request, services=services, workspace_root=workspace_root)


def execute_paper_ingest(node_request, *, services=None, workspace_root=None):
    return _execute_named("paper_ingest", node_request, services=services, workspace_root=workspace_root)


def execute_material_ingest(node_request, *, services=None, workspace_root=None):
    return _execute_named("material_ingest", node_request, services=services, workspace_root=workspace_root)


def execute_paper_analyze(node_request, *, services=None, workspace_root=None):
    return _execute_named("paper_analyze", node_request, services=services, workspace_root=workspace_root)


def execute_content_analyze(node_request, *, services=None, workspace_root=None):
    return _execute_named("content_analyze", node_request, services=services, workspace_root=workspace_root)


def execute_memory_update_initial(node_request, *, services=None, workspace_root=None):
    return _execute_named("memory_update_initial", node_request, services=services, workspace_root=workspace_root)


def execute_memory_update_final(node_request, *, services=None, workspace_root=None):
    return _execute_named("memory_update_final", node_request, services=services, workspace_root=workspace_root)


def execute_graph_update(node_request, *, services=None, workspace_root=None):
    return _execute_named("graph_update", node_request, services=services, workspace_root=workspace_root)


def execute_claim_extract(node_request, *, services=None, workspace_root=None):
    return _execute_named("claim_extract", node_request, services=services, workspace_root=workspace_root)


def execute_method_extract(node_request, *, services=None, workspace_root=None):
    return _execute_named("method_extract", node_request, services=services, workspace_root=workspace_root)


def execute_code_evidence_map(node_request, *, services=None, workspace_root=None):
    return _execute_named("code_evidence_map", node_request, services=services, workspace_root=workspace_root)
