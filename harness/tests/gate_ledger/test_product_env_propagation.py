"""Product-env propagation to tmux-spawned pool workers (P2 smoke follow-up).

multi_task_runner's pool workers run inside tmux windows: their environment
comes from the tmux SERVER, not from the scheduler that generated them. Any
flag-gated product behavior (gate ledger route records, product mode, provider
pinning) silently degrades in a worker unless the generated runner script
carries the flags itself. The runner template must embed a generation-time
snapshot of the product-env allowlist.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import multi_task_runner as mtr  # noqa: E402


def _payload(tmp_path: Path) -> dict:
    return {
        "graph": str(tmp_path / "g.task_graph.json"),
        "handoff": str(tmp_path / "h.md"),
        "node_id": "S1",
        "sprint_id": "env-snap-sprint",
        "role": "builder",
        "profile": "test-profile",
        "backend": "command",
        "model": "fake-local",
        "provider": "anthropic",
        "command": "true",
        "work_dir": str(tmp_path),
    }


def test_runner_script_embeds_product_env_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setenv("SOLAR_PRODUCT_MODE", "1")
    monkeypatch.setenv("SOLAR_MULTI_TASK_DEFAULT_PROVIDERS", "openai")
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    runner = mtr.runner_script(task_dir, _payload(tmp_path))
    text = runner.read_text(encoding="utf-8")
    assert "export SOLAR_GATE_LEDGER=1" in text
    assert "export SOLAR_PRODUCT_MODE=1" in text
    assert "export SOLAR_MULTI_TASK_DEFAULT_PROVIDERS=openai" in text


def test_runner_script_omits_unset_flags(tmp_path, monkeypatch):
    for var in ("SOLAR_GATE_LEDGER", "SOLAR_PRODUCT_MODE", "SOLAR_WORKFLOW_ROUTER",
                "SOLAR_MULTI_TASK_DEFAULT_PROVIDERS", "SOLAR_PM_DEFAULT_PROVIDERS",
                "HARNESS_SPRINTS_DIR"):
        monkeypatch.delenv(var, raising=False)
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    runner = mtr.runner_script(task_dir, _payload(tmp_path))
    text = runner.read_text(encoding="utf-8")
    assert "export SOLAR_GATE_LEDGER" not in text
    assert "export SOLAR_PRODUCT_MODE" not in text
    # Flag-off worlds generate byte-equivalent runners: legacy behavior untouched.


def test_product_env_exports_are_shell_correct(monkeypatch):
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", "/tmp/dir with spaces/sprints")
    exports = mtr._product_env_exports()
    out = subprocess.run(
        ["bash", "-c", f'{exports}\necho "$SOLAR_GATE_LEDGER|$HARNESS_SPRINTS_DIR"'],
        text=True, capture_output=True, timeout=10, env={"PATH": "/usr/bin:/bin"},
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "1|/tmp/dir with spaces/sprints"


def test_tmux_start_injects_product_env_into_window_command(monkeypatch):
    """Smoke 20260707T190540Z (second consecutive zero-route-record run): the
    runner-template snapshot only helps when the SCHEDULER has the flags — but
    tmux-hosted lineages (pool windows, pm loops) inherit the tmux SERVER's
    environment. tmux_start must inject the product-env allowlist into the
    window command itself, so any process it hosts (and anything that process
    auto-kicks, e.g. operatord) carries the flags regardless of server env."""
    monkeypatch.setenv("SOLAR_GATE_LEDGER", "1")
    monkeypatch.setenv("SOLAR_MULTI_TASK_DEFAULT_PROVIDERS", "openai")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:  # noqa: N801
            returncode = 0
        return R()

    def fake_check_call(cmd, **kwargs):
        calls.append(list(cmd))
        return 0

    monkeypatch.setattr(mtr.subprocess, "run", fake_run)
    monkeypatch.setattr(mtr.subprocess, "check_call", fake_check_call)
    mtr.tmux_start("w1", Path("/tmp/r u n/runner.sh"), Path("/tmp"))

    spawn = next(c for c in calls if c[:2] == ["tmux", "new-window"] or c[:2] == ["tmux", "new-session"])
    command_string = spawn[-1]
    assert "SOLAR_GATE_LEDGER=1" in command_string, command_string
    assert "SOLAR_MULTI_TASK_DEFAULT_PROVIDERS=openai" in command_string, command_string
    assert "runner.sh" in command_string


def test_tmux_start_command_unchanged_when_flags_unset(monkeypatch):
    for var in mtr._PRODUCT_ENV_ALLOWLIST:
        monkeypatch.delenv(var, raising=False)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:  # noqa: N801
            returncode = 0
        return R()

    monkeypatch.setattr(mtr.subprocess, "run", fake_run)
    monkeypatch.setattr(mtr.subprocess, "check_call", lambda cmd, **k: calls.append(list(cmd)) or 0)
    mtr.tmux_start("w1", Path("/tmp/runner.sh"), Path("/tmp"))
    spawn = next(c for c in calls if c[:2] == ["tmux", "new-window"] or c[:2] == ["tmux", "new-session"])
    assert "SOLAR_GATE_LEDGER" not in spawn[-1]
