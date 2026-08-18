"""The seam that actually runs AutoSci.

autosci_bridge.py verifies runtime evidence and converts it; it executes
nothing. This executor runs the stage's AutoSci skill and feeds the bridge, so
its safety properties matter: it must fail closed, never synthesise a runtime
record, and never leak provider credentials into the skill subprocess.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[3] / "harness"
EXECUTOR = HARNESS / "plugins/autosci/bin/autosci_skill_executor.py"
_SPEC = importlib.util.spec_from_file_location("autosci_skill_executor", EXECUTOR)
assert _SPEC and _SPEC.loader
ex = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ex)


def _bridge_actions() -> set[str]:
    source = (HARNESS / "plugins/autosci/bin/autosci_bridge.py").read_text(encoding="utf-8")
    block = source.split("ACTIONS: dict[str, Callable", 1)[1].split("}", 1)[0]
    return {line.split('"')[1] for line in block.splitlines() if line.strip().startswith('"')}


def test_every_stage_maps_to_a_real_bridge_action() -> None:
    actions = _bridge_actions()
    for stage, (skill, action) in ex.STAGES.items():
        assert action in actions, f"stage {stage} maps to unknown bridge action {action}"
        assert skill.startswith("$"), f"stage {stage} must name an AutoSci skill invocation"


def test_part_b_stages_are_covered() -> None:
    for stage in (
        "idea_generation",
        "idea_evaluation",
        "experiment_design",
        "experiment_run",
        "experiment_monitor",
        "claim_verification",
        "report_delivery",
    ):
        assert stage in ex.STAGES


def test_fails_closed_without_an_autosci_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOLAR_AUTOSCI_HOME", raising=False)
    with pytest.raises(ex.ExecutorError, match="SOLAR_AUTOSCI_HOME is not set"):
        ex._autosci_home()


def test_fails_closed_when_the_autosci_home_is_not_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bogus = tmp_path / "not-a-dir"
    bogus.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SOLAR_AUTOSCI_HOME", str(bogus))
    with pytest.raises(ex.ExecutorError, match="not a directory"):
        ex._autosci_home()


def test_provider_credentials_are_not_forwarded_to_the_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Codex CLI authenticates from its own CODEX_HOME; an inherited API key
    would silently change the provider boundary the evidence claims."""
    for key in ex.SECRET_ENV_KEYS:
        monkeypatch.setenv(key, "must-not-propagate")
    env = ex._skill_env()
    for key in ex.SECRET_ENV_KEYS:
        assert key not in env


def test_runtime_record_carries_the_real_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed skill run must be recorded as failed so the bridge fails closed.
    With no approval node ahead of execution, a synthesised success here would
    be indistinguishable from a real one."""
    home = tmp_path / "autosci"
    home.mkdir()
    monkeypatch.setenv("SOLAR_AUTOSCI_HOME", str(home))
    # a "codex" that always fails
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "codex").write_text("#!/bin/sh\necho boom >&2\nexit 3\n", encoding="utf-8")
    (fake / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")

    record_path = tmp_path / "rec.json"
    record = ex.run_skill(
        stage="experiment_run", request="anything", record_path=record_path, timeout_seconds=30
    )
    assert record["exit_code"] == 3
    assert record["credential_contents_recorded"] is False
    on_disk = json.loads(record_path.read_text(encoding="utf-8"))
    assert on_disk["exit_code"] == 3
    assert Path(on_disk["stderr_path"]).read_text(encoding="utf-8").strip() == "boom"


def test_cli_reports_the_failure_as_json_and_exits_nonzero(tmp_path: Path) -> None:
    env = dict(os.environ)
    env.pop("SOLAR_AUTOSCI_HOME", None)
    envelope = tmp_path / "envelope.json"
    envelope.write_text(json.dumps({"task_id": "t", "inputs": {}}), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(EXECUTOR), "--stage", "experiment_run", "--envelope", str(envelope)],
        capture_output=True, text=True, env=env, check=False,
    )
    assert proc.returncode == 2
    assert json.loads(proc.stderr)["ok"] is False
