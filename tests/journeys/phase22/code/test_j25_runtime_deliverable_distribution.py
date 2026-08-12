from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from evidence import JourneyRecorder


def _wsl_path(path: Path) -> str:
    proc = subprocess.run(
        ["wsl.exe", "wslpath", "-a", "--", str(path.resolve())],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    translated = proc.stdout.strip()
    if proc.returncode != 0 or not translated:
        raise RuntimeError(proc.stderr.strip() or f"could not translate WSL path: {path}")
    if not translated.startswith("/") or "\\" in translated:
        raise RuntimeError(f"wslpath returned a non-POSIX path: {translated}")
    return translated


def _wsl_executable(path: Path) -> bool:
    return subprocess.run(
        ["wsl.exe", "test", "-x", _wsl_path(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def test_wsl_path_preserves_spaces_and_removes_backslashes(tmp_path: Path) -> None:
    if os.name != "nt" or shutil.which("wsl.exe") is None:
        return
    spaced = tmp_path / "directory with spaces" / "artifact.whl"
    spaced.parent.mkdir(parents=True)
    spaced.write_bytes(b"wheel")
    translated = _wsl_path(spaced)
    assert translated.startswith("/mnt/")
    assert "directory with spaces" in translated
    assert "\\" not in translated


def test_smoke_failure_atomically_replaces_stale_healthy_evidence(repo_root: Path) -> None:
    if os.name == "nt" and shutil.which("wsl.exe") is None:
        return
    smoke_root = f"/tmp/p22-j25-stale-evidence-{os.getpid()}"
    seed_code = (
        "import json, pathlib, sys; "
        "p=pathlib.Path(sys.argv[1]); p.mkdir(parents=True, exist_ok=True); "
        "(p/'smoke-evidence.json').write_text(json.dumps({'status':'passed','run_id':'stale'})); "
        "r=p/'.runs'/'stale'; (r/'logs').mkdir(parents=True); "
        "(r/'logs'/'doctor.stdout').write_text(json.dumps({'verdict':'ok'})); "
        "(r/'health-response.json').write_text(json.dumps({'http_status':200,'body_sha256':'f'*64})); "
        "(r/'command-ledger.jsonl').write_text(json.dumps({'run_id':'stale','label':'doctor','exit_code':0})+'\\n'+json.dumps({'run_id':'stale','label':'health','exit_code':0})+'\\n')"
    )
    if os.name == "nt":
        seed_argv = ["wsl.exe", "python3", "-c", seed_code, smoke_root]
        smoke_script = _wsl_path(repo_root / "distribution" / "pipx" / "smoke.sh")
        failed_prefix = ["wsl.exe"]
        read_argv = ["wsl.exe", "cat", f"{smoke_root}/smoke-evidence.json"]
    else:
        seed_argv = ["python3", "-c", seed_code, smoke_root]
        smoke_script = str(repo_root / "distribution" / "pipx" / "smoke.sh")
        failed_prefix = []
        read_argv = ["cat", f"{smoke_root}/smoke-evidence.json"]
    assert subprocess.run(seed_argv, check=False).returncode == 0
    failed = subprocess.run(
        [
            *failed_prefix,
            "env",
            f"OPENJIUWEN_SOLAR_SMOKE_ROOT={smoke_root}",
            "OPENJIUWEN_SOLAR_INSTALL_TARGET=/missing/runtime.whl",
            "OPENJIUWEN_SOLAR_GET_SOLAR_URL=/missing/bootstrap.sh",
            "bash",
            smoke_script,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert failed.returncode != 0
    read = subprocess.run(
        read_argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert read.returncode == 0
    evidence = json.loads(read.stdout)
    assert evidence["status"] == "failed", failed.stderr
    assert evidence["run_id"] != "stale"
    assert evidence["observations"]["clean_sandbox_install"] is False
    assert evidence["observations"]["doctor_verdict"] == "unavailable"
    assert evidence["observations"]["health_http_status"] is None
    assert evidence["observations"]["health_body_sha256"] == ""
    assert evidence["observations"]["runtime_uninstalled"] is False
    assert evidence["observations"]["wrapper_uninstalled"] is False
    assert evidence["commands"] == []


def _git_head(repo_root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()


def test_p22_j25_runtime_deliverable_distribution(
    repo_root: Path, tmp_path: Path, phase22_python: str
) -> None:
    rec = JourneyRecorder(repo_root, "P22-J25")
    if shutil.which("wsl.exe") is None:
        rec.add_assertion("wsl_runtime_available", False, "wsl.exe not found")
        rec.add_l2(
            "Foundation",
            "Runtime Deliverable Construction",
            "The Linux runtime bundle could not be replayed because WSL is unavailable.",
            rec.run_dir / "commands.json",
            False,
        )
        rec.finalize("ENVIRONMENT_BLOCKED", blockers=["WSL/Linux is required for this target."])
        return

    common_git_dir = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], cwd=repo_root, text=True
    ).strip()
    common_git_path = Path(common_git_dir)
    if not common_git_path.is_absolute():
        common_git_path = (repo_root / common_git_path).resolve()
    canonical_checkout = common_git_path.parent
    wheelhouse = canonical_checkout / ".codex-tmp" / "p22-119-wheelhouse"
    jq_binary = canonical_checkout / ".codex-tmp" / "wsl-bin" / "jq"
    wheel_count = len(list(wheelhouse.glob("*.whl"))) if wheelhouse.is_dir() else 0
    environment_ready = wheel_count >= 5 and _wsl_executable(jq_binary)
    rec.add_assertion(
        "constructor_inputs_available",
        environment_ready,
        {"wheelhouse": str(wheelhouse), "wheel_count": wheel_count, "jq": str(jq_binary)},
    )
    if not environment_ready:
        rec.add_l2(
            "Foundation",
            "Runtime Deliverable Construction",
            "The configured offline wheelhouse or jq construction input is unavailable.",
            rec.run_dir / "commands.json",
            False,
        )
        rec.finalize(
            "ENVIRONMENT_BLOCKED",
            blockers=["Offline CPython 3.12/Linux wheelhouse or jq build input is unavailable."],
        )
        return

    commit = _git_head(repo_root)
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
            "--wheelhouse",
            str(wheelhouse),
            "--jq-binary",
            str(jq_binary),
        ],
        timeout=300,
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
        timeout=180,
    )

    manifest_path = bundle / "runtime-deliverable-manifest.json"
    manifest: dict[str, object] = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    assets = manifest.get("assets", []) if isinstance(manifest.get("assets"), list) else []
    wheel_assets = [
        item for item in assets if isinstance(item, dict) and item.get("kind") == "python-wheel"
    ]
    wheel_path = bundle / str(wheel_assets[0]["path"]) if len(wheel_assets) == 1 else bundle / "missing.whl"
    source = manifest.get("source", {}) if isinstance(manifest.get("source"), dict) else {}
    replay_archive = bundle.parent / f"openjiuwen-solar-runtime-deliverable-{commit}.tar.gz"
    configuration = (
        manifest.get("configuration", {}) if isinstance(manifest.get("configuration"), dict) else {}
    )

    rec.add_assertion("constructor_exit_zero", build.returncode == 0, build.returncode)
    rec.add_assertion("jsonschema_and_independent_verifier_exit_zero", verify.returncode == 0, verify.returncode)
    rec.add_assertion(
        "one_nonempty_wheel_constructed",
        len(wheel_assets) == 1 and wheel_path.is_file() and wheel_path.stat().st_size > 1000,
        str(wheel_path),
    )
    rec.add_assertion("manifest_records_exact_source_commit", source.get("git_commit") == commit, source)
    rec.add_assertion(
        "bundle_is_self_contained_for_replay",
        replay_archive.is_file()
        and replay_archive.stat().st_size > 1000
        and configuration.get("network_required_for_replay") is False
        and configuration.get("external_checkout_required_for_replay") is False
        and configuration.get("environment_injection_required_for_replay") is False,
        {"archive": str(replay_archive), "bytes": replay_archive.stat().st_size if replay_archive.is_file() else 0, "configuration": configuration},
    )

    extract_root = f"/tmp/{rec.run_id}-bundle"
    replay_root = f"/tmp/{rec.run_id}-replay"
    prepare = rec.run(
        "prepare-empty-replay-root",
        [
            "wsl.exe",
            "python3",
            "-c",
            "import pathlib,sys; p=pathlib.Path(sys.argv[1]); assert not p.exists(); p.mkdir(parents=True)",
            extract_root,
        ],
        timeout=30,
    )
    extract = rec.run(
        "extract-durable-replay-archive",
        ["wsl.exe", "tar", "-xzf", _wsl_path(replay_archive), "-C", extract_root],
        timeout=180,
    )
    replay_script = f"{extract_root}/runtime-deliverable/replay.sh"
    replay = rec.run(
        "replay-clean-install-start-health-rollback",
        ["wsl.exe", "bash", replay_script, replay_root],
        timeout=480,
    )
    smoke_evidence_result = rec.run(
        "read-smoke-evidence",
        ["wsl.exe", "cat", f"{replay_root}/product/smoke-evidence.json"],
        timeout=30,
    )
    smoke_evidence: dict[str, object] = {}
    try:
        smoke_evidence = json.loads(smoke_evidence_result.stdout)
    except json.JSONDecodeError:
        smoke_evidence = {}
    durable_smoke_evidence = rec.artifact_dir / "runtime-deliverable-smoke-evidence.json"
    valid_smoke_schema = smoke_evidence.get("schema_version") == "opensolar.runtime-deliverable-smoke/v2"
    if valid_smoke_schema:
        durable_smoke_evidence.write_text(
            json.dumps(smoke_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    commands = smoke_evidence.get("commands", []) if isinstance(smoke_evidence.get("commands"), list) else []
    executed = [item for item in commands if isinstance(item, dict) and item.get("exit_code") is not None]
    executed_labels = {str(item.get("label")) for item in executed}
    observations = (
        smoke_evidence.get("observations", {})
        if isinstance(smoke_evidence.get("observations"), dict)
        else {}
    )
    pipx = (
        smoke_evidence.get("package_manager", {}).get("pipx", {})
        if isinstance(smoke_evidence.get("package_manager"), dict)
        else {}
    )
    required_labels = {
        "package-install",
        "runtime-install",
        "status",
        "doctor",
        "status-server-start",
        "health",
        "status-server-stop",
        "runtime-uninstall",
        "package-uninstall",
    }
    rec.add_assertion("durable_archive_extracted_without_external_checkout", prepare.returncode == 0 and extract.returncode == 0, {"prepare": prepare.returncode, "extract": extract.returncode})
    rec.add_assertion("replay_entrypoint_exit_zero", replay.returncode == 0, replay.returncode)
    rec.add_assertion("smoke_evidence_v2_has_unique_run_id", valid_smoke_schema and bool(smoke_evidence.get("run_id")), smoke_evidence.get("run_id"))
    rec.add_assertion(
        "real_commands_and_exit_codes_recorded",
        required_labels.issubset(executed_labels)
        and all(item.get("exit_code") == 0 for item in executed)
        and all(item.get("run_id") == smoke_evidence.get("run_id") for item in commands)
        and all(re.fullmatch(r"[0-9a-f]{64}", str(item.get("stdout_sha256", ""))) for item in executed),
        {"required": sorted(required_labels), "observed": sorted(executed_labels)},
    )
    rec.add_assertion(
        "runtime_started_and_health_response_hashed",
        smoke_evidence.get("status") == "passed"
        and observations.get("doctor_verdict") == "ok"
        and observations.get("health_http_status") == 200
        and bool(re.fullmatch(r"[0-9a-f]{64}", str(observations.get("health_body_sha256", "")))),
        observations,
    )
    rec.add_assertion(
        "runtime_and_wrapper_rollback_verified",
        observations.get("runtime_uninstalled") is True
        and observations.get("wrapper_uninstalled") is True
        and observations.get("source_retained_for_rollback") is True,
        observations,
    )
    rec.add_assertion(
        "pipx_result_is_explicit",
        isinstance(pipx, dict)
        and pipx.get("status") in {"PASS", "NOT_TESTED"}
        and (pipx.get("status") != "NOT_TESTED" or bool(pipx.get("reason"))),
        pipx,
    )
    rec.add_assertion(
        "no_placeholder_smoke_artifact",
        durable_smoke_evidence.is_file() and durable_smoke_evidence.stat().st_size > 500,
        durable_smoke_evidence.stat().st_size if durable_smoke_evidence.is_file() else 0,
    )

    rec.add_artifact(manifest_path, "runtime_deliverable_manifest", "schema-valid complete asset inventory")
    # JourneyRecorder prefixes the source basename with the artifact type. Keep
    # the durable evidence filename short enough for Windows MAX_PATH while
    # retaining the constructor's commit-addressed archive unchanged.
    evidence_archive = tmp_path / "bundle.tar.gz"
    if replay_archive.is_file():
        os.link(replay_archive, evidence_archive)
    rec.add_artifact(
        evidence_archive if evidence_archive.is_file() else replay_archive,
        "runtime_deliverable_replay_archive",
        "self-contained source, dependencies, tools, verifier, and replay entrypoint",
    )
    rec.add_artifact(wheel_path, "runtime_deliverable_wheel", "wrapper wheel installed by replay")
    rec.add_artifact(durable_smoke_evidence, "runtime_deliverable_smoke", "atomic command/exit/hash lifecycle evidence")
    success = all(item["passed"] for item in rec.assertions)
    rec.add_l2(
        "Foundation",
        "Runtime Deliverable Construction",
        "The durable bundle was independently extracted and replayed through install, service health, and rollback without an external checkout or injected runtime environment.",
        durable_smoke_evidence if durable_smoke_evidence.is_file() else rec.run_dir / "commands.json",
        success,
    )
    if success:
        rec.finalize(
            "PASS_WITH_KNOWN_LIMITATIONS",
            limitations=[
                "Verified WSL/Linux x86_64 with CPython 3.12 only; pipx is NOT_TESTED when unavailable, and container, launchd, workflow, macOS, and native-Windows targets remain NOT_TESTED."
            ],
        )
    else:
        rec.finalize("FAIL")
