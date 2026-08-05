"""Fail-closed registry for bounded physical research operators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


class PhysicalOperatorResolutionError(ValueError):
    """Raised when a physical operator binding is absent, ambiguous, or disabled."""


@dataclass(frozen=True)
class PhysicalOperatorBinding:
    operator_id: str
    runner: Callable[[dict], dict]
    version: str = "1"
    enabled: bool = True


class PhysicalOperatorResolver:
    """Resolve only explicitly registered physical operators.

    There is deliberately no node-name fallback, import guessing, provider
    fallback, or permissive truthy result.  Duplicate identities are rejected
    while constructing the resolver.
    """

    def __init__(self, bindings: list[PhysicalOperatorBinding] | tuple[PhysicalOperatorBinding, ...]) -> None:
        self._bindings: dict[str, PhysicalOperatorBinding] = {}
        for binding in bindings:
            if not isinstance(binding, PhysicalOperatorBinding):
                raise PhysicalOperatorResolutionError("operator bindings must be PhysicalOperatorBinding values")
            operator_id = binding.operator_id.strip()
            if not operator_id:
                raise PhysicalOperatorResolutionError("operator_id must be non-empty")
            if operator_id in self._bindings:
                raise PhysicalOperatorResolutionError(f"duplicate physical operator binding: {operator_id}")
            if not callable(binding.runner):
                raise PhysicalOperatorResolutionError(f"physical operator is not callable: {operator_id}")
            self._bindings[operator_id] = binding

    def resolve(self, operator_id: str) -> Mapping[str, Any]:
        identity = str(operator_id or "").strip()
        binding = self._bindings.get(identity)
        if binding is None:
            raise PhysicalOperatorResolutionError(f"unknown physical operator: {identity or '<empty>'}")
        if not binding.enabled:
            raise PhysicalOperatorResolutionError(f"disabled physical operator: {identity}")
        return {
            "operator_id": binding.operator_id,
            "version": binding.version,
            "enabled": True,
            "runtime_state": "active",
        }

    def execute(self, node_request: dict) -> dict:
        physical = node_request.get("physical_operator") if isinstance(node_request, dict) else None
        operator_id = str((physical or {}).get("operator_id") or "")
        self.resolve(operator_id)
        return self._bindings[operator_id].runner(node_request)

    def operator_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._bindings))
