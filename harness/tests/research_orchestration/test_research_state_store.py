from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from research_orchestration.state_store import (  # noqa: E402
    ResearchStateConflictError,
    ResearchStateStore,
    ResearchStateStoreError,
)


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


def test_optimistic_revision_rejects_stale_writer(tmp_path: Path) -> None:
    store = ResearchStateStore(tmp_path)
    store.create(state())
    first, revision = store.load_with_revision("run-state")
    second, same_revision = store.load_with_revision("run-state")
    assert revision == same_revision
    first["status_updated_at"] = "2030-01-01T00:00:01Z"
    _path, new_revision = store.save_with_revision(first, expected_revision=revision)
    assert new_revision != revision
    second["status_updated_at"] = "2030-01-01T00:00:02Z"

    with pytest.raises(ResearchStateConflictError, match="revision conflict"):
        store.save_with_revision(second, expected_revision=same_revision)

    assert store.load("run-state")["status_updated_at"] == "2030-01-01T00:00:01Z"


def test_real_subprocesses_cannot_silently_overwrite_same_revision(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    store = ResearchStateStore(state_root)
    store.create(state())
    gate = tmp_path / "go"
    ready_root = tmp_path / "ready"
    ready_root.mkdir()
    worker = r'''
import json
import sys
import time
from pathlib import Path
from research_orchestration.state_store import ResearchStateStore

root, gate, ready, marker = map(Path, sys.argv[1:])
store = ResearchStateStore(root)
payload, revision = store.load_with_revision("run-state")
ready.write_text("ready", encoding="utf-8")
deadline = time.time() + 15
while not gate.exists():
    if time.time() > deadline:
        raise SystemExit("gate timeout")
    time.sleep(0.01)
payload["status_updated_at"] = marker.name
try:
    store.save_with_revision(payload, expected_revision=revision)
except Exception as exc:
    print(json.dumps({"status": "conflict", "type": type(exc).__name__}))
else:
    print(json.dumps({"status": "saved"}))
'''
    env = os.environ.copy()
    env["PYTHONPATH"] = str(LIB)
    processes = []
    for index in range(2):
        ready = ready_root / f"worker-{index}"
        marker = tmp_path / f"2030-01-01T00-00-0{index}Z"
        processes.append(
            subprocess.Popen(
                [sys.executable, "-c", worker, str(state_root), str(gate), str(ready), str(marker)],
                cwd=tmp_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )
    deadline = time.time() + 15
    while len(list(ready_root.iterdir())) < 2 and time.time() < deadline:
        time.sleep(0.01)
    assert len(list(ready_root.iterdir())) == 2
    gate.write_text("go", encoding="utf-8")
    outputs = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        outputs.append(json.loads(stdout.strip()))

    assert sorted(item["status"] for item in outputs) == ["conflict", "saved"]
    loaded = store.load("run-state")
    assert loaded["status_updated_at"] in {
        "2030-01-01T00-00-00Z",
        "2030-01-01T00-00-01Z",
    }


def test_node_records_are_immutable_content_addressed_sidecars(tmp_path: Path) -> None:
    store = ResearchStateStore(tmp_path)
    first = store.store_node_record(
        run_id="run-state",
        node_id="a",
        result={"status": "completed", "output_artifacts": [{"artifact_id": "one", "path": "one.json"}]},
        evaluation={"accepted": True, "evidence_refs": ["ev-one"]},
    )
    second = store.store_node_record(
        run_id="run-state",
        node_id="a",
        result={"status": "completed", "output_artifacts": [{"artifact_id": "two", "path": "two.json"}]},
        evaluation={"accepted": True, "evidence_refs": ["ev-two"]},
    )

    assert first != second
    assert Path(first).is_file() and Path(second).is_file()
    assert store.load_node_record(first)["result"]["output_artifacts"][0]["artifact_id"] == "one"
    assert store.load_node_record(second)["result"]["output_artifacts"][0]["artifact_id"] == "two"
