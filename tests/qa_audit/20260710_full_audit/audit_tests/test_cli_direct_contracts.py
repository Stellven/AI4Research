from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
PYTHON = CHECKOUT / ".venv/bin/python"
SAFE_BIN = AUDIT_ROOT / "tmp" / "safe-bin"


def isolated_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if any(marker in key.upper() for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
            env.pop(key, None)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env.update(
        {
            "HOME": str(home),
            "SOLAR_HOME": str(home / ".solar"),
            "CLAUDE_DIR": str(home / ".claude"),
            "CODEX_HOME": str(home / ".codex"),
            "HARNESS_TEST": "1",
            "AUTOSCI_DISABLE_NETWORK_FETCH": "1",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost",
            "PATH": os.pathsep.join([str(SAFE_BIN), str(CHECKOUT / ".venv/bin"), os.environ.get("PATH", "")]),
        }
    )
    return env


def run(command: list[str], tmp_path: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=CHECKOUT,
        env=isolated_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


CLI_CASES = [
    (
        "graph-scheduler",
        [str(PYTHON), str(CHECKOUT / "harness/tools/graph_scheduler.py")],
        {"validate", "topo", "layers", "critical-path", "ready", "batches", "assign", "mark", "doctor"},
    ),
    (
        "graph-node-dispatcher",
        [str(PYTHON), str(CHECKOUT / "harness/tools/graph_node_dispatcher.py")],
        {"drain-queue", "dispatch-ready", "dispatch-evals", "node-verdict"},
    ),
    (
        "knowledge-ingest-dispatcher",
        [str(PYTHON), str(CHECKOUT / "harness/tools/knowledge_ingest_dispatcher.py")],
        {"status", "qmd-watermarks", "submit-event", "discover-raw", "process-queue", "reconcile", "dashboard"},
    ),
    (
        "knowledge-ingest-health",
        [str(PYTHON), str(CHECKOUT / "harness/tools/knowledge_ingest_health.py")],
        {"health", "audit", "circuit-check"},
    ),
    (
        "knowledge-qmd-indexer",
        [str(PYTHON), str(CHECKOUT / "harness/tools/knowledge_qmd_indexer.py")],
        {"watermarks", "mark-indexed", "microbatch", "advance-indexed-states"},
    ),
]


@pytest.mark.parametrize("case,command,subcommands", CLI_CASES, ids=[item[0] for item in CLI_CASES])
def test_cli_help_exposes_documented_subcommands_and_unknown_is_rejected(
    case: str,
    command: list[str],
    subcommands: set[str],
    tmp_path: Path,
) -> None:
    help_proc = run([*command, "--help"], tmp_path)
    assert help_proc.returncode == 0, help_proc.stdout + help_proc.stderr
    help_text = help_proc.stdout + help_proc.stderr
    assert all(name in help_text for name in subcommands)

    invalid = run([*command, "qa-unsupported-command"], tmp_path)
    assert invalid.returncode != 0
    invalid_text = (invalid.stdout + invalid.stderr).lower()
    assert "invalid choice" in invalid_text or "usage:" in invalid_text


def test_benchmark_cli_help_doctor_list_and_invalid_contract(tmp_path: Path) -> None:
    command = [str(PYTHON), "-m", "tools.benchmark.runner"]
    env = isolated_env(tmp_path)
    env["PYTHONPATH"] = str(CHECKOUT / "harness")
    help_proc = subprocess.run(
        [*command, "--help"], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert help_proc.returncode == 0
    for name in ("doctor", "list", "plan", "run", "report"):
        assert name in help_proc.stdout

    invalid = subprocess.run(
        [*command, "qa-unsupported-command"], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert invalid.returncode != 0
    assert "invalid choice" in invalid.stderr.lower()

    doctor = subprocess.run(
        [*command, "doctor"], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert doctor.returncode in {0, 2}
    doctor_text = (doctor.stdout + doctor.stderr).lower()
    assert "terminal" in doctor_text or "harbor" in doctor_text or "doctor" in doctor_text


def test_solar_lifecycle_read_only_commands_are_typed_and_do_not_create_home_state(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    home = Path(env["HOME"])
    solar = str(CHECKOUT / "bin/solar")
    solar_home = Path(env["SOLAR_HOME"])
    solar_home.mkdir(parents=True)
    receipt = solar_home / "install-receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "version": "qa-fixture",
                "git_sha": "fb3f589b08e4167ac3cb0043fb3d59801a0f110b",
                "channel": "audit",
                "repo": "https://github.com/Stellven/AI4Research",
                "components": [],
            }
        ),
        encoding="utf-8",
    )
    before = {path.relative_to(home) for path in home.rglob("*")}

    help_proc = subprocess.run(
        [solar, "--help"], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert help_proc.returncode == 0
    for name in ("version", "status", "doctor", "update", "repair", "backup", "restore", "ui", "harness", "uninstall", "components"):
        assert name in help_proc.stdout

    version = subprocess.run(
        [solar, "version", "--json"], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert version.returncode == 0
    version_payload = json.loads(version.stdout)
    assert version_payload.get("version")

    status = subprocess.run(
        [solar, "status", "--json"], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert status.returncode != 0
    status_payload = json.loads(status.stdout)
    assert status_payload["install"]["verdict"] == "fail"
    assert status_payload["runtime"]["harness"] == "not-installed"
    assert status_payload["daemon"]["component"] == "not-installed"

    doctor = subprocess.run(
        [solar, "doctor", "--json"], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert doctor.returncode != 0
    doctor_payload = json.loads(doctor.stdout)
    assert doctor_payload["verdict"] == "fail"
    assert doctor_payload["paths"]["receipt"] == "ok"
    assert doctor_payload["paths"]["kernel"] == "missing"
    assert doctor_payload["models"]["anthropic_credentials"] == "missing"

    after = {path.relative_to(home) for path in home.rglob("*")}
    assert after == before
    assert not (home / ".claude").exists()


def test_solar_uninstall_dry_run_and_invalid_restore_preserve_isolated_home(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    home = Path(env["HOME"])
    solar = str(CHECKOUT / "bin/solar")

    uninstall = subprocess.run(
        [solar, "uninstall", "--yes", "--dry-run"], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert uninstall.returncode in {0, 1}
    assert "dry" in (uninstall.stdout + uninstall.stderr).lower() or "not installed" in (uninstall.stdout + uninstall.stderr).lower()

    restore = subprocess.run(
        [solar, "restore", str(tmp_path / "missing-backup.tar.gz")], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert restore.returncode != 0
    assert "missing" in (restore.stdout + restore.stderr).lower() or "not found" in (restore.stdout + restore.stderr).lower()
    assert not (home / ".solar").exists()


def test_solar_backup_restore_round_trip_is_scoped_to_isolated_home(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    solar_home = Path(env["SOLAR_HOME"])
    solar_home.mkdir(parents=True)
    (solar_home / "config.env").write_text("QA_VALUE=preserve\n", encoding="utf-8")
    (solar_home / "install-receipt.json").write_text(
        json.dumps({"version": "qa", "components": ["kernel"]}),
        encoding="utf-8",
    )
    archive = tmp_path / "backup.tar.gz"
    solar = str(CHECKOUT / "bin/solar")

    backup = subprocess.run(
        [solar, "backup", "--out", str(archive)], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert backup.returncode == 0, backup.stdout + backup.stderr
    assert archive.is_file() and archive.stat().st_size > 0

    (solar_home / "config.env").unlink()
    restore = subprocess.run(
        [solar, "restore", str(archive)], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert restore.returncode == 0, restore.stdout + restore.stderr
    assert (solar_home / "config.env").read_text(encoding="utf-8") == "QA_VALUE=preserve\n"
    assert json.loads((solar_home / "install-receipt.json").read_text(encoding="utf-8"))["components"] == ["kernel"]


def test_solar_components_list_has_observable_output(tmp_path: Path) -> None:
    solar = str(CHECKOUT / "bin/solar")
    listed = run([solar, "components", "list"], tmp_path)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert listed.stdout.strip(), "components list exited 0 but emitted no component inventory"


def test_solar_components_invalid_usage_fails(tmp_path: Path) -> None:
    solar = str(CHECKOUT / "bin/solar")
    invalid = run([solar, "components", "--json"], tmp_path)
    assert invalid.returncode != 0, "unsupported components --json was accepted as generic help"


def test_solar_harness_help_and_invalid_command_are_explicit_and_scoped(tmp_path: Path) -> None:
    solar = str(CHECKOUT / "bin/solar")
    env = isolated_env(tmp_path)
    home = Path(env["HOME"])
    before = {path.relative_to(home) for path in home.rglob("*")}

    help_proc = subprocess.run(
        [solar, "harness", "--help"], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert help_proc.returncode == 0
    assert "Solar Harness" in help_proc.stdout

    invalid = subprocess.run(
        [solar, "harness", "qa-unsupported-command"], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert invalid.returncode != 0
    assert "qa-unsupported-command" in (invalid.stdout + invalid.stderr)
    after = {path.relative_to(home) for path in home.rglob("*")}
    assert after == before


def test_solar_ui_once_reports_not_installed_without_mutating_home(tmp_path: Path) -> None:
    solar = str(CHECKOUT / "bin/solar")
    env = isolated_env(tmp_path)
    home = Path(env["HOME"])
    before = {path.relative_to(home) for path in home.rglob("*")}

    proc = subprocess.run(
        [solar, "ui", "--once", "--no-color"], cwd=CHECKOUT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Solar UI-lite" in proc.stdout
    assert "status: not-installed" in proc.stdout
    assert "live Claude status: manual-pending" in proc.stdout
    after = {path.relative_to(home) for path in home.rglob("*")}
    assert after == before


def test_solar_ui_invalid_option_is_rejected(tmp_path: Path) -> None:
    proc = run([str(CHECKOUT / "bin/solar"), "ui", "--qa-invalid"], tmp_path)
    assert proc.returncode != 0
    assert "unrecognized arguments" in (proc.stdout + proc.stderr).lower()
