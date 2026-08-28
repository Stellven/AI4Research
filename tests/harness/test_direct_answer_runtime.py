from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "harness" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import direct_answer_runtime
import elastic_planner
import graph_node_dispatcher
import graph_scheduler


class DirectAnswerModel:
    provider = "test"
    model = "test-model"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, prompt, schema_path, work_dir):
        self.calls.append(schema_path.name)
        if schema_path == elastic_planner.DIRECT_RESPONSE_BODY_SCHEMA:
            return {
                "answer": "The sky looks blue because air scatters blue light more strongly.",
                "requirement_ids": ["REQ-001"],
                "limitations": ["This is a concise explanation."],
            }
        if schema_path == elastic_planner.DIRECT_RESPONSE_REVIEW_BODY_SCHEMA:
            return {
                "checks": [
                    {"kind": "requirement_coverage", "status": "pass", "reason": "Covered."},
                    {"kind": "answer_fidelity", "status": "pass", "reason": "Faithful."},
                    {"kind": "factual_restraint", "status": "pass", "reason": "Restrained."},
                ],
                "errors": [],
                "warnings": [],
            }
        raise AssertionError(f"unexpected model call: {schema_path}")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_direct_answer_runtime_finishes_without_dispatching_proposal_graph(tmp_path: Path) -> None:
    sid = "sprint-direct-answer-test"
    sprints = tmp_path / "sprints"
    requirement_ir = {
        "schema_version": "solar.requirement_ir.v1",
        "id": "req-direct-answer-test",
        "request_type": "direct_answer",
        "planner_hints": {
            "preferred_outcome": "direct_answer",
            "runtime_handoff_allowed": False,
            "response_authority": "planner",
        },
        "requirements": [{"id": "REQ-001", "source_text": "Why is the sky blue?"}],
    }
    graph = {
        "sprint_id": sid,
        "proposal_only": True,
        "runtime_handoff_allowed": False,
        "nodes": [{"id": "A1", "status": "pending"}],
    }
    status = {
        "id": sid,
        "status": "active",
        "phase": "direct_answer",
        "round": 0,
        "history": [],
    }
    _write_json(sprints / f"{sid}.requirement_ir.json", requirement_ir)
    _write_json(sprints / f"{sid}.task_graph.json", graph)
    _write_json(sprints / f"{sid}.status.json", status)
    graph_before = (sprints / f"{sid}.task_graph.json").read_bytes()
    planner_model = DirectAnswerModel()
    reviewer_model = DirectAnswerModel()

    result = direct_answer_runtime.run_direct_answer(
        harness_dir=tmp_path,
        sprint_id=sid,
        planner_model=planner_model,
        reviewer_model=reviewer_model,
    )

    final_status = json.loads((sprints / f"{sid}.status.json").read_text(encoding="utf-8"))
    assert result["status"] == "completed"
    assert final_status["status"] == "completed"
    assert final_status["direct_answer_status"] == "accepted"
    assert final_status["runtime_handoff_allowed"] is False
    assert (sprints / f"{sid}.answer.md").is_file()
    assert (sprints / sid / "workdir" / "workspace" / "direct_response" / "answer.md").is_file()
    assert (sprints / f"{sid}.task_graph.json").read_bytes() == graph_before
    assert planner_model.calls == [elastic_planner.DIRECT_RESPONSE_BODY_SCHEMA.name]
    assert reviewer_model.calls == [elastic_planner.DIRECT_RESPONSE_REVIEW_BODY_SCHEMA.name]


def test_dispatcher_refuses_proposal_only_graph_before_worker_selection(tmp_path: Path) -> None:
    graph_path = tmp_path / "sprint-direct.task_graph.json"
    _write_json(
        graph_path,
        {
            "sprint_id": "sprint-direct",
            "proposal_only": True,
            "runtime_handoff_allowed": False,
            "nodes": [],
        },
    )

    result = graph_node_dispatcher.dispatch_ready(str(graph_path), dry_run=True)

    assert result["ok"] is True
    assert result["status"] == "dispatch_forbidden"
    assert result["reason"] == "runtime_handoff_forbidden"
    assert result["enqueue"]["enqueued"] == []


def test_proposal_graph_cannot_overwrite_direct_answer_status(tmp_path: Path) -> None:
    sid = "sprint-direct-status"
    graph_path = tmp_path / f"{sid}.task_graph.json"
    status_path = tmp_path / f"{sid}.status.json"
    _write_json(
        graph_path,
        {
            "sprint_id": sid,
            "proposal_only": True,
            "runtime_handoff_allowed": False,
            "nodes": [{"id": "A1", "status": "pending"}],
        },
    )
    _write_json(
        status_path,
        {
            "id": sid,
            "status": "active",
            "phase": "direct_answer",
            "direct_answer_status": "running",
            "runtime_handoff_allowed": False,
        },
    )
    before = status_path.read_bytes()

    result = graph_scheduler.sync_status_cache_from_graph(
        graph_scheduler.load_graph(graph_path), graph_path
    )

    assert result["reason"] == "runtime_handoff_forbidden"
    assert result["updated"] is False
    assert status_path.read_bytes() == before


def test_direct_answer_runtime_rejects_duplicate_process(tmp_path: Path) -> None:
    lock_path = tmp_path / "run" / "direct-answer-locks" / "sprint-duplicate.lock"
    lock_path.parent.mkdir(parents=True)
    with lock_path.open("a+b") as handle:
        direct_answer_runtime.fcntl.flock(
            handle,
            direct_answer_runtime.fcntl.LOCK_EX | direct_answer_runtime.fcntl.LOCK_NB,
        )
        result = direct_answer_runtime.run_direct_answer(
            harness_dir=tmp_path,
            sprint_id="sprint-duplicate",
        )

    assert result == {"status": "already_running", "sprint_id": "sprint-duplicate"}


def test_direct_answer_cli_imports_library_when_pythonpath_already_contains_lib() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(LIB)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "harness" / "tools" / "direct_answer_runtime.py"), "--help"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Planner-owned direct-answer path" in proc.stdout
