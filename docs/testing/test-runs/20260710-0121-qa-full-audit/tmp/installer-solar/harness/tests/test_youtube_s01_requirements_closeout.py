from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import youtube_s01_requirements_closeout as ys1  # noqa: E402


def test_auto_closeout_youtube_s01_requirements_passes_when_matrix_and_terms_are_clean(tmp_path, monkeypatch):
    runtime_root = tmp_path
    sprints = runtime_root / "sprints"
    sprints.mkdir()
    sid = ys1.SPRINT_ID

    trace = {
        "outcome_dependency_matrix": {f"R{i}": [] for i in range(1, 17)},
    }
    (sprints / f"{sid}.traceability.json").write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")
    (sprints / f"{sid}.handoff.md").write_text("no reserved terms here", encoding="utf-8")
    (sprints / f"{sid}.{ys1.NODE_ID}-handoff.md").write_text("node handoff clean", encoding="utf-8")
    (sprints / f"{sid}.task_graph.json").write_text("{}", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_closeout(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "node_results": {ys1.NODE_ID: {"ok": True}}, "status_sync": {"ok": True}}

    monkeypatch.setattr(ys1, "auto_closeout_graph_nodes", fake_closeout)

    result = ys1.auto_closeout_youtube_s01_requirements(runtime_root)

    assert result["ok"] is True
    assert captured["reason"] == "youtube_s01_requirements_traceability_repaired"
    payload = captured["node_payloads"][ys1.NODE_ID]
    assert payload["verdict"] == "PASS"
