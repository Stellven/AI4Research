"""hard_policy_checker.py — frozen policy guard for GEPA candidates.

GEPA may mutate instructions, routing hints, and other soft sections, but it
must never be allowed to relax core safety policy.  This module validates
candidates before they enter replay or publication.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Mapping

from .candidate_schema import OptimizationCandidate, normalize_candidate

__all__ = ["PolicyCheckResult", "check_candidate"]

_DENIED_ONLY_VALUES: dict[str, set[Any]] = {
    "secrets_access": {"denied", "none", False, None},
    "git_push": {"denied", False, None},
    "destructive_shell": {"denied", False, None},
    "payment_action": {"denied", False, None},
    "payment_or_external_action": {"denied", False, None},
    "external_api_write": {"denied", False, None},
}


@dataclasses.dataclass(frozen=True)
class PolicyCheckResult:
    ok: bool
    violations: list[str]
    frozen_section_diff: dict[str, dict[str, Any]]
    decision: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _walk(
    value: Any,
    *,
    prefix: str = "",
):
    if isinstance(value, Mapping):
        for key, inner in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _walk(inner, prefix=path)
    elif isinstance(value, list):
        for idx, inner in enumerate(value):
            path = f"{prefix}[{idx}]"
            yield from _walk(inner, prefix=path)
    else:
        yield prefix, value


def _lookup_path(payload: Mapping[str, Any], dotted_path: str) -> Any:
    node: Any = payload
    for key in dotted_path.split("."):
        if not isinstance(node, Mapping) or key not in node:
            return None
        node = node[key]
    return node


def _compare_frozen_values(
    candidate: OptimizationCandidate,
) -> dict[str, dict[str, Any]]:
    diff: dict[str, dict[str, Any]] = {}
    for path, expected in _walk(candidate.frozen_values):
        if not path:
            continue
        actual = _lookup_path(candidate.payload, path)
        if actual is None:
            continue
        if actual != expected:
            diff[path] = {"expected": expected, "actual": actual}
    return diff


def check_candidate(
    candidate: OptimizationCandidate | Mapping[str, Any],
) -> dict[str, Any]:
    """Validate that a candidate does not relax immutable policy."""
    normalized = normalize_candidate(candidate)
    violations: list[str] = []

    for path, value in _walk(normalized.payload):
        key = path.rsplit(".", 1)[-1]
        if key in _DENIED_ONLY_VALUES and value not in _DENIED_ONLY_VALUES[key]:
            violations.append(f"{path} relaxed to {value!r}")

        if key == "forbidden" and isinstance(value, list) and not value:
            violations.append(f"{path} removed all forbidden entries")

        if key == "requires_human_approval" and isinstance(value, list) and not value:
            violations.append(f"{path} removed human approval requirements")

    frozen_diff = _compare_frozen_values(normalized)
    if frozen_diff:
        violations.extend(f"frozen section changed: {path}" for path in sorted(frozen_diff))

    result = PolicyCheckResult(
        ok=not violations,
        violations=violations,
        frozen_section_diff=frozen_diff,
        decision="allow" if not violations else "hard_reject",
    )
    return result.to_dict()
