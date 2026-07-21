"""Gate registry for survey quality gates.

Provides a decorator-based plugin registration system.  Gates register
themselves via ``@register_gate(name)`` and are looked up at runtime with
``GateRegistry.get(name)``.
"""

from ._registry import GateRegistry, register_gate

GATE_SLOTS = [
    "source_quality",
    "argument_density",
    "controversy",
    "aggregator",
]

__all__ = ["GateRegistry", "register_gate", "GATE_SLOTS"]
