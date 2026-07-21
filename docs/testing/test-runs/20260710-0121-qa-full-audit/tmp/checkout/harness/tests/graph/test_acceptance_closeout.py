import json
from pathlib import Path

from acceptance_closeout import auto_closeout_graph_nodes


def test_auto_closeout_graph_nodes_writes_eval_and_syncs(monkeypatch, tmp_path):
    graph_path = tmp_path / "demo.task_graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": "demo",
                "nodes": [
                    {"id": "N1", "status": "reviewing"},
                    {"id": "N2", "status": "pending"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    node_payloads = {
        "N1": {"verdict": "PASS", "summary": "ok"},
        "N2": {"verdict": "FAIL", "summary": "blocked"},
    }
    eval_json_paths = {
        "N1": tmp_path / "N1.eval.json",
        "N2": tmp_path / "N2.eval.json",
    }
    verdict_calls = []

    def _fake_node_verdict(*, graph_path, node_id, eval_json_path, reason, dispatch_downstream):
        verdict_calls.append((str(graph_path), node_id, str(eval_json_path), reason, dispatch_downstream))
        return {"ok": True, "node": node_id, "status": "passed"}

    def _fake_status_sync(*, graph_path, actor, event):
        return {"ok": True, "graph_path": str(graph_path), "actor": actor, "event": event}

    monkeypatch.setattr("acceptance_closeout.invoke_node_verdict", _fake_node_verdict)
    monkeypatch.setattr("acceptance_closeout.invoke_status_sync", _fake_status_sync)

    result = auto_closeout_graph_nodes(
        graph_path=graph_path,
        node_payloads=node_payloads,
        eval_json_paths=eval_json_paths,
        reason="test-auto-closeout",
        actor="pytest",
        event="acceptance_auto_closeout",
        dispatch_downstream=False,
    )

    assert result["ok"] is False
    assert eval_json_paths["N1"].exists()
    assert eval_json_paths["N2"].exists()
    assert len(verdict_calls) == 1
    assert verdict_calls[0][1] == "N1"
    assert result["node_results"]["N2"]["reason"] == "eval_verdict_fail"
    assert result["status_sync"]["actor"] == "pytest"
