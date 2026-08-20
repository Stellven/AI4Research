#!/usr/bin/env python3
"""Contract checks for Codex-backed operatord execution.

These tests do not invoke Codex. They verify the dispatch environment that
must be correct before a live model call is attempted.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = (Path(__file__).resolve().parents[3] / 'harness')


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


def test_pm_operator_envelope_carries_work_dir_and_provider_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_PM_DEFAULT_PROVIDERS", "openai")
    pm_dispatch = _load_module("pm_dispatch_contract", ROOT / "tools" / "pm_dispatch.py")
    monkeypatch.setattr(pm_dispatch, "SPRINTS_DIR", tmp_path / "sprints")
    dispatch_file = tmp_path / "dispatch.md"
    dispatch_file.write_text("dispatch", encoding="utf-8")

    envelope = pm_dispatch._build_pm_operator_envelope(
        task_id="pm-sprint-1-N0-abc",
        sprint_id="sprint-1",
        node_id="N0",
        operator_id="mini-codex-gpt55-medium-planner-1",
        operator={"provider": "openai", "backend": "command", "model": "gpt-5.5"},
        task_type="planning",
        objective="Plan the work",
        dispatch_file=dispatch_file,
        result_path=str(tmp_path / "result.md"),
        role="planner",
        expected_artifacts=[str(tmp_path / "handoff.md")],
    )

    assert envelope["work_dir"] == str(tmp_path / "sprints" / "sprint-1" / "workdir")
    assert Path(envelope["work_dir"]).is_dir()
    assert envelope["runtime_mode"] == "codex"
    assert envelope["provider_policy"] == "openai"
    assert envelope["operator_provider"] == "openai"
    assert envelope["expected_artifacts"] == [str(tmp_path / "handoff.md")]


def test_pm_route_preflight_fails_closed_on_provider_mismatch(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOLAR_PM_DEFAULT_PROVIDERS", "openai")
    pm_dispatch = _load_module("pm_dispatch_route_contract", ROOT / "tools" / "pm_dispatch.py")
    registry = {
        "operators": {
            "codex-planner": {
                "role": "planner",
                "roles": ["planner"],
                "provider": "openai",
                "backend": "command",
                "model": "gpt-5.5",
                "enabled": True,
                "available": True,
            },
            "claude-builder": {
                "role": "builder",
                "roles": ["builder"],
                "provider": "anthropic",
                "backend": "claude-cli",
                "model": "sonnet",
                "enabled": True,
                "available": True,
            },
            "codex-evaluator": {
                "role": "evaluator",
                "roles": ["evaluator"],
                "provider": "openai",
                "backend": "command",
                "model": "gpt-5.5",
                "enabled": True,
                "available": True,
            },
        }
    }
    monkeypatch.setattr(pm_dispatch, "load_registry", lambda: registry)
    monkeypatch.setattr(pm_dispatch, "get_operator_runtime_state", lambda _op_id: "idle")
    monkeypatch.setattr(pm_dispatch, "_operator_external_health", lambda _op: (True, ""))
    args = type("Args", (), {
        "runtime": "codex",
        "expect_provider": "openai",
        "roles": "planner,builder,evaluator",
        "pretty": False,
    })()

    assert pm_dispatch.cmd_route_preflight(args) == 1
    payload = capsys.readouterr().out
    assert '"ok": false' in payload
    assert "builder" in payload


def test_pm_route_preflight_constrains_selection_to_requested_provider(monkeypatch, capsys):
    monkeypatch.delenv("SOLAR_PM_DEFAULT_PROVIDERS", raising=False)
    monkeypatch.delenv("SOLAR_MULTI_TASK_DEFAULT_PROVIDERS", raising=False)
    pm_dispatch = _load_module("pm_dispatch_route_provider_contract", ROOT / "tools" / "pm_dispatch.py")
    registry = {
        "operators": {
            "claude-planner": {
                "role": "planner",
                "roles": ["planner"],
                "provider": "anthropic",
                "backend": "command",
                "model": "opus",
                "enabled": True,
                "available": True,
                "priority": 100,
            },
            "codex-planner": {
                "role": "planner",
                "roles": ["planner"],
                "provider": "openai",
                "backend": "command",
                "model": "gpt-5.5",
                "enabled": True,
                "available": True,
            },
        }
    }
    monkeypatch.setattr(pm_dispatch, "load_registry", lambda: registry)
    monkeypatch.setattr(pm_dispatch, "get_operator_runtime_state", lambda _op_id: "idle")
    monkeypatch.setattr(pm_dispatch, "_operator_external_health", lambda _op: (True, ""))
    args = type("Args", (), {
        "runtime": "codex",
        "expect_provider": "openai",
        "roles": "planner",
        "pretty": False,
    })()

    assert pm_dispatch.cmd_route_preflight(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["roles"][0]["operator_id"] == "codex-planner"
    assert payload["roles"][0]["provider"] == "openai"


def test_operatord_materializes_work_dir_for_codex(tmp_path, monkeypatch):
    operatord = _load_module("operatord_contract", ROOT / "tools" / "operatord.py")
    monkeypatch.setattr(operatord, "HARNESS_DIR", tmp_path / "harness")
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    dispatch_file = tmp_path / "dispatch.md"
    dispatch_file.write_text("dispatch", encoding="utf-8")
    result_path = result_dir / "result.md"
    handoff_path = tmp_path / "harness" / "sprints" / "sprint-1.N1-handoff.md"

    env = operatord._materialize_envelope_context(
        result_dir,
        {
            "task_id": "dispatch-1",
            "sprint_id": "sprint-1",
            "node_id": "N1",
            "dispatch_file": str(dispatch_file),
            "graph_path": str(tmp_path / "sprint.task_graph.json"),
            "work_dir": str(tmp_path / "sprint-workdir"),
            "result_path": str(result_path),
            "expected_artifacts": [str(handoff_path)],
        },
    )

    assert env["WORK_DIR"] == str(tmp_path / "sprint-workdir")
    assert env["CODEX_WORKDIR"] == str(tmp_path / "sprint-workdir")
    assert env["GRAPH"] == str(tmp_path / "sprint.task_graph.json")
    assert Path(env["SOLAR_OPERATOR_ENVELOPE_JSON"]).exists()
    assert result_path.is_file()
    assert handoff_path.is_file()
    assert set(json.loads(env["SOLAR_OPERATOR_ALLOWED_OUTPUTS_JSON"])) == {
        str(result_path),
        str(handoff_path),
    }


def test_operatord_derives_work_dir_for_legacy_pm_envelope(tmp_path, monkeypatch):
    operatord = _load_module("operatord_contract_legacy_workdir", ROOT / "tools" / "operatord.py")
    harness = tmp_path / "harness"
    monkeypatch.setattr(operatord, "HARNESS_DIR", harness)
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    dispatch_file = tmp_path / "dispatch.md"
    dispatch_file.write_text("dispatch", encoding="utf-8")

    env = operatord._materialize_envelope_context(
        result_dir,
        {
            "task_id": "pm-sprint-1-N0-abc",
            "sprint_id": "sprint-1",
            "node_id": "N0",
            "dispatch_file": str(dispatch_file),
        },
    )

    expected = harness / "sprints" / "sprint-1" / "workdir"
    assert env["WORK_DIR"] == str(expected)
    assert env["CODEX_WORKDIR"] == str(expected)
    assert expected.is_dir()


def test_operatord_refuses_expected_artifact_outside_authorized_roots(tmp_path, monkeypatch):
    operatord = _load_module("operatord_contract_output_refusal", ROOT / "tools" / "operatord.py")
    harness = tmp_path / "harness"
    monkeypatch.setattr(operatord, "HARNESS_DIR", harness)
    result_dir = harness / "run" / "operator-results" / "op" / "task"
    result_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="outside Solar-authorized roots"):
        operatord._materialize_envelope_context(
            result_dir,
            {
                "task_id": "dispatch-escape",
                "sprint_id": "sprint-1",
                "work_dir": str(harness / "sprints" / "sprint-1" / "workdir"),
                "expected_artifacts": [str(tmp_path / "outside" / "escape.md")],
            },
        )


def test_codex_operator_explains_precreated_output_placeholders(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_output_guidance", ROOT / "tools" / "codex_operator.py")
    dispatch_file = tmp_path / "dispatch.md"
    dispatch_file.write_text("# Build the artifacts\n", encoding="utf-8")
    expected = tmp_path / "design.md"
    expected.touch()
    monkeypatch.setenv("DISPATCH_FILE", str(dispatch_file))
    monkeypatch.setenv("SOLAR_OPERATOR_ALLOWED_OUTPUTS_JSON", json.dumps([str(expected)]))

    dispatch = codex_operator._read_dispatch()

    assert dispatch.startswith("# Build the artifacts")
    assert "zero-byte placeholders" in dispatch
    assert "use Update File rather than Add File" in dispatch
    assert str(expected) in dispatch


def test_codex_operator_materializes_direct_skill_bridge_evidence(tmp_path, monkeypatch):
    codex_operator = _load_module(
        "codex_operator_contract_skill_bridge",
        ROOT / "tools" / "codex_operator.py",
    )
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(
        json.dumps(
            {
                "capability_capsule_id": "cap.skill-execution-bridge",
                "selected_skills": ["research_compilation"],
                "resolved_capability_capsule": {
                    "capability_capsule_id": "cap.skill-execution-bridge",
                    "selected_skills": [],
                },
                "task_graph_node": {"required_skills": ["research_compilation"]},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SOLAR_OPERATOR_ENVELOPE_JSON", str(envelope_path))

    evidence = codex_operator._materialize_skill_bridge_evidence(
        tmp_path,
        "Compile the grounded report.",
    )
    codex_operator._write_skill_bridge_result(tmp_path, evidence, 0)

    expected = {
        "skill-dispatch-result.json",
        "skill-dispatch-pane-prompt.md",
        "skill-dispatch-selection-proof.json",
        "skill-dispatch-bridge-contract.json",
    }
    assert expected.issubset({path.name for path in tmp_path.iterdir()})
    contract = json.loads((tmp_path / "skill-dispatch-bridge-contract.json").read_text(encoding="utf-8"))
    assert contract["command_protocol"]["mode"]
    assert contract["command_protocol"]["execution_surface"] == "direct_command_operator"
    assert contract["workflow_contract"]["phases"]
    assert contract["workflow_contract"]["delivery_expectation"]
    result = json.loads((tmp_path / "skill-dispatch-result.json").read_text(encoding="utf-8"))
    assert result["status"] == "completed"
    assert result["selected_skills"] == ["research_compilation"]


def test_codex_operator_uses_writable_sqlite_home_and_ephemeral_flag(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract", ROOT / "tools" / "codex_operator.py")
    harness_dir = tmp_path / "harness"
    task_dir = harness_dir / "run" / "operator-results" / "op" / "task"
    task_dir.mkdir(parents=True)
    monkeypatch.delenv("CODEX_SQLITE_HOME", raising=False)
    monkeypatch.delenv("SOLAR_CODEX_STATE_HOME", raising=False)
    monkeypatch.delenv("SOLAR_CODEX_SOURCE_HOME", raising=False)
    monkeypatch.delenv("SOLAR_CODEX_OPERATOR_EPHEMERAL", raising=False)
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    stale_codex_home = tmp_path / "stale-codex-home"
    stale_codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(stale_codex_home))

    env = codex_operator._codex_exec_env(task_dir)
    assert env["CODEX_SQLITE_HOME"] == str(harness_dir / "run" / "codex-state")
    assert Path(env["CODEX_SQLITE_HOME"]).is_dir()
    assert env["SOLAR_CODEX_SOURCE_HOME"] == str(Path.home() / ".codex")

    cmd = codex_operator._codex_exec_command("gpt-5.5", "medium", str(tmp_path), task_dir / "last.md")
    assert "--ephemeral" in cmd
    assert "--skip-git-repo-check" in cmd
    assert 'cli_auth_credentials_store="file"' in cmd
    assert "--cd" in cmd
    assert str(tmp_path) in cmd


def test_codex_operator_prefers_bound_workspace_virtualenv(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_bound_venv", ROOT / "tools" / "codex_operator.py")
    workspace_binding = _load_module("workspace_binding_contract_bound_venv", ROOT / "lib" / "workspace_binding.py")
    harness_dir = tmp_path / "harness"
    sprints_dir = harness_dir / "sprints"
    task_dir = harness_dir / "run" / "operator-results" / "op" / "task"
    workspace = tmp_path / "workspace"
    venv_bin = workspace / ".venv" / "bin"
    sid = "sprint-bound-venv"
    task_dir.mkdir(parents=True)
    sprints_dir.mkdir(parents=True)
    venv_bin.mkdir(parents=True)
    (venv_bin / "python3").touch()
    (sprints_dir / f"{sid}.raw_intent.json").write_text(
        json.dumps({"context": {"repo": str(workspace)}}) + "\n",
        encoding="utf-8",
    )
    workspace_binding.bind_active_workspace(harness_dir, workspace, source="test")
    monkeypatch.setitem(sys.modules, "workspace_binding", workspace_binding)
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("SPRINTS_DIR", str(sprints_dir))
    monkeypatch.setenv("SID", sid)

    env = codex_operator._codex_exec_env(task_dir)

    path_entries = env["PATH"].split(os.pathsep)
    assert str(venv_bin) in path_entries
    assert path_entries.index(str(venv_bin)) < path_entries.index(str(harness_dir))


def test_codex_operator_prefers_harness_wide_model_policy(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_model_policy", ROOT / "tools" / "codex_operator.py")
    monkeypatch.setenv("CODEX_MODEL", "gpt-5.5")
    monkeypatch.setenv("SOLAR_CODEX_MODEL", "gpt-5.3-codex-spark")

    assert codex_operator._codex_model() == "gpt-5.3-codex-spark"


def test_codex_operator_uses_resolved_cross_platform_binary(tmp_path):
    codex_operator = _load_module("codex_operator_contract_binary", ROOT / "tools" / "codex_operator.py")
    binary = tmp_path / "codex"
    command = codex_operator._codex_exec_command(
        "gpt-5.5",
        "medium",
        str(tmp_path),
        tmp_path / "last.md",
        str(binary),
    )

    assert command[0] == str(binary)
    assert command[1] == "exec"
    assert "--skip-git-repo-check" in command


def test_codex_operator_projects_auth_on_macos(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_non_linux_auth", ROOT / "tools" / "codex_operator.py")
    harness_dir = tmp_path / "harness"
    task_dir = harness_dir / "run" / "operator-results" / "op" / "task"
    work_dir = tmp_path / "work"
    source_codex_home = tmp_path / "source-codex-home"
    task_dir.mkdir(parents=True)
    work_dir.mkdir()
    source_codex_home.mkdir()
    (source_codex_home / "auth.json").write_text('{"fixture": true}\n', encoding="utf-8")
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("SOLAR_CODEX_SOURCE_HOME", str(source_codex_home))
    monkeypatch.setenv("SOLAR_CODEX_OPERATOR_STATE_ROOT", str(tmp_path / "operator-state"))
    monkeypatch.setenv("SOLAR_OPERATOR_STRICT_FS_SCOPE", "0")
    monkeypatch.setattr(codex_operator.sys, "platform", "darwin")
    env = codex_operator._codex_exec_env(task_dir)

    command, proof = codex_operator._filesystem_isolated_command(
        ["codex", "exec", "-"], task_dir=task_dir, cwd=work_dir, env=env
    )

    assert command == ["codex", "exec", "--sandbox", "workspace-write", "-"]
    assert proof == {"mode": "codex_workspace_write", "strict": False, "read_write": []}
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    sandbox_codex_home = Path(env["CODEX_HOME"])
    assert sandbox_codex_home.parent.parent == tmp_path / "operator-state"
    assert (sandbox_codex_home / "auth.json").read_text(encoding="utf-8") == '{"fixture": true}\n'
    if os.name != "nt":
        assert (sandbox_codex_home / "auth.json").stat().st_mode & 0o777 == 0o600
    assert (sandbox_codex_home / "config.toml").read_text(encoding="utf-8") == (
        'cli_auth_credentials_store = "file"\n'
    )


def test_codex_operator_grants_only_declared_output_parent_on_macos(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_non_linux_outputs", ROOT / "tools" / "codex_operator.py")
    harness_dir = tmp_path / "harness"
    task_dir = harness_dir / "run" / "operator-results" / "op" / "task"
    work_dir = harness_dir / "sprints" / "sprint-1" / "workdir"
    output = harness_dir / "sprints" / "sprint-1.N0.pm-result.md"
    outside = tmp_path / "outside" / "escape.md"
    source_codex_home = tmp_path / "source-codex-home"
    task_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)
    output.touch()
    source_codex_home.mkdir()
    (source_codex_home / "auth.json").write_text('{"fixture": true}\n', encoding="utf-8")
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("SOLAR_CODEX_SOURCE_HOME", str(source_codex_home))
    monkeypatch.setenv("SOLAR_CODEX_OPERATOR_STATE_ROOT", str(tmp_path / "operator-state"))
    monkeypatch.setenv("SOLAR_OPERATOR_STRICT_FS_SCOPE", "0")
    monkeypatch.setenv(
        "SOLAR_OPERATOR_ALLOWED_OUTPUTS_JSON",
        json.dumps([str(output), str(outside)]),
    )
    monkeypatch.setattr(codex_operator.sys, "platform", "darwin")
    env = codex_operator._codex_exec_env(task_dir)

    command, proof = codex_operator._filesystem_isolated_command(
        ["codex", "exec", "-"], task_dir=task_dir, cwd=work_dir, env=env
    )

    assert command == [
        "codex",
        "exec",
        "--sandbox",
        "workspace-write",
        "--add-dir",
        str(harness_dir / "sprints"),
        "-",
    ]
    assert proof == {
        "mode": "codex_workspace_write",
        "strict": False,
        "read_write": [str(harness_dir / "sprints")],
    }
    assert str(outside.parent) not in command


def test_codex_operator_preserves_proven_windows_command(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_windows", ROOT / "tools" / "codex_operator.py")
    harness_dir = tmp_path / "harness"
    task_dir = harness_dir / "run" / "operator-results" / "op" / "task"
    work_dir = harness_dir / "sprints" / "sprint-1" / "workdir"
    source_codex_home = tmp_path / "source-codex-home"
    task_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)
    source_codex_home.mkdir()
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("SOLAR_CODEX_SOURCE_HOME", str(source_codex_home))
    monkeypatch.setenv("SOLAR_CODEX_OPERATOR_STATE_ROOT", str(tmp_path / "operator-state"))
    monkeypatch.setenv("SOLAR_OPERATOR_STRICT_FS_SCOPE", "0")
    monkeypatch.setattr(codex_operator.sys, "platform", "win32")
    env = codex_operator._codex_exec_env(task_dir)
    original = ["codex.exe", "exec", "--dangerously-bypass-approvals-and-sandbox", "-"]

    command, proof = codex_operator._filesystem_isolated_command(
        original, task_dir=task_dir, cwd=work_dir, env=env
    )

    assert command == original
    assert proof == {"mode": "unsupported", "strict": False}


@pytest.mark.skipif(sys.platform != "linux", reason="Landlock is Linux-only")
def test_codex_operator_wraps_strict_run_in_landlock(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_landlock", ROOT / "tools" / "codex_operator.py")
    harness_dir = tmp_path / "harness"
    task_dir = harness_dir / "run" / "operator-results" / "op" / "task"
    work_dir = harness_dir / "sprints" / "sprint-1" / "workdir"
    task_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)
    source_codex_home = tmp_path / "source-codex-home"
    source_codex_home.mkdir()
    (source_codex_home / "auth.json").write_text('{"fixture": true}\n', encoding="utf-8")
    (source_codex_home / "config.toml").write_text("must_not_be_projected = true\n", encoding="utf-8")
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("SOLAR_CODEX_SOURCE_HOME", str(source_codex_home))
    monkeypatch.setenv("SOLAR_CODEX_OPERATOR_STATE_ROOT", str(tmp_path / "operator-state"))
    monkeypatch.setenv("SOLAR_OPERATOR_STRICT_FS_SCOPE", "1")
    env = codex_operator._codex_exec_env(task_dir)
    exact_handoff = harness_dir / "sprints" / "sprint-1.N1-handoff.md"
    exact_handoff.parent.mkdir(parents=True, exist_ok=True)
    exact_handoff.touch()
    env["SOLAR_OPERATOR_ALLOWED_OUTPUTS_JSON"] = json.dumps([str(exact_handoff)])
    published = tmp_path / "published" / "evidence.jsonl"
    published.parent.mkdir()
    published.write_text("evidence\n", encoding="utf-8")
    relative_read = work_dir / "inputs" / "source.json"
    relative_read.parent.mkdir()
    relative_read.write_text("{}\n", encoding="utf-8")
    env["SOLAR_OPERATOR_READ_SCOPE_JSON"] = json.dumps(
        [str(published), "inputs/source.json"]
    )

    command, proof = codex_operator._filesystem_isolated_command(
        ["codex", "exec", "-"], task_dir=task_dir, cwd=work_dir, env=env
    )

    assert command[0] == sys.executable
    assert command[1].endswith("landlock_exec.py")
    assert command[-4] == "--"
    assert Path(command[-3]).name == "codex"
    assert command[-2:] == ["exec", "-"]
    assert proof["mode"] == "landlock"
    assert proof["strict"] is True
    assert str(harness_dir.resolve()) in proof["read_only"]
    assert str(harness_dir.resolve()) not in proof["read_write"]
    assert str(work_dir.resolve()) in proof["read_write"]
    assert str(task_dir.resolve()) in proof["read_write"]
    assert str(exact_handoff.resolve()) in proof["read_write"]
    assert str(published.resolve()) in proof["read_only"]
    assert str(relative_read.resolve()) in proof["read_only"]
    assert str(tmp_path.resolve()) not in proof["read_write"]
    assert str(Path("/etc/resolv.conf").resolve()) in proof["read_only"]
    sandbox_codex_home = Path(env["CODEX_HOME"])
    assert Path(env["HOME"]) == sandbox_codex_home.parent
    assert sandbox_codex_home == Path(env["CODEX_SQLITE_HOME"]) / "home"
    assert (sandbox_codex_home / "auth.json").is_file()
    assert not (sandbox_codex_home / "auth.json").is_symlink()
    assert (sandbox_codex_home / "auth.json").stat().st_mode & 0o777 == 0o600
    assert (sandbox_codex_home / "auth.json").read_text(encoding="utf-8") == '{"fixture": true}\n'
    assert (sandbox_codex_home / "config.toml").read_text(encoding="utf-8") == (
        'cli_auth_credentials_store = "file"\n'
    )


def test_codex_operator_refuses_disabled_isolation_for_strict_run(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_landlock_refusal", ROOT / "tools" / "codex_operator.py")
    harness_dir = tmp_path / "harness"
    task_dir = harness_dir / "run" / "operator-results" / "op" / "task"
    task_dir.mkdir(parents=True)
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("SOLAR_OPERATOR_STRICT_FS_SCOPE", "1")
    env = codex_operator._codex_exec_env(task_dir)
    env["SOLAR_CODEX_OPERATOR_FS_ISOLATION"] = "off"

    with pytest.raises(RuntimeError, match="cannot disable Landlock"):
        codex_operator._filesystem_isolated_command(
            ["codex", "exec", "-"], task_dir=task_dir, cwd=tmp_path, env=env
        )


@pytest.mark.skipif(sys.platform != "linux", reason="WSL mount isolation is Linux-only")
def test_codex_operator_uses_mount_namespace_for_drvfs(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_drvfs", ROOT / "tools" / "codex_operator.py")
    harness_dir = tmp_path / "harness"
    task_dir = harness_dir / "run" / "operator-results" / "op" / "task"
    work_dir = harness_dir / "sprints" / "sprint-1" / "workdir"
    task_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# Test agent instructions\n", encoding="utf-8")
    (tmp_path / ".agents").mkdir()
    source_codex_home = tmp_path / "source-codex-home"
    source_codex_home.mkdir()
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("SOLAR_CODEX_SOURCE_HOME", str(source_codex_home))
    monkeypatch.setenv("SOLAR_CODEX_OPERATOR_STATE_ROOT", str(tmp_path / "operator-state"))
    monkeypatch.setenv("SOLAR_OPERATOR_STRICT_FS_SCOPE", "1")
    monkeypatch.setattr(codex_operator, "_path_filesystem_type", lambda _path: "9p")
    env = codex_operator._codex_exec_env(task_dir)

    command, proof = codex_operator._filesystem_isolated_command(
        ["codex", "exec", "-"], task_dir=task_dir, cwd=work_dir, env=env
    )

    assert Path(command[0]).name == "unshare"
    assert "mount_namespace_exec.py" in command
    assert "landlock_exec.py" in command
    assert "--read-scope-only" in command
    assert proof["mode"] == "mount_namespace+landlock-read"
    assert str(tmp_path.resolve()) in proof["read_directories"]
    assert str((tmp_path / "AGENTS.md").resolve()) in proof["read_only"]
    assert str((tmp_path / ".agents").resolve()) in proof["read_only"]


@pytest.mark.skipif(sys.platform != "linux", reason="WSL mount isolation is Linux-only")
def test_drvfs_mount_namespace_writes_only_declared_paths(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_drvfs_live", ROOT / "tools" / "codex_operator.py")
    if codex_operator._path_filesystem_type(ROOT) not in {"9p", "v9fs"}:
        pytest.skip("requires a WSL DrvFS checkout")
    harness_dir = tmp_path / "harness"
    task_dir = harness_dir / "run" / "operator-results" / "op" / "task"
    work_dir = harness_dir / "sprints" / "sprint-1" / "workdir"
    allowed = harness_dir / "sprints" / "allowed.md"
    denied = harness_dir / "sprints" / "denied.md"
    task_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)
    allowed.parent.mkdir(parents=True, exist_ok=True)
    allowed.touch()
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("SOLAR_CODEX_OPERATOR_STATE_ROOT", "/tmp/solar-codex-mount-test")
    monkeypatch.setenv("SOLAR_OPERATOR_STRICT_FS_SCOPE", "1")
    env = codex_operator._codex_exec_env(task_dir)
    env["SOLAR_OPERATOR_ALLOWED_OUTPUTS_JSON"] = json.dumps([str(allowed)])
    env["TEST_ALLOWED_OUTPUT"] = str(allowed)
    env["TEST_DENIED_OUTPUT"] = str(denied)
    script = (
        "import os\n"
        "from pathlib import Path\n"
        "Path(os.environ['TEST_ALLOWED_OUTPUT']).write_text('ok', encoding='utf-8')\n"
        "try:\n"
        "    Path(os.environ['TEST_DENIED_OUTPUT']).write_text('bad', encoding='utf-8')\n"
        "except OSError:\n"
        "    pass\n"
        "else:\n"
        "    raise SystemExit(9)\n"
    )

    command, proof = codex_operator._filesystem_isolated_command(
        [sys.executable, "-c", script], task_dir=task_dir, cwd=work_dir, env=env
    )
    result = subprocess.run(command, env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert proof["mode"] == "mount_namespace+landlock-read"
    assert allowed.read_text(encoding="utf-8") == "ok"
    assert not denied.exists()


@pytest.mark.skipif(os.name == "nt", reason="generated harness shim is a POSIX shell script")
def test_codex_operator_binds_model_shell_to_active_harness(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_active_harness", ROOT / "tools" / "codex_operator.py")
    harness_dir = tmp_path / "clean-harness"
    harness_dir.mkdir()
    (harness_dir / "lib").mkdir()
    (harness_dir / "tools").mkdir()
    harness_cmd = harness_dir / "solar-harness.sh"
    harness_cmd.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'active-harness=%s\\n' \"$HARNESS_DIR\"\n"
        "printf 'args=%s\\n' \"$*\"\n",
        encoding="utf-8",
    )
    harness_cmd.chmod(0o755)
    task_dir = harness_dir / "run" / "operator-results" / "op" / "task"
    task_dir.mkdir(parents=True)
    monkeypatch.setenv("HARNESS_DIR", str(harness_dir))
    monkeypatch.delenv("SOLAR_HARNESS_DIR", raising=False)

    env = codex_operator._codex_exec_env(task_dir)
    shim = task_dir / "cmd-shims" / "solar-harness"

    assert env["HARNESS_DIR"] == str(harness_dir)
    assert env["SOLAR_HARNESS_DIR"] == str(harness_dir)
    assert env["SOLAR_HARNESS_CMD"] == str(shim)
    assert os.access(shim, os.X_OK)
    assert env["PATH"].split(os.pathsep)[0] == str(task_dir / "cmd-shims")
    assert str(harness_dir / "lib") in env["PYTHONPATH"].split(os.pathsep)
    assert str(harness_dir / "tools") in env["PYTHONPATH"].split(os.pathsep)

    completed = subprocess.run(
        [str(shim), "context", "inject", "--node", "N0"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert f"active-harness={harness_dir}" in completed.stdout
    assert "args=context inject --node N0" in completed.stdout


def test_codex_operator_respects_explicit_non_ephemeral(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_no_ephemeral", ROOT / "tools" / "codex_operator.py")
    monkeypatch.setenv("SOLAR_CODEX_OPERATOR_EPHEMERAL", "0")
    cmd = codex_operator._codex_exec_command("gpt-5.5", "medium", str(tmp_path), tmp_path / "last.md")
    assert "--ephemeral" not in cmd


def test_codex_operator_places_requested_live_search_before_exec(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_live_search", ROOT / "tools" / "codex_operator.py")
    monkeypatch.setenv(
        "SOLAR_CODEX_EXTRA_FLAGS",
        "--search -c model_reasoning_effort=high",
    )

    cmd = codex_operator._codex_exec_command("gpt-5.5", "medium", str(tmp_path), tmp_path / "last.md")

    assert cmd[:3] == ["codex", "--search", "exec"]
    assert cmd.count("--search") == 1
    assert "-c" not in cmd


def test_codex_operator_does_not_forward_unrecognized_extra_flags(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_flag_allowlist", ROOT / "tools" / "codex_operator.py")
    monkeypatch.setenv(
        "SOLAR_CODEX_EXTRA_FLAGS",
        "--json --add-dir /tmp/not-authorized-by-the-operator-contract",
    )

    cmd = codex_operator._codex_exec_command("gpt-5.5", "medium", str(tmp_path), tmp_path / "last.md")

    assert cmd[:2] == ["codex", "exec"]
    assert "--json" not in cmd
    assert "--add-dir" not in cmd
    assert "/tmp/not-authorized-by-the-operator-contract" not in cmd


def test_codex_operator_treats_malformed_extra_flags_as_search_disabled(tmp_path, monkeypatch):
    codex_operator = _load_module("codex_operator_contract_malformed_flags", ROOT / "tools" / "codex_operator.py")
    monkeypatch.setenv("SOLAR_CODEX_EXTRA_FLAGS", "'--search")

    cmd = codex_operator._codex_exec_command("gpt-5.5", "medium", str(tmp_path), tmp_path / "last.md")

    assert cmd[:2] == ["codex", "exec"]
    assert "--search" not in cmd
