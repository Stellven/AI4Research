"""Terminal-Bench 2.0 benchmark adapter package.

S03 N1 ships the schema + registry foundation. Adapter seeding (importing
`terminal_bench`) is deferred to N3 per the design.md §4.8 contract.
"""

from __future__ import annotations

from . import registry
from .registry import ADAPTER_REGISTRY, get_adapter, list_adapters, normalize_adapter_id, register
from .schemas import (
    AGENT_ALLOWLIST,
    DEFAULT_DATASET,
    SAFE_TASKS,
    SCHEMA_VERSION,
    VALID_ENVS,
    BenchmarkAdapter,
    BenchmarkDoctor,
    BenchmarkRunPlan,
    BenchmarkRunRequest,
    BenchmarkRunResult,
    BenchmarkTask,
    asdict_run_result,
    new_run_id,
)

__all__ = [
    "ADAPTER_REGISTRY",
    "AGENT_ALLOWLIST",
    "DEFAULT_DATASET",
    "SAFE_TASKS",
    "SCHEMA_VERSION",
    "VALID_ENVS",
    "BenchmarkAdapter",
    "BenchmarkDoctor",
    "BenchmarkRunPlan",
    "BenchmarkRunRequest",
    "BenchmarkRunResult",
    "BenchmarkTask",
    "asdict_run_result",
    "get_adapter",
    "list_adapters",
    "new_run_id",
    "normalize_adapter_id",
    "register",
    "registry",
]
