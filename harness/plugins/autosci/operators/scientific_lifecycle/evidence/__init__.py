"""Executable evidence operators and their package-local discovery seam."""

from .registry import (
    OPERATOR_SPECS,
    execute_operator,
    get_operator_spec,
    registration_entries,
    resolve_entrypoint,
)

__all__ = [
    "OPERATOR_SPECS",
    "execute_operator",
    "get_operator_spec",
    "registration_entries",
    "resolve_entrypoint",
]
