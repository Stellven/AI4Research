from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from research_orchestration.state_store import ResearchStateStore, ResearchStateStoreError  # noqa: E402


def state(run_id: str = "run-state") -> dict:
    return {
        "schema": "research_run_state.v1",
        "task_id": "task",
        "run_id": run_id,
        "workflow_id": "wf",
        "graph_identity": {"graph_id": "wf", "graph_version": 1, "workflow_kind": "research_synthesis"},
        "node_states": {
            "a": {
                "node_id": "a",
                "required_for_completion": True,
                "previous_status": None,
                "status": "ready",
                "depends_on": [],
                "result_ref": None,
                "updated_at": "2030-01-01T00:00:00Z",
            }
        },
        "ready_nodes": ["a"],
        "current_blockers": [],
        "resume_import_provenance": {"run_mode": "execute", "imported_evidence_refs": [], "source_run_ids": []},
        "final_status": "pending",
        "status_updated_at": "2030-01-01T00:00:00Z",
        "final_status_evidence_refs": [],
    }


def test_state_store_create_save_load_round_trip(tmp_path: Path) -> None:
    store = ResearchStateStore(tmp_path / "states")
    path = store.create(state())

    assert path.exists()
    assert path.resolve().is_relative_to((tmp_path / "states").resolve())
    assert store.load("run-state") == state()


def test_duplicate_save_is_idempotent(tmp_path: Path) -> None:
    store = ResearchStateStore(tmp_path)
    payload = state()
    store.save(payload)
    first = store.load("run-state")
    store.save(payload)
    second = store.load("run-state")

    assert first == second == payload


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    store = ResearchStateStore(tmp_path)

    with pytest.raises(ResearchStateStoreError, match="unsafe"):
        store.load("..\\escape")
    with pytest.raises(ResearchStateStoreError, match="unsafe"):
        store.save(state("../escape"))


def test_corrupted_json_does_not_get_overwritten_by_load(tmp_path: Path) -> None:
    store = ResearchStateStore(tmp_path)
    path = store.save(state())
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ResearchStateStoreError, match="corrupted"):
        store.load("run-state")
    assert path.read_text(encoding="utf-8") == "{not-json"


def test_concurrent_writes_leave_complete_json(tmp_path: Path) -> None:
    store = ResearchStateStore(tmp_path)

    def write(index: int) -> None:
        payload = state()
        payload["status_updated_at"] = f"2030-01-01T00:00:{index:02d}Z"
        store.save(payload)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(write, range(20)))

    loaded = store.load("run-state")
    assert isinstance(loaded, dict)
    assert loaded["schema"] == "research_run_state.v1"
    json.loads((tmp_path / "run-state.research_run_state.json").read_text(encoding="utf-8"))


def test_missing_state_returns_none(tmp_path: Path) -> None:
    store = ResearchStateStore(tmp_path)

    assert store.load("missing") is None


def test_interrupted_replace_temp_file_does_not_hide_committed_state(tmp_path: Path) -> None:
    store = ResearchStateStore(tmp_path)
    path = store.save(state())
    temp = path.with_name(path.name + ".interrupted.tmp")
    temp.write_text("{partial", encoding="utf-8")

    assert store.load("run-state") == state()
    assert temp.read_text(encoding="utf-8") == "{partial"
