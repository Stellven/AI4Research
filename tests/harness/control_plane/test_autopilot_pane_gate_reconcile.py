#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import time
from pathlib import Path


MODULE_PATH = (Path(__file__).resolve().parents[3] / 'harness') / "tools" / "solar-autopilot-monitor.py"
spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["solar_autopilot_monitor"] = mod
spec.loader.exec_module(mod)


def _utc_after(seconds: int) -> str:
    return (
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_pane_gate_clears_stale_assignment_without_graph_or_lease(tmp_path, monkeypatch) -> None:
    assignments = tmp_path / ".pane-assignments"
    assignments.write_text("solar-harness-lab:0.1=stale-sprint:1779000000\n")
    monkeypatch.setattr(mod, "PANE_ASSIGNMENTS", assignments)
    monkeypatch.setattr(mod, "PANE_LEASE_DIR", tmp_path / "pane-leases")
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "assigned_graph_node_for_pane", lambda target: {})
    monkeypatch.setattr(mod, "pane_is_busy", lambda target: False)

    allowed, reason, detail = mod.pane_gate("solar-harness-lab:0.1", "new-sprint")

    assert allowed is True
    assert reason == "ok"
    assert detail["assignment"] == {}
    assert "assignment_cleared" in detail["reconciled"]
    assert mod.pane_assignment("solar-harness-lab:0.1") == {}


def test_pane_gate_clears_stale_live_lease_without_graph_node(tmp_path, monkeypatch) -> None:
    lease_dir = tmp_path / "pane-leases"
    lease_dir.mkdir(parents=True)
    lease_path = lease_dir / f"{mod.pane_safe('solar-harness-lab:0.2')}.json"
    lease_path.write_text(json.dumps({
        "pane": "solar-harness-lab:0.2",
        "sid": "stale-sprint",
        "dispatch_id": "d-1",
        "expires_at": _utc_after(600),
        "ttl_sec": 600,
    }) + "\n")
    monkeypatch.setattr(mod, "PANE_ASSIGNMENTS", tmp_path / ".pane-assignments")
    monkeypatch.setattr(mod, "PANE_LEASE_DIR", lease_dir)
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "assigned_graph_node_for_pane", lambda target: {})
    monkeypatch.setattr(mod, "pane_is_busy", lambda target: False)

    allowed, reason, detail = mod.pane_gate("solar-harness-lab:0.2", "fresh-sprint")

    assert allowed is True
    assert reason == "ok"
    assert detail["lease"] == {}
    assert "lease_cleared" in detail["reconciled"]
    assert lease_path.exists() is False


def test_pane_gate_keeps_active_graph_claims_even_when_pane_is_idle(tmp_path, monkeypatch) -> None:
    assignments = tmp_path / ".pane-assignments"
    assignments.write_text("solar-harness-lab:0.3=active-sprint:1779000000\n")
    lease_dir = tmp_path / "pane-leases"
    lease_dir.mkdir(parents=True)
    lease_path = lease_dir / f"{mod.pane_safe('solar-harness-lab:0.3')}.json"
    lease_path.write_text(json.dumps({
        "pane": "solar-harness-lab:0.3",
        "sid": "active-sprint",
        "dispatch_id": "d-2",
        "expires_at": _utc_after(600),
        "ttl_sec": 600,
    }) + "\n")
    monkeypatch.setattr(mod, "PANE_ASSIGNMENTS", assignments)
    monkeypatch.setattr(mod, "PANE_LEASE_DIR", lease_dir)
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mod,
        "assigned_graph_node_for_pane",
        lambda target: {"sid": "active-sprint", "node_id": "S2", "status": "dispatched"},
    )
    monkeypatch.setattr(mod, "pane_is_busy", lambda target: False)

    allowed, reason, detail = mod.pane_gate("solar-harness-lab:0.3", "fresh-sprint")

    assert allowed is False
    assert reason == "pane_leased"
    assert detail["graph_node"]["node_id"] == "S2"
    assert detail["lease"]["sid"] == "active-sprint"
    assert detail["assignment"]["sid"] == "active-sprint"
    assert lease_path.exists() is True


def test_reconcile_preserves_lease_when_graph_claim_is_recoverable_from_runtime_evidence(tmp_path, monkeypatch) -> None:
    lease_dir = tmp_path / "pane-leases"
    lease_dir.mkdir(parents=True)
    lease_path = lease_dir / f"{mod.pane_safe('solar-harness-lab:0.4')}.json"
    lease_path.write_text(json.dumps({
        "pane": "solar-harness-lab:0.4",
        "sid": "recoverable-sprint",
        "dispatch_id": "dispatch-ua-1",
        "expires_at": _utc_after(600),
        "ttl_sec": 600,
    }) + "\n")
    graph_path = tmp_path / "sprints" / "recoverable-sprint.task_graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps({
        "sprint_id": "recoverable-sprint",
        "nodes": [
            {
                "id": "S1",
                "status": "dispatched",
                "assigned_to": "solar-harness-lab:0.4",
                "dispatch_id": "dispatch-ua-1",
            }
        ],
    }) + "\n")
    monkeypatch.setattr(mod, "PANE_ASSIGNMENTS", tmp_path / ".pane-assignments")
    monkeypatch.setattr(mod, "PANE_LEASE_DIR", lease_dir)
    monkeypatch.setattr(mod, "SPRINTS", graph_path.parent)
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "active_statuses", lambda: [])
    monkeypatch.setattr(mod, "load_graph", lambda path: json.loads(Path(path).read_text()))
    monkeypatch.setattr(mod, "node_status", lambda graph, node_id: graph["nodes"][0]["status"])
    monkeypatch.setattr(mod, "pane_is_busy", lambda target: False)

    allowed, reason, detail = mod.pane_gate("solar-harness-lab:0.4", "fresh-sprint")

    assert allowed is False
    assert reason == "pane_leased"
    assert detail["graph_node"]["sid"] == "recoverable-sprint"
    assert detail["graph_node"]["node_id"] == "S1"
    assert detail["graph_node"]["recovered_from_runtime_evidence"] is True
    assert lease_path.exists() is True


def test_inspect_sprints_releases_blocked_dependency_waiting_status_when_route_is_ready(tmp_path, monkeypatch) -> None:
    sprints = tmp_path / "sprints"
    sprints.mkdir(parents=True)
    sid = "sprint-unblock-ready"
    status_path = sprints / f"{sid}.status.json"
    status_path.write_text(json.dumps({
        "sprint_id": sid,
        "status": "blocked",
        "phase": "external_dependency_waiting",
        "handoff_to": "",
        "target_role": "",
    }) + "\n")
    monkeypatch.setattr(mod, "SPRINTS", sprints)
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "epic_child_dependency_ready", lambda sid: (True, []))
    monkeypatch.setattr(
        mod,
        "workflow_guard_route",
        lambda sid: {
            "ok": True,
            "violations": [],
            "route_role": "planner",
            "stage": "prd_ready",
            "reason": "pm_prd_ready",
        },
    )

    mod.inspect_sprints()
    payload = json.loads(status_path.read_text())

    assert payload["status"] == "drafting"
    assert payload["phase"] == "prd_ready"
    assert payload["handoff_to"] == "planner"
    assert payload["target_role"] == "planner"


def test_builder_handoff_prefers_idle_lab_builder_when_primary_is_occupied(monkeypatch) -> None:
    monkeypatch.setattr(
        mod,
        "discover_worker_panes",
        lambda: ["solar-harness:0.2", "solar-harness-lab:0.0", "solar-harness-lab:0.1"],
    )
    monkeypatch.setattr(mod, "pane_title_matches_role", lambda pane, role, title="": role == "builder")
    monkeypatch.setattr(
        mod,
        "pane_gate",
        lambda pane, sid: (
            (False, "pane_leased", {}) if pane == "solar-harness:0.2" else (True, "ok", {})
        ),
    )
    monkeypatch.setattr(mod, "pane_is_busy", lambda pane: False)

    assert mod.pane_target_for_handoff("builder_main") == "solar-harness-lab:0.0"


def test_builder_queue_item_reroutes_to_idle_lab_builder(monkeypatch) -> None:
    monkeypatch.setattr(mod, "pane_target_for_handoff", lambda handoff: "solar-harness-lab:0.1")
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    item = {
        "type": "ready_for_builder",
        "target": "solar-harness:0.2",
    }

    target = mod.maybe_reroute_builder_target(item, "sprint-demo")

    assert target == "solar-harness-lab:0.1"
    assert item["target"] == "solar-harness-lab:0.1"


def test_planner_handoff_prefers_idle_planner_pool_candidate(monkeypatch) -> None:
    monkeypatch.setattr(
        mod,
        "discover_role_pool",
        lambda role: [
            {"pane": "solar-harness:0.1"},
            {"pane": "solar-harness-lab:0.4"},
        ] if role == "planner" else [],
    )
    monkeypatch.setattr(
        mod,
        "pane_gate",
        lambda pane, sid: (
            (False, "pane_leased", {}) if pane == "solar-harness:0.1" else (True, "ok", {})
        ),
    )
    monkeypatch.setattr(mod, "pane_is_busy", lambda pane: False)

    assert mod.pane_target_for_handoff("planner") == "solar-harness-lab:0.4"


def test_should_act_retries_role_handoff_soon_after_failed_pm_attempt(tmp_path, monkeypatch) -> None:
    inbox = tmp_path / "pm-inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod, "PM_INBOX_DIR", inbox)
    monkeypatch.setattr(mod, "ROLE_HANDOFF_RETRY_COOLDOWN_SEC", 30)
    monkeypatch.setattr(mod, "_active_pm_task_ids", lambda: set())
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "task_id": "pm-sprint-yt-N0-deadbeef",
        "sprint_id": "sprint-yt",
        "requested_role": "planner",
        "status": "failed_missing_pm_result",
        "submitted_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (inbox / "pm-sprint-yt-N0-deadbeef.json").write_text(json.dumps(payload), encoding="utf-8")
    state = {"actions": {"sprint-yt:ready_for_planner:solar-harness:0.1": {"at": time.time() - 40}}}
    finding = {"sid": "sprint-yt", "type": "ready_for_planner", "target": "solar-harness:0.1"}

    assert mod.should_act(state, finding, 300) is True


def test_apply_findings_skips_duplicate_role_handoff_when_live_pm_task_exists(tmp_path, monkeypatch) -> None:
    inbox = tmp_path / "pm-inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod, "PM_INBOX_DIR", inbox)
    monkeypatch.setattr(mod, "_active_pm_task_ids", lambda: {"pm-sprint-yt-N0-live"})
    live = {
        "task_id": "pm-sprint-yt-N0-live",
        "sprint_id": "sprint-yt",
        "requested_role": "planner",
        "status": "submitted",
        "submitted_at": _utc_after(60),
    }
    (inbox / "pm-sprint-yt-N0-live.json").write_text(json.dumps(live), encoding="utf-8")
    monkeypatch.setattr(mod, "load_json", lambda path: {"sprint_id": "sprint-yt", "handoff_to": "planner", "phase": "prd_ready", "status": "active"})
    monkeypatch.setattr(mod, "save_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "dispatch_role_handoff", lambda sid, ftype: (_ for _ in ()).throw(AssertionError("dispatch should be skipped")))

    findings = [{"sid": "sprint-yt", "type": "ready_for_planner", "target": "solar-harness:0.1", "message": "retry"}]
    state = {"actions": {}, "target_actions": {}}
    actions = mod.apply_findings(findings, True, state, 300)

    assert actions[0]["skipped"] == "live_pm_task_exists"
    assert actions[0]["task_id"] == "pm-sprint-yt-N0-live"


def test_evaluator_handoff_prefers_idle_evaluator_pool_candidate(monkeypatch) -> None:
    monkeypatch.setattr(
        mod,
        "discover_role_pool",
        lambda role: [
            {"pane": "solar-harness:0.3"},
            {"pane": "solar-harness-lab:0.1"},
        ] if role == "evaluator" else [],
    )
    monkeypatch.setattr(
        mod,
        "pane_gate",
        lambda pane, sid: (
            (False, "pane_leased", {}) if pane == "solar-harness:0.3" else (True, "ok", {})
        ),
    )
    monkeypatch.setattr(mod, "pane_is_busy", lambda pane: False)

    assert mod.pane_target_for_handoff("evaluator") == "solar-harness-lab:0.1"


def test_ready_for_planner_queue_bypasses_fixed_pane_busy(tmp_path, monkeypatch) -> None:
    sid = "sprint-planner-demo"
    monkeypatch.setattr(mod, "QUEUE", tmp_path / "autopilot-queue.jsonl")
    monkeypatch.setattr(mod, "SPRINTS", tmp_path / "sprints")
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "pane_gate", lambda target, sid: (True, "ok", {}))
    monkeypatch.setattr(mod, "pane_is_busy", lambda target: True)
    monkeypatch.setattr(mod, "clear_current_prompt", lambda target: None)
    role_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(mod, "dispatch_role_handoff", lambda s, t: role_calls.append((s, t)) or (True, {"role": "planner"}))
    monkeypatch.setattr(mod, "wake_sid", lambda s: False)
    mod.SPRINTS.mkdir(parents=True)
    (mod.SPRINTS / f"{sid}.status.json").write_text(json.dumps({
        "sprint_id": sid,
        "status": "drafting",
        "phase": "prd_ready",
        "handoff_to": "planner",
    }) + "\n")
    mod.QUEUE.write_text(json.dumps({
        "sid": sid,
        "type": "ready_for_planner",
        "target": "solar-harness:0.1",
        "created_at_epoch": 9999999999,
    }) + "\n")

    actions = mod.retry_queue({"actions": {}, "target_actions": {}}, dispatch=True, cooldown=0)

    assert role_calls == [(sid, "ready_for_planner")]
    assert actions[0]["dispatched_from_queue"] is True
    assert actions[0]["role_pool_dispatch"]["role"] == "planner"
    assert mod.load_queue() == []


def test_ready_for_planner_queue_drops_when_planner_outputs_already_exist(tmp_path, monkeypatch) -> None:
    sid = "sprint-planner-complete"
    monkeypatch.setattr(mod, "QUEUE", tmp_path / "autopilot-queue.jsonl")
    monkeypatch.setattr(mod, "SPRINTS", tmp_path / "sprints")
    events: list[tuple[str, str]] = []
    monkeypatch.setattr(
        mod,
        "append_event",
        lambda event_sid, event, *_args, **_kwargs: events.append((event_sid, event)),
    )
    monkeypatch.setattr(
        mod,
        "dispatch_role_handoff",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("stale planner handoff must not dispatch")),
    )
    mod.SPRINTS.mkdir(parents=True)
    (mod.SPRINTS / f"{sid}.status.json").write_text(
        json.dumps({
            "sprint_id": sid,
            "status": "active",
            "phase": "planning_complete",
            "handoff_to": "builder_main",
        }) + "\n",
        encoding="utf-8",
    )
    (mod.SPRINTS / f"{sid}.design.md").write_text("# Design\n", encoding="utf-8")
    (mod.SPRINTS / f"{sid}.plan.md").write_text("# Plan\n", encoding="utf-8")
    (mod.SPRINTS / f"{sid}.task_graph.json").write_text(
        json.dumps({"sprint_id": sid, "nodes": []}) + "\n",
        encoding="utf-8",
    )
    mod.QUEUE.write_text(
        json.dumps({
            "sid": sid,
            "type": "ready_for_planner",
            "target": "solar-harness:0.1",
            "created_at_epoch": time.time(),
        }) + "\n",
        encoding="utf-8",
    )

    actions = mod.retry_queue({"actions": {}, "target_actions": {}}, dispatch=True, cooldown=0)

    assert actions == [{
        "sid": sid,
        "action": "ready_for_planner",
        "dropped": "stale_planner_handoff",
        "target": "solar-harness:0.1",
        "status": "active",
        "phase": "planning_complete",
    }]
    assert events == [(sid, "autopilot_queue_drop_stale_planner_handoff")]
    assert mod.load_queue() == []


def test_ready_for_planner_finding_bypasses_fixed_pane_busy(monkeypatch) -> None:
    sid = "sprint-planner-demo"
    finding = {
        "sid": sid,
        "type": "ready_for_planner",
        "target": "solar-harness:0.1",
        "message": "planner dispatch",
        "severity": "info",
    }
    state: dict = {"actions": {}, "target_actions": {}}
    monkeypatch.setattr(mod, "should_act", lambda state, f, cooldown: True)
    monkeypatch.setattr(mod, "target_recently_dispatched", lambda state, target, cooldown: False)
    monkeypatch.setattr(mod, "pane_gate", lambda target, sid: (True, "ok", {}))
    monkeypatch.setattr(mod, "pane_is_busy", lambda target: True)
    monkeypatch.setattr(mod, "clear_current_prompt", lambda target: None)
    monkeypatch.setattr(mod, "save_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "load_json", lambda path: {
        "sprint_id": sid,
        "status": "drafting",
        "phase": "prd_ready",
        "handoff_to": "planner",
    })
    monkeypatch.setattr(mod, "mark_action", lambda *args, **kwargs: None)
    role_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(mod, "dispatch_role_handoff", lambda s, t: role_calls.append((s, t)) or (True, {"role": "planner"}))
    monkeypatch.setattr(mod, "wake_sid", lambda s: False)

    actions = mod.apply_findings([finding], dispatch=True, state=state, cooldown=0)

    assert role_calls == [(sid, "ready_for_planner")]
    assert actions[0]["dispatched"] is True
    assert actions[0]["role_pool_dispatch"]["role"] == "planner"


def test_codex_runtime_disables_role_pool_handoff_by_default(monkeypatch) -> None:
    monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
    monkeypatch.delenv("SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH", raising=False)

    assert mod.finding_uses_operator_role_pool("ready_for_planner") is False

    monkeypatch.setenv("SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH", "1")
    assert mod.finding_uses_operator_role_pool("ready_for_planner") is True


def test_codex_runtime_ready_for_planner_uses_wake_not_role_pool(monkeypatch) -> None:
    sid = "sprint-codex-planner"
    finding = {
        "sid": sid,
        "type": "ready_for_planner",
        "target": "solar-harness:0.1",
        "message": "planner dispatch",
        "severity": "info",
    }
    state: dict = {"actions": {}, "target_actions": {}}
    monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
    monkeypatch.delenv("SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH", raising=False)
    monkeypatch.setattr(mod, "should_act", lambda state, f, cooldown: True)
    monkeypatch.setattr(mod, "target_recently_dispatched", lambda state, target, cooldown: False)
    monkeypatch.setattr(mod, "pane_gate", lambda target, sid: (True, "ok", {}))
    monkeypatch.setattr(mod, "pane_is_busy", lambda target: False)
    monkeypatch.setattr(mod, "clear_current_prompt", lambda target: None)
    monkeypatch.setattr(mod, "save_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "load_json", lambda path: {
        "sprint_id": sid,
        "status": "drafting",
        "phase": "prd_ready",
        "handoff_to": "planner",
    })
    monkeypatch.setattr(mod, "mark_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mod,
        "dispatch_role_handoff",
        lambda s, t: (_ for _ in ()).throw(AssertionError("role pool should be skipped")),
    )
    wake_calls: list[str] = []
    monkeypatch.setattr(mod, "wake_sid", lambda s: wake_calls.append(s) or True)

    actions = mod.apply_findings([finding], dispatch=True, state=state, cooldown=0)

    assert wake_calls == [sid]
    assert actions[0]["dispatched"] is True
    assert "role_pool_dispatch" not in actions[0]


def test_wake_sid_uses_current_harness_command(tmp_path, monkeypatch) -> None:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    harness_cmd = harness_dir / "solar-harness.sh"
    harness_cmd.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setattr(mod, "HARNESS", harness_dir)
    monkeypatch.setattr(mod, "SESSION", "solar-codex-test")
    monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
    calls = []

    class Proc:
        returncode = 0

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return Proc()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    assert mod.wake_sid("sprint-local-harness") is True

    assert calls
    cmd, kwargs = calls[0]
    assert cmd == ["bash", str(harness_cmd), "wake", "sprint-local-harness"]
    assert str(mod.HOME / ".solar" / "bin" / "solar-harness") not in cmd
    assert kwargs["env"]["HARNESS_DIR"] == str(harness_dir)
    assert kwargs["env"]["SOLAR_HARNESS_DIR"] == str(harness_dir)
    assert kwargs["env"]["SOLAR_HARNESS_SESSION"] == "solar-codex-test"
    assert kwargs["env"]["SOLAR_PANE_RUNTIME"] == "codex"


def test_role_pool_handoffs_do_not_share_fixed_target_cooldown(monkeypatch) -> None:
    findings = [
        {"sid": "sprint-a", "type": "ready_for_planner", "target": "solar-harness:0.1", "message": "a"},
        {"sid": "sprint-b", "type": "ready_for_planner", "target": "solar-harness:0.1", "message": "b"},
    ]
    state: dict = {"actions": {}, "target_actions": {}}
    monkeypatch.setattr(mod, "should_act", lambda state, f, cooldown: True)
    monkeypatch.setattr(mod, "target_recently_dispatched", lambda state, target, cooldown: True)
    monkeypatch.setattr(mod, "pane_gate", lambda target, sid: (False, "pane_leased", {}))
    monkeypatch.setattr(mod, "pane_is_busy", lambda target: True)
    monkeypatch.setattr(mod, "clear_current_prompt", lambda target: None)
    monkeypatch.setattr(mod, "save_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "load_json", lambda path: {
        "sprint_id": "x",
        "status": "drafting",
        "phase": "prd_ready",
        "handoff_to": "planner",
    })
    monkeypatch.setattr(mod, "mark_action", lambda *args, **kwargs: None)
    role_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(mod, "dispatch_role_handoff", lambda s, t: role_calls.append((s, t)) or (True, {"role": "planner"}))

    actions = mod.apply_findings(findings, dispatch=True, state=state, cooldown=300)

    assert role_calls == [
        ("sprint-a", "ready_for_planner"),
        ("sprint-b", "ready_for_planner"),
    ]
    assert [item["dispatched"] for item in actions] == [True, True]


def test_ready_for_planner_role_pool_failure_queues_without_wake(monkeypatch) -> None:
    sid = "sprint-planner-no-capacity"
    finding = {
        "sid": sid,
        "type": "ready_for_planner",
        "target": "solar-harness:0.1",
        "message": "planner dispatch",
        "severity": "info",
    }
    state: dict = {"actions": {}, "target_actions": {}}
    queued: list[tuple[dict, str, dict]] = []
    monkeypatch.setattr(mod, "should_act", lambda state, f, cooldown: True)
    monkeypatch.setattr(mod, "target_recently_dispatched", lambda state, target, cooldown: False)
    monkeypatch.setattr(mod, "pane_gate", lambda target, sid: (False, "pane_leased", {}))
    monkeypatch.setattr(mod, "pane_is_busy", lambda target: True)
    monkeypatch.setattr(mod, "clear_current_prompt", lambda target: None)
    saved_statuses: list[dict] = []
    monkeypatch.setattr(
        mod,
        "save_json",
        lambda path, payload: saved_statuses.append(json.loads(json.dumps(payload))),
    )
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "load_json", lambda path: {
        "sprint_id": sid,
        "status": "drafting",
        "phase": "prd_ready",
        "handoff_to": "planner",
        "planner_dispatch_claim": {
            "owner": "operator_pool",
            "state": "pending",
            "claimed_at": _utc_after(-1),
            "expires_at": _utc_after(120),
        },
    })
    monkeypatch.setattr(mod, "enqueue_action", lambda f, reason, detail=None: queued.append((f, reason, detail or {})))
    monkeypatch.setattr(
        mod,
        "dispatch_role_handoff",
        lambda s, t: (
            False,
            {
                "role": "planner",
                "returncode": 1,
                "stderr": "ERROR: no_dispatchable_operator_for_role: planner; provider unavailable",
            },
        ),
    )
    wake_calls: list[str] = []
    monkeypatch.setattr(mod, "wake_sid", lambda s: wake_calls.append(s) or True)

    actions = mod.apply_findings([finding], dispatch=True, state=state, cooldown=0)

    assert wake_calls == []
    assert queued[0][1] == "role_pool_unavailable"
    assert actions[0]["queued"] is True
    assert actions[0]["reason"] == "role_pool_unavailable"
    assert saved_statuses[-1]["planner_dispatch_claim"]["state"] == "failed"
    assert saved_statuses[-1]["planner_dispatch_claim"]["released_at"]
    assert saved_statuses[-1]["planner_dispatch_claim"]["failure_reason"] == (
        "no_dispatchable_operator_for_role: planner"
    )
    assert saved_statuses[-1]["planner_dispatch_claim"]["returncode"] == 1


def test_ready_for_planner_role_pool_success_marks_claim_submitted(monkeypatch) -> None:
    sid = "sprint-planner-claimed"
    finding = {
        "sid": sid,
        "type": "ready_for_planner",
        "target": "solar-harness:0.1",
        "message": "planner dispatch",
        "severity": "info",
    }
    state: dict = {"actions": {}, "target_actions": {}}
    saved_statuses: list[dict] = []
    monkeypatch.setattr(mod, "should_act", lambda state, f, cooldown: True)
    monkeypatch.setattr(mod, "target_recently_dispatched", lambda state, target, cooldown: False)
    monkeypatch.setattr(mod, "save_json", lambda path, payload: saved_statuses.append(json.loads(json.dumps(payload))))
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "load_json", lambda path: {
        "sprint_id": sid,
        "status": "drafting",
        "phase": "prd_ready",
        "handoff_to": "planner",
        "planner_dispatch_claim": {
            "owner": "operator_pool",
            "state": "pending",
            "claimed_at": _utc_after(-1),
            "expires_at": _utc_after(120),
        },
    })
    monkeypatch.setattr(mod, "mark_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "_live_pm_task_for_sprint_role", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mod,
        "dispatch_role_handoff",
        lambda s, t: (True, {"role": "planner", "task_id": "pm-sprint-planner-claimed-N0-abc123"}),
    )

    actions = mod.apply_findings([finding], dispatch=True, state=state, cooldown=0)

    assert actions[0]["dispatched"] is True
    assert saved_statuses[-1]["planner_dispatch_claim"]["state"] == "submitted"
    assert saved_statuses[-1]["planner_dispatch_claim"]["task_id"] == "pm-sprint-planner-claimed-N0-abc123"
