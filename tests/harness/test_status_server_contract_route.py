from __future__ import annotations

import importlib.util
import json
import threading
import time
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = (Path(__file__).resolve().parents[2] / 'harness')
MODULE_PATH = ROOT / "lib" / "symphony" / "status-server.py"


def _load_status_server(tmp_path: Path):
    harness = tmp_path / "harness"
    for rel in ("sprints", "sessions", "events", "run"):
        (harness / rel).mkdir(parents=True, exist_ok=True)
    name = f"status_server_contract_route_{time.time_ns()}"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HARNESS_DIR = harness
    module.SPRINTS_DIR = harness / "sprints"
    return module, harness


def _import_status_server(name: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _get_json(module, path: str) -> dict:
    status, payload = _get_response(module, path)
    assert status == 200, payload
    return payload


def _get_response(module, path: str) -> tuple[int, dict]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.StatusHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}{path}", timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_contract_route_uses_ledger_projection_and_manifest_links(tmp_path: Path):
    module, harness = _load_status_server(tmp_path)
    sid = "sprint-contract-route"
    _write_json(
        harness / "sprints" / f"{sid}.task_graph.json",
        {
            "sprint_id": sid,
            "workflow_contract_id": "research.deepdive.rsi_demo",
            "workflow_contract_version": "1.0",
            "nodes": [
                {"id": "D1", "status": "running"},
                {"id": "D2", "status": "pending"},
            ],
        },
    )
    _write_jsonl(
        harness / "sprints" / f"{sid}.gate-ledger.jsonl",
        [
            {
                "sid": sid,
                "node_id": "D1",
                "kind": "status_transition",
                "from_status": "running",
                "to_status": "passed",
                "author": {"type": "scheduler"},
                "created_at": "2026-07-07T00:00:00Z",
            }
        ],
    )
    _write_json(harness / "sprints" / f"{sid}.D1-manifest.json", {"sid": sid, "node_id": "D1"})

    payload = _get_json(module, f"/api/sprints/{sid}/contract")

    assert payload["ok"] is True
    assert payload["contracted"] is True
    assert payload["contract"]["workflow_id"] == "research.deepdive.rsi_demo"
    assert payload["contract"]["version"] == "1.0"
    stages = {stage["id"]: stage for stage in payload["stages"]}
    assert stages["D1"]["state"] == "passed"
    assert stages["D1"]["state_source"] == "gate_ledger"
    assert stages["D1"]["manifest"]["exists"] is True
    assert stages["D1"]["manifest"]["path"].endswith(f"{sid}.D1-manifest.json")
    assert stages["D2"]["state"] == "pending"
    assert stages["D2"]["state_source"] == "graph"
    assert stages["D2"]["manifest"]["exists"] is False
    assert stages["D2"]["manifest"]["path"].endswith(f"{sid}.D2-manifest.json")


def test_contract_route_honors_harness_sprints_dir_env(tmp_path: Path, monkeypatch):
    harness = tmp_path / "harness"
    sprints_dir = tmp_path / "custom-sprints"
    harness.mkdir(parents=True, exist_ok=True)
    sprints_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HARNESS_DIR", str(harness))
    monkeypatch.setenv("SOLAR_HARNESS_DIR", str(tmp_path / "ignored-harness"))
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(sprints_dir))

    module = _import_status_server(f"status_server_contract_route_env_{time.time_ns()}")

    assert module.HARNESS_DIR == harness
    assert module.SPRINTS_DIR == sprints_dir


def test_contract_route_returns_legacy_shape_for_uncontracted_sprint(tmp_path: Path):
    module, harness = _load_status_server(tmp_path)
    sid = "sprint-legacy-route"
    _write_json(
        harness / "sprints" / f"{sid}.task_graph.json",
        {"sprint_id": sid, "nodes": [{"id": "N1", "status": "active"}]},
    )

    payload = _get_json(module, f"/api/sprints/{sid}/contract")

    assert payload["ok"] is True
    assert payload["contracted"] is False
    assert payload["contract"] == {}
    assert payload["stages"] == [
        {
            "id": "N1",
            "label": "N1",
            "state": "active",
            "state_source": "graph",
            "manifest": {"path": "", "exists": False, "url": ""},
        }
    ]


def test_contract_route_returns_404_for_nonexistent_sprint(tmp_path: Path):
    module, _harness = _load_status_server(tmp_path)

    status, payload = _get_response(module, "/api/sprints/sprint-does-not-exist-r5/contract")

    assert status == 404
    assert payload["ok"] is False
    assert payload["status"] == "not_found"
    assert payload["error"] == "sprint_not_found"
    assert payload["contracted"] is False
    assert payload["sprint_id"] == "sprint-does-not-exist-r5"
