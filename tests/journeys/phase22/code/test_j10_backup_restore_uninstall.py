from __future__ import annotations

import json
import platform
import sqlite3
import sys
from pathlib import Path

from evidence import JourneyRecorder, redact, sha256
from journey_runner import base_env, bash_argv, bash_blocker, write_json


def _load_fixture(repo_root: Path) -> dict[str, object]:
    fixture = (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "j01_j10"
        / "j01_j10_journey_inputs.json"
    )
    return json.loads(fixture.read_text(encoding="utf-8-sig"))


def _snapshot_files(targets: dict[str, Path]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for label, path in targets.items():
        if not path.exists():
            snapshot[f"{label}:exists"] = "false"
            continue
        if path.is_file():
            snapshot[f"{label}:exists"] = "true"
            snapshot[f"{label}:sha256"] = sha256(path)
            return_snapshot_key = "dummy"
        else:
            snapshot[f"{label}:type"] = "dir"
            child_files = sorted(
                p for p in path.glob("**/*") if p.is_file() and ".git" not in p.parts
            )
            for file in child_files[:200]:
                rel = str(file.relative_to(path))
                snapshot[f"{label}:{rel}"] = sha256(file)
            snapshot[f"{label}:dir_files"] = str(len(child_files))
    return snapshot


def _write_db_marker(db: Path, value: str) -> None:
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS phase22_j10_marker (id INTEGER PRIMARY KEY CHECK (id = 1), value TEXT)")
        conn.execute(
            "INSERT INTO phase22_j10_marker (id, value) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET value = excluded.value",
            (value,),
        )
        conn.commit()
    finally:
        conn.close()


def _doctor_ok(proc) -> bool:
    if proc.returncode != 0:
        return False
    payload: dict[str, object] = {}
    if not proc.stdout.strip():
        return False
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False
    return payload.get("verdict") == "ok"


def test_p22_j10_backup_restore_uninstall(repo_root: Path, tmp_path: Path) -> None:
    rec = JourneyRecorder(repo_root, "P22-J10")
    blocker = bash_blocker(repo_root)
    if blocker:
        rec.add_assertion("bash_available_for_lifecycle_cli", False, blocker)
        rec.finalize("ENVIRONMENT_BLOCKED", blockers=[blocker])
        return

    payload = _load_fixture(repo_root).get("j10", {})
    integration_requests: list[str] = []

    sandbox = tmp_path / "p22-j10"
    env = base_env(repo_root, sandbox)
    install_cmd = [
        *bash_argv(
            repo_root,
            str(repo_root / "install.sh"),
            "--yes",
            "--components",
            "kernel,harness",
            "--solar-home",
            env["SOLAR_HOME"],
            "--claude-dir",
            env["CLAUDE_DIR"],
        )
    ]
    install = rec.run("install", install_cmd, env=env, timeout=180)
    solar_home = Path(env["SOLAR_HOME"]).resolve()
    claude_dir = Path(env["CLAUDE_DIR"]).resolve()
    harness_dir = solar_home / "harness"
    solar = solar_home / "bin" / "solar"
    receipt = solar_home / "install-receipt.json"

    if install.returncode != 0:
        detail = (install.stderr or install.stdout)[-1000:]
        rec.add_assertion("install_exit_zero", False, install.returncode)
        if "unsupported OS" in detail:
            rec.finalize("ENVIRONMENT_BLOCKED", blockers=[redact(detail).strip()])
            return
        rec.finalize("FAIL")
        return
    env["HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_HARNESS_DIR"] = str(harness_dir)
    rec.add_artifact(receipt, "install_receipt")
    rec.add_artifact(solar, "cli_launcher")

    db = solar_home / "db" / "solar.db"
    config = solar_home / "config.env"
    solar_env = solar_home / ".env"
    claude_md = claude_dir / "CLAUDE.md"

    db.parent.mkdir(parents=True, exist_ok=True)
    _write_db_marker(db, str(payload.get("db_initial", "phase22-db-initial")).strip())
    config.write_text(str(payload.get("config_env", "PHASE22_CONFIG=1")).strip() + "\n", encoding="utf-8")
    solar_env.write_text(str(payload.get("solar_env", "PHASE22_SOLAR_ENV=1")).strip() + "\n", encoding="utf-8")
    claude_md.write_text(str(payload.get("claude_md", "User-owned CLAUDE.md")).strip() + "\n", encoding="utf-8")

    pre_contract = _snapshot_files(
        {
            "db": db,
            "config_env": config,
            "solar_env": solar_env,
            "claude_md": claude_md,
            "receipt": receipt,
        }
    )
    write_json(rec.run_dir / "j10-pre-contract.json", pre_contract)

    migration_out = sandbox / "migrations"
    migration_out.mkdir(parents=True, exist_ok=True)
    migrate_export = rec.run(
        "migrate-export",
        [
            *bash_argv(repo_root, str(solar), "harness", "migrate", "export", "--out", str(migration_out))
        ],
        env=env,
        timeout=180,
    )
    rec.add_assertion("migration_export_exit_zero", migrate_export.returncode == 0, migrate_export.returncode)
    migration_bundle_candidates = sorted(
        migration_out.glob("solar-bundle-*.tar"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    migration_bundle = migration_bundle_candidates[0] if migration_bundle_candidates else None
    rec.add_assertion("migration_bundle_generated", migration_bundle is not None and migration_bundle.exists(), migration_bundle)

    migration_bundle_sha = None
    if migration_bundle:
        migration_bundle_sha = (str((migration_bundle.parent / f"{migration_bundle.name}.sha256").read_text(encoding="utf-8").strip()) if (migration_bundle.parent / f"{migration_bundle.name}.sha256").exists() else "")
        migrate_verify = rec.run(
            "migrate-verify",
            [*bash_argv(repo_root, str(solar), "harness", "migrate", "verify", str(migration_bundle))],
            env=env,
            timeout=180,
        )
        rec.add_assertion("migration_verify_exit_zero", migrate_verify.returncode == 0, migrate_verify.returncode)
        if migrate_verify.returncode != 0:
            integration_requests.append("Product gap: migration verify command reported non-zero exit under expected invocation.")
    else:
        integration_requests.append("Product gap: migration export did not emit solar-bundle-*.tar under out directory.")

    if migration_bundle:
        pre_dryrun_snapshot = _snapshot_files({"db": db, "config_env": config, "solar_env": solar_env, "claude_md": claude_md})
        write_json(rec.run_dir / "j10-migrate-dryrun-before.json", pre_dryrun_snapshot)
        migrate_dry_run = rec.run(
            "migrate-import-dry-run",
            [*bash_argv(repo_root, str(solar), "harness", "migrate", "import", str(migration_bundle), "--dry-run")],
            env=env,
            timeout=180,
        )
        rec.add_assertion("migration_dry_run_exit_zero", migrate_dry_run.returncode == 0, migrate_dry_run.returncode)
        post_dryrun_snapshot = _snapshot_files({"db": db, "config_env": config, "solar_env": solar_env, "claude_md": claude_md})
        write_json(rec.run_dir / "j10-migrate-dryrun-after.json", post_dryrun_snapshot)
        rec.add_assertion("migration_dry_run_no_change", pre_dryrun_snapshot == post_dryrun_snapshot, "snapshot diff before/after dry-run")

    backup_root = sandbox / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_archive = backup_root / str(payload.get("backup_archive_name", "phase22-j10-backup.tar.gz"))
    backup_before_hash = sha256(db)
    backup = rec.run(
        "backup",
        [*bash_argv(repo_root, str(solar), "backup", "--out", str(backup_archive))],
        env=env,
        timeout=120,
    )
    rec.add_assertion("backup_exit_zero", backup.returncode == 0 and backup_archive.exists(), backup.returncode)
    if backup_archive.exists():
        rec.add_artifact(backup_archive, "backup_archive")

    if not backup_archive.exists():
        integration_requests.append("Product gap: backup command did not generate expected archive file.")

    rec.add_assertion("backup_archive_non_empty", backup_archive.exists() and backup_archive.stat().st_size > 0, backup_archive.stat().st_size if backup_archive.exists() else 0)
    _write_db_marker(db, str(payload.get("db_mutated", "phase22-db-mutated")).strip())
    restore = rec.run(
        "restore",
        [*bash_argv(repo_root, str(solar), "restore", str(backup_archive))],
        env=env,
        timeout=120,
    )
    restored_hash = sha256(db) if db.exists() else ""
    rec.add_assertion("restore_exit_zero", restore.returncode == 0, restore.returncode)
    rec.add_assertion("restore_matches_pre_backup_db_hash", restored_hash == backup_before_hash, restored_hash)

    doctor_after_restore = rec.run("doctor-after-restore", bash_argv(repo_root, str(solar), "doctor", "--json"), env=env, timeout=60)
    rec.add_assertion("doctor_after_restore_ok", _doctor_ok(doctor_after_restore), doctor_after_restore.stdout[-500:])
    rec.add_assertion(
        "home_scoped_to_sandbox",
        str(Path(env["HOME"]).resolve()).startswith(str(sandbox.resolve())),
        env["HOME"],
    )

    uninstall_dry = rec.run(
        "uninstall-dry-run",
        [*bash_argv(repo_root, str(solar), "uninstall", "--yes", "--dry-run")],
        env=env,
        timeout=60,
    )
    rec.add_assertion("uninstall_dry_run_exit_zero", uninstall_dry.returncode == 0, uninstall_dry.returncode)

    keep = rec.run(
        "uninstall-keep-data",
        [*bash_argv(repo_root, str(solar), "uninstall", "--yes", "--keep-data")],
        env=env,
        timeout=120,
    )
    rec.add_assertion("uninstall_keep_data_exit_zero", keep.returncode == 0, keep.returncode)
    after_keep = _snapshot_files({"db": db, "config_env": config, "solar_env": solar_env, "claude_md": claude_md, "receipt": receipt})
    write_json(rec.run_dir / "j10-after-keep.json", after_keep)
    rec.add_assertion("keep_data_retains_db", after_keep.get("db:sha256") == backup_before_hash, after_keep.get("db:sha256"))
    rec.add_assertion("keep_data_retains_config_env", after_keep.get("config_env:sha256") is not None and after_keep.get("config_env:exists") == "true", after_keep.get("config_env:exists"))
    rec.add_assertion("keep_data_retains_solar_env", after_keep.get("solar_env:sha256") is not None and after_keep.get("solar_env:exists") == "true", after_keep.get("solar_env:exists"))
    rec.add_assertion("keep_data_removes_receipt", after_keep.get("receipt:exists") != "true", after_keep.get("receipt:exists"))
    rec.add_assertion("claude_md_preserved", claude_md.exists() and claude_md.read_text(encoding="utf-8").strip() == str(payload.get("claude_md", "User-owned CLAUDE.md")).strip(), claude_md.exists())

    reinstall = rec.run("reinstall-after-keep", install_cmd, env=env, timeout=180)
    rec.add_assertion("reinstall_after_keep_data_exit_zero", reinstall.returncode == 0, reinstall.returncode)

    _write_db_marker(db, str(payload.get("db_post_reinstall_mutated", "phase22-db-post-reinstall-mutated")).strip())
    restore_after_reinstall = rec.run(
        "restore-after-reinstall",
        [*bash_argv(repo_root, str(solar), "restore", str(backup_archive))],
        env=env,
        timeout=120,
    )
    rec.add_assertion("restore_after_reinstall_exit_zero", restore_after_reinstall.returncode == 0, restore_after_reinstall.returncode)
    rec.add_assertion("restore_after_reinstall_hash_match", sha256(db) == backup_before_hash, sha256(db))
    doctor_after_restore2 = rec.run("doctor-after-reinstall-restore", bash_argv(repo_root, str(solar), "doctor", "--json"), env=env, timeout=60)
    rec.add_assertion("doctor_after_reinstall_restore_ok", _doctor_ok(doctor_after_restore2), doctor_after_restore2.stdout[-500:])

    full = rec.run("uninstall-full", [*bash_argv(repo_root, str(solar), "uninstall", "--yes")], env=env, timeout=120)
    rec.add_assertion("uninstall_full_exit_zero", full.returncode == 0, full.returncode)

    rec.add_assertion("full_uninstall_removed_solar_home", not solar_home.exists(), str(solar_home.exists()))
    rec.add_assertion("full_uninstall_removed_solar_bin", not (solar_home / "bin").exists(), str(solar_home / "bin"))
    rec.add_assertion("full_uninstall_preserved_user_claude_md", claude_md.exists(), "user claude file exists")

    process_scan_script = rec.run_dir / "j10-process-scan.py"
    if platform.system() == "Windows":
        scan_command = "Get-CimInstance Win32_Process | Select-Object -ExpandProperty CommandLine"
        process_command = ["powershell", "-NoProfile", "-Command", scan_command]
    else:
        process_command = ["ps", "ax", "-o", "args="]
    process_scan_script.write_text(
        "\n".join(
            [
                "import json, os, subprocess",
                "needle = os.environ.get('PHASE22_SCAN_HARNESS', '').lower()",
                "terms = [item.strip().lower() for item in os.environ.get('PHASE22_SCAN_TERMS', '').split('|') if item.strip()]",
                "command = json.loads(os.environ['PHASE22_PROCESS_SCAN_COMMAND'])",
                "proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)",
                "matches = []",
                "for raw in (proc.stdout or '').splitlines():",
                "    line = raw.strip()",
                "    lower = line.lower()",
                "    if needle and needle in lower and any(term in lower for term in terms) and 'j10-process-scan.py' not in lower:",
                "        matches.append(line)",
                "print('\\n'.join(matches))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    scan_env = dict(env)
    scan_env["PHASE22_SCAN_HARNESS"] = env["HARNESS_DIR"]
    scan_env["PHASE22_SCAN_TERMS"] = "solar-harness|solar backup|solar restore|solar uninstall|status-server"
    scan_env["PHASE22_PROCESS_SCAN_COMMAND"] = json.dumps(process_command)
    process_scan = rec.run(
        "service-process-scan",
        [sys.executable, str(process_scan_script)],
        env=scan_env,
        timeout=30,
    )
    rec.add_assertion("background_services_no_residue", process_scan.stdout.strip() == "", process_scan.stdout.strip())

    rec.add_assertion(
        "migration_bundle_sha_recorded",
        migration_bundle_sha is not None,
        migration_bundle_sha,
    )
    rec.add_assertion(
        "j10_backup_archive_written",
        backup_archive.exists() and backup_archive.stat().st_size > 0,
        str(backup_archive) if backup_archive.exists() else "missing",
    )

    if integration_requests:
        rec.add_assertion("integration_requests", True, integration_requests)

    rec.add_l2(
        "Vertical",
        "Workflow & Platform Status Visibility",
        "migration export/verify, dry-run, backup/restore, keep-data/full uninstall commands were exercised",
        rec.run_dir / "commands.json",
        True,
    )

    if all(item["passed"] for item in rec.assertions):
        rec.finalize("PASS")
    else:
        rec.finalize("FAIL")
