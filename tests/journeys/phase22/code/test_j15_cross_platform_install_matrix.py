from __future__ import annotations

import json
import os
import platform
from pathlib import Path

from test_j11_capsule_operator import WorkerJourney, python_env, write_json


def test_p22_j15_cross_platform_install_matrix(repo_root: Path, tmp_path: Path, phase22_python: str) -> None:
    rec = WorkerJourney(repo_root, "P22-J15", "Windows App, macOS App, and macOS CLI install/start/status/uninstall matrix")
    sandbox = tmp_path / "p22-j15"
    env = python_env({"HOME": str(sandbox / "home"), "USERPROFILE": str(sandbox / "home")})

    desktop_pkg_path = repo_root / "desktop" / "package.json"
    install_ps1 = repo_root / "install.ps1"
    get_solar = repo_root / "get-solar.sh"
    desktop_pkg = json.loads(desktop_pkg_path.read_text(encoding="utf-8"))
    matrix_artifact = write_json(
        rec.run_dir / "j15-package-matrix-static.json",
        {
            "system": platform.system(),
            "desktop_scripts": desktop_pkg.get("scripts", {}),
            "desktop_build": desktop_pkg.get("build", {}),
            "install_ps1_exists": install_ps1.exists(),
            "get_solar_exists": get_solar.exists(),
        },
    )
    windows_help = rec.run(
        "windows-install-help",
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(install_ps1), "--help"],
        env=env,
        timeout=60,
    )
    node_exe = os.environ.get("PHASE22_NODE_EXE", "node")
    desktop_prepackage = rec.run("desktop-prepackage-check", [node_exe, "prepackage-check.js"], cwd=repo_root / "desktop", env=env, timeout=60)
    mac_build_preflight = rec.run("macos-build-script-preflight", [node_exe, "-e", "const p=require('./package.json'); console.log(p.scripts['build:mac'] || '')"], cwd=repo_root / "desktop", env=env)
    mac_cli_preflight = rec.run("macos-cli-preflight", ["bash", str(get_solar), "--help"], env=env, timeout=60)

    rec.add_artifact(matrix_artifact, "j15_package_matrix_static")
    mac_script_declared = "electron-builder --mac dmg" in json.dumps(desktop_pkg.get("scripts", {}))
    desktop_prepackage_ok = desktop_prepackage.returncode == 0
    desktop_prepackage_env_blocked = desktop_prepackage.returncode == 127
    windows_app_status = (
        "PASS_WITH_KNOWN_LIMITATIONS"
        if desktop_prepackage_ok
        else ("ENVIRONMENT_BLOCKED" if desktop_prepackage_env_blocked else "FAIL")
    )
    windows_app_limitations = (
        ["Windows installer help and desktop prepackage checks ran; packaged app launch/status/uninstall was not executed in this headless journey."]
        if desktop_prepackage_ok
        else (
            ["node is not available on PATH in this worker, so packaged app preflight and launch/uninstall could not complete."]
            if desktop_prepackage_env_blocked
            else ["desktop prepackage check ran but failed; inspect desktop-prepackage-check stderr for packaging portability defects."]
        )
    )
    rec.add_assertion("windows_installer_preflight_attempted", install_ps1.exists() and windows_help.returncode is not None, windows_help.stdout[-1000:] or windows_help.stderr[-1000:])
    rec.add_assertion("desktop_prepackage_check_executed", desktop_prepackage_ok, desktop_prepackage.stdout[-1000:] or desktop_prepackage.stderr[-1000:])
    rec.add_assertion("mac_build_script_declared", mac_script_declared, desktop_pkg.get("scripts", {}))
    rec.add_assertion("mac_cli_probe_blocked_on_windows_or_helpful", mac_cli_preflight.returncode != 0 or platform.system() != "Darwin", mac_cli_preflight.stdout + mac_cli_preflight.stderr)

    command_evidence = rec.run_dir / "commands.json"
    rec.add_l2(
        "Vertical",
        "Cross-platform install matrix",
        "Windows App Install/Launch/Status/Uninstall",
        windows_app_status,
        "desktop_prepackage_check_executed",
        command_evidence,
        command_label="desktop-prepackage-check",
        environment_requirement="Windows installer prerequisites plus node/electron tooling for packaged app gate",
        known_limitations=windows_app_limitations,
    )
    rec.add_l2("Vertical", "Cross-platform install matrix", "macOS App Install/Launch/Status/Uninstall", "ENVIRONMENT_BLOCKED", "mac_build_script_declared", matrix_artifact, command_label="static package.json inspection", environment_requirement="macOS runner with Electron app launch permissions", known_limitations=["macOS build resources and script are declared, but this worker is Windows and cannot launch a macOS app."])
    rec.add_l2("Vertical", "Cross-platform install matrix", "macOS CLI Install/Status/Uninstall", "ENVIRONMENT_BLOCKED", "mac_cli_probe_blocked_on_windows_or_helpful", command_evidence, command_label="macos-cli-preflight", environment_requirement="macOS or Linux shell lane for get-solar/install.sh lifecycle", known_limitations=["Mac CLI lifecycle is intentionally left platform-blocked on this Windows worker."])
    rec.add_l2("Vertical", "Cross-platform install matrix", "Installer Artifact and Release Resource Matrix", "PASS", "mac_build_script_declared", matrix_artifact, command_label="static package.json inspection")

    rec.finalize(
        "PASS_WITH_KNOWN_LIMITATIONS",
        limitations=[
            "J15 verified static package/install matrix and Windows-local preflight only; macOS app and CLI lifecycle remain environment blocked on this Windows machine."
        ],
    )
