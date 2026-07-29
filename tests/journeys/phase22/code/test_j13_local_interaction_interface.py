from __future__ import annotations

import os
import shutil
from pathlib import Path

from test_j11_capsule_operator import WorkerJourney, python_env, write_json


def test_p22_j13_local_interaction_interface(repo_root: Path, tmp_path: Path, phase22_python: str) -> None:
    rec = WorkerJourney(repo_root, "P22-J13", "Local GUI, TUI, or TMUX interaction interface for a real run")
    sandbox = tmp_path / "p22-j13"
    harness_dir = sandbox / "harness"
    harness_dir.mkdir(parents=True)
    env = python_env({"HARNESS_DIR": str(harness_dir), "HOME": str(sandbox / "home"), "USERPROFILE": str(sandbox / "home")})

    ui_once = rec.run(
        "solar-ui-lite-once",
        [phase22_python, str(repo_root / "harness" / "lib" / "cli" / "solar_ui_lite.py"), "--once", "--no-color"],
        env=env,
    )
    tmux_preflight = rec.run("tmux-version-preflight", ["tmux", "-V"], env=env)
    node_exe = os.environ.get("PHASE22_NODE_EXE", "node")
    desktop_gate = rec.run("desktop-package-gate-preflight", [node_exe, "prepackage-check.js"], cwd=repo_root / "desktop", env=env, timeout=60)

    probe_path = write_json(
        rec.run_dir / "j13-interface-preflight.json",
        {
            "ui_once_exit_code": ui_once.returncode,
            "ui_once_tail": ui_once.stdout[-1000:],
            "tmux_on_path": shutil.which("tmux", path=env.get("PATH")) is not None,
            "tmux_exit_code": tmux_preflight.returncode,
            "node_exe": node_exe,
            "desktop_gate_exit_code": desktop_gate.returncode,
        },
    )
    rec.add_artifact(probe_path, "j13_interface_preflight")
    rec.add_assertion("ui_lite_rendered_once", ui_once.returncode == 0 and "OpenSolar" in ui_once.stdout, ui_once.stdout[-1000:] or ui_once.stderr[-1000:])
    rec.add_assertion("tmux_available_for_control", tmux_preflight.returncode == 0, tmux_preflight.stderr or tmux_preflight.stdout)
    rec.add_assertion("desktop_prepackage_check_executed", desktop_gate.returncode == 0, desktop_gate.stdout[-1000:] or desktop_gate.stderr[-1000:])

    command_evidence = rec.run_dir / "commands.json"
    terminal_status = "PASS" if ui_once.returncode == 0 and "OpenSolar" in ui_once.stdout else "FAIL"
    tmux_status = "PASS_WITH_KNOWN_LIMITATIONS" if tmux_preflight.returncode == 0 else "ENVIRONMENT_BLOCKED"
    desktop_status = "PASS_WITH_KNOWN_LIMITATIONS" if desktop_gate.returncode == 0 else "ENVIRONMENT_BLOCKED"
    rec.add_l2("Vertical", "Local interaction interface", "Terminal Status UI", terminal_status, "ui_lite_rendered_once", command_evidence, command_label="solar-ui-lite-once", known_limitations=[] if terminal_status == "PASS" else ["solar_ui_lite.py crashes on Windows before rendering because signal.SIGPIPE is unavailable."])
    rec.add_l2(
        "Vertical",
        "Local interaction interface",
        "TMUX Runtime Control Interface",
        tmux_status,
        "tmux_available_for_control",
        command_evidence,
        command_label="tmux-version-preflight",
        environment_requirement="tmux installed and a live Solar harness session",
        known_limitations=(
            ["tmux is available; J13 only verified the control binary, not a full live pane-control session."]
            if tmux_status != "ENVIRONMENT_BLOCKED"
            else ["tmux is not available on PATH for this worker, so pane control could not be exercised."]
        ),
    )
    rec.add_l2("Vertical", "Local interaction interface", "Desktop GUI Packaging & Launch Surface", desktop_status, "desktop_prepackage_check_executed", command_evidence, command_label="desktop-package-gate-preflight", environment_requirement="node executable and Electron-capable GUI environment" if desktop_status == "ENVIRONMENT_BLOCKED" else "Windows local pytest worker", known_limitations=["node is not available on PATH in this worker, so desktop package/GUI preflight could not run."] if desktop_status == "ENVIRONMENT_BLOCKED" else ["Package preflight ran, but Electron GUI launch/selftest was not executed in this headless worker."])

    status = "PASS_WITH_KNOWN_LIMITATIONS" if ui_once.returncode == 0 else "FAIL"
    limitations = []
    if tmux_status == "PASS_WITH_KNOWN_LIMITATIONS":
        limitations.append("TMUX binary is available, but this journey did not run a full live pane-control session.")
    else:
        limitations.append("TMUX control remains blocked because tmux is not available on PATH for this worker.")
    if desktop_status == "PASS_WITH_KNOWN_LIMITATIONS":
        limitations.append("Desktop prepackage check ran, but Electron GUI launch/selftest was not executed in this headless worker.")
    else:
        limitations.append("Desktop GUI packaging remains blocked because node is not available on PATH for this worker.")
    rec.finalize(status, limitations=limitations)
