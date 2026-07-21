from __future__ import annotations

import json
import sys
from pathlib import Path

HARNESS_LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import thunderomlx_cache_warm_advisor_closeout as tcw  # noqa: E402


def test_auto_closeout_thunderomlx_cache_warm_advisor_builds_eval_payloads(tmp_path, monkeypatch):
    runtime_root = tmp_path
    (runtime_root / "scripts").mkdir(parents=True)
    (runtime_root / "monitor-reports").mkdir(parents=True)
    sprints = runtime_root / "sprints"
    sprints.mkdir()
    sid = tcw.SPRINT_ID

    for suffix in [".N2-handoff.md", ".N3-handoff.md", ".N4-handoff.md", ".finalized", ".task_graph.json"]:
        content = "{}" if suffix.endswith(".json") else f"artifact {suffix}"
        (sprints / f"{sid}{suffix}").write_text(content, encoding="utf-8")

    (runtime_root / "scripts" / "thunderomlx_auto_prewarm.py").write_text("print('ok')\n", encoding="utf-8")
    (runtime_root / "scripts" / "thunderomlx_cache_advisor_report.py").write_text("print('ok')\n", encoding="utf-8")
    (runtime_root / "monitor-reports" / "thunderomlx-four-pane-prewarm-20260520T194407Z.json").write_text("{}", encoding="utf-8")
    (runtime_root / "monitor-reports" / "thunderomlx-four-pane-prewarm-20260520T194407Z.md").write_text("report", encoding="utf-8")
    (runtime_root / "monitor-reports" / "thunderomlx-cache-advisor-20260520T194510Z.json").write_text("{}", encoding="utf-8")
    (runtime_root / "monitor-reports" / "thunderomlx-cache-advisor-20260520T194510Z.md").write_text("report", encoding="utf-8")

    thunder = tmp_path / "ThunderOMLX"
    (thunder / "src" / "omlx").mkdir(parents=True)
    (thunder / "src" / "omlx" / "server.py").write_text("server", encoding="utf-8")
    (thunder / "src" / "omlx" / "cache_tuning_advisor.py").write_text("advisor", encoding="utf-8")
    monkeypatch.setattr(tcw, "THUNDER_ROOT", thunder)

    captured: dict[str, object] = {}

    def fake_closeout(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "node_results": {node_id: {"ok": True} for node_id in tcw.NODE_IDS},
            "status_sync": {"ok": True},
        }

    monkeypatch.setattr(tcw, "auto_closeout_graph_nodes", fake_closeout)

    result = tcw.auto_closeout_thunderomlx_cache_warm_advisor(runtime_root)

    assert result["ok"] is True
    assert captured["reason"] == "thunderomlx_cache_warm_advisor_eval_restored"
    payloads = captured["node_payloads"]
    assert payloads["N2"]["verdict"] == "PASS"
    assert payloads["N3"]["verdict"] == "PASS"
    assert payloads["N4"]["verdict"] == "PASS"
    traceability = json.loads((sprints / f"{sid}.traceability.json").read_text(encoding="utf-8"))
    assert traceability["nodes"]["N2"]["gate"] == "auto prewarm report appears after restart or startup hook simulation"
