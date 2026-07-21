"""Adapter registry for the Terminal-Bench 2.0 benchmark package.

Adapters register themselves by decorating their class with `@register`.
N1 ships an empty registry; N3 seeds `terminal-bench@2.0` via `terminal_bench.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schemas import BenchmarkAdapter


ADAPTER_REGISTRY: dict[str, type] = {}
ADAPTER_ALIASES: dict[str, str] = {
    "terminal-bench": "terminal-bench@2.0",
    "terminal-bench-2": "terminal-bench@2.0",
    "terminal-bench-2.0": "terminal-bench@2.0",
    "terminal-bench@2": "terminal-bench@2.0",
}


def register(adapter_cls: type) -> type:
    """Class decorator that records `adapter_cls` under its `id` attribute.

    The class must expose a class-level `id: str`. Re-registering the same id
    overwrites the prior entry (intentional, so tests can swap in fakes).
    """
    adapter_id = getattr(adapter_cls, "id", None)
    if not isinstance(adapter_id, str) or not adapter_id:
        raise TypeError(
            f"register: {adapter_cls!r} must define a non-empty class attribute `id: str`"
        )
    ADAPTER_REGISTRY[adapter_id] = adapter_cls
    return adapter_cls


def normalize_adapter_id(adapter_id: str) -> str:
    """Return the canonical adapter id for user-facing aliases."""
    return ADAPTER_ALIASES.get(adapter_id, adapter_id)


def get_adapter(adapter_id: str) -> "BenchmarkAdapter":
    """Instantiate the adapter class registered under `adapter_id`.

    Raises KeyError listing all known ids if `adapter_id` is unknown.
    """
    canonical_id = normalize_adapter_id(adapter_id)
    cls = ADAPTER_REGISTRY.get(canonical_id)
    if cls is None:
        known = sorted(ADAPTER_REGISTRY)
        raise KeyError(
            f"unknown benchmark adapter {adapter_id!r}; known adapters: {known}"
        )
    return cls()


def list_adapters() -> list[str]:
    """Return the sorted list of registered adapter ids."""
    return sorted(ADAPTER_REGISTRY)
