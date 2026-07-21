#!/usr/bin/env python3
"""Regression tests for pane hygiene projection in status-server."""

import importlib.util
import json
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "lib" / "symphony" / "status-server.py"
spec = importlib.util.spec_from_file_location("status_server", MODULE)
status_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(status_server)


def test_pane_info_and_main_screen_include_hygiene_and_host_role(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    run_dir = harness / "run"
    sprints.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    (sprints / "sprint-a.status.json").write_text(json.dumps({"id": "sprint-a", "status": "active"}), encoding="utf-8")
    (harness / ".pane-assignments").write_text("solar-harness:0.0=sprint-a:pm\n", encoding="utf-8")
    (run_dir / "pane-hygiene.json").write_text(
        json.dumps(
            {
                "solar-harness:0.0": {"pane_role": "pm", "state": "clean"},
                "solar-harness:0.1": {"pane_role": "planner", "state": "dirty"},
            }
        ),
        encoding="utf-8",
    )

    def fake_tmux(cmd, timeout=0.8):
        target = cmd[3]
        field = cmd[4] if len(cmd) > 4 else ""
        if cmd[:3] == ["display-message", "-p", "-t"] and field == "#{pane_id}":
            return "%1"
        if cmd[:3] == ["display-message", "-p", "-t"] and field == "#{pane_title}":
            return {
                "solar-harness:0.0": "PM 产品经理 | 状态:idle",
                "solar-harness:0.1": "Planner 规划者 | 状态:idle",
                "solar-harness:0.2": "Builder 主建设者 | 状态:idle",
                "solar-harness:0.3": "Evaluator 审判官 | 状态:idle",
            }.get(target, "N/A")
        if cmd[:3] == ["capture-pane", "-t", target]:
            return "❯\n  ⏵⏵ bypass permissions on (shift+tab to cycle)\n"
        return ""

    monkeypatch.setattr(status_server, "HARNESS_DIR", harness)
    monkeypatch.setattr(status_server, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(status_server, "PANE_ASSIGNMENTS", harness / ".pane-assignments")
    monkeypatch.setattr(status_server, "PANE_HYGIENE_JSON", run_dir / "pane-hygiene.json")
    monkeypatch.setattr(status_server, "_run_tmux", fake_tmux)
    monkeypatch.setattr(status_server, "_capability_health_summary", lambda: {"status": "ok"})
    monkeypatch.setattr(
        status_server,
        "_latest_model_call_for_pane",
        lambda target, pane_id="": {"status": "unknown", "model": "", "provider": ""},
    )

    info = status_server._pane_info()
    assert info[0]["host_role"] == "pm"
    assert info[0]["hygiene_state"] == "clean"

    main = status_server._main_screen(include_model_call=False)
    first = main["panes"][0]
    second = main["panes"][1]
    assert first["host_role"] == "PM"
    assert first["hygiene_state"] == "clean"
    assert second["host_role"] == "Planner"
    assert second["hygiene_state"] == "dirty"


def test_status_server_source_renders_host_role_and_hygiene_columns():
    source = MODULE.read_text(encoding="utf-8")
    assert "<th>Host Role</th>" in source
    assert "<th>Hygiene</th>" in source


def test_read_jsonl_fast_tail_returns_last_entries_without_full_scan(tmp_path):
    path = tmp_path / "all.jsonl"
    rows = []
    for i in range(20):
        rows.append(json.dumps({"sprint_id": f"s{i}", "seq": i}, ensure_ascii=False))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    got = status_server._read_jsonl(path, limit=5)
    assert [item["seq"] for item in got] == [15, 16, 17, 18, 19]


def test_status_payload_short_cache_hits_on_second_call(monkeypatch):
    monkeypatch.setattr(status_server, "_STATUS_PAYLOAD_CACHE", {})
    monkeypatch.setattr(status_server, "_sprint_meta", lambda sid="": {"sprint_id": sid or "sprint-a", "status": "active"})
    monkeypatch.setattr(status_server, "_current_sprint", lambda: {"sprint_id": "sprint-a", "status": "active"})
    monkeypatch.setattr(status_server, "_execution_plan_summary", lambda sid: {"count": 0, "summary": "N/A", "items": []})
    monkeypatch.setattr(status_server, "_current_understand_anything_summary", lambda plan: {"present": False, "summary": "N/A"})
    monkeypatch.setattr(status_server, "_latest_task_graph_gate_audit_summary", lambda: {"present": False, "summary": "N/A"})
    monkeypatch.setattr(status_server, "_runtime_interfaces_status", lambda sid: {"ok": True, "status": "ok"})
    monkeypatch.setattr(status_server, "_capability_health_summary", lambda runtime=None: {"ok": True, "status": "ok"})
    monkeypatch.setattr(status_server, "_multi_task_panes_info", lambda: [])
    monkeypatch.setattr(status_server, "_multi_task_pane_pool_summary", lambda panes: {"total": 0})
    monkeypatch.setattr(status_server, "_pane_info", lambda: [])
    monkeypatch.setattr(status_server, "_main_screen", lambda *args, **kwargs: {"panes": []})
    monkeypatch.setattr(status_server, "_lab_screen", lambda *args, **kwargs: {"panes": []})
    monkeypatch.setattr(status_server, "_read_jsonl", lambda *args, **kwargs: [])
    monkeypatch.setattr(status_server, "_kpi", lambda: {"total": 0})
    monkeypatch.setattr(status_server, "_obsidian_wiki_readiness", lambda: {})
    monkeypatch.setattr(status_server, "_mirage_status", lambda: {})
    monkeypatch.setattr(status_server, "_knowledge_ingest_progress_payload", lambda: {})
    monkeypatch.setattr(status_server, "_tech_hotspot_reasoning_policy_summary", lambda: {})
    monkeypatch.setattr(status_server, "_solar_kb_status", lambda: {})
    monkeypatch.setattr(status_server, "_obsidian_sync_status", lambda: {})
    monkeypatch.setattr(status_server, "_apple_notes_ingest_status", lambda: {})
    monkeypatch.setattr(status_server, "_evolution_status", lambda: {})
    monkeypatch.setattr(status_server, "_human_search_waiting_status", lambda: {})
    monkeypatch.setattr(status_server, "_research_status_summary", lambda: {})
    monkeypatch.setattr(status_server, "_autoresearch_impact_summary", lambda: {})
    monkeypatch.setattr(status_server, "_meta_harness_summary", lambda: {})
    monkeypatch.setattr(status_server, "_pm_dispatch_summary", lambda: {})
    monkeypatch.setattr(status_server, "_physical_operator_summary", lambda: {})
    monkeypatch.setattr(status_server, "_final_contract_summary_status", lambda: {})
    monkeypatch.setattr(status_server, "_requirement_coverage_summary", lambda sid: {})

    first = status_server._status_payload(limit=5, sprint_id="sprint-a")
    second = status_server._status_payload(limit=5, sprint_id="sprint-a")
    assert first["status_cache"] == "miss"
    assert second["status_cache"] == "hit"
