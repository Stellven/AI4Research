"""View registry for survey gate CLI formatters.

Provides ``register_view(name)`` decorator and ``VIEW_REGISTRY`` dict
for pluggable view registration, mirroring the gate registry pattern.
"""

from __future__ import annotations

from typing import Any, Callable

VIEW_REGISTRY: dict[str, dict[str, Callable[..., Any]]] = {}


def register_view(name: str):
    """Decorator that registers a view module's format + to_dict functions.

    Usage::

        @register_view("source_quality")
        def _register():
            from .source_quality_view import format_source_quality, to_dict_source_quality
            return {"format": format_source_quality, "to_dict": to_dict_source_quality}
    """
    def decorator(fn: Callable[[], dict[str, Callable[..., Any]]]):
        entries = fn()
        VIEW_REGISTRY[name] = entries
        return entries
    return decorator
