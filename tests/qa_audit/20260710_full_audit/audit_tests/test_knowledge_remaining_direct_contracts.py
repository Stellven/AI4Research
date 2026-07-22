from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
PYTHON = CHECKOUT / ".venv/bin/python"
DISPATCHER = CHECKOUT / "harness/tools/knowledge_ingest_dispatcher.py"
HEALTH = CHECKOUT / "harness/tools/knowledge_ingest_health.py"
QMD = CHECKOUT / "harness/tools/knowledge_qmd_indexer.py"


def safe_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if any(marker in key.upper() for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
            env.pop(key, None)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    safe_bin = tmp_path / "safe-bin"
    safe_bin.mkdir(exist_ok=True)
    solar_harness = safe_bin / "solar-harness"
    if not solar_harness.exists():
        solar_harness.symlink_to(CHECKOUT / "harness/solar-harness.sh")
    env.update(
        {
            "HOME": str(home),
            "SOLAR_HOME": str(home / ".solar"),
            "HARNESS_DIR": str(CHECKOUT / "harness"),
            "AUTOSCI_DISABLE_NETWORK_FETCH": "1",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "PATH": os.pathsep.join([str(safe_bin), os.environ.get("PATH", "")]),
        }
    )
    return env


def run(tool: Path, args: list[str], tmp_path: Path, timeout: int = 40) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON), str(tool), *args],
        cwd=CHECKOUT,
        env=safe_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def json_run(tool: Path, args: list[str], tmp_path: Path, timeout: int = 40) -> dict:
    proc = run(tool, args, tmp_path, timeout=timeout)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def seed_workspace(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    db = tmp_path / "knowledge.sqlite"
    raw = tmp_path / "raw"
    vault = tmp_path / "vault"
    extracted = tmp_path / "extracted"
    raw.mkdir()
    vault.mkdir()
    extracted.mkdir()
    (raw / "paper.md").write_text("# Paper\n\nGrounded fixture.\n", encoding="utf-8")
    (vault / "note.md").write_text("# Note\n\nVault fixture.\n", encoding="utf-8")
    (extracted / "legacy.md").write_text("# Legacy\n\nExtracted fixture.\n", encoding="utf-8")
    return db, raw, vault, extracted


def test_dispatcher_report_commands_emit_typed_json_and_dashboard(tmp_path: Path) -> None:
    db, raw, vault, extracted = seed_workspace(tmp_path)
    json_run(DISPATCHER, ["--db", str(db), "discover-raw", "--source-dir", str(raw), "--json"], tmp_path)
    json_run(DISPATCHER, ["--db", str(db), "discover-vault", "--vault", str(vault), "--json"], tmp_path)

    status = json_run(DISPATCHER, ["--db", str(db), "status", "--json"], tmp_path)
    assert status["schema_version"]
    coverage = json_run(DISPATCHER, ["--db", str(db), "coverage-report", "--json"], tmp_path)
    assert isinstance(coverage, dict) and coverage
    watermarks = json_run(DISPATCHER, ["--db", str(db), "qmd-watermarks", "--json"], tmp_path)
    assert isinstance(watermarks, dict) and watermarks

    dashboard_path = tmp_path / "dashboard.html"
    dashboard = json_run(
        DISPATCHER,
        ["--db", str(db), "dashboard", "--html", str(dashboard_path), "--json"],
        tmp_path,
    )
    assert isinstance(dashboard, dict) and dashboard
    assert dashboard_path.is_file() and "html" in dashboard_path.read_text(encoding="utf-8").lower()


def test_dispatcher_discovery_queue_and_legacy_import_are_idempotent(tmp_path: Path) -> None:
    db, raw, vault, extracted = seed_workspace(tmp_path)
    first = json_run(
        DISPATCHER,
        ["--db", str(db), "discover-sources", "--source-dir", str(raw), "--source-kind", "qa", "--json"],
        tmp_path,
    )
    second = json_run(
        DISPATCHER,
        ["--db", str(db), "discover-sources", "--source-dir", str(raw), "--source-kind", "qa", "--json"],
        tmp_path,
    )
    assert first.get("count") == second.get("count")

    imported = json_run(
        DISPATCHER,
        ["--db", str(db), "import-legacy-extracted", "--extracted-dir", str(extracted), "--json"],
        tmp_path,
    )
    assert isinstance(imported, dict)
    processed = json_run(DISPATCHER, ["--db", str(db), "process-queue", "--json"], tmp_path)
    assert isinstance(processed, dict)
    retry = json_run(DISPATCHER, ["--db", str(db), "drain-retry", "--json"], tmp_path)
    skipped = json_run(DISPATCHER, ["--db", str(db), "drain-skip", "--json"], tmp_path)
    assert isinstance(retry, dict) and isinstance(skipped, dict)


def test_dispatcher_reconcile_and_pipeline_remain_local_and_typed(tmp_path: Path) -> None:
    db, raw, vault, extracted = seed_workspace(tmp_path)
    reconciled = json_run(
        DISPATCHER,
        [
            "--db", str(db), "reconcile", "--raw-dir", str(raw), "--vault", str(vault),
            "--extracted-dir", str(extracted), "--skip-qmd", "--no-fail", "--json",
        ],
        tmp_path,
        timeout=60,
    )
    assert isinstance(reconciled, dict) and reconciled

    pipeline = json_run(
        DISPATCHER,
        [
            "--db", str(db), "run-pipeline", "--raw-dir", str(raw), "--vault", str(vault),
            "--discover", "--skip-embed", "--max-batches", "1", "--json",
        ],
        tmp_path,
        timeout=60,
    )
    assert isinstance(pipeline, dict) and pipeline


@pytest.mark.parametrize("command", ["health", "audit", "circuit-check"])
def test_knowledge_health_commands_emit_typed_results(command: str, tmp_path: Path) -> None:
    db, raw, vault, extracted = seed_workspace(tmp_path)
    json_run(DISPATCHER, ["--db", str(db), "status", "--json"], tmp_path)
    proc = run(HEALTH, ["--db", str(db), command], tmp_path)
    assert proc.returncode in {0, 1, 2, 3}, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert isinstance(payload, dict) and payload
    assert any(key in payload for key in ("status", "health", "ok", "verdict", "schema"))


@pytest.mark.parametrize("command", ["mark-indexed", "microbatch", "advance-indexed-states"])
def test_qmd_index_commands_reject_missing_required_input_without_state_corruption(command: str, tmp_path: Path) -> None:
    db, raw, vault, extracted = seed_workspace(tmp_path)
    before = db.read_bytes() if db.exists() else b""
    proc = run(QMD, ["--db", str(db), command, "--qa-invalid"], tmp_path)
    assert proc.returncode != 0
    assert "usage:" in (proc.stdout + proc.stderr).lower()
    after = db.read_bytes() if db.exists() else b""
    assert after == before
