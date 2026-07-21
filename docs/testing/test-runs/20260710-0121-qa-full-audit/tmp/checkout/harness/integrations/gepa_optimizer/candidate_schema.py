"""candidate_schema.py — structured candidates for GEPA meta-optimization.

This module defines the typed candidate envelope that Solar's future
GEPA-backed meta-optimizer will mutate and evaluate.  The contract is kept
stdlib-only so it remains import-safe even when ``gepa`` is not installed.
"""

from __future__ import annotations

import dataclasses
import json
from enum import Enum
from typing import Any, Mapping

__all__ = [
    "CandidateType",
    "CandidateSchemaError",
    "OptimizationCandidate",
    "normalize_candidate",
]


class CandidateType(str, Enum):
    """The mutable artifact families GEPA is allowed to optimize."""

    SKILL = "skill"
    CAPSULE = "capsule"
    ROUTING_POLICY = "routing_policy"
    REWRITE_RULES = "rewrite_rules"
    COST_MODEL = "cost_model"


class CandidateSchemaError(ValueError):
    """Raised when a candidate payload violates the schema contract."""


def _as_string_tuple(
    raw: Any,
    *,
    field_name: str,
) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise CandidateSchemaError(f"{field_name} must be a list of strings")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise CandidateSchemaError(f"{field_name} entries must be non-empty strings")
        values.append(item.strip())
    if len(values) != len(set(values)):
        raise CandidateSchemaError(f"{field_name} contains duplicates")
    return tuple(values)


def _ensure_mapping(raw: Any, *, field_name: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise CandidateSchemaError(f"{field_name} must be an object/mapping")
    return dict(raw)


@dataclasses.dataclass(frozen=True)
class OptimizationCandidate:
    """Typed envelope for one mutable GEPA optimization candidate."""

    candidate_type: CandidateType
    target_id: str
    payload: dict[str, Any]
    mutable_sections: tuple[str, ...]
    frozen_sections: tuple[str, ...]
    origin_run_id: str | None = None
    lineage: tuple[str, ...] = ()
    frozen_values: dict[str, Any] = dataclasses.field(default_factory=dict)
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.target_id.strip():
            raise CandidateSchemaError("target_id must be a non-empty string")
        if set(self.mutable_sections) & set(self.frozen_sections):
            overlap = sorted(set(self.mutable_sections) & set(self.frozen_sections))
            raise CandidateSchemaError(
                "mutable_sections and frozen_sections overlap: "
                + ", ".join(overlap)
            )
        for item in self.lineage:
            if not isinstance(item, str) or not item.strip():
                raise CandidateSchemaError("lineage entries must be non-empty strings")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OptimizationCandidate":
        """Normalize and validate a candidate mapping."""
        if "candidate_type" not in raw:
            raise CandidateSchemaError("candidate_type is required")
        try:
            candidate_type = CandidateType(str(raw["candidate_type"]))
        except ValueError as exc:
            raise CandidateSchemaError(
                f"unsupported candidate_type: {raw['candidate_type']!r}"
            ) from exc
        payload = _ensure_mapping(raw.get("payload"), field_name="payload")
        mutable_sections = _as_string_tuple(
            raw.get("mutable_sections"), field_name="mutable_sections"
        )
        frozen_sections = _as_string_tuple(
            raw.get("frozen_sections"), field_name="frozen_sections"
        )
        lineage = _as_string_tuple(raw.get("lineage"), field_name="lineage")
        return cls(
            candidate_type=candidate_type,
            target_id=str(raw.get("target_id", "")).strip(),
            payload=payload,
            mutable_sections=mutable_sections,
            frozen_sections=frozen_sections,
            origin_run_id=(
                None
                if raw.get("origin_run_id") in (None, "")
                else str(raw["origin_run_id"])
            ),
            lineage=lineage,
            frozen_values=_ensure_mapping(raw.get("frozen_values"), field_name="frozen_values"),
            metadata=_ensure_mapping(raw.get("metadata"), field_name="metadata"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a plain JSON-serializable dict."""
        return {
            "candidate_type": self.candidate_type.value,
            "target_id": self.target_id,
            "payload": self.payload,
            "mutable_sections": list(self.mutable_sections),
            "frozen_sections": list(self.frozen_sections),
            "origin_run_id": self.origin_run_id,
            "lineage": list(self.lineage),
            "frozen_values": self.frozen_values,
            "metadata": self.metadata,
        }

    def canonical_json(self) -> str:
        """Canonical JSON for hashing, storage, and lineage diffing."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )


def normalize_candidate(
    candidate: OptimizationCandidate | Mapping[str, Any],
) -> OptimizationCandidate:
    """Return a validated :class:`OptimizationCandidate`."""
    if isinstance(candidate, OptimizationCandidate):
        return candidate
    return OptimizationCandidate.from_dict(candidate)
