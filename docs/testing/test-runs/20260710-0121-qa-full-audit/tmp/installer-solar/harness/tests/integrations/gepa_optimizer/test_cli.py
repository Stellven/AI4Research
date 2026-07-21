"""CLI safety-gate tests run via ``python -m integrations.gepa_optimizer.cli``.

The CLI uses positional args for ``target`` / ``run_dir`` / ``candidate``;
the tests below mirror the real argparse layout (verified via ``--help``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def _run_cli(*args: str, env_extra: dict[str, str] | None = None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO) + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "integrations.gepa_optimizer.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
    )


def _last_json_line(stdout: str) -> dict:
    """Pluck the JSON object out of the stdout produced by the CLI commands."""
    body = stdout.strip()
    if body.startswith("{"):
        return json.loads(body)
    # The CLI may print a short notice on the first line; the JSON body
    # is the remaining lines concatenated.
    last_open = body.rfind("{")
    last_close = body.rfind("}")
    assert last_open != -1 and last_close > last_open, body
    return json.loads(body[last_open : last_close + 1])


def test_cli_help_lists_subcommands():
    out = _run_cli("--help")
    assert out.returncode == 0, out.stderr
    for cmd in ("propose", "run", "review", "promote", "rollback", "status"):
        assert cmd in out.stdout


def test_cli_propose_default_is_dry_run(tmp_path):
    out = _run_cli("propose", str(tmp_path / "x.txt"))
    assert out.returncode == 0, out.stderr
    payload = _last_json_line(out.stdout)
    assert payload["status"] == "proposal_only"
    assert payload["dry_run"] is True


def test_cli_run_without_execute_is_dry_run(tmp_path):
    out = _run_cli("run", str(tmp_path / "x.txt"))
    assert out.returncode == 0, out.stderr
    assert "dry_run" in out.stdout


def test_cli_run_execute_requires_all_three_budgets(tmp_path):
    out = _run_cli(
        "run",
        str(tmp_path / "x.txt"),
        "--execute",
        "--max-evals",
        "10",
        # missing --max-spend and --max-walltime
    )
    assert out.returncode != 0
    assert "SAFETY" in out.stderr
    assert "--max-spend" in out.stderr
    assert "--max-walltime" in out.stderr


def test_cli_promote_rejects_production_target(tmp_path):
    # The CLI uses /tmp allowlist; rejecting anything outside it.
    target = "/etc/passwd"
    out = _run_cli(
        "promote",
        str(tmp_path / "run-1"),
        "c-1",
        "--target",
        target,
    )
    assert out.returncode != 0
    assert "SAFETY" in out.stderr


def test_cli_promote_dry_run_allows_tmp_target(tmp_path):
    target = "/tmp/gepa_test_promote_target.txt"
    out = _run_cli(
        "promote",
        str(tmp_path / "run-1"),
        "c-1",
        "--target",
        target,
    )
    assert out.returncode == 0, out.stderr
    payload = _last_json_line(out.stdout)
    assert payload["status"] == "dry_run"


def test_cli_rollback_default_is_dry_run():
    target = "/tmp/gepa_test_rollback_target.txt"
    out = _run_cli("rollback", "--target", target)
    assert out.returncode == 0, out.stderr
    assert "dry_run" in out.stdout
