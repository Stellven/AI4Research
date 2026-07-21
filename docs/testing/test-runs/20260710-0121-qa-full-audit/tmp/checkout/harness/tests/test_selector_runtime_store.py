#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from actor_lease import RUNNING
import selector_runtime_store as store


def test_round_robin_cursor_persists_to_runtime_store(tmp_path):
    state_path = tmp_path / "selector-state" / "runtime.json"
    lock_path = tmp_path / "selector-state" / "runtime.lock"

    first = store.round_robin_start_index(
        "DeepArchitect",
        3,
        state_path=state_path,
        lock_path=lock_path,
    )
    second = store.round_robin_start_index(
        "DeepArchitect",
        3,
        state_path=state_path,
        lock_path=lock_path,
    )
    payload = json.loads(state_path.read_text(encoding="utf-8"))

    assert first == 0
    assert second == 1
    assert payload["bindings"]["DeepArchitect"]["round_robin_cursor"] == 2


def test_actor_load_snapshot_uses_leases_and_selection_history(tmp_path):
    state_path = tmp_path / "selector-state" / "runtime.json"
    lock_path = tmp_path / "selector-state" / "runtime.lock"
    lease_dir = tmp_path / "actor-leases"
    lease_dir.mkdir(parents=True, exist_ok=True)
    (lease_dir / "actor-a.json").write_text(
        json.dumps({"actor_id": "actor-a", "state": RUNNING}, ensure_ascii=False),
        encoding="utf-8",
    )

    store.record_selection(
        "ResearchScout",
        "actor-a",
        selection_policy="least_loaded",
        state_path=state_path,
        lock_path=lock_path,
    )
    store.record_selection(
        "ResearchScout",
        "actor-a",
        selection_policy="least_loaded",
        state_path=state_path,
        lock_path=lock_path,
    )
    snapshot = store.actor_load_snapshot(
        "actor-a",
        state_path=state_path,
        lease_dir=lease_dir,
    )

    assert snapshot["active_lease_count"] == 1
    assert snapshot["selection_count"] == 2
    assert snapshot["last_selected_at"]
