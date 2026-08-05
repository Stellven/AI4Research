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
    assert 'cli_auth_credentials_store="file"' in cmd
    assert "--cd" in cmd
    assert str(tmp_path) in cmd


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

    command, proof = codex_operator._filesystem_isolated_command(
        ["codex", "exec", "-"], task_dir=task_dir, cwd=work_dir, env=env
    )

    assert command[0] == sys.executable
    assert command[1].endswith("landlock_exec.py")
    assert command[-4:] == ["--", "codex", "exec", "-"]
    assert proof["mode"] == "landlock"
    assert proof["strict"] is True
    assert str(harness_dir.resolve()) in proof["read_only"]
    assert str(harness_dir.resolve()) not in proof["read_write"]
    assert str(work_dir.resolve()) in proof["read_write"]
    assert str(task_dir.resolve()) in proof["read_write"]
    assert str(exact_handoff.resolve()) in proof["read_write"]
    assert str(tmp_path.resolve()) not in proof["read_write"]
    assert str(Path("/etc/resolv.conf").resolve()) in proof["read_only"]
    sandbox_codex_home = Path(env["CODEX_HOME"])
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
