"""Unit tests for the benchmark registry.

S03 N6 acceptance: roundtrip register/get, seeded discovery (terminal-bench@2.0
present after importing the package), and unknown-id error path.
"""

from __future__ import annotations

import pytest

from harness.lib.benchmark import registry as _registry_mod
from harness.lib.benchmark.registry import (
    ADAPTER_REGISTRY,
    get_adapter,
    list_adapters,
    register,
)


@pytest.fixture
def isolated_registry(monkeypatch):
    """Snapshot ADAPTER_REGISTRY and restore after the test."""
    snapshot = dict(ADAPTER_REGISTRY)
    yield
    ADAPTER_REGISTRY.clear()
    ADAPTER_REGISTRY.update(snapshot)


def test_register_then_get_roundtrip(isolated_registry):
    @register
    class _FakeAdapter:
        id = "fake@0.0"
        version = "0.0"

        def doctor(self): ...
        def list_tasks(self): return []
        def plan(self, req): ...
        def run(self, req): ...
        def parse_result(self, run_dir): ...

    assert "fake@0.0" in ADAPTER_REGISTRY
    instance = get_adapter("fake@0.0")
    assert isinstance(instance, _FakeAdapter)
    assert "fake@0.0" in list_adapters()


def test_register_rejects_class_without_id(isolated_registry):
    class _NoId:
        version = "1.0"

    with pytest.raises(TypeError, match="non-empty class attribute"):
        register(_NoId)


def test_register_rejects_empty_id(isolated_registry):
    class _EmptyId:
        id = ""

    with pytest.raises(TypeError):
        register(_EmptyId)


def test_get_adapter_unknown_id_raises_with_known_list(isolated_registry):
    @register
    class _Adapter:
        id = "x@1"
        version = "1"

    with pytest.raises(KeyError) as exc_info:
        get_adapter("does-not-exist@0.0")
    msg = str(exc_info.value)
    assert "does-not-exist@0.0" in msg
    assert "x@1" in msg


def test_seeded_discovery_terminal_bench_present():
    """After importing the package, terminal-bench@2.0 must be registered.

    The seed lives at the bottom of terminal_bench.py via @registry.register.
    Importing harness.lib.benchmark indirectly imports it via runner.
    """
    import harness.lib.benchmark  # noqa: F401
    import harness.lib.benchmark.terminal_bench  # noqa: F401

    assert "terminal-bench@2.0" in ADAPTER_REGISTRY
    adapter = get_adapter("terminal-bench@2.0")
    assert getattr(adapter, "id", None) == "terminal-bench@2.0"
    assert getattr(adapter, "version", None) == "2.0"


def test_list_adapters_returns_sorted_unique():
    """list_adapters() must return a sorted list with no duplicates."""
    import harness.lib.benchmark.terminal_bench  # noqa: F401

    items = list_adapters()
    assert items == sorted(items)
    assert len(items) == len(set(items))


def test_re_register_same_id_overwrites(isolated_registry):
    @register
    class _V1:
        id = "swap@1"

    @register
    class _V2:
        id = "swap@1"

    assert ADAPTER_REGISTRY["swap@1"] is _V2
