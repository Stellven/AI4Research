from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from evidence import JourneyRecorder


def _wsl_path(path: Path) -> str:
    proc = subprocess.run(
        ["wsl.exe", "wslpath", "-a", str(path.resolve())],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(proc.stderr.strip() or f"could not translate WSL path: {path}")
    return proc.stdout.strip()


def test_p22_j25_runtime_deliverable_distribution(
    repo_root: Path, tmp_path: Path, phase22_python: str
) -> None:
    rec = JourneyRecorder(repo_root, "P22-J25")
    bundle = tmp_path / "runtime-deliverable"
    build = rec.run(
        "construct-runtime-deliverable",
        [
            phase22_python,
            str(repo_root / "distribution" / "runtime_deliverable.py"),
            "build",
            "--repo-root",
            str(repo_root),
            "--output-dir",
            str(bundle),
        ],
        timeout=180,
    )
    verify = rec.run(
        "verify-runtime-deliverable",
        [
            phase22_python,
            str(repo_root / "distribution" / "runtime_deliverable.py"),
            "verify",
            "--bundle",
            str(bundle),
        ],
        timeout=60,
    )

    manifest_path = bundle / "runtime-deliverable-manifest.json"
    manifest: dict[str, object] = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    wheel_assets = [
        item
        for item in manifest.get("assets", [])
        if isinstance(item, dict) and item.get("kind") == "python-wheel"
    ]
    wheel_path = bundle / str(wheel_assets[0]["path"]) if len(wheel_assets) == 1 else bundle / "missing.whl"

    rec.add_assertion("constructor_exit_zero", build.returncode == 0, build.returncode)
    rec.add_assertion("independent_verifier_exit_zero", verify.returncode == 0, verify.returncode)
    rec.add_assertion("one_nonempty_wheel_constructed", len(wheel_assets) == 1 and wheel_path.stat().st_size > 0 if wheel_path.is_file() else False, str(wheel_path))
    rec.add_assertion("manifest_records_source_commit", manifest.get("source", {}).get("git_commit") == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip() if isinstance(manifest.get("source"), dict) else False, manifest.get("source"))
    rec.add_assertion("manifest_embeds_no_credentials", manifest.get("configuration", {}).get("embedded_credentials") is False if isinstance(manifest.get("configuration"), dict) else False, manifest.get("configuration"))
    lifecycle = manifest.get("lifecycle", {})
    rec.add_assertion("manifest_documents_install_health_and_rollback", all(isinstance(lifecycle.get(key), list) and lifecycle[key] for key in ("clean_install", "start_health", "rollback")) if isinstance(lifecycle, dict) else False, lifecycle)

    if shutil.which("wsl.exe") is None:
        rec.add_assertion("linux_or_wsl_runtime_available", False, "wsl.exe not found")
        rec.finalize("ENVIRONMENT_BLOCKED", blockers=["A Linux/macOS runtime is required to execute the pipx wheel lifecycle."])
        return

    common_git_dir = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], cwd=repo_root, text=True
    ).strip()
    common_git_path = Path(common_git_dir)
    if not common_git_path.is_absolute():
        common_git_path = (repo_root / common_git_path).resolve()
    canonical_checkout = common_git_path.parent
    runtime_python = canonical_checkout / ".codex-tmp" / "wsl-phase22-venv" / "bin" / "python"
    runtime_bin = canonical_checkout / ".codex-tmp" / "wsl-bin"
    if not runtime_python.is_file() or not (runtime_bin / "jq").is_file():
        rec.add_assertion(
            "configured_wsl_runtime_dependencies_available",
            False,
            {"python": str(runtime_python), "jq": str(runtime_bin / "jq")},
        )
        rec.finalize(
            "ENVIRONMENT_BLOCKED",
            blockers=["Configured WSL Phase 22 Python runtime or jq binary is unavailable."],
        )
        return
    rec.add_assertion("configured_wsl_runtime_dependencies_available", True, str(runtime_python))
    source_branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=repo_root, text=True
    ).strip()
    if not source_branch:
        rec.add_assertion("source_branch_available", False, "detached HEAD")
        rec.finalize("FAIL")
        return
    rec.add_assertion("source_branch_available", True, source_branch)
    runtime_source = f"/tmp/p22-j25-source-{os.getpid()}"
    source_clone = rec.run(
        "prepare-standalone-runtime-source",
        [
            "wsl.exe",
            "git",
            "clone",
            "--no-local",
            "--branch",
            source_branch,
            _wsl_path(canonical_checkout),
            runtime_source,
        ],
        timeout=180,
    )
    rec.add_assertion("standalone_source_clone_exit_zero", source_clone.returncode == 0, source_clone.returncode)
    smoke_root = f"/tmp/p22-j25-runtime-{os.getpid()}"
    smoke = rec.run(
        "clean-install-start-health-rollback",
        [
            "wsl.exe",
            "env",
            f"OPENJIUWEN_SOLAR_INSTALL_TARGET={_wsl_path(wheel_path)}",
            f"OPENJIUWEN_SOLAR_SMOKE_ROOT={smoke_root}",
            f"OPENJIUWEN_SOLAR_REPO_ROOT={runtime_source}",
            f"SOLAR_PYTHON={_wsl_path(runtime_python)}",
            f"PATH={_wsl_path(runtime_bin)}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            f"SOLAR_CHANNEL={source_branch}",
            "bash",
            _wsl_path(repo_root / "distribution" / "pipx" / "smoke.sh"),
        ],
        timeout=360,
    )
    smoke_evidence_result = rec.run(
        "read-smoke-evidence",
        ["wsl.exe", "cat", f"{smoke_root}/smoke-evidence.json"],
        timeout=30,
    )
    smoke_evidence: dict[str, object] = {}
    try:
        smoke_evidence = json.loads(smoke_evidence_result.stdout)
    except json.JSONDecodeError:
        pass
    durable_smoke_evidence = rec.artifact_dir / "runtime-deliverable-smoke-evidence.json"
    durable_smoke_evidence.write_text(json.dumps(smoke_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rec.add_assertion("clean_sandbox_lifecycle_exit_zero", smoke.returncode == 0, smoke.returncode)
    rec.add_assertion("runtime_started_and_health_checked", smoke_evidence.get("runtime_status") == "healthy" and smoke_evidence.get("doctor") == "ok" and smoke_evidence.get("status_server_health") == "passed", smoke_evidence)
    rec.add_assertion("runtime_and_wrapper_rollback_verified", smoke_evidence.get("runtime_uninstalled") is True and smoke_evidence.get("wrapper_uninstalled") is True, smoke_evidence)
    rec.add_assertion("source_retained_for_reinstall", smoke_evidence.get("source_retained_for_rollback") is True, smoke_evidence)

    rec.add_artifact(manifest_path, "runtime_deliverable_manifest", "hash-bound package, lifecycle, and provenance manifest")
    rec.add_artifact(wheel_path, "runtime_deliverable_wheel", "installed wheel used by the clean-sandbox smoke")
    rec.add_artifact(durable_smoke_evidence, "runtime_deliverable_smoke", "install/start/health/rollback result")
    rec.add_l2(
        "Foundation",
        "Runtime Deliverable Construction",
        "A hash-bound wheel was constructed, independently verified, installed in a clean Linux sandbox, health-checked, and rolled back.",
        durable_smoke_evidence,
        True,
    )

    if all(item["passed"] for item in rec.assertions):
        rec.finalize(
            "PASS_WITH_KNOWN_LIMITATIONS",
            limitations=[
                "Verified the Python wheel/pipx target on WSL Linux only; container, launchd, workflow, macOS, and native-Windows targets remain NOT_TESTED."
            ],
        )
    else:
        rec.finalize("FAIL")
