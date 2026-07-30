from __future__ import annotations

import json
import subprocess
import tarfile
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from journey_runner import bash_argv, bash_blocker, base_env, python_executable, write_json


WORKER_BATCH_ID = "J24-privacy-lifecycle-001"
SELECTOR = "tests/journeys/phase22/code/test_j24_privacy_lifecycle.py::test_p22_j24_real_privacy_lifecycle"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        return _load_json(path)
    except Exception:
        return None


def _run_repo_head(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return (proc.stdout or proc.stderr).strip()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _walk_path(root: Path) -> set[Path]:
    if not root.exists():
        return set()
    return {p.resolve() for p in root.rglob("*")}


def _archive_members(archive_path: Path) -> list[str]:
    if not archive_path.exists():
        return []
    with tarfile.open(archive_path, "r:gz") as tf:
        return sorted(tf.getnames())


def _read_path_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


@dataclass
class J24Recorder:
    repo_root: Path
    run_dir: Path
    command_records: list[dict[str, Any]] = field(default_factory=list)
    assertions: list[dict[str, Any]] = field(default_factory=list)
    command_index: int = 0

    def run(
        self,
        label: str,
        argv: list[str],
        env: dict[str, str],
        *,
        cwd: Path | None = None,
        timeout: float = 120.0,
    ) -> subprocess.CompletedProcess[str]:
        cwd = cwd or self.run_dir
        command_dir = self.run_dir / "commands"
        command_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = command_dir / f"{self.command_index + 1:03d}-{label}.stdout.txt"
        stderr_path = command_dir / f"{self.command_index + 1:03d}-{label}.stderr.txt"
        self.command_index += 1
        started = datetime.now(timezone.utc)
        timed_out = False
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd),
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            proc = subprocess.CompletedProcess(argv, 127, "", str(exc))
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            proc = subprocess.CompletedProcess(
                argv,
                124,
                exc.stdout or "",
                exc.stderr or f"command timed out after {timeout}s",
            )

        duration = round((datetime.now(timezone.utc) - started).total_seconds(), 3)
        stdout_path.write_text(proc.stdout or "", encoding="utf-8", errors="replace")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8", errors="replace")

        record = {
            "index": self.command_index,
            "label": label,
            "argv": list(argv),
            "cwd": str(cwd),
            "env_home": env.get("HOME", ""),
            "env_solar_home": env.get("SOLAR_HOME", ""),
            "env_claude_dir": env.get("CLAUDE_DIR", ""),
            "exit_code": int(proc.returncode),
            "timed_out": timed_out,
            "duration_seconds": duration,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }
        self.command_records.append(record)
        return proc

    def assert_result(self, name: str, passed: bool, observed: Any = None, required_for_status: bool = True) -> None:
        self.assertions.append(
            {
                "name": name,
                "passed": bool(passed),
                "observed": observed,
                "required_for_status": required_for_status,
            }
        )

    def command_count(self) -> int:
        return len(self.command_records)


def _final_payload(
    *,
    repo_root: Path,
    plan: dict[str, Any],
    run_id: str,
    run_dir: Path,
    sandbox_root: Path,
    commands: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    created_paths: set[Path],
    deleted_paths: list[str],
    backup_path: Path | None,
    evidence_paths: list[str],
    rec: J24Recorder,
    recommended_status: str,
    reason: list[str],
    limitations: list[str],
    run_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "phase22.j24_worker_result.v1",
        "journey_id": "P22-J24",
        "name": "Privacy Lifecycle",
        "selector": SELECTOR,
        "run_id": run_id,
        "production_entrypoint": plan["product_entrypoints"]["solar_cli"],
        "repo_root": str(repo_root),
        "repo_head": _run_repo_head(repo_root),
        "run_dir": str(run_dir),
        "sandbox_root": str(sandbox_root),
        "commands": commands,
        "assertions": assertions,
        "evidence_paths": evidence_paths,
        "created_paths": sorted(str(p) for p in created_paths),
        "deleted_paths": deleted_paths,
        "evidence_count": len(evidence_paths),
        "command_count": rec.command_count(),
        "recommended_status": recommended_status,
        "reason": reason,
        "limitations": limitations,
        "self_review": run_summary,
        "artifacts": {
            "backup": str(backup_path) if backup_path else "",
            "export": run_summary.get("redacted_export", ""),
            "commands_json": str(run_dir / "commands.json"),
        },
    }


def test_p22_j24_real_privacy_lifecycle(repo_root: Path, tmp_path: Path) -> None:
    fixture_root = (
        repo_root
        / "tests"
        / "journeys"
        / "phase22"
        / "fixtures"
        / "j24_privacy_lifecycle"
    )
    plan = _load_json(fixture_root / "j24_privacy_lifecycle_plan.json")

    blocker = bash_blocker(repo_root)
    if blocker:
        pytest.skip(f"J24 requires bash: {blocker}")

    run_id = f"p22-j24-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = repo_root / "outputs" / "phase22-real-journeys" / run_id
    worker_root = repo_root / ".codex-tmp" / "phase22-worker-results" / WORKER_BATCH_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    rec = J24Recorder(repo_root=repo_root, run_dir=run_dir)

    # Hard isolation root for all product data + test fixtures
    sandbox = repo_root / ".codex-tmp" / "p22-j24-privacy-sandbox"
    shutil.rmtree(sandbox, ignore_errors=True)
    sandbox.mkdir(parents=True, exist_ok=True)
    env = base_env(repo_root, sandbox)

    solar_home = Path(env["SOLAR_HOME"]).resolve()
    claude_dir = Path(env["CLAUDE_DIR"]).resolve()
    harness_root = Path(env["HARNESS_DIR"]).resolve()
    home_root = Path(env["HOME"]).resolve()

    assert _is_within(solar_home, sandbox), f"SOLAR_HOME outside sandbox: {solar_home}"
    assert _is_within(claude_dir, sandbox), f"CLAUDE_DIR outside sandbox: {claude_dir}"
    assert _is_within(harness_root, sandbox), f"HARNESS_DIR outside sandbox: {harness_root}"
    assert _is_within(home_root, sandbox), f"HOME outside sandbox: {home_root}"

    created_paths: set[Path] = {sandbox}
    initial_tree = _walk_path(sandbox)

    install_script = repo_root / "install.sh"
    install_cmd = [
        *bash_argv(
            repo_root,
            str(install_script),
            "--yes",
            "--components",
            "kernel,harness",
            "--solar-home",
            env["SOLAR_HOME"],
            "--claude-dir",
            env["CLAUDE_DIR"],
        )
    ]
    install = rec.run("install", install_cmd, env=env, timeout=240)
    rec.assert_result("install_exit_zero", install.returncode == 0, install.returncode)
    if install.returncode != 0:
        blocker_reason = ""
        combined_install_output = (install.stderr or install.stdout or "").lower()
        if "unsupported os" in combined_install_output:
            blocker_reason = "unsupported OS"
            recommended = "ENVIRONMENT_BLOCKED"
        else:
            blocker_reason = "install command failed before lifecycle path execution"
            recommended = "FAIL"
        write_json(run_dir / "commands.json", rec.command_records)
        install_stdout = run_dir / "commands" / "001-install.stdout.txt"
        install_stderr = run_dir / "commands" / "001-install.stderr.txt"
        payload = _final_payload(
            repo_root=repo_root,
            plan=plan,
            run_id=run_id,
            run_dir=run_dir,
            sandbox_root=sandbox,
            commands=rec.command_records,
            assertions=rec.assertions,
            created_paths=created_paths,
            deleted_paths=[],
            backup_path=None,
            evidence_paths=[
                str(run_dir / "commands.json"),
                str(install_stdout),
                str(install_stderr),
            ],
            rec=rec,
            recommended_status=recommended,
            reason=[blocker_reason] if blocker_reason else ["install_exit_zero"],
            limitations=[blocker_reason] if blocker_reason else ["install command failed"],
            run_summary={
                "created_and_deleted_paths_scoped": True,
                "all_created_paths_scoped": all(_is_within(path, sandbox) for path in created_paths),
                "sandbox_path": str(sandbox),
            },
        )
        write_json(run_dir / "journey-result.json", payload)
        worker_root.mkdir(parents=True, exist_ok=True)
        write_json(worker_root / "result.json", payload)
        if recommended == "ENVIRONMENT_BLOCKED":
            pytest.skip(blocker_reason)
        pytest.fail("install failed")

    solar_bin = solar_home / "bin" / "solar"
    rec.assert_result("solar_cli_exists", solar_bin.is_file(), str(solar_bin))

    seed = plan["seed"]
    db_path = solar_home / "db" / seed["sandbox_db_file"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    seeded_db = dict(seed["db_record"])
    seeded_db["fixture_token"] = "J24-STATIC-TOKEN-LOCAL"
    db_path.write_text(json.dumps(seeded_db, ensure_ascii=False, indent=2), encoding="utf-8")

    config_env = solar_home / "config.env"
    config_env.write_text("\n".join(seed["config_values"]) + "\n", encoding="utf-8")
    solar_env = solar_home / ".env"
    solar_env.write_text("\n".join(seed["env_values"]) + "\n", encoding="utf-8")
    created_paths.update({db_path, config_env, solar_env, db_path.parent, solar_home / "db", solar_home / "config.env", solar_home / ".env"})
    rec.assert_result("seed_db_written", db_path.exists(), str(db_path))
    rec.assert_result("seed_config_written", config_env.exists(), str(config_env))
    rec.assert_result("seed_env_written", solar_env.exists(), str(solar_env))

    status = rec.run(
        "status-json",
        [*bash_argv(repo_root, str(solar_bin), "status", "--json")],
        env=env,
        timeout=120,
    )
    status_payload: dict[str, Any] = {}
    status_parse_ok = False
    if status.returncode == 0 and status.stdout:
        try:
            status_payload = json.loads(status.stdout)
            status_parse_ok = True
        except json.JSONDecodeError:
            status_payload = {"raw": status.stdout[-1024:]}
    rec.assert_result("solar_status_json_parseable", status_parse_ok, status_payload)
    if status_parse_ok:
        rec.assert_result("solar_status_reconciled_install", status_payload.get("status", "") in {"installed", "ok"}, status_payload.get("status"))

    backup_dir = sandbox / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_out = backup_dir / plan["backup_archive_name"]
    backup = rec.run(
        "backup",
        [*bash_argv(repo_root, str(solar_bin), "backup", "--out", str(backup_out))],
        env=env,
        timeout=180,
    )
    rec.assert_result("backup_exit_zero", backup.returncode == 0, backup.returncode)
    rec.assert_result("backup_non_empty", backup_out.exists() and backup_out.stat().st_size > 0, backup_out.stat().st_size if backup_out.exists() else 0)
    rec.assert_result("backup_location_scoped", _is_within(backup_out, sandbox), str(backup_out))
    created_paths.add(backup_out)

    members = _archive_members(backup_out)
    write_json(run_dir / "artifacts" / "backup-members.json", {"members": members})
    rec.assert_result(
        "backup_contains_seed_db",
        db_path.name in "\n".join(members) and "db" in "".join(members),
        members,
    )
    rec.assert_result("backup_contains_config", "config.env" in members, members)
    rec.assert_result("backup_contains_dotenv", ".env" in members, members)

    notes_mock_source = fixture_root / "apple_notes_mock_note.json"
    notes_mock_dir = sandbox / "apple-notes-mock"
    notes_mock_dir.mkdir(parents=True, exist_ok=True)
    notes_mock_target = notes_mock_dir / "apple_notes_mock_note.json"
    notes_mock_target.write_text(
        json.dumps(_load_json(notes_mock_source), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    created_paths.update({notes_mock_dir, notes_mock_target})
    rec.assert_result("notes_mock_seed_written", notes_mock_target.exists(), str(notes_mock_target))

    scan_env = dict(env)
    scan_env["APPLE_NOTES_MOCK_DIR"] = str(notes_mock_dir)
    scan = rec.run(
        "apple-notes-scan",
        [
            python_executable(repo_root),
            str(repo_root / "harness" / "lib" / "apple_notes_ingest.py"),
            "scan",
            "--json",
        ],
        env=scan_env,
        cwd=repo_root,
        timeout=120,
    )
    rec.assert_result("apple_notes_scan_exit_zero", scan.returncode == 0, scan.returncode)

    scan_payload: dict[str, Any] = {}
    scan_json_ok = False
    if scan.returncode == 0 and scan.stdout:
        try:
            scan_payload = json.loads(scan.stdout)
            scan_json_ok = True
        except json.JSONDecodeError:
            scan_json_ok = False
            scan_payload = {"raw": scan.stdout[:1600]}
    rec.assert_result("apple_notes_scan_json", scan_json_ok, scan_payload)

    exported_files: list[Path] = []
    if scan_json_ok:
        exported_files = [Path(p) for p in scan_payload.get("exported", [])]
    rec.assert_result("apple_notes_exported", bool(exported_files), [str(p) for p in exported_files])

    redacted_export = None
    if exported_files:
        redacted_export = exported_files[0].resolve()
        rec.assert_result("apple_notes_export_in_sandbox", _is_within(redacted_export, sandbox), str(redacted_export))
        export_text = _read_path_text(redacted_export)
        rec.assert_result(
            "apple_notes_export_frontmatter",
            export_text.startswith("---") and "\n---\n" in export_text,
            export_text[:160],
        )
        markers = list(plan["privacy_markers"])
        seen_markers = [m for m in markers if m in export_text]
        rec.assert_result("sensitive_markers_removed", not seen_markers, seen_markers)
        expected_tags = list(plan["expected_redaction_tags"])
        rec.assert_result("redaction_tags_visible", all(tag in export_text for tag in expected_tags), expected_tags)
        created_paths.add(redacted_export)
        write_json(run_dir / "artifacts" / "apple-notes-export.json", scan_payload)
        if redacted_export.exists():
            rec.assert_result(
                "redacted_export_preserved_size",
                redacted_export.stat().st_size > 0,
                redacted_export.stat().st_size,
            )

    pre_keep_tree = _walk_path(solar_home)
    dry_run = rec.run(
        "uninstall-dry-run",
        [*bash_argv(repo_root, str(solar_bin), "uninstall", "--yes", "--dry-run")],
        env=env,
        timeout=60,
    )
    rec.assert_result("uninstall_dry_run_exit_zero", dry_run.returncode == 0, dry_run.returncode)
    post_dry_tree = _walk_path(solar_home)
    rec.assert_result("dry_run_non_destructive", pre_keep_tree == post_dry_tree, f"before={len(pre_keep_tree)} after={len(post_dry_tree)}")

    keep = rec.run(
        "uninstall-keep-data",
        [*bash_argv(repo_root, str(solar_bin), "uninstall", "--yes", "--keep-data")],
        env=env,
        timeout=120,
    )
    rec.assert_result("uninstall_keep_data_exit_zero", keep.returncode == 0, keep.returncode)
    rec.assert_result("keep_data_retains_db", (solar_home / "db").is_dir(), str(solar_home / "db"))
    rec.assert_result("keep_data_retains_db_record", db_path.exists(), str(db_path))
    rec.assert_result("keep_data_retains_config_env", config_env.exists(), str(config_env))
    rec.assert_result("keep_data_retains_solar_env", solar_env.exists(), str(solar_env))
    rec.assert_result("keep_data_removed_bin", not (solar_home / "bin").exists(), str(solar_home / "bin"))
    rec.assert_result("keep_data_removed_receipt", not (solar_home / "install-receipt.json").exists(), "receipt")
    rec.assert_result("keep_data_removed_claude_runtime", not (claude_dir / "solar").exists(), str(claude_dir / "solar"))

    reinstall_after_keep = rec.run(
        "reinstall-after-keep-data",
        install_cmd,
        env=env,
        timeout=240,
    )
    rec.assert_result("reinstall_after_keep_data_exit_zero", reinstall_after_keep.returncode == 0, reinstall_after_keep.returncode)

    restore = rec.run(
        "restore-from-backup",
        [*bash_argv(repo_root, str(solar_bin), "restore", str(backup_out))],
        env=env,
        timeout=120,
    )
    rec.assert_result("restore_exit_zero", restore.returncode == 0, restore.returncode)
    restored_db_payload = _safe_load_json(db_path)
    rec.assert_result("restore_restored_db", restored_db_payload == seeded_db, restored_db_payload)

    uninstall = rec.run(
        "uninstall-full",
        [*bash_argv(repo_root, str(solar_bin), "uninstall", "--yes")],
        env=env,
        timeout=180,
    )
    rec.assert_result("uninstall_full_exit_zero", uninstall.returncode == 0, uninstall.returncode)
    rec.assert_result("full_uninstall_removed_solar_home", not solar_home.exists(), str(solar_home))
    rec.assert_result("full_uninstall_removed_claude_runtime", not (claude_dir / "solar").exists(), str(claude_dir / "solar"))

    privacy_script = repo_root / "scripts" / "check-privacy.sh"
    privacy_scan = rec.run(
        "check-privacy",
        [*bash_argv(repo_root, str(privacy_script))],
        env=env,
        cwd=repo_root,
        timeout=90,
    )
    rec.assert_result("check_privacy_exit_zero", privacy_scan.returncode == 0, privacy_scan.returncode)

    final_tree = _walk_path(sandbox)
    deleted_paths = sorted(str(p) for p in created_paths if not p.exists())
    all_deleted_scoped = all(_is_within(Path(p), sandbox) for p in deleted_paths)
    run_summary = {
        "created_and_deleted_paths_scoped": all_deleted_scoped and all(_is_within(p, sandbox) for p in created_paths),
        "sandbox_scoped_seeded_data": all(_is_within(p, sandbox) for p in created_paths),
        "sandbox_initial_count": len(initial_tree),
        "sandbox_final_count": len(final_tree),
        "redacted_export_has_no_seeded_markers": all(
            redacted_export is not None
            and marker not in redacted_export.read_text(encoding="utf-8")
            for marker in plan["privacy_markers"]
        ),
        "sandbox_entries_added": sorted(str(p) for p in (final_tree - initial_tree) if _is_within(p, sandbox)),
        "backup_members_count": len(members),
        "redacted_export": str(redacted_export) if redacted_export is not None else "",
        "retained_after_keep_data": {
            "db": db_path.exists(),
            "config_env": config_env.exists(),
            "solar_env": solar_env.exists(),
        },
    }
    write_json(run_dir / "commands.json", rec.command_records)

    core_assertions = [item for item in rec.assertions if item.get("required_for_status", True)]
    required_ok = all(item["passed"] for item in core_assertions)
    limitations = [
        "privacy lifecycle executed on local backup/export/clear CLI only",
        "no cloud-account policy revocation or consent-dashboard variant covered",
    ]
    recommended_status = "PASS_WITH_KNOWN_LIMITATIONS" if required_ok else "FAIL"
    if not required_ok:
        limitations.insert(0, "core assertions failed")

    reason = [item["name"] for item in rec.assertions if not item["passed"]]
    evidence_paths = [
        str(run_dir / "journey-result.json"),
        str(run_dir / "commands.json"),
        str(run_dir / "artifacts" / "backup-members.json"),
        str(run_dir / "artifacts" / "apple-notes-export.json"),
    ]

    payload = _final_payload(
        repo_root=repo_root,
        plan=plan,
        run_id=run_id,
        run_dir=run_dir,
        sandbox_root=sandbox,
        commands=rec.command_records,
        assertions=rec.assertions,
        created_paths=created_paths,
        deleted_paths=deleted_paths,
        backup_path=backup_out,
        evidence_paths=evidence_paths,
        rec=rec,
        recommended_status=recommended_status,
        reason=reason,
        limitations=limitations,
        run_summary=run_summary,
    )
    write_json(run_dir / "journey-result.json", payload)
    worker_root.mkdir(parents=True, exist_ok=True)
    write_json(worker_root / "result.json", payload)

    if recommended_status == "FAIL":
        pytest.fail("P22-J24 failed required privacy lifecycle assertions.")
