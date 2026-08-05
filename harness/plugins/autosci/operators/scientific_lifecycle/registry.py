"""Unified production registry for Solar research physical operators."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from ..research_synthesis import registry as synthesis_registry
from .action import registry as action_registry
from .evidence import registry as evidence_registry


_SYNTHESIS_NODES = (
    "seed_fetch",
    "source_discovery",
    "source_validation",
    "evidence_synthesis",
    "report_draft",
    "independent_review",
    "final_acceptance",
)


def registration_entries() -> tuple[dict[str, str], ...]:
    """Return every workflow-facing binding once in deterministic order."""

    entries: list[dict[str, str]] = [
        {
            "node_id": node_id,
            "physical_operator_id": f"{node_id}_operator",
            "implementation_operator_id": f"research-synthesis-{node_id}",
            "operator_version": "research_synthesis.v1.6",
            "operator_family": "research_synthesis",
        }
        for node_id in _SYNTHESIS_NODES
    ]
    entries.extend(
        {
            "node_id": str(item["node_id"]),
            "physical_operator_id": f"{item['node_id']}_worker",
            "implementation_operator_id": str(item["operator_id"]),
            "operator_version": str(item["operator_version"]),
            "operator_family": "scientific_lifecycle_evidence",
        }
        for item in evidence_registry.registration_entries()
    )
    entries.extend(
        {
            "node_id": str(item["node_id"]),
            "physical_operator_id": f"{item['node_id']}_worker",
            "implementation_operator_id": str(item["operator_id"]),
            "operator_version": str(item["operator_version"]),
            "operator_family": "scientific_lifecycle_action",
        }
        for item in action_registry.registration_entries()
    )
    identities = [item["physical_operator_id"] for item in entries]
    if len(identities) != len(set(identities)):
        duplicates = sorted({item for item in identities if identities.count(item) > 1})
        raise ValueError(f"duplicate unified physical bindings: {', '.join(duplicates)}")
    return tuple(entries)


def production_bindings(
    *,
    services: dict[str, Any] | None = None,
    workspace_root: Path,
    binding_factory: Callable[..., Any] | None = None,
) -> list[Any]:
    """Build executable bindings without fallback or dynamic import guessing."""

    injected = deepcopy(services or {})
    root = Path(workspace_root).resolve()
    if binding_factory is None:
        try:
            from harness.lib.research_orchestration.resolver import PhysicalOperatorBinding
        except ModuleNotFoundError:
            from lib.research_orchestration.resolver import PhysicalOperatorBinding
        binding_factory = PhysicalOperatorBinding

    def run_synthesis(request: dict) -> dict:
        return synthesis_registry.execute_operator(
            request,
            services=injected,
            workspace_root=root,
        )

    def run_evidence(request: dict) -> dict:
        return evidence_registry.execute_operator(
            request,
            services=injected,
            workspace_root=root,
        )

    def run_action(request: dict) -> dict:
        return action_registry.execute_operator(
            request,
            services=injected,
            workspace_root=root,
        )

    runners = {
        "research_synthesis": run_synthesis,
        "scientific_lifecycle_evidence": run_evidence,
        "scientific_lifecycle_action": run_action,
    }
    return [
        binding_factory(
            operator_id=item["physical_operator_id"],
            runner=runners[item["operator_family"]],
            version=item["operator_version"],
        )
        for item in registration_entries()
    ]
