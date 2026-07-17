"""rc.10 A4a — logical work roles survive physical-host selection.

The published rc.9 run scheduled an S3 ``Verifier`` node onto an available
builder-hosted operator-pool slot.  The scheduler correctly retained
``dispatch_role=evaluator``, but the queue dispatcher inferred the role from
the physical pane name and submitted the work as a builder.  These regressions
keep the two identities separate:

* the node/assignment owns the logical role;
* the selected pane/operator is only the physical execution host; and
* command, attempt, and attribution records all retain the logical role.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


HARNESS = Path(__file__).resolve().parents[2]
LIB = HARNESS / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import graph_node_dispatcher as gnd  # noqa: E402
import graph_scheduler as gs  # noqa: E402


SID = "sprint-logical-role"
NODE_ID = "S3"


def _evaluator_node(*, status: str = "assigned") -> dict:
    return {
        "id": NODE_ID,
        "status": status,
        "depends_on": [],
        "logical_operator": "Verifier",
        "dispatch_task_type": "verification",
        "task_type": "verification",
        "capsule_plan_ir": {
            "logical_operator": "Verifier",
            "role": "evaluator",
        },
        "required_capabilities": [],
        "required_skills": [],
    }


def _graph(node: dict) -> dict:
    return {
        "sprint_id": SID,
        "nodes": [node],
        "node_results": {},
        "gate_results": {},
        "required_gates": [],
    }


def test_scheduler_keeps_evaluator_role_on_builder_host() -> None:
    result = gs.assign_workers(
        [_evaluator_node(status="pending")],
        [
            {
                "pane": "operator-pool:builder.0",
                "dispatch_role": "builder",
                "host_role": "operator_pool",
                "models": ["operator-pool"],
                "skills": [],
                "capabilities": [],
                "busy": False,
            }
        ],
    )

    assert result["queued"] == []
    assert result["assigned"][0]["dispatch_role"] == "evaluator"
    assert result["assigned"][0]["worker_role"] == "builder"


def test_queue_role_comes_from_logical_assignment_not_builder_pane() -> None:
    node = _evaluator_node()
    assignment = {
        "pane": "operator-pool:builder.0",
        "dispatch_role": "evaluator",
        "worker_role": "builder",
    }

    assert gnd._graph_queue_dispatch_role({}, node, assignment) == "evaluator"
    assert (
        gnd._graph_queue_dispatch_role(
            {"pane": "operator-pool:builder.0"},
            node,
            {"pane": "operator-pool:builder.0"},
        )
        == "evaluator"
    )


def test_operator_pool_submission_persists_logical_role_and_physical_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    node = _evaluator_node()
    node.update(
        {
            "assigned_to": "operator-pool:builder.0",
            "dispatch_id": "graph-evaluator-dispatch",
        }
    )
    graph_path = sprints / f"{SID}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(node)), encoding="utf-8")

    captured: dict[str, object] = {}

    def capture_dispatch(payload: dict, pane: str) -> str:
        captured["dispatch_payload"] = dict(payload)
        captured["dispatch_pane"] = pane
        return "# graph dispatch\n"

    def capture_run(cmd: list[str], **_kwargs) -> SimpleNamespace:
        captured["cmd"] = list(cmd)
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "task_id = pm-evaluator-current\n"
                "operator = evaluator-current\n"
                "dispatch = dispatch.json\n"
                "result = result.md\n"
            ),
            stderr="",
        )

    def capture_attribution(_sid: str, _node_id: str, fields: dict) -> None:
        captured["attribution"] = dict(fields)

    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "_builder_operator_pool_enabled", lambda: True)
    monkeypatch.setattr(gnd, "_builder_operator_pool_allowed_for_pane", lambda _pane: True)
    monkeypatch.setattr(gnd, "build_dispatch_text", capture_dispatch)
    monkeypatch.setattr(gnd, "_inject_dispatch_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_broker_env", lambda _sid: {})
    monkeypatch.setattr(gnd.subprocess, "run", capture_run)
    monkeypatch.setattr(gnd, "release_lease", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_write_submit_ack", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_append_dispatch_ledger", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_record_node_attribution", capture_attribution)
    monkeypatch.setattr(gnd, "_append_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gnd, "_actorhost_bridge", lambda **_kwargs: {})
    monkeypatch.setattr(
        gnd,
        "_physical_operator_spec",
        lambda _operator_id: {
            "role": "evaluator",
            "persona": "evaluator",
            "profile": "codex-evaluator",
            "backend": "command",
            "provider": "openai",
            "model": "gpt-5.5",
        },
    )

    payload = {
        "assignment": {
            "pane": "operator-pool:builder.0",
            "dispatch_role": "evaluator",
            "worker_role": "builder",
        }
    }
    result = gnd._submit_builder_to_operator_pool(
        item={"id": "queue-item", "payload": payload},
        payload=payload,
        sid=SID,
        node=node,
        node_id=NODE_ID,
        graph_path=str(graph_path),
        pane="operator-pool:builder.0",
        dispatch_id="graph-evaluator-dispatch",
        dry_run=False,
    )

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[cmd.index("--role") + 1] == "evaluator"
    assert captured["dispatch_pane"] == "operator-pool:builder.0"
    dispatch_payload = captured["dispatch_payload"]
    assert isinstance(dispatch_payload, dict)
    assert dispatch_payload["dispatch_role"] == "evaluator"
    assert dispatch_payload["physical_host_role"] == "builder"
    assert result["logical_role"] == "evaluator"
    assert result["physical_host_role"] == "builder"

    persisted = gnd.load_graph(graph_path)
    attempt = persisted["nodes"][0]["execution_attempt"]
    assert attempt["logical_role"] == "evaluator"
    assert attempt["operator_id"] == "evaluator-current"

    attribution = captured["attribution"]
    assert isinstance(attribution, dict)
    assert attribution["role"] == "evaluator"
    assert attribution["physical_host_role"] == "builder"
    assert attribution["operator_role"] == "evaluator"


def test_direct_pane_attempt_records_logical_evaluator_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node = _evaluator_node()
    graph_path = tmp_path / f"{SID}.task_graph.json"
    graph_path.write_text(json.dumps(_graph(node)), encoding="utf-8")

    monkeypatch.setattr(gnd, "save_graph", gs.save_graph)
    monkeypatch.setattr(gnd, "load_graph", gs.load_graph)

    assert gnd._activate_direct_pane_attempt(
        str(graph_path),
        NODE_ID,
        sid=SID,
        pane="solar-test-lab:0.0",
        dispatch_id="graph-evaluator-direct",
        logical_role="evaluator",
    )

    persisted = gs.load_graph(graph_path)
    assert persisted["nodes"][0]["execution_attempt"]["logical_role"] == "evaluator"
