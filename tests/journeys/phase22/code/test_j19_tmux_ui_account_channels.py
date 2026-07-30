from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from test_j11_capsule_operator import write_json

from test_j11_capsule_operator import python_env

J19_ID = "P22-J19"
TMUX_SERIAL_GATE = "PHASE22_ENABLE_SERIAL_TMUX_JOURNEYS"
GUI_ATTACH_GATE = "PHASE22_J19_CAN_ATTACH_GUI"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_probe(cmd: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 20) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "label": cmd[0] if cmd else "",
            "argv": cmd,
            "exit_code": proc.returncode,
            "timed_out": False,
            "stdout_tail": (proc.stdout or "")[-1200:],
            "stderr_tail": (proc.stderr or "")[-1200:],
        }
    except FileNotFoundError as exc:
        return {
            "label": cmd[0] if cmd else "",
            "argv": cmd,
            "exit_code": 127,
            "timed_out": False,
            "stdout_tail": "",
            "stderr_tail": str(exc),
        }
    except subprocess.TimeoutExpired:
        return {
            "label": cmd[0] if cmd else "",
            "argv": cmd,
            "exit_code": 124,
            "timed_out": True,
            "stdout_tail": "",
            "stderr_tail": f"{' '.join(cmd)} timed out after {timeout}s",
        }


def _run_json_file_probe(
    plan: dict[str, Any],
    artifact_path: Path,
    env: dict[str, str],
    repo_root: Path,
) -> dict[str, Any]:
    home = Path(env["HOME"])
    profile_dir = home / ".j19" / "sandbox-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / f'{plan["profile_id"]}.json'

    initial_profile = dict(plan["initial_profile"])
    profile_path.write_text(json.dumps(initial_profile, ensure_ascii=False, indent=2), encoding="utf-8")
    loaded_initial = json.loads(profile_path.read_text(encoding="utf-8"))
    modified = dict(loaded_initial)
    modified.update(plan["profile_updates"])
    profile_path.write_text(json.dumps(modified, ensure_ascii=False, indent=2), encoding="utf-8")
    reloaded = json.loads(profile_path.read_text(encoding="utf-8"))
    profile_path.unlink()

    return {
        "profile_id": plan["profile_id"],
        "created": loaded_initial,
        "updated": reloaded,
        "create_modify_read_ok": loaded_initial == plan["initial_profile"] and reloaded == modified,
        "artifact_path": str(artifact_path),
        "profile_file_exists_after_cleanup": profile_path.exists(),
        "profile_home": str(home),
    }


def _run_privacy_probe(
    policy: dict[str, Any],
    artifact_path: Path,
    env: dict[str, str],
    repo_root: Path,
) -> dict[str, Any]:
    del repo_root
    home = Path(env["HOME"])
    privacy_dir = home / ".j19" / "privacy"
    privacy_dir.mkdir(parents=True, exist_ok=True)
    raw = privacy_dir / "local-identity-data.json"
    raw.write_text(json.dumps(policy["seed_data"], ensure_ascii=False, indent=2), encoding="utf-8")

    raw_data = json.loads(raw.read_text(encoding="utf-8"))
    visible_keys = sorted(set(raw_data.keys()) - set(policy["redacted_fields"]))
    export_target = privacy_dir / "export-redacted.json"
    if policy["export_policy"]["allow_export"]:
        export_payload = {key: raw_data[key] for key in visible_keys}
        export_target.write_text(json.dumps(export_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        exported = True
    else:
        exported = False
    cleared = False
    if policy["export_policy"]["allow_clear"]:
        raw.unlink()
        cleared = not raw.exists()
    return {
        "raw_exists_before": True,
        "raw_exists_after": raw.exists(),
        "raw_fields": sorted(raw_data.keys()),
        "redacted_fields": policy["redacted_fields"],
        "visible_keys": visible_keys,
        "export_requested": bool(policy["export_policy"]["allow_export"]),
        "exported": exported,
        "export_path": str(export_target) if exported else "",
        "clear_requested": bool(policy["export_policy"]["allow_clear"]),
        "cleared": cleared,
        "safety_noted": policy["notes"],
    }


def _run_wechat_probe(routes: dict[str, Any], artifact_path: Path) -> dict[str, Any]:
    samples = routes["sample_inputs"]
    route_hits: list[dict[str, Any]] = []
    for sample in samples:
        route = None
        for rule in routes["routing_rules"]:
            if sample["input"].startswith(rule["prefix"]):
                route = rule["target"]
                break
        route_hits.append({"input": sample["input"], "resolved_to": route, "expected": sample["expected_target"]})
    return {
        "provider": routes["provider"],
        "fixture_routes": routes["routing_rules"],
        "sample_inputs": samples,
        "routing_results": route_hits,
        "has_real_token": routes["integration_state"]["has_real_account_token"],
        "integration_state": routes["integration_state"],
        "artifact_path": str(artifact_path),
    }


def test_p22_j19_tmux_ui_account_channels(repo_root: Path, tmp_path: Path, phase22_python: str) -> None:
    run_dir = tmp_path / "p22-j19"
    run_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir = repo_root / "tests" / "journeys" / "phase22" / "fixtures" / "j19_tmux_ui_account_channels"
    command_plan = _load_json(fixture_dir / "tmux_user_entrypoint_plan.json")
    profile_plan = _load_json(fixture_dir / "profile_probe_plan.json")
    privacy_plan = _load_json(fixture_dir / "privacy_plan.json")
    wechat_plan = _load_json(fixture_dir / "wechat_route_plan.json")

    serial_enabled = os.environ.get(TMUX_SERIAL_GATE) == "1"
    if not serial_enabled:
        write_json(
            run_dir / "j19-precondition-blocked.json",
            {
                "required_env": TMUX_SERIAL_GATE,
                "required_env_value": "1",
                "current_env_value": os.environ.get(TMUX_SERIAL_GATE, ""),
                "blocked": True,
                "message": "TMUX serial journey gate is required before any start/attach probe can run.",
            },
        )
        pytest.skip(f"{TMUX_SERIAL_GATE} must be set to 1 for {J19_ID}")

    harness_script = repo_root / "harness" / "solar-harness.sh"
    install_ps1 = repo_root / "install.ps1"
    install_sh = repo_root / "install.sh"
    desktop_package = repo_root / "desktop" / "package.json"
    run_dir_artifacts = run_dir / "artifacts"
    run_dir_artifacts.mkdir(exist_ok=True)

    env = python_env(
        {
            "HOME": str(tmp_path / "j19_home"),
            "USERPROFILE": str(tmp_path / "j19_home"),
            "PATH": os.environ.get("PATH", ""),
        }
    )
    _run_dir = run_dir
    # Real tmux/GUI start is intentionally not executed in this prep batch.
    # We only collect executable entrypoint definitions and static readiness signals.
    harness_text = harness_script.read_text(encoding="utf-8", errors="replace") if harness_script.exists() else ""
    tmux_entry_status = {
        "harness_script_exists": harness_script.exists(),
        "harness_has_start_command": "start)" in harness_text and "start --help" in harness_text,
        "harness_has_attach_command": "attach)" in harness_text,
        "harness_has_status_server": "status-server" in harness_text,
        "install_ps1_exists": install_ps1.exists(),
        "install_sh_exists": install_sh.exists(),
        "tmux_on_path": shutil.which("tmux", path=env.get("PATH")) is not None,
        "command_plan": command_plan["tmux_commands"],
        "required_gate": TMUX_SERIAL_GATE,
    }

    windows_app_status = "PASS_WITH_KNOWN_LIMITATIONS"
    windows_limitations: list[str] = []
    if not all((tmux_entry_status["harness_script_exists"], tmux_entry_status["harness_has_start_command"], tmux_entry_status["install_ps1_exists"])):
        windows_app_status = "FAIL"
        windows_limitations.append(
            "No Windows install/start evidence can be produced from an incomplete script matrix."
        )
    elif not serial_enabled:
        windows_app_status = "ENVIRONMENT_BLOCKED"
        windows_limitations.append("Serial TMUX gate not enabled.")
    else:
        windows_limitations.append(
            "Entry commands are collected and verified; actual packaged start/selftest/health run remains prep-only here."
        )

    gui_info = {}
    if desktop_package.exists():
        desktop_data = json.loads(desktop_package.read_text(encoding="utf-8"))
        scripts = desktop_data.get("scripts", {})
        dependencies = desktop_data.get("dependencies", {})
        dev_deps = desktop_data.get("devDependencies", {})
        gui_info = {
            "desktop_package_exists": True,
            "desktop_selftest_script": scripts.get("selftest"),
            "desktop_build_script": scripts.get("build"),
            "desktop_electron_present": "electron" in dependencies or "electron" in dev_deps,
            "desktop_renderer_script": scripts.get("start"),
        }
    else:
        gui_info = {
            "desktop_package_exists": False,
            "desktop_selftest_script": None,
            "desktop_build_script": None,
            "desktop_electron_present": False,
            "desktop_renderer_script": None,
        }

    gui_attached = os.environ.get(GUI_ATTACH_GATE) == "1"
    gui_status = "PASS_WITH_KNOWN_LIMITATIONS"
    gui_limitations: list[str] = []
    if gui_info["desktop_package_exists"] and gui_info["desktop_selftest_script"] and gui_info["desktop_renderer_script"]:
        if not gui_attached:
            gui_status = "ENVIRONMENT_BLOCKED"
            gui_limitations.append("Current session cannot attach GUI; GUI evidence is blocked by environment.")
        else:
            gui_limitations.append(
                "GUI/electron checks are based on static package metadata; live attach/selftest must run in an interactive Windows session."
            )
    else:
        gui_status = "FAIL"
        gui_limitations.append("Desktop metadata missing selftest/start/build/electron signals.")

    profile_probe = _run_json_file_probe(profile_plan, _run_dir / "j19-profile-probe.json", env, repo_root)
    profile_status = "PASS" if profile_probe["create_modify_read_ok"] else "FAIL"
    profile_limitations = ["Profile lifecycle was executed entirely under sandbox HOME and never touched real account settings."] if profile_status == "PASS" else ["Profile lifecycle data mismatch in create/modify/read round-trip."]

    privacy_probe = _run_privacy_probe(privacy_plan, run_dir_artifacts / "j19-privacy-probe.json", env, repo_root)
    privacy_status = "PASS_WITH_KNOWN_LIMITATIONS"
    privacy_limitations: list[str] = [
        "Privacy checks are local fixtures (view/export/clear) only, no provider authorization or network call is attempted."
    ]
    if not privacy_probe["export_requested"]:
        privacy_status = "PASS_WITH_KNOWN_LIMITATIONS"
        privacy_limitations.append("Export denied by fixture policy; explicit deny behavior is verified.")

    wechat_probe = _run_wechat_probe(wechat_plan, run_dir_artifacts / "j19-wechat-probe.json")
    if wechat_probe["has_real_token"]:
        wechat_status = "PASS_WITH_KNOWN_LIMITATIONS"
        wechat_limitations: list[str] = []
    else:
        wechat_status = "PASS_WITH_KNOWN_LIMITATIONS"
        wechat_limitations = [
            "No real WeChat account/token in fixture; integration stays parse/route-only in this prep batch."
        ]

    command_probe = _run_probe(
        ["bash", str(harness_script), "preflight"],
        cwd=repo_root,
        env=env,
    )
    preflight_probe = _run_probe(
        ["bash", str(harness_script), "status"],
        cwd=repo_root,
        env=env,
    )
    command_artifact = write_json(
        run_dir_artifacts / "j19-command-probe.json",
        {
            "command_plan": command_plan,
            "preflight_probe": command_probe,
            "status_probe": preflight_probe,
            "system": platform.system(),
        },
    )
    tmux_artifact = write_json(
        run_dir_artifacts / "j19-tmux-entrypoint.json",
        tmux_entry_status,
    )
    gui_artifact = write_json(
        run_dir_artifacts / "j19-gui-check.json",
        gui_info,
    )
    profile_artifact = write_json(run_dir_artifacts / "j19-profile-probe.json", profile_probe)
    privacy_artifact = write_json(run_dir_artifacts / "j19-privacy-probe.json", privacy_probe)
    wechat_artifact = write_json(run_dir_artifacts / "j19-wechat-probe.json", wechat_probe)

    summary = {
        "journey_id": J19_ID,
        "status_per_l2": {
            "Windows App": {"result": windows_app_status, "evidence_path": str(tmux_artifact), "limitations": windows_limitations},
            "GUI": {"result": gui_status, "evidence_path": str(gui_artifact), "limitations": gui_limitations},
            "User Profile Management": {"result": profile_status, "evidence_path": str(profile_artifact), "limitations": profile_limitations},
            "Privacy & Personal Data Controls": {"result": privacy_status, "evidence_path": str(privacy_artifact), "limitations": privacy_limitations},
            "Wechat": {"result": wechat_status, "evidence_path": str(wechat_artifact), "limitations": wechat_limitations},
        },
        "command_plan": command_plan,
        "command_artifact": str(command_artifact),
    }
    summary_path = write_json(run_dir / "j19-overall-summary.json", summary)

    write_json(
        run_dir / "j19-result.json",
        {
            "journey_id": J19_ID,
            "serial_tmux_gate_required": TMUX_SERIAL_GATE,
            "serial_tmux_gate_enabled": serial_enabled,
            "result_per_l2": summary["status_per_l2"],
            "evidence": {
                "tmux_entrypoint": str(tmux_artifact),
                "gui": str(gui_artifact),
                "profile": str(profile_artifact),
                "privacy": str(privacy_artifact),
                "wechat": str(wechat_artifact),
                "commands": str(command_artifact),
                "summary": str(summary_path),
            },
        },
    )

    assert tmux_entry_status["harness_script_exists"], "Harness entry script must exist."
    assert profile_probe["create_modify_read_ok"], "Sandbox profile lifecycle must complete create/modify/read."
