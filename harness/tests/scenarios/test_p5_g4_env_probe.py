"""G4 — the e2e sandboxes prove DEFAULT resolution, and a probe exists.

With the governed spine default-on at the parser level (owner decision
2026-07-10), the isolated e2e scripts must STOP exporting
SOLAR_PLAN_VALIDATOR / SOLAR_GATE_LEDGER: the G4 acceptance rung's whole
point is that a run governed with NO flag injection anywhere is what a
fresh-machine user gets. (This deliberately supersedes the run-10 pin that
required the exports — that class is closed at the parser: children resolve
the default themselves, no inheritance needed.)

Because the flags may now be absent from every environment, /proc-grep can
no longer prove the spine — `plan_validator.py env-status` is the
introspection probe: it prints the RESOLVED state and its source, runnable
inside any sandbox.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[2]


def _env_status(extra_env: dict) -> dict:
    env = dict(os.environ)
    env.pop("SOLAR_PLAN_VALIDATOR", None)
    env.pop("SOLAR_GATE_LEDGER", None)
    env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, str(_HARNESS / "lib" / "plan_validator.py"), "env-status"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


class TestEnvStatusProbe:
    def test_fresh_machine_resolves_governed(self):
        status = _env_status({})
        assert status["plan_validator"] == {"enabled": True, "source": "default"}
        assert status["gate_ledger"] == {"enabled": True, "source": "default"}

    def test_kill_switch_reported_with_source(self):
        status = _env_status({"SOLAR_PLAN_VALIDATOR": "0"})
        assert status["plan_validator"] == {"enabled": False, "source": "env"}
        assert status["gate_ledger"] == {"enabled": True, "source": "default"}

    def test_explicit_on_reported_with_source(self):
        status = _env_status({"SOLAR_GATE_LEDGER": "1"})
        assert status["gate_ledger"] == {"enabled": True, "source": "env"}


class TestSandboxScriptsInjectNothing:
    def test_e2e_scripts_do_not_export_the_governed_spine(self):
        """The rung must exercise the runtime default, not injected env."""
        for script in ("scripts/live-codex-e2e-isolated.sh", "scripts/live-claude-e2e-isolated.sh"):
            text = (_HARNESS.parent / script).read_text(encoding="utf-8")
            assert "export SOLAR_PLAN_VALIDATOR" not in text, script
            assert "export SOLAR_GATE_LEDGER" not in text, script


class TestGeneratedEnvIsCleanOfFlagNames:
    def test_generated_e2e_env_heredoc_never_mentions_the_flags(self):
        """G4-lite run 1 (p5-g4-lite-live-rung-20260710T042427Z) stopped at
        the setup gate: the no-injection comment REPLACING the exports sat
        inside the e2e.env generation heredoc and mentioned the flag names,
        so the rung's substring grep (deliberately simple — operator-proof)
        counted 1. The generated file must not contain the flag NAMES at
        all, in any form — the contract is `grep -c '<name>' e2e.env == 0`."""
        import re
        for script in ("scripts/live-codex-e2e-isolated.sh", "scripts/live-claude-e2e-isolated.sh"):
            text = (_HARNESS.parent / script).read_text(encoding="utf-8")
            blocks = re.findall(r'cat > "\$env_file" <<ENV\n(.*?)\nENV\n', text, flags=re.S)
            assert blocks, f"{script}: e2e.env generation heredoc not found"
            for block in blocks:
                assert "SOLAR_PLAN_VALIDATOR" not in block, script
                assert "SOLAR_GATE_LEDGER" not in block, script
