#!/usr/bin/env python3
"""operator_persona.py — Shared persona resolver for Solar Harness operators.

Single source of truth for resolving an operator's persona file.

Resolution order
----------------
1. ``persona`` field in the operator config (authoritative).
2. ``role`` field as a backwards-compatible fallback.

Raises ``RuntimeError`` consistently when the binding is absent or the
persona file cannot be found.  Callers decide whether to propagate the
error (submit / dispatch path) or warn-and-continue (daemon bootstrap).

Evaluator protocol
------------------
When the resolved persona name is ``"evaluator"``, the companion
``evaluator-verification-protocol.md`` file is also loaded from the
same personas directory.  If the protocol file is absent, the resolution
still succeeds but ``eval_protocol_loaded`` is ``False``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

EVALUATOR_PROTOCOL_FILENAME = "evaluator-verification-protocol.md"


class PersonaResolution:
    """Holds the result of a successful persona resolution."""

    __slots__ = (
        "persona_name",
        "persona_path",
        "persona_text",
        "source",
        "eval_protocol_path",
        "eval_protocol_text",
    )

    def __init__(
        self,
        *,
        persona_name: str,
        persona_path: Path,
        persona_text: str,
        source: str,
        eval_protocol_path: Optional[Path] = None,
        eval_protocol_text: Optional[str] = None,
    ) -> None:
        self.persona_name = persona_name
        self.persona_path = persona_path
        self.persona_text = persona_text
        # "persona" when resolved from the persona field, "role" when via fallback
        self.source = source
        self.eval_protocol_path = eval_protocol_path
        self.eval_protocol_text = eval_protocol_text

    @property
    def eval_protocol_loaded(self) -> bool:
        return self.eval_protocol_path is not None


def resolve_persona(
    operator_id: str,
    config: dict,
    personas_dir: Path,
    *,
    load_content: bool = True,
) -> PersonaResolution:
    """Resolve the persona for an operator.

    Args:
        operator_id: Used only in error messages.
        config: Operator config dict from the registry.
        personas_dir: Directory that contains persona ``.md`` files.
        load_content: When ``False``, validate file existence only and
            return empty strings for text fields.  Faster path used by
            ``submit()`` before the lease is acquired.

    Returns:
        A :class:`PersonaResolution` describing the resolved persona.

    Raises:
        RuntimeError: Neither ``persona`` nor ``role`` is set, or the
            resolved persona file does not exist.
    """
    persona_name: Optional[str] = config.get("persona") or None
    source: str

    if persona_name:
        source = "persona"
    else:
        role: Optional[str] = config.get("role") or None
        if not role:
            raise RuntimeError(
                f"Operator '{operator_id}' has no persona binding in registry"
            )
        persona_name = role
        source = "role"

    persona_path = personas_dir / f"{persona_name}.md"
    if not persona_path.exists():
        raise RuntimeError(
            f"Operator '{operator_id}' persona file missing: {persona_path}"
        )

    persona_text = ""
    if load_content:
        try:
            persona_text = persona_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(
                f"Operator '{operator_id}' persona file unreadable: {persona_path}: {exc}"
            ) from exc

    # Load evaluator protocol only when the resolved persona is "evaluator".
    # Missing protocol file is tolerated (eval_protocol_loaded → False).
    eval_protocol_path: Optional[Path] = None
    eval_protocol_text: Optional[str] = None
    if persona_name == "evaluator":
        proto_path = personas_dir / EVALUATOR_PROTOCOL_FILENAME
        if proto_path.exists():
            eval_protocol_path = proto_path
            if load_content:
                try:
                    eval_protocol_text = proto_path.read_text(encoding="utf-8")
                except OSError:
                    eval_protocol_path = None

    return PersonaResolution(
        persona_name=persona_name,
        persona_path=persona_path,
        persona_text=persona_text,
        source=source,
        eval_protocol_path=eval_protocol_path,
        eval_protocol_text=eval_protocol_text,
    )
