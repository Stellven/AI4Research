"""P1.5 regression for the isolated Claude smoke sandbox.

This locks the deterministic launch-path contract for P2 without running a
live Claude model. The fake ``claude`` binary only satisfies preflight
CLI-presence checks; no prompt is submitted.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "live-claude-e2e-isolated.sh"
CONTRACT = REPO / "harness" / "config" / "workflows" / "code.cli_smoke_anthropic.workflow.json"


def _fake_toolchain(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    for name in ("claude", "tmux"):
        exe = bin_dir / name
        exe.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        exe.chmod(0o755)
    return bin_dir


def test_prepare_only_sandbox_env_passes_anthropic_contract_preflight(tmp_path):
    """The Claude prepare-only sandbox must satisfy the product-mode preflight:
    active harness lib pinned, sandbox-local shim first on PATH, HOME-relative
    Claude credentials present by stat only, and the Anthropic workflow contract
    compiled under the anthropic-only provider policy."""
    sandbox = tmp_path / "sandbox"
    host_home = tmp_path / "host-home"
    credentials = host_home / ".claude" / ".credentials.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text('{"fixture":"stat-only"}\n', encoding="utf-8")
    fake_bin = _fake_toolchain(tmp_path)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(host_home),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "SOLAR_LIVE_E2E_SANDBOX": str(sandbox),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    for key in (
        "SOLAR_PANE_RUNTIME",
        "SOLAR_PM_DEFAULT_PROVIDERS",
        "SOLAR_MULTI_TASK_DEFAULT_PROVIDERS",
        "SOLAR_GATE_LEDGER",
        "SOLAR_PRODUCT_MODE",
        "SOLAR_WORKFLOW_ROUTER",
    ):
        env.pop(key, None)

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
    report_path = sandbox / "home" / ".solar" / "harness" / "sprints" / "live-claude-preflight.preflight.json"
    preflight = json.loads(report_path.read_text(encoding="utf-8"))
    assert preflight["ok"] is True
    assert preflight["failed"] == []
    assert preflight["provider_policy"] == ["anthropic"]

    env_text = env_file.read_text(encoding="utf-8")
    for flag in (
        "SOLAR_PANE_RUNTIME=claude",
        "SOLAR_PM_DEFAULT_PROVIDERS=anthropic",
        "SOLAR_MULTI_TASK_DEFAULT_PROVIDERS=anthropic",
        "SOLAR_GATE_LEDGER=1",
        "SOLAR_PRODUCT_MODE=1",
        "SOLAR_WORKFLOW_ROUTER=1",
    ):
        assert flag in env_text, f"generated e2e.env must pin {flag} explicitly:\n{env_text}"

    creds_link = sandbox / "home" / ".claude" / ".credentials.json"
    assert creds_link.is_symlink()
    assert creds_link.resolve() == credentials.resolve()

    cmd = (
        f". {env_file}; "
        "printf '%s\n' \"$PYTHONPATH\" \"$PATH\" \"$HOME\" \"$HARNESS_DIR\"; "
        "python3 \"$HARNESS_DIR/lib/run_preflight.py\" "
        "--sid test --providers anthropic "
        f"--contract {CONTRACT} "
        "--expect-harness-dir \"$HARNESS_DIR\" --no-write"
    )
    replay = subprocess.run(
        ["bash", "-c", cmd],
        cwd=sandbox / "workspace",
        env={"PATH": f"{fake_bin}:/usr/bin:/bin"},
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert replay.returncode == 0, replay.stdout + replay.stderr
    lines = replay.stdout.splitlines()
    assert lines[0] == str(sandbox / "home" / ".solar" / "harness" / "lib")
    assert lines[1].split(":")[0] == str(sandbox / "home" / ".solar" / "bin")
    assert lines[2] == str(sandbox / "home")
    assert lines[3] == str(sandbox / "home" / ".solar" / "harness")


def test_prepare_only_sandbox_env_emits_anthropic_route_records(tmp_path):
    """The generated e2e.env is authoritative for sandbox children: sourcing it
    alone must expose product flags and provider pins so route records are
    written as anthropic without inheriting shell state."""
    sandbox = tmp_path / "sandbox"
    host_home = tmp_path / "host-home"
    credentials = host_home / ".claude" / ".credentials.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text('{"fixture":"stat-only"}\n', encoding="utf-8")
    fake_bin = _fake_toolchain(tmp_path)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(host_home),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "SOLAR_LIVE_E2E_SANDBOX": str(sandbox),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    for key in (
        "SOLAR_PANE_RUNTIME",
        "SOLAR_PM_DEFAULT_PROVIDERS",
        "SOLAR_MULTI_TASK_DEFAULT_PROVIDERS",
        "SOLAR_GATE_LEDGER",
        "SOLAR_PRODUCT_MODE",
        "SOLAR_WORKFLOW_ROUTER",
    ):
        env.pop(key, None)

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
    probe = (
        f". {env_file}; "
        "python3 - <<'PY'\n"
        "import operator_runtime as opr, gate_ledger as gl\n"
        "opr.write_result(operator_id='env-probe-op', task_id='t1', sprint_id='env-probe',\n"
        "                 node_id='S1', status='succeeded', exit_code=0,\n"
        "                 started_at='2026-07-07T00:00:00Z', finished_at='2026-07-07T00:01:00Z',\n"
        "                 log_tail='probe', model_route={'effective_provider': 'anthropic'})\n"
        "rows = gl.read_records(gl.default_sprints_dir(), 'env-probe', kind='route_record')\n"
        "print('route_records=%d provider=%s' % (len(rows), rows[0].get('route', {}).get('provider')))\n"
        "assert len(rows) == 1, rows\n"
        "assert rows[0].get('route', {}).get('provider') == 'anthropic', rows\n"
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
    assert "route_records=1 provider=anthropic" in result.stdout
