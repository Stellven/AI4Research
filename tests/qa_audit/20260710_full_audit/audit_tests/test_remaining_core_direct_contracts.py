from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
HARNESS = CHECKOUT / "harness"
PYTHON = CHECKOUT / ".venv/bin/python"
SOLAR_HARNESS = HARNESS / "solar-harness.sh"


def isolated_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if any(marker in key.upper() for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
            env.pop(key, None)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    user_config = tmp_path / "solar-user-config.json"
    if not user_config.exists():
        user_config.write_bytes((HARNESS / "config/solar-user-config.json").read_bytes())
    env.update(
        {
            "HOME": str(home),
            "SOLAR_HOME": str(home / ".solar"),
            "HARNESS_DIR": str(HARNESS),
            "SOLAR_USER_CONFIG": str(user_config),
            "PYTHONPATH": str(HARNESS),
            "AUTOSCI_DISABLE_NETWORK_FETCH": "1",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
        }
    )
    return env


def run(command: list[str], tmp_path: Path, timeout: int = 60) -> subprocess.CompletedProcess[str]:
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


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_models_show_is_read_only_and_lists_roles(tmp_path: Path) -> None:
    home = tmp_path / "home"
    before = snapshot(home)
    proc = run([str(SOLAR_HARNESS), "models", "show"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for role in ("main pm", "main planner", "main builder", "main evaluator", "lab matrix"):
        assert role in proc.stdout
    assert snapshot(home) == before


def test_models_invalid_alias_is_rejected_with_allowed_options(tmp_path: Path) -> None:
    proc = run([str(SOLAR_HARNESS), "models", "set-main", "qa-invalid-model"], tmp_path)
    assert proc.returncode != 0
    text = (proc.stdout + proc.stderr).lower()
    assert "opus" in text and "anthropic-sonnet" in text


def test_models_set_main_without_apply_does_not_write_config(tmp_path: Path) -> None:
    env = isolated_env(tmp_path)
    config = Path(env["SOLAR_USER_CONFIG"])
    before = config.read_bytes()
    proc = run([str(SOLAR_HARNESS), "models", "set-main", "opus"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert config.read_bytes() == before, "models set-main mutated config without --apply"


def test_benchmark_doctor_list_and_status_banner_are_typed(tmp_path: Path) -> None:
    base = [str(PYTHON), "-m", "tools.benchmark.runner"]
    doctor = run([*base, "doctor", "--json"], tmp_path)
    assert doctor.returncode in {0, 2}, doctor.stdout + doctor.stderr
    doctor_payload = json.loads(doctor.stdout)
    assert doctor_payload.get("adapter_id") and "missing_prereqs" in doctor_payload

    listed = run([*base, "list", "--json"], tmp_path)
    assert listed.returncode in {0, 2}, listed.stdout + listed.stderr
    listed_payload = json.loads(listed.stdout)
    assert isinstance(listed_payload, list) and listed_payload
    assert all(row.get("id") and row.get("title") for row in listed_payload)

    env = isolated_env(tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir()
    env["SOLAR_BENCH_REPORTS_DIR"] = str(reports)
    empty = subprocess.run(
        [str(PYTHON), "-m", "lib.benchmark.orchestration.status_banner"],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    assert empty.returncode == 0 and "no recent benchmark run" in empty.stdout
    (reports / "latest-terminal-bench-2.json").write_text(
        json.dumps(
            {
                "verdict": "ok",
                "score": 0.75,
                "pass_count": 3,
                "fail_count": 1,
                "started_at": "2026-07-13T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    populated = subprocess.run(
        [str(PYTHON), "-m", "lib.benchmark.orchestration.status_banner"],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    assert populated.returncode == 0
    assert "verdict=ok" in populated.stdout and "3/4 tasks passed" in populated.stdout
    assert len(populated.stdout.strip()) <= 80
