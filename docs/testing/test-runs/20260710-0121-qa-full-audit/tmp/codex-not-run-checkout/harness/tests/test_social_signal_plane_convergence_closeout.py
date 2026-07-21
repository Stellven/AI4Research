from __future__ import annotations

import sys
from pathlib import Path

HARNESS_LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import social_signal_plane_convergence_closeout as sspc  # noqa: E402


def test_auto_closeout_social_signal_plane_convergence_creates_missing_artifacts(tmp_path, monkeypatch):
    runtime_root = tmp_path
    sprints = runtime_root / "sprints"
    sprints.mkdir()
    sid = sspc.SPRINT_ID

    for suffix in [
        ".S2-handoff.md",
        ".S2-patch.diff",
        ".S2-guard-decision.json",
        ".S2-resource-binding.json",
        ".S3-handoff.md",
        ".S4-traceability.json",
        ".task_graph.json",
    ]:
        payload = "{}" if suffix.endswith(".json") else f"artifact {suffix}"
        (sprints / f"{sid}{suffix}").write_text(payload, encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_closeout(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "node_results": {"S2": {"ok": True}, "S5": {"ok": True}}, "status_sync": {"ok": True}}

    monkeypatch.setattr(sspc, "auto_closeout_graph_nodes", fake_closeout)

    result = sspc.auto_closeout_social_signal_plane_convergence(runtime_root)

    assert result["ok"] is True
    assert (sprints / f"{sid}.S2-bridged_artifact.md").exists()
    assert (sprints / f"{sid}.S5-rollout-notes.md").exists()
    assert (sprints / f"{sid}.S5-handoff.md").exists()
    assert (sprints / f"{sid}.review_decision.yaml").exists()
    assert (sprints / f"{sid}.acceptance_verdict.json").exists()
    assert captured["reason"] == "social_signal_plane_convergence_integrated_closeout"
