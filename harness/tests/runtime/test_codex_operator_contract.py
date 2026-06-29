#!/usr/bin/env python3
"""Contract checks for Codex-backed operatord execution.

These tests do not invoke Codex. They verify the dispatch environment that
must be correct before a live model call is attempted.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_multi_task_operator_envelope_carries_work_dir_and_graph_path():
    multi_task_runner = _load_module("multi_task_runner_contract", ROOT / "lib" / "multi_task_runner.py")
    envelope = multi_task_runner._build_operator_envelope(
        "dispatch-1",
        "sprint-1",
        "N1",
        {"id": "N1", "goal": "Build the thing"},
        {
            "operator_id": "mini-codex-gpt55-medium-builder-1",
            "role": "builder",
            "backend": "command",
            "model": "gpt-5.5",
            "name": "codex-builder",
            "approval_mode": "yolo",
        },
        {
            "write_scope": ["/tmp/out.py"],
            "handoff": "/tmp/handoff.md",
            "dispatch_file": "/tmp/dispatch.md",
            "graph": "/tmp/sprint.task_graph.json",
            "work_dir": "/tmp/sprint-workdir",
        },
    )

    assert envelope["work_dir"] == "/tmp/sprint-workdir"
    assert envelope["graph_path"] == "/tmp/sprint.task_graph.json"


def test_operatord_materializes_work_dir_for_codex(tmp_path, monkeypatch):
    operatord = _load_module("operatord_contract", ROOT / "tools" / "operatord.py")
    monkeypatch.setattr(operatord, "HARNESS_DIR", tmp_path / "harness")
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    dispatch_file = tmp_path / "dispatch.md"
    dispatch_file.write_text("dispatch", encoding="utf-8")

    env = operatord._materialize_envelope_context(
        result_dir,
        {
            "task_id": "dispatch-1",
            "sprint_id": "sprint-1",
            "node_id": "N1",
            "dispatch_file": str(dispatch_file),
            "graph_path": str(tmp_path / "sprint.task_graph.json"),
            "work_dir": str(tmp_path / "sprint-workdir"),
        },
    )

    assert env["WORK_DIR"] == str(tmp_path / "sprint-workdir")
    assert env["CODEX_WORKDIR"] == str(tmp_path / "sprint-workdir")
    assert env["GRAPH"] == str(tmp_path / "sprint.task_graph.json")
    assert Path(env["SOLAR_OPERATOR_ENVELOPE_JSON"]).exists()


def test_codex_operator_uses_writable_sqlite_home_and_ephemeral_flag(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract", ROOT / "tools" / "codex_operator.py")
    harness_dir = tmp_path / "harness"
    task_dir = harness_dir / "run" / "operator-results" / "op" / "task"
    task_dir.mkdir(parents=True)
    monkeypatch.delenv("CODEX_SQLITE_HOME", raising=False)
    monkeypatch.delenv("SOLAR_CODEX_STATE_HOME", raising=False)
    monkeypatch.delenv("SOLAR_CODEX_OPERATOR_EPHEMERAL", raising=False)
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))

    env = codex_operator._codex_exec_env(task_dir)
    assert env["CODEX_SQLITE_HOME"] == str(harness_dir / "run" / "codex-state")
    assert Path(env["CODEX_SQLITE_HOME"]).is_dir()

    cmd = codex_operator._codex_exec_command("gpt-5.5", "medium", str(tmp_path), task_dir / "last.md")
    assert "--ephemeral" in cmd
    assert "--cd" in cmd
    assert str(tmp_path) in cmd


def test_codex_operator_respects_explicit_non_ephemeral(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_no_ephemeral", ROOT / "tools" / "codex_operator.py")
    monkeypatch.setenv("SOLAR_CODEX_OPERATOR_EPHEMERAL", "0")
    cmd = codex_operator._codex_exec_command("gpt-5.5", "medium", str(tmp_path), tmp_path / "last.md")
    assert "--ephemeral" not in cmd

