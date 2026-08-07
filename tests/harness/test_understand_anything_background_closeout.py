import json
from pathlib import Path

from understand_anything_background_closeout import (
    NODE_IDS,
    SPRINT_ID,
    auto_closeout_understand_anything_background,
)


def test_auto_closeout_understand_anything_background(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    sprint_root = runtime_root / "sprints"
    run_root = runtime_root / "run" / "understand-anything-background" / SPRINT_ID
    output_dir = tmp_path / "repo" / ".understand-anything"
    sprint_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    (sprint_root / f"{SPRINT_ID}.task_graph.json").write_text(
        json.dumps(
            {
                "sprint_id": SPRINT_ID,
                "nodes": [
                    {"id": "U1_preflight_runtime", "status": ""},
                    {"id": "U2_run_understand_zh_background", "status": "", "depends_on": ["U1_preflight_runtime"]},
                    {"id": "U3_verify_graph_artifacts", "status": "", "depends_on": ["U2_run_understand_zh_background"]},
                    {"id": "U4_handoff_resume_contract", "status": "", "depends_on": ["U3_verify_graph_artifacts"]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_root / "preflight.json").write_text(
        json.dumps(
            {
                "node_version": "v1",
                "pnpm_version": "9",
                "plugin_root_exists": True,
                "plugin_root_readable": True,
                "claude_cli_auth_status": "claude_config_json",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_root / "verify.json").write_text(
        json.dumps(
            {
                "config_exists": True,
                "knowledge_graph_exists": True,
                "knowledge_graph_json_valid": True,
                "meta_exists": True,
                "chunk_manifest_exists": True,
                "resume_state_exists": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_root / "status.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    (sprint_root / f"{SPRINT_ID}.handoff.md").write_text("resume later\n", encoding="utf-8")

    verdict_calls = []

    def _fake_closeout(**kwargs):
        verdict_calls.append(kwargs)
        return {
            "ok": True,
            "graph_path": str(kwargs["graph_path"]),
            "node_results": {node_id: {"ok": True} for node_id in kwargs["node_payloads"]},
            "status_sync": {"ok": True},
        }

    monkeypatch.setattr("understand_anything_background_closeout.auto_closeout_graph_nodes", _fake_closeout)

    result = auto_closeout_understand_anything_background(
        runtime_root=runtime_root,
        target_repo=output_dir.parent,
    )

    assert result["ok"] is True
    assert len(verdict_calls) == 1
    payloads = verdict_calls[0]["node_payloads"]
    assert set(payloads) == set(NODE_IDS)
    assert all(payload["verdict"] == "PASS" for payload in payloads.values())
    for node_id in NODE_IDS:
        assert (sprint_root / f"{SPRINT_ID}.{node_id}-handoff.md").exists()
