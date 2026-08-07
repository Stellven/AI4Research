"""P1.5 regression for the isolated Codex smoke sandbox.

Captured failing-scenario.json context:
{
  "id": "P2-CODEX-SMOKE-R6-1",
  "commit": "ccb5e9c493a1d8a47f4d4bafc61adac6a7cc6b99",
  "provider": "openai",
  "runtime": "codex",
  "sandbox": "/tmp/solar-live-p2-codex-20260707T172158Z",
  "failed": ["harness_path_consistency", "auth_presence"]
}
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "live-codex-e2e-isolated.sh"


def _fake_toolchain(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    for name in ("codex", "tmux"):
        exe = bin_dir / name
        exe.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        exe.chmod(0o755)
    return bin_dir


def test_prepare_only_sandbox_env_passes_openai_run_preflight(tmp_path):
    """The prepare-only sandbox must satisfy the same product-mode preflight that
    blocked the live /intake run: active harness lib pinned, sandbox-local shim on
    PATH, and HOME-relative Codex auth present by stat only. No LLM process is
    launched; the fake codex binary is only for run_preflight's CLI-presence
    checks."""
    sandbox = tmp_path / "sandbox"
    codex_home = tmp_path / "host-codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text('{"fixture":"stat-only"}\n', encoding="utf-8")
    fake_bin = _fake_toolchain(tmp_path)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "SOLAR_LIVE_E2E_SANDBOX": str(sandbox),
            "SOLAR_LIVE_E2E_CODEX_HOME": str(codex_home),
            "SOLAR_MULTI_TASK_DEFAULT_PROVIDERS": "openai",
            "SOLAR_PM_DEFAULT_PROVIDERS": "openai",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    prepared = subprocess.run(
        ["bash", str(SCRIPT), "--prepare-only"],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    runtime_config = json.loads(
        (sandbox / "home" / ".solar" / "harness" / "config" / "solar-user-config.json").read_text(
            encoding="utf-8"
        )
    )
    assert runtime_config["codex"]["search"] is True

    env_file = sandbox / "evidence" / "e2e.env"
    report_path = sandbox / "home" / ".solar" / "harness" / "sprints" / "test.preflight.json"
    cmd = (
        f". {env_file}; "
        "export SOLAR_MULTI_TASK_DEFAULT_PROVIDERS=openai; "
        "python3 \"$HARNESS_DIR/lib/run_preflight.py\" "
        "--sid test --providers openai --expect-harness-dir \"$HARNESS_DIR\""
    )
    preflight = subprocess.run(
        ["bash", "-c", cmd],
        cwd=sandbox / "workspace",
        env={"PATH": f"{fake_bin}:/usr/bin:/bin"},
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["failed"] == []


def test_sandbox_env_uses_default_on_governance_and_writes_route_records(tmp_path):
    """P2 smoke run 2 (bundle 20260707T180639Z): the sandboxed run produced ZERO
    kind=route_record rows because the generated e2e.env is the authoritative
    environment for every sandbox process, and it did not carry the product
    flags — the operatord lineage ran before governance became default-on. The
    sandbox must now prove the fresh-machine default: it pins product/router
    mode, leaves both governed-spine override variables absent, and still makes
    operator_runtime.write_result emit a completed route record."""
    sandbox = tmp_path / "sandbox"
    codex_home = tmp_path / "host-codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text('{"fixture":"stat-only"}\n', encoding="utf-8")
    fake_bin = _fake_toolchain(tmp_path)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "SOLAR_LIVE_E2E_SANDBOX": str(sandbox),
            "SOLAR_LIVE_E2E_CODEX_HOME": str(codex_home),
            "SOLAR_MULTI_TASK_DEFAULT_PROVIDERS": "openai",
            "SOLAR_PM_DEFAULT_PROVIDERS": "openai",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    # The launching shell deliberately does NOT export the product flags — the
    # generated env must supply them itself.
    for flag in (
        "SOLAR_GATE_LEDGER",
        "SOLAR_PLAN_VALIDATOR",
        "SOLAR_PRODUCT_MODE",
        "SOLAR_WORKFLOW_ROUTER",
    ):
        env.pop(flag, None)
    prepared = subprocess.run(
        ["bash", str(SCRIPT), "--prepare-only"],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    env_file = sandbox / "evidence" / "e2e.env"
    env_text = env_file.read_text(encoding="utf-8")
    for flag in ("SOLAR_PRODUCT_MODE=1", "SOLAR_WORKFLOW_ROUTER=1"):
        assert flag in env_text, f"generated e2e.env must pin {flag} explicitly:\n{env_text}"
    for flag in ("SOLAR_GATE_LEDGER", "SOLAR_PLAN_VALIDATOR"):
        assert flag not in env_text, f"generated e2e.env must exercise default-on {flag}:\n{env_text}"

    probe = (
        f". {env_file}; "
        "python3 - <<'PY'\n"
        "import os\n"
        "import operator_runtime as opr, gate_ledger as gl, plan_validator as pv\n"
        "assert 'SOLAR_GATE_LEDGER' not in os.environ\n"
        "assert 'SOLAR_PLAN_VALIDATOR' not in os.environ\n"
        "assert gl.enabled() is True\n"
        "assert pv._env_gate_enabled() is True\n"
        "opr.write_result(operator_id='env-probe-op', task_id='t1', sprint_id='env-probe',\n"
        "                 node_id='S1', status='succeeded', exit_code=0,\n"
        "                 started_at='2026-07-07T00:00:00Z', finished_at='2026-07-07T00:01:00Z',\n"
        "                 log_tail='probe', model_route={'effective_provider': 'openai'})\n"
        "rows = gl.read_records(gl.default_sprints_dir(), 'env-probe', kind='route_record')\n"
        "print('route_records=%d' % len(rows))\n"
        "assert len(rows) == 1, rows\n"
        "PY"
    )
    result = subprocess.run(
        ["bash", "-c", probe],
        cwd=sandbox / "workspace",
        env={"PATH": f"{fake_bin}:/usr/bin:/bin"},
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "route_records=1" in result.stdout
