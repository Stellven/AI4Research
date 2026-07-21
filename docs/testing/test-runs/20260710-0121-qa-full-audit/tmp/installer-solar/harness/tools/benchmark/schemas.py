"""Frozen schema contract for the Terminal-Bench 2.0 benchmark adapter.

S02 design.md §4.1 froze every public symbol exported here. S03 N1 introduces them
as Python; no later node may rename or retype any field. New optional fields with
defaults are allowed.
"""

from __future__ import annotations

import datetime
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


SCHEMA_VERSION: str = "benchmark.run.v1"

AGENT_ALLOWLIST: tuple[str, ...] = (
    "oracle",
    "solar-harness-agent",
    "host-claude-code",
    "claude-code",
    "codex",
    "deepagents-cli",
    "openai-cli",
)

SAFE_TASKS: tuple[str, ...] = ("chess-best-move", "build-pmars", "cancel-async-tasks")

DEFAULT_DATASET: str = "terminal-bench@2.0"

VALID_ENVS: tuple[str, ...] = ("docker", "daytona", "modal", "e2b", "runloop")


@dataclass(frozen=True)
class BenchmarkTask:
    id: str
    title: str
    tags: list[str]


@dataclass(frozen=True)
class BenchmarkDoctor:
    adapter_id: str
    harbor_available: bool
    harbor_kind: str
    docker_available: bool
    dataset_known: bool
    agents_known: tuple[str, ...]
    missing_prereqs: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class BenchmarkRunRequest:
    adapter_id: str
    agent: str
    model: str
    env: str
    tasks: tuple[str, ...]
    max_tasks: int | None = None
    n_concurrent: int = 1
    full: bool = False
    confirm_budget: bool = False
    dry_run: bool = True
    run_dir: str | None = None


@dataclass(frozen=True)
class BenchmarkRunPlan:
    command: tuple[str, ...]
    env_overrides: dict[str, str]
    notes: str = ""


@dataclass(frozen=True)
class BenchmarkRunResult:
    schema_version: str
    run_id: str
    benchmark: str
    benchmark_version: str
    dataset: str
    adapter: str
    agent: str
    model: str
    env: str
    tasks_requested: tuple[str, ...]
    tasks_completed: tuple[str, ...]
    score: float | None
    pass_count: int
    fail_count: int
    pending_count: int
    started_at: str
    completed_at: str | None
    duration_sec: float | None
    command: tuple[str, ...]
    exit_code: int | None
    stdout_path: str | None
    stderr_path: str | None
    artifacts: tuple[str, ...]
    verdict: str
    failure_modes: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@runtime_checkable
class BenchmarkAdapter(Protocol):
    id: str
    version: str

    def doctor(self) -> BenchmarkDoctor: ...
    def list_tasks(self) -> list[BenchmarkTask]: ...
    def plan(self, request: BenchmarkRunRequest) -> BenchmarkRunPlan: ...
    def run(self, request: BenchmarkRunRequest) -> BenchmarkRunResult: ...
    def parse_result(self, run_dir: Path) -> BenchmarkRunResult: ...


def new_run_id() -> str:
    """Return a run id of the form `bench-<YYYYMMDDHHMMSS>-<8hex>` (CBD8)."""
    stamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    suffix = secrets.token_hex(4)
    return f"bench-{stamp}-{suffix}"


def asdict_run_result(result: BenchmarkRunResult) -> dict[str, Any]:
    """Serialize a BenchmarkRunResult to a JSON-compatible dict."""
    payload = asdict(result)
    for key, value in list(payload.items()):
        if isinstance(value, tuple):
            payload[key] = list(value)
    return payload
