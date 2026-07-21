from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import multitask_history_window_label_closeout as mhw  # noqa: E402


def test_auto_closeout_multitask_history_window_label_builds_eval_payloads(tmp_path, monkeypatch):
    runtime_root = tmp_path
    (runtime_root / "lib").mkdir(parents=True)
    (runtime_root / "monitor-reports").mkdir(parents=True)
    (runtime_root / "tests").mkdir(parents=True)
    sprints = runtime_root / "sprints"
    sprints.mkdir()
    sid = mhw.SPRINT_ID

    for suffix in [".N1-audit.md", ".N1-handoff.md", ".N2-handoff.md", ".task_graph.json"]:
        content = "{}" if suffix.endswith(".json") else f"artifact {suffix}"
        (sprints / f"{sid}{suffix}").write_text(content, encoding="utf-8")
    (sprints / f"{sid}.N1-audit.md").write_text(
        "render_plain\nrender_screen_status_lines\nrender_tvs\npane_title\nrename-window\n",
        encoding="utf-8",
    )
    (runtime_root / "lib" / "multi_task_runner.py").write_text(
        'def _display_tmux_status():\n    pass\n_display_tmux_status(\neffective_status\n--ttl-minutes\n',
        encoding="utf-8",
    )
    (runtime_root / "monitor-reports" / "safe-reap-guide.md").write_text(
        "--dry-run\n--ttl-minutes\nforce-all\n禁止\nstale-schedulers\n",
        encoding="utf-8",
    )
    (runtime_root / "tests" / "test_multitask_history_window_label.py").write_text("def test_stub():\n    assert True\n", encoding="utf-8")
    (runtime_root / "solar-harness.sh").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")

    commands: list[list[str]] = []

    def fake_run(cmd):
        commands.append(cmd)
        return {"ok": True, "returncode": 0, "stdout": "ok", "stderr": "", "cmd": cmd}

    captured: dict[str, object] = {}

    def fake_closeout(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "node_results": {node_id: {"ok": True} for node_id in mhw.NODE_IDS},
            "status_sync": {"ok": True},
        }

    monkeypatch.setattr(mhw, "_run", fake_run)
    monkeypatch.setattr(mhw, "auto_closeout_graph_nodes", fake_closeout)

    result = mhw.auto_closeout_multitask_history_window_label(runtime_root)

    assert result["ok"] is True
    assert captured["reason"] == "multitask_history_window_label_eval_restored"
    payloads = captured["node_payloads"]
    assert payloads["N1"]["verdict"] == "PASS"
    assert payloads["N2"]["verdict"] == "PASS"
    assert (sprints / f"{sid}.traceability.json").exists()
    traceability = json.loads((sprints / f"{sid}.traceability.json").read_text(encoding="utf-8"))
    assert traceability["nodes"]["N2"]["gate"] == "status output separates active live work from historical open windows"
    assert any(cmd[:2] == ["pytest", "-q"] for cmd in commands)
