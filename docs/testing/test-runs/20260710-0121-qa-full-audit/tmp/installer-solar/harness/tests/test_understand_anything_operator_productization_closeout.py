import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from understand_anything_operator_productization_closeout import (  # noqa: E402
    NODE_IDS,
    auto_closeout_understand_anything_operator_productization,
)


def test_auto_closeout_understand_anything_operator_productization(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    sprint_root = runtime_root / "sprints"
    config_root = runtime_root / "config" / "capability-capsules"
    tools_root = runtime_root / "tools"
    tests_root = runtime_root / "tests"
    sprint_root.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)
    tools_root.mkdir(parents=True, exist_ok=True)
    tests_root.mkdir(parents=True, exist_ok=True)

    sid = "sprint-20260527-understand-anything-operator-productization"
    (sprint_root / f"{sid}.task_graph.json").write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "nodes": [
                    {"id": "S1", "status": "dispatched", "depends_on": []},
                    {"id": "S2", "status": None, "depends_on": ["S1"]},
                    {"id": "S3", "status": None, "depends_on": ["S2"]},
                    {"id": "S4", "status": None, "depends_on": ["S3"]},
                    {"id": "S5", "status": None, "depends_on": ["S4"]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (sprint_root / f"{sid}.design.md").write_text("design\n", encoding="utf-8")
    (sprint_root / f"{sid}.plan.md").write_text("plan\n", encoding="utf-8")
    (sprint_root / f"{sid}.traceability.json").write_text("{}", encoding="utf-8")
    (config_root / "cap.understand-anything-indexer.yaml").write_text("capability_capsule_id: cap.understand-anything-indexer\n", encoding="utf-8")
    (runtime_root / "config" / "capability-capsules.registry.yaml").write_text("registry: true\n", encoding="utf-8")
    for name in ("understand_anything_operator.py", "understand_anything_local_pipeline.py", "backfill_understand_anything_task_graphs.py"):
        (tools_root / name).write_text("# stub\n", encoding="utf-8")
    for name in (
        "test_capability_capsules_understand_anything.py",
        "test_codex_pm_router_understand_anything.py",
        "test_understand_anything_operator.py",
        "test_understand_anything_local_pipeline.py",
        "test-status-server-understand-anything-summary.py",
    ):
        (tests_root / name).write_text("print('PASS')\n", encoding="utf-8")

    def fake_run(*args, **kwargs):
        cmd = args[0]
        if "-m" in cmd:
            return type("P", (), {"returncode": 0, "stdout": "7 passed", "stderr": ""})()
        return type("P", (), {"returncode": 0, "stdout": "PASS status-server understand-anything summary", "stderr": ""})()

    monkeypatch.setattr("understand_anything_operator_productization_closeout.subprocess.run", fake_run)

    calls = []

    def _fake_closeout(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "node_results": {node_id: {"ok": True, "status": "passed"} for node_id in kwargs["node_payloads"]}, "status_sync": {"ok": True}}

    monkeypatch.setattr("understand_anything_operator_productization_closeout.auto_closeout_graph_nodes", _fake_closeout)

    result = auto_closeout_understand_anything_operator_productization(runtime_root)

    assert result["ok"] is True
    assert len(calls) == len(NODE_IDS)
    assert (sprint_root / f"{sid}.S4-review_decision.yaml").exists()
    assert (sprint_root / f"{sid}.S5-rollout_notes.md").exists()
