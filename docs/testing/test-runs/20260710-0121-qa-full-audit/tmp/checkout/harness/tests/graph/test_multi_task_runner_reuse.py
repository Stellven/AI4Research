from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE = Path(__file__).resolve().parents[2] / "lib" / "multi_task_runner.py"
spec = importlib.util.spec_from_file_location("multi_task_runner", MODULE)
multi_task_runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(multi_task_runner)


def test_select_reusable_tmux_window_prefers_historical_live_shell() -> None:
    tasks = [
        {
            "id": "graph-task-running",
            "window": "mt-live-window",
            "effective_status": "running",
        },
        {
            "id": "graph-task-completed",
            "window": "mt-reusable-window",
            "effective_status": "completed",
        },
    ]
    windows = [
        {"window_id": "@1", "window": "mt-live-window", "target": "solar-harness-multi-task:@1", "active": "0", "dead": "0", "command": "claude"},
        {"window_id": "@2", "window": "mt-reusable-window", "target": "solar-harness-multi-task:@2", "active": "0", "dead": "0", "command": "zsh"},
    ]

    window, reused, task_id, target = multi_task_runner.select_reusable_tmux_window(
        "mt-fresh-window",
        tasks=tasks,
        windows=windows,
    )

    assert window == "mt-reusable-window"
    assert reused is True
    assert task_id == "graph-task-completed"
    assert target == "solar-harness-multi-task:@2"


def test_select_reusable_tmux_window_skips_active_and_non_shell_windows() -> None:
    tasks = [
        {
            "id": "graph-task-active-window",
            "window": "mt-active-window",
            "effective_status": "completed",
        },
        {
            "id": "graph-task-non-shell-window",
            "window": "mt-non-shell-window",
            "effective_status": "reaped",
        },
    ]
    windows = [
        {"window_id": "@3", "window": "mt-active-window", "target": "solar-harness-multi-task:@3", "active": "1", "dead": "0", "command": "zsh"},
        {"window_id": "@4", "window": "mt-non-shell-window", "target": "solar-harness-multi-task:@4", "active": "0", "dead": "0", "command": "claude"},
    ]

    window, reused, task_id, target = multi_task_runner.select_reusable_tmux_window(
        "mt-fresh-window",
        tasks=tasks,
        windows=windows,
    )

    assert window == "mt-fresh-window"
    assert reused is False
    assert task_id == ""
    assert target == ""


def test_tmux_start_uses_respawn_window_for_reuse(monkeypatch, tmp_path: Path) -> None:
    runner = tmp_path / "runner.sh"
    runner.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    cwd = tmp_path
    calls: list[list[str]] = []

    class _Proc:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["tmux", "has-session", "-t"]:
            return _Proc(0)
        return _Proc(0)

    def fake_check_call(cmd, **kwargs):
        calls.append(cmd)
        return 0

    monkeypatch.setattr(multi_task_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(multi_task_runner.subprocess, "check_call", fake_check_call)

    multi_task_runner.tmux_start("mt-reuse-window", runner, cwd, reuse=True)

    assert any(cmd[:3] == ["tmux", "respawn-window", "-k"] for cmd in calls)
    assert not any(cmd[:3] == ["tmux", "new-window", "-d"] for cmd in calls)


def test_prune_idle_tmux_windows_kills_only_excess_old_shells(monkeypatch) -> None:
    tasks = [
        {
            "id": "task-old",
            "window": "mt-old-window",
            "effective_status": "completed",
            "updated_at": "2026-05-23T10:00:00Z",
        },
        {
            "id": "task-new",
            "window": "mt-new-window",
            "effective_status": "completed",
            "updated_at": "2026-05-23T11:00:00Z",
        },
    ]
    windows = [
        {"window_id": "@5", "window": "mt-old-window", "target": "solar-harness-multi-task:@5", "active": "0", "dead": "0", "command": "zsh"},
        {"window_id": "@6", "window": "mt-new-window", "target": "solar-harness-multi-task:@6", "active": "0", "dead": "0", "command": "zsh"},
    ]
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class _Proc:
            returncode = 0
        return _Proc()

    monkeypatch.setattr(multi_task_runner.subprocess, "run", fake_run)

    result = multi_task_runner.prune_idle_tmux_windows(
        target_keep=1,
        dry_run=False,
        tasks=tasks,
        windows=windows,
    )

    assert [row["window"] for row in result["killed"]] == ["mt-old-window"]
    assert any(cmd[:3] == ["tmux", "kill-window", "-t"] and cmd[3] == "solar-harness-multi-task:@5" for cmd in calls)


def test_idle_tmux_window_candidates_preserve_duplicate_window_names() -> None:
    tasks = [
        {
            "id": "task-a",
            "window": "mt-dup-window",
            "effective_status": "completed",
            "updated_at": "2026-05-23T10:00:00Z",
        }
    ]
    windows = [
        {"window_id": "@8", "window": "mt-dup-window", "target": "solar-harness-multi-task:@8", "active": "0", "dead": "0", "command": "zsh"},
        {"window_id": "@9", "window": "mt-dup-window", "target": "solar-harness-multi-task:@9", "active": "0", "dead": "0", "command": "zsh"},
    ]

    candidates = multi_task_runner.idle_tmux_window_candidates(tasks=tasks, windows=windows)

    assert len(candidates) == 2
    assert {row["window_target"] for row in candidates} == {"solar-harness-multi-task:@8", "solar-harness-multi-task:@9"}


def test_prepare_tmux_window_protects_reused_window_during_shrink(monkeypatch) -> None:
    tasks = [{"id": "task-reuse", "window": "mt-reuse-window", "effective_status": "completed"}]
    windows = [{"window_id": "@7", "window": "mt-reuse-window", "target": "solar-harness-multi-task:@7", "active": "0", "dead": "0", "command": "zsh"}]
    prune_calls: list[tuple[int, bool, set[str]]] = []

    monkeypatch.setattr(multi_task_runner, "list_task_rows", lambda: tasks)
    monkeypatch.setattr(multi_task_runner, "tmux_window_records", lambda: windows)

    def fake_prune(target_keep, dry_run=False, keep_windows=None, tasks=None, windows=None):
        prune_calls.append((target_keep, dry_run, set(keep_windows or set())))
        return {"killed": [], "kept": []}

    monkeypatch.setattr(multi_task_runner, "prune_idle_tmux_windows", fake_prune)

    window, reused, task_id, reuse_target = multi_task_runner.prepare_tmux_window("mt-fresh-window", dry_run=False)

    assert window == "mt-reuse-window"
    assert reused is True
    assert task_id == "task-reuse"
    assert reuse_target == "solar-harness-multi-task:@7"
    assert prune_calls == [(multi_task_runner.IDLE_WINDOW_POOL_TARGET, False, {"solar-harness-multi-task:@7"})]


def test_compact_tmux_session_switches_clients_and_closes_historical_active(monkeypatch) -> None:
    tasks = [{"id": "task-hist", "window": "mt-hist", "effective_status": "completed"}]
    windows = [
        {"window_id": "@10", "window": "mt-hist", "target": "solar-harness-multi-task:@10", "active": "1", "dead": "0", "command": "zsh"},
        {"window_id": "@11", "window": "mt-idle", "target": "solar-harness-multi-task:@11", "active": "0", "dead": "0", "command": "zsh"},
    ]
    calls: list[list[str]] = []

    monkeypatch.setattr(multi_task_runner, "list_task_rows", lambda: tasks)
    monkeypatch.setattr(multi_task_runner, "tmux_window_records", lambda: windows)
    monkeypatch.setattr(multi_task_runner, "tmux_client_records", lambda: [{"tty": "/dev/ttys001", "window_id": "@10", "session": multi_task_runner.SESSION}])
    monkeypatch.setattr(multi_task_runner, "ensure_tmux_anchor_window", lambda cwd=None: ("solar-harness-multi-task:@99", True))

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class _Proc:
            returncode = 0
        return _Proc()

    monkeypatch.setattr(multi_task_runner.subprocess, "run", fake_run)

    result = multi_task_runner.compact_tmux_session(target_keep=1, dry_run=False)

    assert result["destination_target"] == "solar-harness-multi-task:@11"
    assert result["closed"][0]["action"] == "killed-window"
    assert any(cmd[:3] == ["tmux", "switch-client", "-c"] for cmd in calls)
    assert any(cmd[:3] == ["tmux", "kill-window", "-t"] and cmd[3] == "solar-harness-multi-task:@10" for cmd in calls)


def test_compact_tmux_session_creates_anchor_when_no_reusable_target(monkeypatch, tmp_path: Path) -> None:
    tasks = [{"id": "task-hist", "window": "mt-hist", "effective_status": "completed"}]
    windows = [{"window_id": "@12", "window": "mt-hist", "target": "solar-harness-multi-task:@12", "active": "1", "dead": "0", "command": "zsh"}]

    monkeypatch.setattr(multi_task_runner, "list_task_rows", lambda: tasks)
    monkeypatch.setattr(multi_task_runner, "tmux_window_records", lambda: windows)
    monkeypatch.setattr(multi_task_runner, "tmux_client_records", lambda: [])
    monkeypatch.setattr(multi_task_runner, "ensure_tmux_anchor_window", lambda cwd=None: ("solar-harness-multi-task:@99", True))
    monkeypatch.setattr(multi_task_runner, "prune_idle_tmux_windows", lambda *args, **kwargs: {"killed": [], "kept": []})

    result = multi_task_runner.compact_tmux_session(target_keep=1, dry_run=False, cwd=tmp_path)

    assert result["created_anchor"] is True
    assert result["destination_target"] == "solar-harness-multi-task:@99"


def test_detach_and_anchor_selects_anchor(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(multi_task_runner, "ensure_tmux_anchor_window", lambda cwd=None: ("solar-harness-multi-task:@121", False))

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class _Proc:
            returncode = 0
        return _Proc()

    monkeypatch.setattr(multi_task_runner.subprocess, "run", fake_run)

    result = multi_task_runner.detach_and_anchor(cwd=tmp_path, dry_run=False)

    assert result["target"] == "solar-harness-multi-task:@121"
    assert result["action"] == "selected"
    assert any(cmd[:3] == ["tmux", "select-window", "-t"] and cmd[3] == "solar-harness-multi-task:@121" for cmd in calls)
