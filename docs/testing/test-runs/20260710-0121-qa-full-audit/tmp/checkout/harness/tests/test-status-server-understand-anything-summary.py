#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "lib" / "symphony" / "status-server.py"


def load_module():
    spec = importlib.util.spec_from_file_location("solar_status_server_ua_summary_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    mod = load_module()
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "researchPathLink('meta'" in source
    assert "researchPathLink('chunk-manifest'" in source
    assert "researchPathLink('resume-state'" in source
    with tempfile.TemporaryDirectory(prefix="solar-status-ua-summary-") as td:
        base = Path(td)
        harness = base / "harness"
        sprints = harness / "sprints"
        run_root = harness / "run" / "operator-results" / "mini-understand-anything-pane-bridge" / "task-1"
        sid = "sprint-test-ua-summary"

        write(
            sprints / f"{sid}.status.json",
            json.dumps(
                {
                    "sprint_id": sid,
                    "status": "active",
                    "phase": "implementation_complete",
                    "title": "Understand Anything Summary Test",
                }
            ),
        )
        write(
            sprints / f"{sid}.N1-physical-plan.json",
            json.dumps(
                {
                    "schema_version": "solar.physical_plan_node.v1",
                    "node_id": "N1",
                    "capability_capsule_id": "cap.understand-anything-indexer",
                    "selected_operator_id": "mini-understand-anything-pane-bridge",
                }
            ),
        )
        write(
            sprints / f"{sid}.N1-capsule-plan.json",
            json.dumps(
                {
                    "schema_version": "solar.capsule_plan_node.v1",
                    "node_id": "N1",
                    "capability_capsule_id": "cap.understand-anything-indexer",
                    "selected_skills": ["skill.understand-anything"],
                    "runtime_preferences": {"execution_surface": "deterministic_scan_and_thunderomlx_semantic"},
                }
            ),
        )
        ua_root = base / "repo" / ".understand-anything"
        write(ua_root / "knowledge-graph.json", json.dumps({"ok": True}))
        write(ua_root / "meta.json", json.dumps({"chunks_total": 5, "chunks_completed": 5}))
        write(ua_root / "chunk-manifest.json", json.dumps({"chunk_count": 5}))
        write(ua_root / "resume-state.json", json.dumps({"final_synthesis_completed": True}))
        write(run_root / "result.json", json.dumps({"sprint_id": sid, "node_id": "N1", "status": "completed"}))
        write(
            run_root / "understand-anything-result.json",
            json.dumps(
                {
                    "knowledge_graph_path": str(ua_root / "knowledge-graph.json"),
                    "dispatch_result": {
                        "meta_path": str(ua_root / "meta.json"),
                        "manifest_path": str(ua_root / "chunk-manifest.json"),
                        "resume_state_path": str(ua_root / "resume-state.json"),
                        "chunks_total": 5,
                        "chunks_completed": 5,
                        "resumed": False,
                    },
                }
            ),
        )

        mod.HARNESS_DIR = harness
        mod.SPRINTS_DIR = sprints

        current = mod._current_sprint()
        item = current["execution_plan_artifacts"]["items"][0]
        assert item["knowledge_graph_path"].endswith("knowledge-graph.json")
        assert item["understand_meta_path"].endswith("meta.json")
        assert item["understand_chunk_manifest_path"].endswith("chunk-manifest.json")
        assert item["understand_resume_state_path"].endswith("resume-state.json")
        assert item["understand_chunks_total"] == 5
        assert item["understand_chunks_completed"] == 5
        ua = current["understand_anything_summary"]
        assert ua["present"] is True
        assert ua["node_id"] == "N1"
        assert ua["chunks_total"] == 5
        assert ua["chunks_completed"] == 5
        assert "5/5 chunks" in ua["summary"]
        payload = mod._status_payload(limit=5, sprint_id=sid)
        assert payload["requested_sprint_id"] == sid
        assert payload["current_sprint"]["sprint_id"] == sid
        assert payload["current_sprint"]["focus_mode"] == "requested"
        assert payload["current_sprint"]["understand_anything_summary"]["present"] is True

    print("PASS status-server understand-anything summary")


if __name__ == "__main__":
    main()
