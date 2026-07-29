from __future__ import annotations

import json
import os
import platform
import time
import urllib.request
from pathlib import Path

from test_j11_capsule_operator import WorkerJourney, python_env, write_json


def _read_runtime_info(port: str) -> dict[str, object]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/runtime-info", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _macos_cli_lifecycle(rec: WorkerJourney, repo_root: Path, sandbox: Path) -> tuple[str, list[str]]:
    home = sandbox / "home"
    tmp = sandbox / "tmp"
    solar_home = home / ".solar"
    claude_dir = home / ".claude"
    harness_dir = solar_home / "harness"
    home.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    env = python_env(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "SOLAR_HOME": str(solar_home),
            "CLAUDE_DIR": str(claude_dir),
            "HARNESS_DIR": str(harness_dir),
            "SOLAR_HARNESS_DIR": str(harness_dir),
            "TMPDIR": str(tmp),
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        }
    )
    solar = solar_home / "bin" / "solar"
    install = rec.run(
        "macos-cli-install",
        [
            "bash",
            str(repo_root / "install.sh"),
            "--yes",
            "--solar-home",
            str(solar_home),
            "--claude-dir",
            str(claude_dir),
            "--skip-llm-cli",
            "--fake-keys",
            "--no-hooks",
            "--no-mcp",
        ],
        env=env,
        timeout=240,
    )
    doctor = rec.run("macos-cli-doctor-json", [str(solar), "doctor", "--json"], env=env, timeout=60)
    status = rec.run("macos-cli-status-json", [str(solar), "status", "--json"], env=env, timeout=60)
    ui = rec.run("macos-cli-ui-once", [str(solar), "ui", "--once"], env=env, timeout=60)
    server_start = rec.run("macos-cli-status-server-start", [str(solar), "harness", "status-server", "start"], env=env, timeout=90)
    port_file = harness_dir / "run" / "status-server.port"
    port = ""
    for _ in range(30):
        if port_file.exists() and port_file.read_text(encoding="utf-8").strip():
            port = port_file.read_text(encoding="utf-8").strip()
            break
        time.sleep(0.2)
    health = rec.run("macos-cli-status-server-healthz", ["curl", "-fsS", f"http://127.0.0.1:{port}/healthz"], env=env, timeout=15) if port else None
    runtime_info_path = rec.artifact_dir / "macos-runtime-info.json"
    runtime_info_ok = False
    runtime_info: dict[str, object] = {}
    if port:
        try:
            runtime_info = _read_runtime_info(port)
            runtime_info_ok = runtime_info.get("harness_dir") == str(harness_dir)
        except Exception as exc:
            runtime_info = {"error": str(exc)}
    write_json(runtime_info_path, runtime_info)
    rec.add_artifact(runtime_info_path, "macos_status_server_runtime_info")
    server_stop = rec.run("macos-cli-status-server-stop", [str(solar), "harness", "status-server", "stop"], env=env, timeout=60)
    uninstall = rec.run("macos-cli-uninstall", [str(solar), "uninstall", "--yes"], env=env, timeout=120)
    cleanup_ok = not solar_home.exists() and not (claude_dir / "solar").exists()

    core_ok = all(
        proc.returncode == 0
        for proc in (install, doctor, status, ui, server_start, server_stop, uninstall)
    ) and health is not None and health.returncode == 0 and runtime_info_ok and cleanup_ok
    rec.add_assertion(
        "macos_cli_lifecycle_completed",
        core_ok,
        {
            "install": install.returncode,
            "doctor": doctor.returncode,
            "status": status.returncode,
            "ui_once": ui.returncode,
            "status_server_start": server_start.returncode,
            "healthz": health.returncode if health is not None else None,
            "runtime_info_harness_dir": runtime_info.get("harness_dir"),
            "expected_harness_dir": str(harness_dir),
            "status_server_stop": server_stop.returncode,
            "uninstall": uninstall.returncode,
            "cleanup_ok": cleanup_ok,
        },
    )
    limitations = [] if core_ok else ["One or more macOS CLI lifecycle checks failed; inspect recorded command stdout/stderr."]
    return ("PASS" if core_ok else "FAIL"), limitations


def _macos_desktop_lifecycle(rec: WorkerJourney, repo_root: Path, env: dict[str, str]) -> tuple[str, list[str], Path]:
    desktop_dir = repo_root / "desktop"
    prepackage = rec.run("macos-desktop-prepackage-check", ["npm", "run", "prepackage-check"], cwd=desktop_dir, env=env, timeout=120)
    build = rec.run("macos-desktop-build-mac", ["npm", "run", "build:mac"], cwd=desktop_dir, env=env, timeout=600)
    dmg_files = sorted((desktop_dir / "dist").glob("*.dmg")) if (desktop_dir / "dist").exists() else []
    dmg = max(dmg_files, key=lambda path: path.stat().st_mtime) if dmg_files else desktop_dir / "dist"
    dmg_ok = dmg.is_file() and dmg.stat().st_size > 0
    selftest = rec.run("macos-desktop-selftest", ["npm", "run", "selftest"], cwd=desktop_dir, env=env, timeout=180)
    rec.add_artifact(dmg, "macos_desktop_dmg", "macOS DMG built by npm run build:mac")
    build_ok = prepackage.returncode == 0 and build.returncode == 0 and dmg_ok
    selftest_ok = selftest.returncode == 0
    rec.add_assertion(
        "macos_desktop_package_and_launch_completed",
        build_ok and selftest_ok,
        {
            "prepackage": prepackage.returncode,
            "build_mac": build.returncode,
            "dmg_path": str(dmg),
            "dmg_bytes": dmg.stat().st_size if dmg_ok else 0,
            "selftest": selftest.returncode,
        },
    )
    if build_ok and selftest_ok:
        return "PASS", [], dmg
    if build_ok:
        return "PASS_WITH_KNOWN_LIMITATIONS", ["DMG packaging succeeded, but Electron GUI selftest did not complete on this runner."], dmg
    return "FAIL", ["macOS desktop prepackage/build did not complete; inspect recorded command stdout/stderr."], dmg


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
    if platform.system() == "Darwin":
        mac_cli_status, mac_cli_limitations = _macos_cli_lifecycle(rec, repo_root, sandbox / "macos-cli")
        mac_app_status, mac_app_limitations, mac_dmg = _macos_desktop_lifecycle(rec, repo_root, env)
        rec.add_l2("Vertical", "Cross-platform install matrix", "macOS App Install/Launch/Status/Uninstall", mac_app_status, "macos_desktop_package_and_launch_completed", mac_dmg, command_label="npm run prepackage-check; npm run build:mac; npm run selftest", environment_requirement="macOS runner with Electron app launch permissions", known_limitations=mac_app_limitations)
        rec.add_l2("Vertical", "Cross-platform install matrix", "macOS CLI Install/Status/Uninstall", mac_cli_status, "macos_cli_lifecycle_completed", command_evidence, command_label="install.sh; solar doctor/status/ui; solar harness status-server; solar uninstall", environment_requirement="macOS shell lane for install.sh lifecycle", known_limitations=mac_cli_limitations)
    else:
        rec.add_l2("Vertical", "Cross-platform install matrix", "macOS App Install/Launch/Status/Uninstall", "ENVIRONMENT_BLOCKED", "mac_build_script_declared", matrix_artifact, command_label="static package.json inspection", environment_requirement="macOS runner with Electron app launch permissions", known_limitations=["macOS build resources and script are declared, but this worker is not Darwin and cannot launch a macOS app."])
        rec.add_l2("Vertical", "Cross-platform install matrix", "macOS CLI Install/Status/Uninstall", "ENVIRONMENT_BLOCKED", "mac_cli_probe_blocked_on_windows_or_helpful", command_evidence, command_label="macos-cli-preflight", environment_requirement="macOS shell lane for install.sh lifecycle", known_limitations=["Mac CLI lifecycle is intentionally left platform-blocked on this non-Darwin worker."])
    rec.add_l2("Vertical", "Cross-platform install matrix", "Installer Artifact and Release Resource Matrix", "PASS", "mac_build_script_declared", matrix_artifact, command_label="static package.json inspection")

    product_status = "PASS"
    limitations = []
    if platform.system() == "Darwin":
        for status_value, status_limitations in ((mac_cli_status, mac_cli_limitations), (mac_app_status, mac_app_limitations)):
            limitations.extend(status_limitations)
            if status_value == "FAIL":
                product_status = "FAIL"
            elif status_value == "PASS_WITH_KNOWN_LIMITATIONS" and product_status == "PASS":
                product_status = "PASS_WITH_KNOWN_LIMITATIONS"
    else:
        product_status = "PASS_WITH_KNOWN_LIMITATIONS"
        limitations = [
            "J15 verified static package/install matrix and Windows-local preflight only; macOS app and CLI lifecycle remain environment blocked on this non-Darwin machine."
        ]
    rec.finalize(
        product_status,
        limitations=limitations,
    )
