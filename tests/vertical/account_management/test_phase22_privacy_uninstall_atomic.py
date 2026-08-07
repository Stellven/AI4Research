from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SOLAR_CLI = REPO / "bin" / "solar"


def _bash_executable() -> str | None:
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    if git_bash.exists():
        return str(git_bash)
    executable = shutil.which("bash")
    if executable and "WindowsApps" not in executable:
        return executable
    return None


def _bash_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if len(value) >= 3 and value[1:3] == ":/":
        return f"/{value[0].lower()}{value[2:]}"
    return value


def _quote(path: Path) -> str:
    return "'" + _bash_path(path).replace("'", "'\"'\"'") + "'"


def _seed_solar_home(home: Path) -> tuple[Path, Path]:
    solar_home = home / ".solar"
    claude_dir = home / ".claude"
    for path in (
        solar_home / "bin",
        solar_home / "core",
        solar_home / "codex-bridge",
        solar_home / "harness",
        solar_home / "mempalace",
        solar_home / "venv",
        solar_home / "node_modules",
        solar_home / "cache",
        solar_home / "db",
        solar_home / "identity",
        claude_dir / "solar",
    ):
        path.mkdir(parents=True, exist_ok=True)
    (solar_home / "install-receipt.json").write_text(
        json.dumps({"version": "phase22-test", "components": ["kernel", "harness"]}),
        encoding="utf-8",
    )
    (solar_home / "config.env").write_text("SOLAR_TEST_CONFIG=1\n", encoding="utf-8")
    (solar_home / ".env").write_text("SOLAR_TEST_ENV=1\n", encoding="utf-8")
    (solar_home / "db" / "solar.db").write_text("sandbox database\n", encoding="utf-8")
    (solar_home / "identity" / "local-accounts.json").write_text(
        json.dumps({"schema_version": "test", "accounts": {"sandbox-user": {}}}),
        encoding="utf-8",
    )
    (solar_home / "bin" / "solar").write_text("# sandbox installed cli\n", encoding="utf-8")
    (solar_home / "harness" / "README.txt").write_text("sandbox harness\n", encoding="utf-8")
    (claude_dir / "solar" / "SOLAR.md").write_text("# sandbox kernel\n", encoding="utf-8")
    return solar_home, claude_dir


def _write_python3_shim(fake_bin: Path) -> None:
    fake_bin.mkdir(parents=True, exist_ok=True)
    shim = fake_bin / "python3"
    shim.write_text(
        f'#!/usr/bin/env bash\nexec "{_bash_path(Path(sys.executable))}" "$@"\n',
        encoding="utf-8",
    )
    os.chmod(shim, 0o755)


def _run_uninstall(
    tmp_path: Path,
    home: Path,
    solar_home: Path,
    claude_dir: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    bash = _bash_executable()
    assert bash is not None, "Git Bash or bash is required for bin/solar uninstall tests"
    fake_bin = tmp_path / f"fake-bin-{home.name}"
    _write_python3_shim(fake_bin)
    arg_text = " ".join(args)
    command = (
        f"PATH={_quote(fake_bin)}:$PATH "
        f"HOME={_quote(home)} "
        f"SOLAR_HOME={_quote(solar_home)} "
        f"CLAUDE_DIR={_quote(claude_dir)} "
        f"bash {_quote(SOLAR_CLI)} uninstall {arg_text}"
    )
    return subprocess.run(
        [bash, "-lc", command],
        cwd=REPO,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )


def _snapshot(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        snapshot[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def test_atomic_privacy_personal_data_controls__uninstall_delete_versus_keep_data(tmp_path: Path) -> None:
    delete_home = tmp_path / "delete-home"
    keep_home = tmp_path / "keep-home"
    delete_solar_home, delete_claude_dir = _seed_solar_home(delete_home)
    keep_solar_home, keep_claude_dir = _seed_solar_home(keep_home)

    delete_result = _run_uninstall(
        tmp_path,
        delete_home,
        delete_solar_home,
        delete_claude_dir,
        "--yes",
    )
    keep_result = _run_uninstall(
        tmp_path,
        keep_home,
        keep_solar_home,
        keep_claude_dir,
        "--yes",
        "--keep-data",
    )

    assert delete_result.returncode == 0, delete_result.stdout + delete_result.stderr
    assert keep_result.returncode == 0, keep_result.stdout + keep_result.stderr
    assert not delete_solar_home.exists()
    assert not (delete_claude_dir / "solar").exists()
    assert (keep_solar_home / "db" / "solar.db").is_file()
    assert (keep_solar_home / "identity" / "local-accounts.json").is_file()
    assert (keep_solar_home / "config.env").is_file()
    assert (keep_solar_home / ".env").is_file()
    assert not (keep_solar_home / "install-receipt.json").exists()
    assert not (keep_solar_home / "bin").exists()
    assert not (keep_solar_home / "harness").exists()
    assert not (keep_claude_dir / "solar").exists()


def test_atomic_privacy_personal_data_controls__uninstall_delete_versus_dry_run(tmp_path: Path) -> None:
    dry_run_home = tmp_path / "dry-run-home"
    solar_home, claude_dir = _seed_solar_home(dry_run_home)
    before = _snapshot(dry_run_home)

    result = _run_uninstall(
        tmp_path,
        dry_run_home,
        solar_home,
        claude_dir,
        "--yes",
        "--dry-run",
    )
    after = _snapshot(dry_run_home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Would remove OpenSolar files recorded under" in result.stdout
    assert after == before
    assert (solar_home / "install-receipt.json").is_file()
    assert (solar_home / "bin" / "solar").is_file()
    assert (claude_dir / "solar" / "SOLAR.md").is_file()
