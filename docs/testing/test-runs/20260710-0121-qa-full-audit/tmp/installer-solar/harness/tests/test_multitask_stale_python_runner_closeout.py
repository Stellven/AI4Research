from __future__ import annotations

import json
import sys
from pathlib import Path


HARNESS_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import multitask_stale_python_runner_closeout as closeout  # noqa: E402


def test_closeout_generates_artifacts_and_eval(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    sprints = runtime_root / "sprints"
    reports = runtime_root / "monitor-reports"
    sprints.mkdir(parents=True)
    reports.mkdir(parents=True)
    graph_path = sprints / f"{closeout.SPRINT_ID}.task_graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": closeout.SPRINT_ID,
                "nodes": [
                    {"id": "N2", "status": "reviewing"},
                    {"id": "N3", "status": "reviewing"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(closeout, "_run_pytest", lambda root: {"returncode": 0, "stdout": "11 passed", "stderr": "", "command": "pytest"})
    monkeypatch.setattr(closeout, "_run_auto_exit_smoke", lambda root: {"returncode": 0, "stdout": "exit", "stderr": "", "command": "start"})
    monkeypatch.setattr(closeout, "_run_detector", lambda root: {"returncode": 0, "stdout": '{"rows":[]}', "stderr": "", "command": "stale-schedulers"})
    captured: dict[str, object] = {}

    def _fake_closeout(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "node_results": {"N2": {"ok": True}, "N3": {"ok": True}}, "status_sync": {"ok": True}}

    monkeypatch.setattr(closeout, "auto_closeout_graph_nodes", _fake_closeout)

    result = closeout.auto_closeout(runtime_root)

    assert result["ok"] is True
    assert (sprints / f"{closeout.SPRINT_ID}.N2-handoff.md").exists()
    assert (reports / f"{closeout.SPRINT_ID}-N3-validation.md").exists()
    eval_json_paths = captured["eval_json_paths"]
    assert str(eval_json_paths["N2"]).endswith(".N2-eval.json")
    assert str(eval_json_paths["N3"]).endswith(".N3-eval.json")
