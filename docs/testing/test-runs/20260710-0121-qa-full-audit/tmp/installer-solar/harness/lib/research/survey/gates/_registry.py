"""Implementation of the gate registry and ``@register_gate`` decorator."""

from __future__ import annotations

import fnmatch
from typing import Any, Callable


class DuplicateGateError(Exception):
    """Raised when a gate name is registered more than once."""


class GateNotFoundError(KeyError):
    """Raised when looking up a gate name that has not been registered."""


class _GateRegistry:
    """Singleton registry holding registered gate callables."""

    def __init__(self) -> None:
        self._store: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        if name in self._store:
            raise DuplicateGateError(name)
        self._store[name] = fn

    def get(self, name: str) -> Callable[..., Any]:
        if name not in self._store:
            raise GateNotFoundError(name)
        return self._store[name]

    def list(self) -> list[str]:
        return sorted(self._store.keys())

    def clear(self) -> None:
        self._store.clear()


# Module-level singleton used by the decorator and public helpers.
_registry = _GateRegistry()


class GateRegistry:
    """Public read-only façade over the module-level gate registry."""

    @staticmethod
    def get(name: str) -> Callable[..., Any]:
        return _registry.get(name)

    @staticmethod
    def list() -> list[str]:
        return _registry.list()

    @staticmethod
    def clear() -> None:
        _registry.clear()


def register_gate(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that registers *fn* under *name* in the gate registry."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _registry.register(name, fn)
        return fn

    return decorator
