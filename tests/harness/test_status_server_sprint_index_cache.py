#!/usr/bin/env python3
"""Regression coverage for concurrent /api/sprints index requests."""

from __future__ import annotations

import importlib.util
import threading
import time
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2] / "harness"
MODULE_PATH = ROOT / "lib" / "symphony" / "status-server.py"


def load_module():
    spec = importlib.util.spec_from_file_location("solar_status_server_sprint_index_cache_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_concurrent_sprint_index_requests_share_one_build() -> None:
    mod = load_module()
    worker_count = 8
    start = threading.Barrier(worker_count)
    call_lock = threading.Lock()
    calls = 0
    results: list[dict] = []
    errors: list[BaseException] = []

    def build_sprint_index_payload(*, limit: int):
        nonlocal calls
        with call_lock:
            calls += 1
        time.sleep(0.1)
        return {"sprints": [{"sprint_id": "sprint-cache-test"}], "count": 1}, []

    routes = SimpleNamespace(
        SCHEMA_VERSION="solar.orchestration.v1",
        build_sprint_index_payload=build_sprint_index_payload,
    )
    mod._load_orchestration_routes_module = lambda: routes

    def request_index() -> None:
        try:
            start.wait(timeout=2)
            results.append(mod._sprint_index_payload(limit=80))
        except BaseException as exc:  # preserve worker failures for the main assertion
            errors.append(exc)

    threads = [threading.Thread(target=request_index) for _ in range(worker_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert len(results) == worker_count
    assert calls == 1
    assert all(result["data"]["count"] == 1 for result in results)
    results[0]["data"]["count"] = 99
    assert results[1]["data"]["count"] == 1
