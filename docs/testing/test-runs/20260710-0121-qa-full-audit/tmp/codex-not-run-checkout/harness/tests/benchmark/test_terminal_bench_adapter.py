"""Unit tests for TerminalBench20Adapter and harbor_adapter.

S03 N6 acceptance:
  - build_argv positive (well-formed Harbor argv)
  - allowlist negative (agent not in AGENT_ALLOWLIST → verdict='error')
  - full-without-confirm-budget negative (verdict='error')
  - missing-prereq pending (verdict='pending' when doctor.missing_prereqs)
  - no-secret-logging scan (event payloads + logs never contain real key VALUES)

All subprocess + network calls are mocked. No real harbor/docker/uvx is invoked.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from harness.lib.benchmark import harbor_adapter
from harness.lib.benchmark.schemas import (
    AGENT_ALLOWLIST,
    BenchmarkDoctor,
    BenchmarkRunRequest,
)
from harness.lib.benchmark.terminal_bench import TerminalBench20Adapter


_SENTINEL_SECRET = "sk-FAKE-DO-NOT-LEAK-XYZ-987654321"


def _make_req(**overrides):
    base = dict(
        adapter_id="terminal-bench@2.0",
        agent="claude-code",
        model="claude-opus-4-7",
        env="docker",
        tasks=("hello-world-cli",),
        n_concurrent=1,
        full=False,
        confirm_budget=False,
        dry_run=True,
    )
    base.update(overrides)
    return BenchmarkRunRequest(**base)


# ---------------------------------------------------------------------------
# build_argv: positive
# ---------------------------------------------------------------------------
def test_build_argv_positive_shape_when_harbor_binary_present():
    """build_argv must produce a deterministic, well-shaped Harbor argv."""
    req = _make_req()
    with patch("harness.lib.benchmark.harbor_adapter.detect",
               return_value=(True, "binary")):
        argv = harbor_adapter.build_argv(req)

    assert argv[0] == "harbor"
    assert "run" in argv
    assert "--dataset" in argv
    assert "terminal-bench@2.0" in argv
    assert "--agent" in argv
    assert "claude-code" in argv
    assert "--model" in argv
    assert "claude-opus-4-7" in argv
    assert "--n-concurrent" in argv
    assert "1" in argv
    assert "--env" in argv
    assert "docker" in argv
    assert "hello-world-cli" in argv  # task tail


def test_build_argv_uses_uvx_prefix_when_no_binary():
    req = _make_req()
    with patch("harness.lib.benchmark.harbor_adapter.detect",
               return_value=(True, "uvx")):
        argv = harbor_adapter.build_argv(req)
    assert argv[:2] == ["uvx", "harbor"]


def test_build_argv_is_pure_no_subprocess_call():
    """build_argv must NOT invoke subprocess.run for any executable."""
    req = _make_req()
    with patch("subprocess.run") as mocked_run, \
         patch("harness.lib.benchmark.harbor_adapter.detect",
               return_value=(True, "binary")):
        harbor_adapter.build_argv(req)
    assert mocked_run.call_count == 0, (
        "build_argv leaked a subprocess.run call — must be pure"
    )


# ---------------------------------------------------------------------------
# Allowlist negative
# ---------------------------------------------------------------------------
def test_agent_not_in_allowlist_yields_error_verdict():
    req = _make_req(agent="evil-rogue-cli")
    adapter = TerminalBench20Adapter()
    result = adapter.run(req)
    assert result.verdict == "error"
    assert "agent_not_in_allowlist" in result.failure_modes
    assert result.verdict != "ok"


def test_every_allowlisted_agent_passes_first_gate():
    """Sanity: every name in AGENT_ALLOWLIST clears the agent-allowlist gate."""
    adapter = TerminalBench20Adapter()
    # Force doctor to report no prereqs so we can isolate the agent gate
    fake_doctor = BenchmarkDoctor(
        adapter_id="terminal-bench@2.0",
        harbor_available=True,
        harbor_kind="binary",
        docker_available=True,
        dataset_known=True,
        agents_known=AGENT_ALLOWLIST,
        missing_prereqs=(),
        notes="all-ok-fixture",
    )
    with patch.object(TerminalBench20Adapter, "doctor", return_value=fake_doctor), \
         patch("harness.lib.benchmark.harbor_adapter.detect",
               return_value=(True, "binary")):
        for agent in AGENT_ALLOWLIST:
            req = _make_req(agent=agent, dry_run=True)
            result = adapter.run(req)
            assert "agent_not_in_allowlist" not in result.failure_modes, agent


# ---------------------------------------------------------------------------
# full-without-confirm-budget negative
# ---------------------------------------------------------------------------
def test_full_without_confirm_budget_yields_error_verdict():
    req = _make_req(full=True, confirm_budget=False)
    result = TerminalBench20Adapter().run(req)
    assert result.verdict == "error"
    assert "full_run_without_confirm_budget" in result.failure_modes


def test_full_with_confirm_budget_does_not_trip_budget_gate():
    """full + confirm_budget must clear the budget gate (may still be pending
    on other prereqs, but NOT error/full_run_without_confirm_budget)."""
    req = _make_req(full=True, confirm_budget=True)
    result = TerminalBench20Adapter().run(req)
    assert "full_run_without_confirm_budget" not in result.failure_modes


# ---------------------------------------------------------------------------
# missing-prereq pending  (EXPLICIT assertion: verdict != 'ok' when missing)
# ---------------------------------------------------------------------------
def test_missing_prereqs_yields_pending_verdict_not_ok():
    """REQUIRED by AC: explicit assertion that verdict != 'ok' when
    missing_prereqs is non-empty."""
    req = _make_req(env="")  # bypass cloud-env key gate
    fake_doctor = BenchmarkDoctor(
        adapter_id="terminal-bench@2.0",
        harbor_available=False,
        harbor_kind="missing",
        docker_available=False,
        dataset_known=False,
        agents_known=(),
        missing_prereqs=("harbor_cli", "docker", "api_key:claude-code"),
        notes="all-missing-fixture",
    )
    with patch.object(TerminalBench20Adapter, "doctor", return_value=fake_doctor):
        result = TerminalBench20Adapter().run(req)

    # EXPLICIT AC: verdict != 'ok' when missing_prereqs is non-empty
    assert result.verdict != "ok"
    assert result.verdict == "pending"
    # The missing prereqs propagate into failure_modes (per pending_result path)
    assert "harbor_cli" in result.failure_modes
    assert "docker" in result.failure_modes


def test_empty_missing_prereqs_allows_dry_run_ok():
    """Sanity reverse: when prereqs OK, dry_run yields verdict='ok'."""
    req = _make_req(dry_run=True)
    fake_doctor = BenchmarkDoctor(
        adapter_id="terminal-bench@2.0",
        harbor_available=True,
        harbor_kind="binary",
        docker_available=True,
        dataset_known=True,
        agents_known=AGENT_ALLOWLIST,
        missing_prereqs=(),
        notes="all-ok-fixture",
    )
    with patch.object(TerminalBench20Adapter, "doctor", return_value=fake_doctor), \
         patch("harness.lib.benchmark.harbor_adapter.detect",
               return_value=(True, "binary")):
        result = TerminalBench20Adapter().run(req)
    assert result.verdict == "ok"
    assert result.command and result.command[0] in ("harbor", "uvx")


# ---------------------------------------------------------------------------
# No-secret-logging scan
# ---------------------------------------------------------------------------
def test_probe_api_key_never_returns_or_logs_value(monkeypatch, capsys):
    """probe_api_key must only return bool, never expose the value."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", _SENTINEL_SECRET)
    present = harbor_adapter.probe_api_key("claude-code")
    captured = capsys.readouterr()
    assert present is True
    assert _SENTINEL_SECRET not in captured.out
    assert _SENTINEL_SECRET not in captured.err


def test_plan_env_overrides_marker_does_not_include_value(monkeypatch):
    """plan() must mark key presence with 'present', not the actual value."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", _SENTINEL_SECRET)
    req = _make_req()
    adapter = TerminalBench20Adapter()
    with patch("harness.lib.benchmark.harbor_adapter.detect",
               return_value=(True, "binary")):
        plan = adapter.plan(req)

    serialized = json.dumps({
        "command": list(plan.command),
        "env_overrides": plan.env_overrides,
        "notes": plan.notes,
    })
    assert _SENTINEL_SECRET not in serialized
    # marker is 'present', value is never written
    if "ANTHROPIC_API_KEY" in plan.env_overrides:
        assert plan.env_overrides["ANTHROPIC_API_KEY"] == "present"


def test_run_result_serialization_does_not_leak_env_value(monkeypatch):
    """asdict_run_result on a successful dry-run must not embed the real key."""
    from harness.lib.benchmark.schemas import asdict_run_result

    monkeypatch.setenv("ANTHROPIC_API_KEY", _SENTINEL_SECRET)
    monkeypatch.setenv("OPENAI_API_KEY", _SENTINEL_SECRET + "-openai")
    req = _make_req(dry_run=True)
    fake_doctor = BenchmarkDoctor(
        adapter_id="terminal-bench@2.0",
        harbor_available=True, harbor_kind="binary",
        docker_available=True, dataset_known=True,
        agents_known=AGENT_ALLOWLIST,
        missing_prereqs=(), notes="ok",
    )
    with patch.object(TerminalBench20Adapter, "doctor", return_value=fake_doctor), \
         patch("harness.lib.benchmark.harbor_adapter.detect",
               return_value=(True, "binary")):
        result = TerminalBench20Adapter().run(req)

    payload = json.dumps(asdict_run_result(result), default=str)
    assert _SENTINEL_SECRET not in payload
    assert (_SENTINEL_SECRET + "-openai") not in payload


# ---------------------------------------------------------------------------
# Subprocess discipline guard
# ---------------------------------------------------------------------------
def test_doctor_does_not_invoke_real_docker_when_subprocess_mocked():
    """All subprocess.run calls in doctor() must be mockable — no os.system,
    no os.popen, no shell fork-bomb paths."""
    with patch("subprocess.run") as mocked_run, \
         patch("urllib.request.urlopen") as mocked_url, \
         patch("shutil.which", return_value=None):
        mocked_run.return_value.returncode = 1
        mocked_url.side_effect = Exception("network blocked")
        doc = TerminalBench20Adapter().doctor()

    assert isinstance(doc, BenchmarkDoctor)
    # Doctor MUST surface missing_prereqs when harbor + docker absent
    assert doc.harbor_available is False
    assert doc.docker_available is False
    assert "harbor_cli" in doc.missing_prereqs
    assert "docker" in doc.missing_prereqs
