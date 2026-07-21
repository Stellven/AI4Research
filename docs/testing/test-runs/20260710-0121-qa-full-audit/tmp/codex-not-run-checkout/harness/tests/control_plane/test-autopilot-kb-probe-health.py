#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "solar-autopilot-monitor.py"
spec = importlib.util.spec_from_file_location("solar_autopilot_monitor", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["solar_autopilot_monitor"] = mod
spec.loader.exec_module(mod)


class _Completed:
    def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_kb_probe_classifies_coverage_miss_as_warn(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mod, "KB_PROBE_HEALTH", tmp_path / "knowledge-probe-health.json")
    monkeypatch.setattr(mod, "KB_PROBE_SCRIPT", tmp_path / "probe.sh")
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "ensure_qmd_mcp_ipv4", lambda reason: {"ok": True, "status": "ok", "reason": reason})
    mod.KB_PROBE_SCRIPT.write_text("#!/usr/bin/env bash\nexit 0\n")
    mod.KB_PROBE_SCRIPT.chmod(0o755)
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: _Completed(
            returncode=1,
            stdout="ok - mirage vfs role -> mirage\nPROBES_PASSED=1 PROBES_FAILED=9\n",
            stderr="not ok - coverage\n",
        ),
    )

    probe = mod.run_kb_probe("periodic", force=True)

    assert probe["ok"] is False
    assert probe["status"] == "warn"
    assert probe["failure_class"] == "coverage_miss"
    assert probe["transport_ok"] is True


def test_run_kb_probe_timeout_stays_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mod, "KB_PROBE_HEALTH", tmp_path / "knowledge-probe-health.json")
    monkeypatch.setattr(mod, "KB_PROBE_SCRIPT", tmp_path / "probe.sh")
    monkeypatch.setattr(mod, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "ensure_qmd_mcp_ipv4", lambda reason: {"ok": True, "status": "ok", "reason": reason})
    mod.KB_PROBE_SCRIPT.write_text("#!/usr/bin/env bash\nexit 0\n")
    mod.KB_PROBE_SCRIPT.chmod(0o755)

    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="probe", timeout=120)

    monkeypatch.setattr(mod.subprocess, "run", _raise_timeout)

    probe = mod.run_kb_probe("periodic", force=True)

    assert probe["ok"] is False
    assert probe["status"] == "error"
    assert probe["error"] == "kb_probe_timeout"


def test_inspect_knowledge_context_uses_warn_finding_for_coverage_miss(monkeypatch) -> None:
    monkeypatch.setattr(mod, "SESSION", "solar-harness")
    monkeypatch.setattr(mod, "tmux_capture", lambda target: "")
    monkeypatch.setattr(mod, "load_json", lambda path, default=None: {})
    monkeypatch.setattr(
        mod,
        "run_kb_probe",
        lambda reason, force=False: {
            "ok": False,
            "status": "warn",
            "reason": reason,
            "checked_at": "2026-05-24T15:00:00Z",
            "probes_passed": 1,
            "probes_failed": 9,
            "failure_class": "coverage_miss",
        },
    )

    state: dict = {}
    findings = mod.inspect_knowledge_context(state)

    assert findings
    finding = findings[-1]
    assert finding["type"] == "knowledge_probe_failed"
    assert finding["severity"] == "warn"
    assert "覆盖不完整" in finding["message"]
    assert state["knowledge_probe"]["status"] == "warn"
    assert state["knowledge_probe"]["failure_class"] == "coverage_miss"
