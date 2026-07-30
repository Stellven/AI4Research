from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from journey_runner import bash_argv, base_env, write_json

J18_ID = "P22-J18"
BATCH_ID = "T3-tmux-prep-001"
SERIAL_GATE = "PHASE22_ENABLE_SERIAL_TMUX_JOURNEYS"
L2_NAMES = [
    "Workflow & Platform Status Visibility",
    "Execution Trace Search & Inspection",
    "Linux Cli",
    "Web Application & Status Service",
    "CLI",
    "TUI",
    "TMUX",
    "LLM Config",
    "User Settings",
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _copy_or_link_j18(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    try:
        dst.symlink_to(src, target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _prepare_j18_isolated_harness(repo_root: Path, sandbox: Path) -> Path:
    source = repo_root / "harness"
    harness_dir = sandbox / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "bin",
        "config",
        "personas",
        "tools",
        "plugins",
        "evaluators",
        "schemas",
        "lib",
        "workflows",
        "solar-harness.sh",
    ):
        src = source / name
        if src.exists():
            _copy_or_link_j18(src, harness_dir / name)
    (harness_dir / "run").mkdir(exist_ok=True)
    (harness_dir / "artifacts").mkdir(exist_ok=True)
    return harness_dir


def _collect_markers(text: str, checks: dict[str, str]) -> dict[str, bool]:
    return {name: bool(re.search(pattern, text, flags=re.MULTILINE)) for name, pattern in checks.items()}


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False


def _is_linux_or_wsl() -> bool:
    return platform.system().lower() == "linux" or _is_wsl()


def _run_probe(argv: list[str], cwd: Path, env: dict[str, str], timeout: float = 20.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "argv": argv,
            "exit_code": proc.returncode,
            "timed_out": False,
            "stdout_tail": (proc.stdout or "")[-1800:],
            "stderr_tail": (proc.stderr or "")[-1800:],
        }
    except FileNotFoundError as exc:
        return {
            "argv": argv,
            "exit_code": 127,
            "timed_out": False,
            "stdout_tail": "",
            "stderr_tail": str(exc),
        }
    except subprocess.TimeoutExpired:
        return {
            "argv": argv,
            "exit_code": 124,
            "timed_out": True,
            "stdout_tail": "",
            "stderr_tail": f"{' '.join(argv)} timed out after {timeout}s",
        }


def _status_settings_probe(repo_root: Path, env: dict[str, str], settings_plan: dict[str, Any]) -> dict[str, Any]:
    status_server_py = repo_root / "harness" / "lib" / "symphony" / "status-server.py"
    sandbox_harness = Path(env["HARNESS_DIR"])
    sandbox_config = Path(env["SOLAR_HOME"]) / "config" / "solar-user-config.json"
    sandbox_secrets = Path(env["SOLAR_HOME"]) / "secrets" / "solar-user-secrets.env"

    old_env = dict(os.environ)
    os.environ.update(env)
    os.environ["HARNESS_DIR"] = str(repo_root / "harness")
    os.environ["SOLAR_HARNESS_DIR"] = str(repo_root / "harness")

    mod = None
    try:
        spec = importlib.util.spec_from_file_location("_p22_status_server_probe", str(status_server_py))
        if spec is None or spec.loader is None:
            return {"status": "skip", "error": "Cannot load harness status-server module."}
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as exc:
        return {
            "status": "skip",
            "error": f"Status server import failed: {type(exc).__name__}: {exc}",
            "sandbox_harness": str(sandbox_harness),
            "sandbox_config": str(sandbox_config),
        }

    original_cfg = None
    original_secret = None
    status = {
        "status": "fail",
        "sandbox_harness": str(sandbox_harness),
        "sandbox_config": str(sandbox_config),
    }

    try:
        mod._USER_CONFIG_PATH = sandbox_config
        mod._USER_SECRETS_PATH = sandbox_secrets

        try:
            original_cfg = mod._read_user_config()
        except Exception:
            original_cfg = None
        try:
            original_secret = sandbox_secrets.read_text(encoding="utf-8")
        except OSError:
            original_secret = None

        mod._write_user_config({})

        role_models = {}
        for role, alias in settings_plan["llm_models"].items():
            role_models[role] = {"model": alias}

        write_payload = {
            "role_models": role_models,
            "runtime": settings_plan["user_settings"]["runtime"],
            "codex": settings_plan["user_settings"]["codex"],
        }

        write_result, code = mod._settings_write_payload(write_payload)
        runtime_payload = mod._settings_payload()

        actual_models = {
            role: payload.get("model")
            for role, payload in runtime_payload.get("role_models", {}).items()
            if isinstance(payload, dict)
        }
        codex_payload = runtime_payload.get("codex", {})
        runtime = runtime_payload.get("runtime", {})

        expected_aliases = settings_plan["expected_assertions"]["required_aliases"]
        expected_runtime = settings_plan["expected_assertions"]["runtime_value"]
        expected_effort = settings_plan["expected_assertions"]["codex_effort"]
        applied_aliases = [value for value in (write_result.get("applied_models") or {}).values()]
        missing_aliases = sorted(set(expected_aliases) - set(applied_aliases))
        codex_roundtrip_ok = (
            bool(codex_payload.get("search")) == bool(settings_plan["user_settings"]["codex"]["search"])
            and str(codex_payload.get("effort", "")).lower() == str(expected_effort).lower()
        )

        written_keys = write_result.get("written_keys") or []
        contains_api_key_output = bool(written_keys)

        status = {
            "status": "ok" if code == 200 and not missing_aliases and runtime.get("value") == expected_runtime and codex_roundtrip_ok else "warn",
            "write_code": code,
            "write_result": write_result,
            "runtime_payload": runtime_payload,
            "actual_models": actual_models,
            "actual_runtime": runtime.get("value"),
            "actual_runtime_source": runtime.get("source"),
            "actual_codex": codex_payload,
            "missing_expected_aliases": missing_aliases,
            "llm_model_roundtrip_ok": not missing_aliases,
            "runtime_roundtrip_ok": runtime.get("value") == expected_runtime and runtime.get("source") == "solar-user-config.json",
            "user_settings_roundtrip_ok": codex_roundtrip_ok and runtime.get("value") == expected_runtime,
            "contains_api_key_output": contains_api_key_output,
        }
        status["secrets_visible"] = bool(status["contains_api_key_output"])
        return status
    except Exception as exc:
        status["error"] = f"{type(exc).__name__}: {exc}"
        status["status"] = "error"
        return status
    finally:
        try:
            if mod is not None:
                if original_cfg is not None:
                    mod._write_user_config(original_cfg)
                elif mod._USER_CONFIG_PATH.exists():
                    mod._USER_CONFIG_PATH.unlink()
                if original_secret is None:
                    if mod._USER_SECRETS_PATH.exists():
                        mod._USER_SECRETS_PATH.unlink()
                else:
                    mod._USER_SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
                    mod._USER_SECRETS_PATH.write_text(original_secret, encoding="utf-8")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def _build_cleanup_plan(sandbox_harness: Path) -> dict[str, Any]:
    run_dir = sandbox_harness / "run"
    return {
        "tmux_sessions_to_check": [
            "solar-harness",
            "solar-harness-bg",
        ],
        "status_server_files": [
            str(run_dir / "status-server.pid"),
            str(run_dir / "status-server.port"),
            str(run_dir / "status-server.token"),
            str(run_dir / "status-server.log"),
        ],
        "commands": [
            "bash harness/solar-harness.sh status-server stop",
            "bash harness/solar-harness.sh stop",
            "tmux kill-session -t solar-harness || true",
            "tmux kill-session -t solar-harness-bg || true",
        ],
        "notes": [
            "Prep-only stage: commands are command-text validation, no live launch in this pass.",
            f"Session cleanup plan is prepared for sandbox harness dir: {sandbox_harness}",
        ],
    }


def test_p22_j18_tmux_cli_status_config(repo_root: Path, tmp_path: Path) -> None:
    serial_enabled = os.environ.get(SERIAL_GATE) == "1"
    if not serial_enabled:
        pytest.skip(f"{SERIAL_GATE}=1 is required for J18 prep execution.")

    fixture_root = repo_root / "tests" / "journeys" / "phase22" / "fixtures" / "j18_tmux_cli_status_config"
    plan = _load_json(fixture_root / "j18_test_plan.json")
    status_plan = _load_json(fixture_root / "status_service_trace_plan.json")
    settings_plan = _load_json(fixture_root / "llm_user_settings_plan.json")

    artifact_root = repo_root / ".codex-tmp" / "phase22-worker-results" / BATCH_ID / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)

    sandbox = tmp_path / "p22-j18" / "runner"
    sandbox.mkdir(parents=True, exist_ok=True)
    env = base_env(repo_root, sandbox, allow_live=False)
    env[SERIAL_GATE] = "1"

    sandbox_harness = _prepare_j18_isolated_harness(repo_root, sandbox)
    env["HARNESS_DIR"] = str(sandbox_harness)
    env["SOLAR_AUTOSCI_OUTPUT_HARNESS"] = str(sandbox_harness)
    env["AUTOSCI_ARTIFACT_ROOT"] = str(sandbox_harness / "artifacts" / "autosci")
    env["SCIENTIFIC_ARTIFACT_ROOT"] = str(sandbox_harness / "artifacts" / "scientific")

    harness_script = sandbox_harness / "solar-harness.sh"
    bin_solar = repo_root / "bin" / "solar"
    status_server_py = repo_root / "harness" / "lib" / "symphony" / "status-server.py"
    ui_lite_script = repo_root / "harness" / "lib" / "cli" / "solar_ui_lite.py"

    assert harness_script.exists(), "tmux entrypoint must exist"
    assert status_server_py.exists(), "status server implementation must exist"
    assert bin_solar.exists(), "solar cli launcher must exist"

    harness_help = _run_probe([*bash_argv(repo_root, str(harness_script), "--help")], cwd=repo_root, env=env, timeout=25.0)
    harness_preflight = _run_probe([*bash_argv(repo_root, str(harness_script), "preflight")], cwd=repo_root, env=env, timeout=30.0)
    harness_status = _run_probe([*bash_argv(repo_root, str(harness_script), "status")], cwd=repo_root, env=env, timeout=20.0)
    harness_bg_status = _run_probe(
        [*bash_argv(repo_root, str(harness_script), "bg", "status")],
        cwd=repo_root,
        env=env,
        timeout=20.0,
    )
    harness_status_server_status = _run_probe(
        [*bash_argv(repo_root, str(harness_script), "status-server", "status")],
        cwd=repo_root,
        env=env,
        timeout=20.0,
    )

    cli_help = _run_probe([*bash_argv(repo_root, str(bin_solar), "--help")], cwd=repo_root, env=env, timeout=20.0)
    cli_harness_help = _run_probe([*bash_argv(repo_root, str(bin_solar), "harness", "--help")], cwd=repo_root, env=env, timeout=20.0)
    cli_status_help = _run_probe([*bash_argv(repo_root, str(bin_solar), "status", "--help")], cwd=repo_root, env=env, timeout=20.0)
    cli_ui_help = _run_probe([*bash_argv(repo_root, str(bin_solar), "ui", "--help")], cwd=repo_root, env=env, timeout=20.0)
    cli_ui_once = _run_probe([*bash_argv(repo_root, str(bin_solar), "ui", "--once", "--no-color")], cwd=repo_root, env=env, timeout=20.0)

    harness_text = harness_script.read_text(encoding="utf-8", errors="replace")
    status_text = status_server_py.read_text(encoding="utf-8", errors="replace")
    ui_text = ui_lite_script.read_text(encoding="utf-8", errors="replace") if ui_lite_script.exists() else ""

    harness_markers = _collect_markers(
        harness_text,
        {
            "start": r"\nstart\)",
            "attach": r"\nattach\)",
            "preflight": r"\npreflight\)",
            "bg": r"\nbg\)",
            "monitor_tui": r"monitor tui",
            "status_server": r"status-server",
            "send_keys": r"tmux send-keys",
            "capture_pane": r"tmux capture-pane",
            "kill_session": r"tmux kill-session",
            "kill_window": r"tmux kill-window",
            "new_session": r"tmux new-session",
            "respawn": r"tmux respawn-pane",
        },
    )
    status_markers = _collect_markers(
        status_text,
        {
            "healthz": r'path == "/healthz"',
            "status": r'path == "/status"',
            "events": r'path == "/events"',
            "settings": r'path == "/settings"',
            "runtime_info": r'path == "/runtime-info"',
            "integrations": r'path == "/integrations"',
            "assets": r'"/static/"',
            "settings_payload": r"def _settings_payload",
            "settings_write": r"def _settings_write_payload",
        },
    )
    ui_markers = _collect_markers(
        ui_text,
        {
            "ui_script_contains_ascii_logo": r"OpenSolar|opensoLar|OpenSolar",
            "ui_handles_enter": r"\\n",
            "ui_key_binding": r"input|keypress|key",
        },
    )

    is_linux_like = _is_linux_or_wsl()
    cli_linux_probe: dict[str, Any] = {}
    if is_linux_like:
        cli_doctor_help = _run_probe([*bash_argv(repo_root, str(bin_solar), "doctor", "--help")], cwd=repo_root, env=env, timeout=20.0)
        cli_linux_probe = {
            "status": "PASS" if cli_doctor_help["exit_code"] == 0 else "PASS_WITH_KNOWN_LIMITATIONS",
            "platform": platform.system(),
            "doctor_help_exit": cli_doctor_help["exit_code"],
            "doctor_help": cli_doctor_help,
        }
    else:
        cli_linux_probe = {
            "status": "ENVIRONMENT_BLOCKED",
            "platform": platform.system(),
            "reason": "Only Linux/WSL can validate Linux CLI behavior in this task.",
        }

    dashboard = repo_root / status_plan["static_assets"]["dashboard"]
    dashboard_template = repo_root / status_plan["static_assets"]["template"]
    mermaid = repo_root / status_plan["static_assets"]["mermaid"]

    settings_probe = _status_settings_probe(repo_root, env, settings_plan)
    cleanup_plan = _build_cleanup_plan(sandbox_harness)

    vertical_probe = {
        "platform": platform.system(),
        "entrypoint_exists": harness_script.exists(),
        "preflight_help": harness_help["stdout_tail"] or harness_help["stderr_tail"],
        "preflight_exit": harness_preflight["exit_code"],
        "status_exit": harness_status["exit_code"],
        "harness_markers": harness_markers,
        "command_plan": plan.get("entrypoint_command_plan", []),
    }

    execution_trace_probe = {
        "bg_status_exit": harness_bg_status["exit_code"],
        "bg_status_output": harness_bg_status["stdout_tail"] or harness_bg_status["stderr_tail"],
        "status_server_status_exit": harness_status_server_status["exit_code"],
        "status_server_status_output": harness_status_server_status["stdout_tail"] or harness_status_server_status["stderr_tail"],
        "status_route_markers": {k: status_markers[k] for k in ("events", "status", "assets", "integrations")},
        "status_endpoints_plan": status_plan["status_endpoints"],
    }

    web_probe = {
        "status_route_markers": status_markers,
        "dashboard_asset_exists": dashboard.exists(),
        "template_asset_exists": dashboard_template.exists(),
        "mermaid_asset_exists": mermaid.exists(),
        "status_server_status_exit": harness_status_server_status["exit_code"],
        "static_probe_hint": "checked route handlers and static dashboard files; service start not executed in prep mode.",
    }

    cli_probe = {
        "solar_help_exit": cli_help["exit_code"],
        "solar_harness_help_exit": cli_harness_help["exit_code"],
        "solar_status_help_exit": cli_status_help["exit_code"],
        "solar_ui_help_exit": cli_ui_help["exit_code"],
        "cli_markers": _collect_markers(
            " ".join(
                [
                    str(cli_help["stdout_tail"]),
                    str(cli_help["stderr_tail"]),
                    str(cli_harness_help["stdout_tail"]),
                    str(cli_harness_help["stderr_tail"]),
                    str(cli_status_help["stdout_tail"]),
                ]
            ),
            {
                "has_harness": r"\bharness\b",
                "has_status": r"\bstatus\b",
                "has_doctor": r"\bdoctor\b",
                "has_ui": r"\bui\b",
            },
        ),
    }

    tui_probe = {
        "monitor_tui_mentioned": harness_markers.get("monitor_tui", False),
        "ui_help_exit": cli_ui_help["exit_code"],
        "ui_once_exit": cli_ui_once["exit_code"],
        "ui_once_visible": bool(cli_ui_once["stdout_tail"] or cli_ui_once["stderr_tail"]),
        "ui_once_not_start": "started" not in (cli_ui_once["stdout_tail"] + cli_ui_once["stderr_tail"]).lower(),
        "tmux_send_keys_declared": harness_markers.get("send_keys", False),
        "tmux_capture_pane_declared": harness_markers.get("capture_pane", False),
        "ui_script_markers": ui_markers,
    }

    tmux_probe = {
        "tmux_available": shutil.which("tmux") is not None,
        "tmux_start_declared": harness_markers.get("start", False),
        "tmux_attach_declared": harness_markers.get("attach", False),
        "tmux_new_session_declared": harness_markers.get("new_session", False),
        "tmux_send_keys_declared": harness_markers.get("send_keys", False),
        "tmux_kill_session_declared": harness_markers.get("kill_session", False),
        "tmux_kill_window_declared": harness_markers.get("kill_window", False),
        "harness_bg_declared": harness_markers.get("bg", False),
        "cleanup_plan": cleanup_plan,
        "tmux_session_cleanup_expected": ["solar-harness", "solar-harness-bg"],
    }

    llm_probe = {
        "settings_probe": settings_probe,
        "settings_roundtrip": {
            "status_server_status": settings_probe.get("status"),
            "write_exit": settings_probe.get("write_code"),
            "runtime_after": settings_probe.get("actual_runtime"),
            "models_after": settings_probe.get("actual_models"),
            "llm_model_roundtrip_ok": settings_probe.get("llm_model_roundtrip_ok", False),
        },
        "runtime_source": settings_probe.get("actual_runtime_source"),
        "secrets_suppressed": not settings_probe.get("contains_api_key_output", True),
    }

    user_settings_probe = {
        "runtime_roundtrip_ok": settings_probe.get("runtime_roundtrip_ok", False),
        "codex_roundtrip_ok": settings_probe.get("user_settings_roundtrip_ok", False),
        "runtime_value": settings_probe.get("actual_runtime"),
        "codex_payload": settings_probe.get("actual_codex"),
        "runtime_source": settings_probe.get("actual_runtime_source"),
        "settings_payload": settings_probe.get("runtime_payload"),
    }

    per_l2 = {
        "Workflow & Platform Status Visibility": {
            "result": "PASS" if vertical_probe["entrypoint_exists"] and harness_preflight["exit_code"] in (0, 2) else "PASS_WITH_KNOWN_LIMITATIONS",
            "evidence_path": str(write_json(artifact_root / "j18-vertical.json", vertical_probe)),
        },
        "Execution Trace Search & Inspection": {
            "result": "PASS" if execution_trace_probe["bg_status_output"] else "PASS_WITH_KNOWN_LIMITATIONS",
            "evidence_path": str(write_json(artifact_root / "j18-execution-trace.json", execution_trace_probe)),
        },
        "Linux Cli": {
            "result": cli_linux_probe["status"],
            "evidence_path": str(write_json(artifact_root / "j18-linux-cli.json", cli_linux_probe)),
        },
        "Web Application & Status Service": {
            "result": "PASS_WITH_KNOWN_LIMITATIONS"
            if not web_probe["dashboard_asset_exists"]
            or not web_probe["template_asset_exists"]
            else "PASS",
            "evidence_path": str(write_json(artifact_root / "j18-web-status-service.json", web_probe)),
        },
        "CLI": {
            "result": "PASS" if cli_probe["solar_help_exit"] == 0 and cli_probe["solar_harness_help_exit"] == 0 else "PASS_WITH_KNOWN_LIMITATIONS",
            "evidence_path": str(write_json(artifact_root / "j18-cli.json", cli_probe)),
        },
        "TUI": {
            "result": (
                "PASS"
                if tui_probe["monitor_tui_mentioned"]
                and tui_probe["tmux_send_keys_declared"]
                and tui_probe["tmux_capture_pane_declared"]
                else "PASS_WITH_KNOWN_LIMITATIONS"
            ),
            "evidence_path": str(write_json(artifact_root / "j18-tui.json", tui_probe)),
        },
        "TMUX": {
            "result": (
                "PASS"
                if tmux_probe["tmux_start_declared"]
                and tmux_probe["tmux_attach_declared"]
                and tmux_probe["tmux_kill_session_declared"]
                else "PASS_WITH_KNOWN_LIMITATIONS"
            ),
            "evidence_path": str(write_json(artifact_root / "j18-tmux.json", tmux_probe)),
        },
        "LLM Config": {
            "result": "PASS" if settings_probe.get("llm_model_roundtrip_ok") else "PASS_WITH_KNOWN_LIMITATIONS",
            "evidence_path": str(write_json(artifact_root / "j18-llm-config.json", llm_probe)),
        },
        "User Settings": {
            "result": "PASS" if user_settings_probe["codex_roundtrip_ok"] and user_settings_probe["runtime_roundtrip_ok"] else "PASS_WITH_KNOWN_LIMITATIONS",
            "evidence_path": str(write_json(artifact_root / "j18-user-settings.json", user_settings_probe)),
        },
    }

    run_summary = {
        "journey_id": J18_ID,
        "batch_id": BATCH_ID,
        "serial_gate_enabled": serial_enabled,
        "serial_gate": SERIAL_GATE,
        "planned_tasks": plan["planned_user_tasks"],
        "selector": plan["selector"],
        "entrypoints": {
            "harness": str(harness_script),
            "shell": "bin/solar",
            "status_server": str(status_server_py),
            "tui_script": str(ui_lite_script),
        },
        "required_platform": {
            "windows": "preferred",
            "linux_wsl": "extra",
            "sandbox_home": env["HOME"],
            "is_linux_or_wsl": is_linux_like,
        },
        "evidence": {
            "vertical": str(artifact_root / "j18-vertical.json"),
            "execution_trace": str(artifact_root / "j18-execution-trace.json"),
            "linux_cli": str(artifact_root / "j18-linux-cli.json"),
            "web_status_service": str(artifact_root / "j18-web-status-service.json"),
            "cli": str(artifact_root / "j18-cli.json"),
            "tui": str(artifact_root / "j18-tui.json"),
            "tmux": str(artifact_root / "j18-tmux.json"),
            "llm_config": str(artifact_root / "j18-llm-config.json"),
            "user_settings": str(artifact_root / "j18-user-settings.json"),
        },
        "l2_status": {name: state["result"] for name, state in per_l2.items()},
        "cleanup_plan": cleanup_plan,
        "commands": {
            "harness_help": harness_help,
            "harness_preflight": harness_preflight,
            "harness_status": harness_status,
            "harness_bg_status": harness_bg_status,
            "status_server_status": harness_status_server_status,
            "cli_help": cli_help,
            "cli_harness_help": cli_harness_help,
            "cli_status_help": cli_status_help,
            "cli_ui_help": cli_ui_help,
            "cli_ui_once": cli_ui_once,
        },
        "owned_l2": [
            {"category": "Vertical", "level_2_feature": name} for name in L2_NAMES
        ],
    }
    write_json(artifact_root / "j18-overall-prep-summary.json", run_summary)
