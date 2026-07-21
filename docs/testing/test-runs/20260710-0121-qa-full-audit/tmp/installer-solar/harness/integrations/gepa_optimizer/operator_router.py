"""
operator_router.py — physical operator selection for the GEPA optimizer.

Reads ``~/.solar/harness/config/physical-operators.json`` and exposes a
small selector API that the adapter / CLI uses to pick a proposer or
evaluator LLM. The router never prints secrets and never reaches out to
any provider — it only filters the static config.

Multimodal gate
---------------
GEPA evaluators that consume images (``gepa.Image(...)``) must be paired
with an operator whose ``input_modalities`` list contains ``"image"``.
``OperatorRouter.select_for_image_task`` enforces this; callers that
need image support but pass no modality requirement get a clear error
rather than a silent fall-back to a text-only operator.

Public symbols (re-exported from ``integrations.gepa_optimizer``):
* ``OperatorSpec``   — frozen dataclass with the subset of fields the
                       optimizer relies on.
* ``OperatorRouter`` — selector with cost / availability / modality
                       filters and deterministic preference ordering.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

__all__ = ["OperatorSpec", "OperatorRouter", "OperatorRoutingError"]


# Default physical-operators.json path. Resolved at call time (not import
# time) so unit tests can ``monkeypatch`` ``HOME`` without re-importing.
def _default_config_path() -> Path:
    return Path(
        os.path.expanduser("~/.solar/harness/config/physical-operators.json")
    )


# Cost tier ordering, low-to-high. Operators with unknown tiers are
# treated as "medium" so they sort between the two known endpoints.
_COST_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


class OperatorRoutingError(RuntimeError):
    """Raised when no operator can satisfy the caller's requirements."""


@dataclasses.dataclass(frozen=True)
class OperatorSpec:
    """Subset of ``physical-operators.json`` an optimizer needs.

    The full record includes many fields (auth_mode, key_ref, etc.) that
    must never escape the harness. This dataclass deliberately omits all
    credential-shaped fields so it is safe to log / serialize.
    """

    name: str
    role: str
    provider: str
    model: str
    cost_tier: str
    enabled: bool
    available: bool
    input_modalities: tuple[str, ...] = ()
    task_classes: tuple[str, ...] = ()
    strengths: tuple[str, ...] = ()

    @property
    def is_usable(self) -> bool:
        """True iff the operator is both enabled and available."""
        return bool(self.enabled) and bool(self.available)

    @property
    def supports_image(self) -> bool:
        """True iff the operator advertises image input."""
        return "image" in self.input_modalities


def _to_spec(name: str, record: Mapping[str, Any]) -> OperatorSpec:
    return OperatorSpec(
        name=name,
        role=str(record.get("role", "")),
        provider=str(record.get("provider", "")),
        model=str(record.get("model", "")),
        cost_tier=str(record.get("cost_tier", "medium")),
        enabled=bool(record.get("enabled", False)),
        available=bool(record.get("available", False)),
        input_modalities=tuple(record.get("input_modalities", []) or ()),
        task_classes=tuple(record.get("task_classes", []) or ()),
        strengths=tuple(record.get("strengths", []) or ()),
    )


class OperatorRouter:
    """Pick operators from physical-operators.json with cost/availability filters."""

    def __init__(
        self,
        *,
        config_path: str | os.PathLike | None = None,
        operators: Iterable[OperatorSpec] | None = None,
    ) -> None:
        if operators is not None:
            self._operators: tuple[OperatorSpec, ...] = tuple(operators)
            self._config_path: Path | None = None
        else:
            path = Path(config_path) if config_path else _default_config_path()
            self._config_path = path
            self._operators = self._load_from_disk(path)

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    @staticmethod
    def _load_from_disk(path: Path) -> tuple[OperatorSpec, ...]:
        if not path.exists():
            raise OperatorRoutingError(f"physical-operators.json not found at {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise OperatorRoutingError(
                f"physical-operators.json is malformed ({path}): {exc}"
            ) from exc
        ops = data.get("operators")
        if not isinstance(ops, Mapping):
            raise OperatorRoutingError(
                f"physical-operators.json missing 'operators' object ({path})"
            )
        return tuple(_to_spec(name, rec) for name, rec in ops.items())

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @property
    def operators(self) -> tuple[OperatorSpec, ...]:
        """All operators (including disabled / unavailable)."""
        return self._operators

    def usable(self) -> list[OperatorSpec]:
        """Operators that are both enabled and available."""
        return [o for o in self._operators if o.is_usable]

    def by_role(self, role: str) -> list[OperatorSpec]:
        return [o for o in self.usable() if o.role == role]

    def by_cost_ceiling(self, max_tier: str) -> list[OperatorSpec]:
        ceiling = _COST_RANK.get(max_tier, _COST_RANK["medium"])
        return [
            o for o in self.usable()
            if _COST_RANK.get(o.cost_tier, _COST_RANK["medium"]) <= ceiling
        ]

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select(
        self,
        *,
        role: str | None = None,
        cost_ceiling: str = "medium",
        require_image: bool = False,
        preferred_name: str | None = None,
    ) -> OperatorSpec:
        """Return the first operator matching the requirements.

        Selection order:
          1. preferred_name (if set and matches and meets other filters)
          2. enabled + available
          3. matches role (if set)
          4. cost_tier <= cost_ceiling
          5. supports image if require_image
          6. lowest cost_tier wins; ties broken by deterministic name order

        Raises ``OperatorRoutingError`` if no candidate qualifies.
        """
        candidates = self.usable()

        if role is not None:
            candidates = [o for o in candidates if o.role == role]

        ceiling_rank = _COST_RANK.get(cost_ceiling, _COST_RANK["medium"])
        candidates = [
            o for o in candidates
            if _COST_RANK.get(o.cost_tier, _COST_RANK["medium"]) <= ceiling_rank
        ]

        if require_image:
            candidates = [o for o in candidates if o.supports_image]

        if preferred_name is not None:
            preferred = [o for o in candidates if o.name == preferred_name]
            if preferred:
                return preferred[0]
            # Fall through to general scoring when the preferred name does not
            # match any usable operator under the current filters.

        if not candidates:
            raise OperatorRoutingError(
                "No operator satisfies the requested filters: "
                f"role={role!r}, cost_ceiling={cost_ceiling!r}, "
                f"require_image={require_image}, preferred_name={preferred_name!r}"
            )

        # Deterministic: sort by (cost_rank, name).
        candidates.sort(
            key=lambda o: (_COST_RANK.get(o.cost_tier, _COST_RANK["medium"]), o.name)
        )
        return candidates[0]

    def select_for_image_task(
        self,
        *,
        role: str | None = None,
        cost_ceiling: str = "medium",
    ) -> OperatorSpec:
        """Convenience helper enforcing the multimodal gate.

        Equivalent to ``select(..., require_image=True)`` but with an
        explicit name so callers cannot accidentally drop the requirement.
        """
        return self.select(
            role=role,
            cost_ceiling=cost_ceiling,
            require_image=True,
        )
