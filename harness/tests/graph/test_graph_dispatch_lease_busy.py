"""Regression tests for graph dispatcher lease busy classification."""

from __future__ import annotations

import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

import graph_node_dispatcher as gnd  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _disable_operator_pool_for_pane_discovery_tests(monkeypatch) -> None:
    monkeypatch.setenv("SOLAR_GRAPH_BUILDER_OPERATOR_POOL", "0")


def _ts(delta_seconds: int) -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delta_seconds)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_expired_lease_does_not_make_pane_busy(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "read_lease", lambda pane: {"expires_at": _ts(-60)})
    assert gnd._pane_has_active_lease("solar-harness-lab:0.0") is False


def test_active_lease_makes_pane_busy(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "read_lease", lambda pane: {"expires_at": _ts(60)})
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane: "")
    assert gnd._pane_has_active_lease("solar-harness-lab:0.0") is True


def test_idle_api_timeout_releases_active_lease(monkeypatch) -> None:
    released: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        gnd,
        "read_lease",
        lambda pane: {"expires_at": _ts(60), "dispatch_id": "eval-123"},
    )
    monkeypatch.setattr(
        gnd,
        "_pane_tail",
        lambda pane: "⎿ \u00a0API Error: Request timed out. Check your internet connection and proxy settings\n\n❯\u00a0\n",
    )
    monkeypatch.setattr(
        gnd,
        "release_lease",
        lambda pane, dispatch_id, reason: released.append((pane, dispatch_id, reason)) or {"released": True},
    )

    assert gnd._pane_has_active_lease("solar-harness:0.3") is False
    assert released == [
        ("solar-harness:0.3", "eval-123", "active_lease_released_after_idle_api_timeout")
    ]


def test_default_claude_try_prompt_is_not_prompt_residue() -> None:
    tail = '────────────────\n❯\u00a0Try "how do I log an error?"\n────────────────\n'
    assert gnd.PANE_PROMPT_RESIDUE_RE.search(tail) is None


def test_non_default_prompt_text_is_prompt_residue() -> None:
    tail = "────────────────\n❯\u00a0继续执行下一个 dispatch 文件\n────────────────\n"
    assert gnd.PANE_PROMPT_RESIDUE_RE.search(tail)


def test_worker_discovery_ignores_expired_lease(monkeypatch) -> None:
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *a, **kw: b"solar-harness-lab:0.0\tbuilder-glm\n",
    )
    monkeypatch.setattr(gnd, "read_lease", lambda pane: {"expires_at": _ts(-60)})
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})

    workers = gnd._discover_workers(dry_run=False)

    assert len(workers) == 1
    assert workers[0]["pane"] == "solar-harness-lab:0.0"
    assert workers[0]["busy"] is False


def test_worker_discovery_supports_pandoc_render_nodes(monkeypatch) -> None:
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *a, **kw: b"solar-harness-lab:0.0\tbuilder-glm\n",
    )
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})

    workers = gnd._discover_workers(dry_run=False)

    assert "pandoc" in workers[0]["skills"]


def test_worker_discovery_supports_s05_release_skill_aliases(monkeypatch) -> None:
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *a, **kw: b"solar-harness-lab:0.0\tbuilder-glm\n",
    )
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda pane: "")

    workers = gnd._discover_workers(dry_run=False)

    for skill in [
        "ui",
        "security",
        "grep",
        "http",
        "curl",
        "deepresearch",
        "cli",
        "claude-cli",
        "survey",
        "fixture",
        "release",
        "evidence",
        "autopilot",
        "epic",
    ]:
        assert skill in workers[0]["skills"]


def test_worker_discovery_marks_shell_prompt_residue_as_runtime_not_running(monkeypatch) -> None:
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *a, **kw: b"solar-harness-lab:0.3\tBuilder 4 | \xe7\x8a\xb6\xe6\x80\x81:idle/no active sprint\n",
    )
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "bash")
    monkeypatch.setattr(
        gnd,
        "_pane_tail",
        lambda pane, lines=80: "✻ Baked for 4m 16s\n❯\u00a0继续执行下一个 dispatch 文件\n",
    )
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})

    workers = gnd._discover_workers(dry_run=False)

    assert len(workers) == 1
    assert workers[0]["busy"] is True
    assert workers[0]["unavailable_reason"] == "worker_runtime_not_running"


def test_codex_shell_process_is_runtime_not_running(monkeypatch) -> None:
    monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "bash")
    monkeypatch.setattr(gnd, "_pane_has_codex_process", lambda pane: False)

    assert (
        gnd._pane_runtime_unavailable_reason(
            "solar-harness:0.2",
            "Builder 主建设者 | 模型:codex",
        )
        == "codex_runtime_not_running"
    )


def test_codex_shell_with_child_process_is_available(monkeypatch) -> None:
    monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "bash")
    monkeypatch.setattr(gnd, "_pane_has_codex_process", lambda pane: True)

    assert (
        gnd._pane_runtime_unavailable_reason(
            "solar-harness:0.2",
            "Builder 主建设者 | 模型:codex",
        )
        == ""
    )


def test_codex_dispatch_window_refuses_shell_before_clear(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
    instruction = tmp_path / "node.dispatch.md"
    instruction.write_text("smoke", encoding="utf-8")
    clear_attempts: list[str] = []

    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "bash")
    monkeypatch.setattr(gnd, "_pane_has_codex_process", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_title", lambda pane: "Builder 主建设者 | 模型:codex")
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: "solar-codex-runtime-integration ❯\n")
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: clear_attempts.append(pane) or False)

    ready, reason = gnd._wait_for_dispatch_window("solar-harness:0.2", instruction, attempts=1)

    assert ready is False
    assert reason == "codex_runtime_not_running"
    assert clear_attempts == []


def test_worker_discovery_marks_codex_shell_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("SOLAR_PANE_RUNTIME", "codex")
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *a, **kw: "solar-harness:0.2\tBuilder 主建设者 | 模型:codex\n".encode(),
    )
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "bash")
    monkeypatch.setattr(gnd, "_pane_has_codex_process", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: "solar-codex-runtime-integration ❯\n")
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})

    workers = gnd._discover_workers(dry_run=False)

    assert len(workers) == 1
    assert workers[0]["busy"] is True
    assert workers[0]["unavailable_reason"] == "codex_runtime_not_running"


def test_completed_output_with_empty_prompt_is_not_busy(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "claude")
    monkeypatch.setattr(
        gnd,
        "_pane_tail",
        lambda pane, lines=80: """
⏺ N4 通过 — parent sprint 现在为 ready: true
  ⎿  tests passed

────────────────────────────────────────
❯\u00a0
────────────────────────────────────────
  ⏵⏵ accept edits on (shift+tab to cycle)
""",
    )
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: False)

    assert gnd._pane_tui_busy("solar-harness-lab:0.0") is False


def test_live_thinking_output_with_empty_prompt_is_busy(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "claude")
    monkeypatch.setattr(
        gnd,
        "_pane_tail",
        lambda pane, lines=80: """
⏺ Reading files

✶ Twisting… (1m 52s · thought for 4s)

────────────────────────────────────────
❯\u00a0
────────────────────────────────────────
  ⏵⏵ accept edits on (shift+tab to cycle)
""",
    )
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: False)

    assert gnd._pane_tui_busy("solar-harness-lab:0.0") is True


def test_stale_processing_scrollback_under_shell_is_not_busy(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "bash")
    monkeypatch.setattr(
        gnd,
        "_pane_tail",
        lambda pane, lines=80: """
✻ Waddling… (2m 15s · ↓ 8.8k tokens)
effect=N/A; 读取并执行 /tmp/dispatch.md

────────────────────────────────────────
❯\u00a0
────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
""",
    )
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: False)

    assert gnd._pane_tui_busy("solar-harness-lab:0.0") is False


def test_worker_blocked_submit_ack_on_busy_pane_without_live_lease_requeues(monkeypatch, tmp_path) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    ack_dir = sprints / "graph-acks"
    ack_dir.mkdir(parents=True)
    sid = "sprint-test"
    node_id = "N1"
    pane = "solar-harness-lab:0.0"
    dispatch_id = "dispatch-123"
    dispatch_file = sprints / f"{sid}.{node_id}-dispatch.md"
    dispatch_file.write_text("# dispatch\n", encoding="utf-8")
    (ack_dir / f"{sid}.{node_id}-submit-ack.json").write_text(
        '{"dispatch_id":"dispatch-123"}',
        encoding="utf-8",
    )
    graph = {
        "sprint_id": sid,
        "nodes": [
            {
                "id": node_id,
                "status": "worker_blocked",
                "dispatch_retry_reason": "accept_edits_footer",
            }
        ],
        "node_results": {},
    }
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "_ledger_dispatch_for", lambda *_: {"pane": pane, "dispatch_id": dispatch_id})
    monkeypatch.setattr(gnd, "_pane_title", lambda pane: "Builder | 模型:GLM")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: True)

    repaired = gnd._reconcile_existing_dispatches(graph, sprints / f"{sid}.task_graph.json")

    assert repaired == [
        {
            "node": node_id,
            "pane": pane,
            "dispatch_id": dispatch_id,
            "status": "pending",
            "reason": "stale_submit_ack_without_live_lease",
        }
    ]
    assert graph["nodes"][0]["status"] == "pending"
    assert "assigned_to" not in graph["nodes"][0]
    assert "dispatch_id" not in graph["nodes"][0]
    assert graph["nodes"][0]["dispatch_retry_reason"] == "stale_submit_ack_without_live_lease"


def test_acknowledged_dispatch_idle_pane_requeues_after_grace(monkeypatch, tmp_path) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    ack_dir = sprints / "graph-acks"
    ack_dir.mkdir(parents=True)
    sid = "sprint-test"
    node_id = "N1"
    pane = "solar-harness-lab:0.0"
    dispatch_id = "dispatch-123"
    (ack_dir / f"{sid}.{node_id}-submit-ack.json").write_text(
        '{"dispatch_id":"dispatch-123","submitted_at":"2026-01-01T00:00:00Z"}',
        encoding="utf-8",
    )
    graph = {
        "sprint_id": sid,
        "nodes": [
            {
                "id": node_id,
                "status": "dispatched",
                "assigned_to": pane,
                "dispatch_id": dispatch_id,
            }
        ],
        "node_results": {node_id: {"status": "dispatched"}},
    }
    released: list[tuple[str, str, str]] = []
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "read_lease", lambda pane: {"dispatch_id": dispatch_id, "expires_at": _ts(600)})
    monkeypatch.setattr(gnd, "release_lease", lambda *args: released.append(args))
    monkeypatch.setattr(gnd, "_pane_title", lambda pane: "Builder | 模型:GLM")
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: "❯\u00a0\n")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: False)

    repaired = gnd._reconcile_existing_dispatches(graph, sprints / f"{sid}.task_graph.json")

    assert repaired[0]["status"] == "pending"
    assert repaired[0]["reason"] == "submit_ack_idle_no_worker_activity"
    assert graph["nodes"][0]["status"] == "pending"
    assert "assigned_to" not in graph["nodes"][0]
    assert released == [(pane, dispatch_id, "graph_dispatch_reconcile_ack_idle_no_worker_activity")]


def test_worker_discovery_marks_claude_monthly_limit_as_anthropic_quota(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "SESSION", "solar-harness")
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *a, **kw: b"solar-harness-lab:0.3\tBuilder | \xe6\xa8\xa1\xe5\x9e\x8b:Opus | \xe7\x8a\xb6\xe6\x80\x81:idle/no active sprint\n",
    )
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "bash")
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(
        gnd,
        "_pane_tail",
        lambda pane, lines=80: "You've hit your org's monthly usage limit\n/login to switch to an API usage-billed account.\n❯\n",
    )

    workers = gnd._discover_workers(dry_run=False)

    assert len(workers) == 1
    assert "anthropic" in workers[0]["quota_exhausted"]
    assert "claude" in workers[0]["quota_exhausted"]
    assert "opus" in workers[0]["quota_exhausted"]
    assert workers[0]["busy"] is True
    assert workers[0]["unavailable_reason"] == "rate_limit_or_api_error"


def test_worker_discovery_marks_edit_confirmation_as_busy(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "SESSION", "solar-harness")
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *a, **kw: b"solar-harness-lab:0.2\tBuilder | \xe6\xa8\xa1\xe5\x9e\x8b:GLM | \xe7\x8a\xb6\xe6\x80\x81:idle/no active sprint\n",
    )
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "claude")
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(
        gnd,
        "_pane_tail",
        lambda pane, lines=80: "Do you want to make this edit to /tmp/example.py?\n❯\n",
    )

    workers = gnd._discover_workers(dry_run=False)

    assert len(workers) == 1
    assert workers[0]["busy"] is True


def test_assigned_pane_quota_detection_handles_wrapped_monthly_limit(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "_pane_title", lambda pane: "Builder 4 | 模型:Sonnet")
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "claude")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda pane: "")
    monkeypatch.setattr(
        gnd,
        "_pane_tail",
        lambda pane, lines=80: "⎿  You've hit your org's monthly\n     usage limit\n/login to switch to an API\n",
    )

    assert gnd._assigned_pane_unavailable_reason("solar-harness-lab:0.3") == "rate_limit_or_api_error"


def test_reconcile_keeps_acknowledged_dispatch_when_leases_disabled(monkeypatch, tmp_path) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    ack_dir = sprints / "graph-acks"
    ack_dir.mkdir(parents=True)
    sid = "sprint-test"
    node_id = "N1"
    dispatch_id = "dispatch-123"
    pane = "solar-harness-lab:0.0"
    (ack_dir / f"{sid}.{node_id}-submit-ack.json").write_text(
        '{"dispatch_id":"dispatch-123"}',
        encoding="utf-8",
    )
    graph = {
        "sprint_id": sid,
        "nodes": [
            {
                "id": node_id,
                "status": "dispatched",
                "assigned_to": pane,
                "dispatch_id": dispatch_id,
            }
        ],
        "node_results": {
            node_id: {
                "status": "dispatched",
                "assigned_to": pane,
                "dispatch_id": dispatch_id,
                "updated_at": "2026-05-27T00:00:00Z",
            }
        },
    }
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "release_lease", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not release")))
    monkeypatch.setattr(gnd, "_pane_title", lambda pane: "Builder | 模型:GLM")
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: "❯\n  ⏵⏵ bypass permissions on")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")

    repaired = gnd._reconcile_existing_dispatches(graph, tmp_path / f"{sid}.task_graph.json")

    assert repaired == []
    assert graph["nodes"][0]["status"] == "dispatched"
    assert graph["nodes"][0]["dispatch_id"] == dispatch_id
    assert graph["node_results"][node_id]["status"] == "dispatched"


def test_reconcile_keeps_acknowledged_dispatch_on_recoverable_prompt(monkeypatch, tmp_path) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    ack_dir = sprints / "graph-acks"
    ack_dir.mkdir(parents=True)
    sid = "sprint-test"
    node_id = "N1"
    dispatch_id = "dispatch-123"
    pane = "solar-harness-lab:0.0"
    (ack_dir / f"{sid}.{node_id}-submit-ack.json").write_text(
        '{"dispatch_id":"dispatch-123"}',
        encoding="utf-8",
    )
    graph = {
        "sprint_id": sid,
        "nodes": [
            {
                "id": node_id,
                "status": "dispatched",
                "assigned_to": pane,
                "dispatch_id": dispatch_id,
            }
        ],
        "node_results": {
            node_id: {
                "status": "dispatched",
                "assigned_to": pane,
                "dispatch_id": dispatch_id,
                "updated_at": "2026-05-27T00:00:00Z",
            }
        },
    }
    dismissed: list[tuple[str, str]] = []
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "release_lease", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not release")))
    monkeypatch.setattr(gnd, "_pane_title", lambda pane: "Builder | 模型:GLM")
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: "Do you want to proceed?\n❯ 1. Yes\n2. No")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "proceed_confirmation_prompt")
    monkeypatch.setattr(gnd, "_dismiss_dispatch_prompt", lambda pane, reason: dismissed.append((pane, reason)) or True)

    repaired = gnd._reconcile_existing_dispatches(graph, tmp_path / f"{sid}.task_graph.json")

    assert repaired[0]["reason"] == "recoverable_prompt_kept_active:proceed_confirmation_prompt"
    assert dismissed == [(pane, "proceed_confirmation_prompt")]
    assert graph["nodes"][0]["status"] == "dispatched"
    assert graph["nodes"][0]["dispatch_id"] == dispatch_id


def test_reconcile_recoverable_pane_blocker_requeues_pending(monkeypatch, tmp_path) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    ack_dir = sprints / "graph-acks"
    ack_dir.mkdir(parents=True)
    sid = "sprint-test"
    node_id = "N1"
    dispatch_id = "dispatch-123"
    pane = "solar-harness-lab:0.0"
    (ack_dir / f"{sid}.{node_id}-submit-ack.json").write_text(
        '{"dispatch_id":"dispatch-123"}',
        encoding="utf-8",
    )
    graph = {
        "sprint_id": sid,
        "nodes": [
            {
                "id": node_id,
                "status": "dispatched",
                "assigned_to": pane,
                "dispatch_id": dispatch_id,
            }
        ],
        "node_results": {
            node_id: {
                "status": "dispatched",
                "assigned_to": pane,
                "dispatch_id": dispatch_id,
            }
        },
    }
    released: list[tuple[str, str, str]] = []
    ledger: list[tuple[str, str, str, str, dict]] = []
    monkeypatch.setattr(gnd, "HARNESS_DIR", harness)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "read_lease", lambda pane: {"dispatch_id": dispatch_id, "expires_at": _ts(600)})
    monkeypatch.setattr(gnd, "release_lease", lambda *args: released.append(args))
    monkeypatch.setattr(gnd, "_pane_title", lambda pane: "Builder | 模型:GLM")
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: "Press up to edit queued messages\n❯ 读取并执行 x")
    monkeypatch.setattr(gnd, "_pane_dispatch_prompt_reason", lambda tail: "")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "queued_prompt_residue")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: False)
    monkeypatch.setattr(gnd, "_append_dispatch_ledger", lambda *args: ledger.append(args))

    repaired = gnd._reconcile_existing_dispatches(graph, sprints / f"{sid}.task_graph.json")

    assert repaired == [
        {
            "node": node_id,
            "pane": pane,
            "dispatch_id": dispatch_id,
            "status": "pending",
            "reason": "queued_prompt_residue",
        }
    ]
    assert graph["nodes"][0]["status"] == "pending"
    assert "assigned_to" not in graph["nodes"][0]
    assert "dispatch_id" not in graph["nodes"][0]
    assert node_id not in graph["node_results"]
    assert released == [(pane, dispatch_id, "graph_dispatch_reconcile_recoverable_prompt_failed:queued_prompt_residue")]
    assert ledger[0][0] == "dispatch_reassigned_after_recover_failed"


def test_assigned_recoverable_pane_unavailable_does_not_cooldown(monkeypatch) -> None:
    marked: list[tuple[str, str, str, bool]] = []
    retryable: list[tuple[str, str]] = []

    item = {
        "sprint_id": "sprint-test",
        "intent": "graph_node|node_id=N1",
        "priority": 80,
        "payload": {
            "sprint_id": "sprint-test",
            "graph": "/tmp/sprint-test.task_graph.json",
            "dispatch_id": "dispatch-N1",
            "node": {"id": "N1"},
            "assignment": {"pane": "solar-harness-lab:0.3"},
        },
    }

    monkeypatch.setattr(gnd, "_graph_node_runtime_state", lambda graph_path, node_id: {"status": "pending"})
    monkeypatch.setattr(gnd, "_pane_exists", lambda pane: True)
    monkeypatch.setattr(gnd, "_assigned_pane_unavailable_reason", lambda pane: "queued_prompt_residue")
    monkeypatch.setattr(gnd, "_mark_pane_recover_cooldown", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not cooldown")))
    monkeypatch.setattr(gnd, "_mark_pane_recover_retryable", lambda pane, reason, **kw: retryable.append((pane, reason)))
    monkeypatch.setattr(
        gnd,
        "_mark_graph_node",
        lambda graph_path, node_id, status, clear_assignment=False: marked.append(
            (graph_path, node_id, status, clear_assignment)
        ),
    )
    monkeypatch.setattr(
        gnd,
        "_ensure_lease",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("lease should not be acquired")),
    )

    result = gnd.dispatch_queue_item(item, dry_run=False)

    assert result["ok"] is True
    assert result["reason"] == "assigned_pane_unavailable_retry_later"
    assert result["unavailable_reason"] == "queued_prompt_residue"
    assert marked == [("/tmp/sprint-test.task_graph.json", "N1", "pending", True)]
    assert retryable == [("solar-harness-lab:0.3", "assigned_pane_unavailable:queued_prompt_residue")]


def test_dispatch_queue_item_dry_run_does_not_reset_busy_active_node(monkeypatch, tmp_path) -> None:
    sid = "sprint-test"
    node_id = "N1"
    dispatch_id = "dispatch-123"
    pane = "solar-harness-lab:0.0"
    graph_path = tmp_path / f"{sid}.task_graph.json"
    graph = {
        "sprint_id": sid,
        "nodes": [
            {
                "id": node_id,
                "status": "dispatched",
                "assigned_to": pane,
                "dispatch_id": dispatch_id,
            }
        ],
        "node_results": {
            node_id: {
                "status": "dispatched",
                "assigned_to": pane,
                "dispatch_id": dispatch_id,
                "updated_at": "2026-05-27T00:00:00Z",
            }
        },
    }
    graph_path.write_text(__import__("json").dumps(graph), encoding="utf-8")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: True)
    monkeypatch.setattr(gnd, "_pane_has_matching_queued_prompt", lambda pane, instruction_file: False)

    result = gnd.dispatch_queue_item(
        {
            "sprint_id": sid,
            "intent": f"graph_node|node_id={node_id}|pane={pane}",
            "priority": 80,
            "payload": {
                "sprint_id": sid,
                "graph": str(graph_path),
                "node": {"id": node_id},
                "assignment": {"pane": pane},
                "dispatch_id": dispatch_id,
            },
        },
        dry_run=True,
    )

    after = __import__("json").loads(graph_path.read_text(encoding="utf-8"))
    assert result["dry_run"] is True
    assert after["nodes"][0]["status"] == "dispatched"
    assert after["nodes"][0]["dispatch_id"] == dispatch_id
    assert after["node_results"][node_id]["status"] == "dispatched"


def test_stale_first_run_confirmation_before_idle_prompt_is_not_busy(monkeypatch) -> None:
    tail = """
 Quick safety check: Is this a project you created or one you trust?

 ❯ 1. Yes, I trust this folder ✔
   2. No, exit

 Enter to confirm · Esc to cancel
 ▐▛███▜▌   Claude Code v2.1.119

───────────────────────────────────────
❯ Try "write a test for <filepath>"
───────────────────────────────────────
  ⏵⏵ bypass permissions on
"""
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: tail)
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})

    assert gnd._pane_dispatch_prompt_reason(tail) == ""
    assert gnd._pane_tui_busy("solar-harness:0.3") is False


def test_plan_mode_footer_is_recoverable_dispatch_prompt() -> None:
    tail = """
────────────────────────────────────────
  ⏸ plan mode on (shift+tab to cycle)…
  93031 tokens
"""
    assert gnd._pane_dispatch_prompt_reason(tail) == "plan_mode_blocked"


def test_stale_queued_prompt_scrollback_followed_by_idle_prompt_is_not_blocking() -> None:
    tail = """
────────────────────────────────────────
❯ Press up to edit queued messages
────────────────────────────────────────
  ⏵⏵ bypass permissions on

✶ Sprouting… (0s)

────────────────────────────────────────
❯
────────────────────────────────────────
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""
    assert gnd._pane_dispatch_prompt_reason(tail) == ""


def test_unavailable_reason_auto_dismisses_plan_mode(monkeypatch) -> None:
    tails = [
        "────────────────────────────────────────\n  ⏸ plan mode on (shift+tab to cycle)\n  80346 tokens\n",
        "────────────────────────────────────────\n❯\n────────────────────────────────────────\n  ⏵⏵ bypass permissions on (shift+tab to cycle)\n",
    ]
    fallback = tails[-1]
    sent: list[list[str]] = []

    def fake_run(args, **kwargs):
        sent.append(list(args))

        class Result:
            returncode = 0
            stdout = ""

        return Result()

    monkeypatch.setattr(gnd.subprocess, "run", fake_run)
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: tails.pop(0) if tails else fallback)
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(gnd.time, "sleep", lambda seconds: None)

    assert gnd._pane_unavailable_reason("solar-harness-lab:0.3") == ""
    assert any("BTab" in cmd for cmd in sent)


def test_dismiss_plan_mode_cycles_shift_tab(monkeypatch) -> None:
    tails = [
        "────────────────\n  ⏸ plan mode on (shift+tab to cycle)…\n",
        "────────────────\n❯\u00a0\n────────────────\n",
    ]
    sent: list[list[str]] = []

    def fake_run(args, **kwargs):
        sent.append(list(args))

        class Result:
            stdout = ""

        return Result()

    monkeypatch.setattr(gnd.subprocess, "run", fake_run)
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: tails.pop(0) if tails else tails[-1])
    monkeypatch.setattr(gnd.time, "sleep", lambda seconds: None)

    assert gnd._dismiss_dispatch_prompt("solar-harness-lab:0.3", "plan_mode_blocked") is True
    assert sent and "BTab" in sent[0]


def test_assigned_multi_task_shell_is_not_direct_worker(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "_pane_title", lambda pane: "MT builder | 状态:running | 能力:能力:N/A")
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "zsh")
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: "zsh% ")

    assert (
        gnd._assigned_pane_unavailable_reason("solar-harness-multi-task:0.0")
        == "multi_task_shell_not_direct_worker"
    )


def test_stale_working_title_does_not_block_clean_idle_pane(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "_pane_hygiene_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane: "────────────────\n● 0 tokens\n❯\u00a0\n")

    reason = gnd._pane_title_active_unavailable_reason(
        "solar-harness-lab:0.3",
        "Builder 4 | 状态:working/pane_permissions_prompt_blocked:sprint-old",
    )

    assert reason == ""


def test_working_title_still_blocks_when_live_lease_exists(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "_pane_hygiene_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "read_lease", lambda pane: {"expires_at": _ts(60)})
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane: "────────────────\n● 0 tokens\n❯\u00a0\n")

    reason = gnd._pane_title_active_unavailable_reason(
        "solar-harness-lab:0.3",
        "Builder 4 | 状态:working/active:sprint-live",
    )

    assert reason == "pane_title_active_work"


def test_assigned_pane_recheck_ignores_own_stale_working_title_when_idle(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "_pane_hygiene_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "read_lease", lambda pane: {"expires_at": _ts(60)})
    monkeypatch.setattr(gnd, "_pane_title", lambda pane: "Builder 4 | 状态:working/graph_node_idle_assigned:sprint-old")
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(gnd, "_models_for_pane", lambda pane, title: ["claude-sonnet"])
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane: "────────────────\n● 0 tokens\n❯\u00a0\n")
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_multi_task_direct_dispatch_unavailable_reason", lambda pane, current_command=None: "")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")

    assert gnd._assigned_pane_unavailable_reason("solar-harness-lab:0.3") == ""


def test_worker_discovery_marks_multi_task_shell_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *a, **kw: b"solar-harness-multi-task:0.0\tBuilder Detached | \xe6\xa8\xa1\xe5\x9e\x8b:Sonnet\n",
    )
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "zsh")
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: "zsh% ")
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: False)

    workers = gnd._discover_workers(dry_run=False)

    assert len(workers) == 1
    assert workers[0]["busy"] is True
    assert workers[0]["unavailable_reason"] == "multi_task_shell_not_direct_worker"


def test_dispatch_queue_item_retries_when_assigned_pane_later_hits_quota(monkeypatch) -> None:
    marked: list[tuple[str, str, str, bool]] = []

    item = {
        "sprint_id": "sprint-test",
        "intent": "graph_node|node_id=N1",
        "priority": 80,
        "payload": {
            "sprint_id": "sprint-test",
            "graph": "/tmp/sprint-test.task_graph.json",
            "dispatch_id": "dispatch-N1",
            "node": {"id": "N1"},
            "assignment": {"pane": "solar-harness-lab:0.3"},
        },
    }

    monkeypatch.setattr(gnd, "_graph_node_runtime_state", lambda graph_path, node_id: {"status": "pending"})
    monkeypatch.setattr(gnd, "_pane_exists", lambda pane: True)
    monkeypatch.setattr(gnd, "_assigned_pane_unavailable_reason", lambda pane: "rate_limit_or_api_error")
    monkeypatch.setattr(
        gnd,
        "_mark_graph_node",
        lambda graph_path, node_id, status, clear_assignment=False: marked.append(
            (graph_path, node_id, status, clear_assignment)
        ),
    )
    monkeypatch.setattr(
        gnd,
        "_ensure_lease",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("lease should not be acquired")),
    )

    result = gnd.dispatch_queue_item(item, dry_run=False)

    assert result["ok"] is True
    assert result["reason"] == "assigned_pane_unavailable_retry_later"
    assert result["unavailable_reason"] == "rate_limit_or_api_error"
    assert marked == [("/tmp/sprint-test.task_graph.json", "N1", "pending", True)]


def test_evaluator_discovery_ignores_expired_lease(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "SESSION", "solar-harness")
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *a, **kw: b"solar-harness:0.3\tEvaluator \xe5\xae\xa1\xe5\x88\xa4\xe5\xae\x98 | \xe6\xa8\xa1\xe5\x9e\x8b:Opus\n",
    )
    monkeypatch.setattr(gnd, "_pane_exists", lambda pane: True)
    monkeypatch.setattr(gnd, "_pane_title", lambda pane: "Evaluator 审判官 | 模型:Opus")
    monkeypatch.setattr(gnd, "read_lease", lambda pane: {"expires_at": _ts(-60)})
    monkeypatch.setattr(gnd, "_pane_hygiene_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "bash")

    evaluators = gnd._discover_evaluators(dry_run=False)

    assert len(evaluators) == 1
    assert evaluators[0]["pane"] == "solar-harness:0.3"
    assert evaluators[0]["busy"] is False


def test_evaluator_discovery_finds_pool_candidates_by_role(monkeypatch) -> None:
    monkeypatch.setattr(gnd, "SESSION", "solar-harness-test")
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *a, **kw: (
            b"solar-harness-test:0.3\tEvaluator \xe5\xae\xa1\xe5\x88\xa4\xe5\xae\x98 | \xe6\xa8\xa1\xe5\x9e\x8b:Opus\n"
            b"solar-harness-lab:0.3\tEvaluator Print \xe5\xae\xa1\xe5\x88\xa4\xe5\xae\x98 | \xe6\xa8\xa1\xe5\x9e\x8b:Opus\n"
            b"solar-harness-lab:0.1\tBuilder 2 | \xe6\xa8\xa1\xe5\x9e\x8b:Sonnet\n"
            b"solar-harness-multi-task:7\tEvaluator Detached \xe5\xae\xa1\xe5\x88\xa4\xe5\xae\x98 | \xe6\xa8\xa1\xe5\x9e\x8b:Gemini\n"
        ),
    )
    monkeypatch.setattr(gnd, "_pane_exists", lambda pane: True)
    monkeypatch.setattr(
        gnd,
        "_pane_title",
        lambda pane: {
            "solar-harness-test:0.3": "Evaluator 审判官 | 模型:Opus",
            "solar-harness-lab:0.3": "Evaluator Print 审判官 | 模型:Opus",
            "solar-harness-lab:0.1": "Builder 2 | 模型:Sonnet",
            "solar-harness-multi-task:7": "Evaluator Detached 审判官 | 模型:Gemini",
        }.get(pane, ""),
    )
    monkeypatch.setattr(gnd, "read_lease", lambda pane: {})
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "bash")

    evaluators = gnd._discover_evaluators(dry_run=False)
    panes = [item["pane"] for item in evaluators]

    assert set(panes) == {
        "solar-harness-test:0.3",
        "solar-harness-lab:0.3",
        "solar-harness-lab:0.1",
        "solar-harness-multi-task:7",
    }
    lab_builder = next(item for item in evaluators if item["pane"] == "solar-harness-lab:0.1")
    assert lab_builder["evaluator_host_role"] == "lab_builder_spillover"
    multi_task = next(item for item in evaluators if item["pane"] == "solar-harness-multi-task:7")
    assert multi_task["busy"] is True
    assert multi_task["unavailable_reason"] == "multi_task_shell_not_direct_worker"


def test_force_eval_retry_allows_failed_node_after_repair_artifact(monkeypatch, tmp_path) -> None:
    graph = {
        "sprint_id": "sid-force-retry",
        "nodes": [{"id": "N6", "status": "reviewing"}],
        "node_results": {"N6": {"status": "failed"}},
    }
    node = graph["nodes"][0]
    handoff = tmp_path / "sid-force-retry.N6-handoff.md"
    handoff.write_text("handoff", encoding="utf-8")

    monkeypatch.setattr(gnd, "_eval_json_file", lambda sid, node_id: tmp_path / "missing-eval.json")
    monkeypatch.setattr(gnd, "_existing_node_handoff", lambda sid, node, graph: handoff)

    assert gnd._node_eval_needed(graph, "sid-force-retry", node, force=False) is False
    assert gnd._node_eval_needed(graph, "sid-force-retry", node, force=True) is True


def test_clear_stale_prompt_residue_uses_ctrl_c_fallback(monkeypatch) -> None:
    prompt_residue = "────────────────\n❯\u00a0继续执行下一个 dispatch 文件\n────────────────\n"
    idle_prompt = "────────────────\n❯\u00a0\n────────────────\n"
    tails = [prompt_residue, prompt_residue, prompt_residue, idle_prompt]
    sent: list[tuple[str, ...]] = []

    def fake_tail(pane: str, lines: int = 80) -> str:
        return tails.pop(0) if tails else idle_prompt

    def fake_run(cmd, **kwargs):
        sent.append(tuple(cmd[-(len(cmd) - cmd.index("send-keys") - 3):]))

    monkeypatch.setattr(gnd, "_pane_tail", fake_tail)
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "bash")
    monkeypatch.setattr(gnd.subprocess, "run", fake_run)
    monkeypatch.setattr(gnd.time, "sleep", lambda seconds: None)

    assert gnd._clear_stale_prompt_residue("solar-harness-lab:0.3") is True
    assert ("Escape",) in sent
    assert ("C-a", "C-k") in sent
    assert ("C-u",) in sent


def test_rate_limit_options_modal_is_dismissed_without_selecting_action(monkeypatch) -> None:
    modal = """────────────────
  What do you want to do?

  ❯1. Stop and wait for limit to reset
    2. Upgrade your plan

  Enter to confirm · Esc to cancel
"""
    idle = "────────────────\n❯\u00a0\n────────────────\n"
    tails = [modal, idle]
    sent: list[tuple[str, ...]] = []

    def fake_tail(pane: str, lines: int = 80) -> str:
        return tails.pop(0) if tails else idle

    def fake_run(cmd, **kwargs):
        sent.append(tuple(cmd[-(len(cmd) - cmd.index("send-keys") - 3):]))

    monkeypatch.setattr(gnd, "_pane_tail", fake_tail)
    monkeypatch.setattr(gnd.subprocess, "run", fake_run)
    monkeypatch.setattr(gnd.time, "sleep", lambda seconds: None)

    assert gnd._dismiss_rate_limit_options_modal("solar-harness:0.0") is True
    assert sent == [("Escape",)]


def test_tui_busy_actively_clears_queued_prompt_before_marking_busy(monkeypatch) -> None:
    queued = "────────────────\n❯\u00a0Press up to edit queued messages\n────────────────\n"
    idle = "────────────────\n❯\u00a0\n────────────────\n"
    tails = [queued, idle]
    cleared: list[str] = []

    def fake_tail(pane: str, lines: int = 80) -> str:
        return tails.pop(0) if tails else idle

    monkeypatch.setattr(gnd, "_pane_tail", fake_tail)
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: cleared.append(pane) or True)
    monkeypatch.setattr(gnd.time, "sleep", lambda seconds: None)

    assert gnd._pane_tui_busy("solar-harness-lab:0.2") is False
    assert cleared == ["solar-harness-lab:0.2"]


def test_tui_busy_actively_clears_unsubmitted_prompt_residue(monkeypatch) -> None:
    residue = "────────────────\n❯\u00a0继续执行下一个 dispatch 文件\n────────────────\n"
    idle = "────────────────\n❯\u00a0\n────────────────\n"
    tails = [residue, idle]
    cleared: list[str] = []

    def fake_tail(pane: str, lines: int = 80) -> str:
        return tails.pop(0) if tails else idle

    monkeypatch.setattr(gnd, "_pane_tail", fake_tail)
    monkeypatch.setattr(gnd, "_pane_prompt_residue_is_stale_scrollback", lambda pane, tail: False)
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: cleared.append(pane) or True)
    monkeypatch.setattr(gnd.time, "sleep", lambda seconds: None)

    assert gnd._pane_tui_busy("solar-harness-lab:0.0") is False
    assert cleared == ["solar-harness-lab:0.0"]


def test_tui_busy_recovers_edit_prompt_before_processing_scrollback(monkeypatch) -> None:
    modal = """✻ Running B3 tests and writing handoff…

 Do you want to make this edit to test_dispatch_scheduler.py?
 ❯ 1. Yes
   2. No

 Esc to cancel · Tab to amend
"""
    idle = "────────────────\n❯\u00a0\n────────────────\n"
    tails = [modal, idle]
    dismissed: list[tuple[str, str]] = []

    def fake_tail(pane: str, lines: int = 80) -> str:
        return tails.pop(0) if tails else idle

    monkeypatch.setattr(gnd, "_pane_tail", fake_tail)
    monkeypatch.setattr(gnd, "_dismiss_dispatch_prompt", lambda pane, reason: dismissed.append((pane, reason)) or True)
    monkeypatch.setattr(gnd.time, "sleep", lambda seconds: None)

    assert gnd._pane_tui_busy("solar-harness-lab:0.1") is False
    assert dismissed == [("solar-harness-lab:0.1", "edit_confirmation_prompt")]


def test_overwrite_prompt_is_treated_as_edit_confirmation() -> None:
    tail = """Do you want to overwrite
 test_pane_lifecycle_jobs.py?
 ❯ 1. Yes
  2. Yes, allow all edits during this session (shift+tab)
   3. No

 Esc to cancel · Tab to amend
"""
    assert gnd._pane_dispatch_prompt_reason(tail) == "edit_confirmation_prompt"


def test_unavailable_reason_does_not_dismiss_edit_prompt_after_processing_scrollback(monkeypatch) -> None:
    tail = """Do you want to make this edit to test_pane_clear_manager.py?
 ❯ 1. Yes
   2. No

✢ Running tests… (59s · ↓ 394 tokens)
────────────────
❯\u00a0
────────────────
"""
    idle = "────────────────\n❯\u00a0\n────────────────\n"
    tails = [tail, idle]
    dismissed: list[tuple[str, str]] = []

    def fake_tail(pane: str, lines: int = 80) -> str:
        return tails.pop(0) if tails else idle

    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(gnd, "_pane_tail", fake_tail)
    monkeypatch.setattr(gnd, "_pane_prompt_residue_is_stale_scrollback", lambda pane, value: False)
    monkeypatch.setattr(gnd, "_dismiss_dispatch_prompt", lambda pane, reason: dismissed.append((pane, reason)) or True)
    monkeypatch.setattr(gnd.time, "sleep", lambda seconds: None)

    assert gnd._pane_unavailable_reason("solar-harness-lab:0.0") == ""
    assert dismissed == []


def test_idle_survey_prompt_does_not_block_evaluator_pool(monkeypatch) -> None:
    tail = """● How is Claude doing this session?
  (optional)
  1: Bad   2: Fine   3: Good  0: Dismiss

────────────────
❯\u00a0
────────────────
"""
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(gnd, "_pane_tail", lambda pane, lines=80: tail)

    assert gnd._pane_unavailable_reason("solar-harness:0.3") == ""
