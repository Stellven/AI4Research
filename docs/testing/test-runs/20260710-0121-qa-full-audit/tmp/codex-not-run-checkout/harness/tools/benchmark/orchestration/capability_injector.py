"""Inject benchmark capabilities into graph-scheduler for Builder pane role only.

S04 N1: Provides `inject_benchmark_capabilities()` which returns capability
definitions for `benchmark.run`, `sandbox.docker`, and `harbor.adapter`.
These are injected into the graph-scheduler so that DAG nodes requiring
these capabilities are routed to Builder pane (not Lab panes).

Per PRD OQ-S04-4 decision: Lab panes are excluded to prevent 4 lab builders
from concurrently running expensive benchmark tasks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


BENCHMARK_CAPABILITIES: tuple[str, ...] = (
    "benchmark.run",
    "sandbox.docker",
    "harbor.adapter",
)

BUILDER_ROLE: str = "builder"

EXCLUDED_ROLES: tuple[str, ...] = (
    "lab-builder-1",
    "lab-builder-2",
    "lab-builder-3",
    "lab-builder-4",
)


@dataclass(frozen=True)
class CapabilitySpec:
    """Single capability definition for graph-scheduler injection."""
    name: str
    score: float
    level: str
    provider: str
    allowed_roles: tuple[str, ...]
    excluded_roles: tuple[str, ...]
    description: str


def _benchmark_run_spec() -> CapabilitySpec:
    return CapabilitySpec(
        name="benchmark.run",
        score=3.0,
        level="default_usable",
        provider="harness/lib/benchmark",
        allowed_roles=(BUILDER_ROLE,),
        excluded_roles=EXCLUDED_ROLES,
        description="Execute benchmark adapter commands (doctor/plan/run/report) via Harbor CLI.",
    )


def _sandbox_docker_spec() -> CapabilitySpec:
    return CapabilitySpec(
        name="sandbox.docker",
        score=2.0,
        level="basic_usable",
        provider="system",
        allowed_roles=(BUILDER_ROLE,),
        excluded_roles=EXCLUDED_ROLES,
        description="Local Docker daemon availability for containerized benchmark execution.",
    )


def _harbor_adapter_spec() -> CapabilitySpec:
    return CapabilitySpec(
        name="harbor.adapter",
        score=2.0,
        level="basic_usable",
        provider="harness/lib/benchmark",
        allowed_roles=(BUILDER_ROLE,),
        excluded_roles=EXCLUDED_ROLES,
        description="Harbor CLI adapter for Terminal-Bench 2.0 dataset execution.",
    )


def inject_benchmark_capabilities() -> dict[str, dict[str, Any]]:
    """Return capability definitions for graph-scheduler injection.

    Returns:
        Dict keyed by capability name, each value being a serializable
        dict with score, level, provider, allowed_roles, excluded_roles,
        and description.

    Only Builder pane role is included in allowed_roles.
    Lab builder roles are explicitly excluded.
    """
    specs = (
        _benchmark_run_spec(),
        _sandbox_docker_spec(),
        _harbor_adapter_spec(),
    )
    return {spec.name: asdict(spec) for spec in specs}
