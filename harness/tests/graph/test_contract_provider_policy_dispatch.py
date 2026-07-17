from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


HARNESS = Path(__file__).resolve().parents[2]
LIB = HARNESS / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import graph_node_dispatcher as gnd  # noqa: E402
import graph_scheduler  # noqa: E402
import workflow_contract as wc  # noqa: E402


def _worker(provider: str, pane: str, load: int) -> dict:
    model = "sonnet" if provider == "anthropic" else "gpt-5.5"
    return {
        "pane": pane,
        "models": [model],
        "skills": [],
        "capabilities": ["code_impl"],
        "role": "builder",
        "dispatch_role": "builder",
        "host_role": "builder",
        "provider": provider,
        "busy": False,
        "title": f"{provider} builder",
        "load": load,
    }


def _instantiated_graph(workflow_id: str) -> dict:
    contract = wc.find_contract(workflow_id, HARNESS / "config" / "workflows")
    assert contract is not None
    return wc.instantiate(contract, {"sid": f"{workflow_id}-sid", "sprint_id": f"{workflow_id}-sid", "tool": "wordfreq"})


@pytest.mark.parametrize(
    "workflow_id,env_provider,workers,expected_pane",
    [
        (
            "code.cli_smoke",
            "anthropic",
            [_worker("anthropic", "aaa-anthropic-builder", 0), _worker("openai", "zzz-openai-builder", 1)],
            "zzz-openai-builder",
        ),
        (
            "code.cli_smoke_anthropic",
            "openai",
            [_worker("openai", "aaa-openai-builder", 0), _worker("anthropic", "zzz-anthropic-builder", 1)],
            "zzz-anthropic-builder",
        ),
    ],
)
def test_contracted_dispatch_uses_contract_provider_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workflow_id: str,
    env_provider: str,
    workers: list[dict],
    expected_pane: str,
):
    graph = _instantiated_graph(workflow_id)
    graph_path = tmp_path / f"{graph['sprint_id']}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setenv("SOLAR_PM_DEFAULT_PROVIDERS", env_provider)
    monkeypatch.setenv("SOLAR_MULTI_TASK_DEFAULT_PROVIDERS", env_provider)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "_discover_workers", lambda dry_run=False: list(workers))

    result = gnd.dispatch_ready(str(graph_path), dry_run=True, max_parallel=1)

    enqueued = result["enqueue"]["enqueued"]
    assert enqueued, result
    assert enqueued[0]["pane"] == expected_pane


def test_contracted_dispatch_provider_filter_is_flag_gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    graph = _instantiated_graph("code.cli_smoke")
    graph_path = tmp_path / f"{graph['sprint_id']}.task_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    workers = [
        _worker("anthropic", "aaa-anthropic-builder", 0),
        _worker("openai", "zzz-openai-builder", 1),
    ]

    # G4 default-on: unset now means ON — model the ledger-OFF state explicitly.
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "0")
    monkeypatch.delenv("SOLAR_PRODUCT_MODE", raising=False)
    monkeypatch.setenv("SOLAR_PM_DEFAULT_PROVIDERS", "anthropic")
    monkeypatch.setenv("SOLAR_MULTI_TASK_DEFAULT_PROVIDERS", "anthropic")
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(graph_scheduler, "SPRINTS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "_discover_workers", lambda dry_run=False: list(workers))

    result = gnd.dispatch_ready(str(graph_path), dry_run=True, max_parallel=1)

    enqueued = result["enqueue"]["enqueued"]
    assert enqueued, result
    assert enqueued[0]["pane"] == "aaa-anthropic-builder"
