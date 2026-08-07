"""Tests for the gate registry (gates/_registry.py)."""

from __future__ import annotations

import pytest

from lib.research.survey.gates._registry import (
    DuplicateGateError,
    GateNotFoundError,
    _GateRegistry,
)
from lib.research.survey.gates import register_gate, GateRegistry
from lib.research.survey.gates._registry import _registry as global_reg


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def reg():
    return _GateRegistry()


def _fn_a():
    return "a"


def _fn_b():
    return "b"


# ---------------------------------------------------------------------------
# 1. register + get
# ---------------------------------------------------------------------------

def test_register_and_get(reg):
    reg.register("alpha", _fn_a)
    assert reg.get("alpha") is _fn_a


# ---------------------------------------------------------------------------
# 2. list
# ---------------------------------------------------------------------------

def test_list_sorted(reg):
    reg.register("beta", _fn_b)
    reg.register("alpha", _fn_a)
    assert reg.list() == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# 3. duplicate name raises
# ---------------------------------------------------------------------------

def test_duplicate_raises(reg):
    reg.register("dup", _fn_a)
    with pytest.raises(DuplicateGateError):
        reg.register("dup", _fn_b)


# ---------------------------------------------------------------------------
# 4. clear
# ---------------------------------------------------------------------------

def test_clear(reg):
    reg.register("x", _fn_a)
    reg.clear()
    with pytest.raises(GateNotFoundError):
        reg.get("x")


# ---------------------------------------------------------------------------
# 5. missing name raises
# ---------------------------------------------------------------------------

def test_missing_raises(reg):
    with pytest.raises(GateNotFoundError):
        reg.get("nonexistent")


# ---------------------------------------------------------------------------
# 6. register_gate decorator
# ---------------------------------------------------------------------------

def test_register_gate_decorator():
    global_reg.clear()
    try:
        @register_gate("decorated_test")
        def my_gate():
            return "ok"

        assert GateRegistry.get("decorated_test") is my_gate
        assert my_gate() == "ok"
    finally:
        global_reg.clear()
