"""G4 default-on — the governed spine is the runtime default (owner decision
2026-07-10).

SOLAR_PLAN_VALIDATOR and SOLAR_GATE_LEDGER flip from opt-in to opt-out at
the PARSER level: every consumer resolves "enabled unless the value is
explicitly 0/false/no/off". Unset (the fresh-machine state) means ON — no
shell wiring, no e2e.env injection, no flag knowledge required for a new
install to be governed. The kill switch is an explicit =0, documented and
discouraged (G4 spec §1-2; parser-level chosen over shell-level so direct
CLI entry points and the status-server inherit the default identically).

A source-scan invariant pins the idiom repo-wide so a future consumer
cannot silently reintroduce opt-in parsing for these two flags.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
for _p in (str(_HARNESS / "lib"), str(_HARNESS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import plan_validator as pv  # noqa: E402
import contract_gate_executor as cge  # noqa: E402
import gate_ledger as gl  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402
import multi_task_runner as lib_mtr  # noqa: E402


def _tools_mtr():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "g4_tools_multi_task_runner", _HARNESS / "tools" / "multi_task_runner.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PARSERS = [
    ("plan_validator._env_gate_enabled", lambda: pv._env_gate_enabled(), "SOLAR_PLAN_VALIDATOR"),
    ("contract_gate_executor._plan_validator_enabled", lambda: cge._plan_validator_enabled(), "SOLAR_PLAN_VALIDATOR"),
    ("graph_node_dispatcher._plan_validator_enabled", lambda: gnd._plan_validator_enabled(), "SOLAR_PLAN_VALIDATOR"),
    ("lib_multi_task_runner._plan_validator_env_on", lambda: lib_mtr._plan_validator_env_on(), "SOLAR_PLAN_VALIDATOR"),
    ("gate_ledger.enabled", lambda: gl.enabled(), "SOLAR_GATE_LEDGER"),
]


class TestDefaultOnSemantics:
    @pytest.mark.parametrize("name,parser,env", PARSERS, ids=[p[0] for p in PARSERS])
    def test_unset_means_on(self, monkeypatch, name, parser, env):
        monkeypatch.delenv(env, raising=False)
        assert parser() is True, f"{name}: unset (fresh machine) must resolve ON"

    @pytest.mark.parametrize("name,parser,env", PARSERS, ids=[p[0] for p in PARSERS])
    @pytest.mark.parametrize("value", ["0", "false", "no", "off", " OFF ", "False"])
    def test_explicit_kill_switch_wins(self, monkeypatch, name, parser, env, value):
        monkeypatch.setenv(env, value)
        assert parser() is False, f"{name}: explicit {value!r} must resolve OFF"

    @pytest.mark.parametrize("name,parser,env", PARSERS, ids=[p[0] for p in PARSERS])
    def test_explicit_on_still_on(self, monkeypatch, name, parser, env):
        monkeypatch.setenv(env, "1")
        assert parser() is True

    def test_tools_multi_task_runner_parser_matches(self, monkeypatch):
        mod = _tools_mtr()
        monkeypatch.delenv("SOLAR_PLAN_VALIDATOR", raising=False)
        assert mod._plan_validator_env_on() is True
        monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "0")
        assert mod._plan_validator_env_on() is False


class TestWorkflowGuardFailClosedByDefault:
    def test_uncheckable_validator_fails_closed_when_unset(self, tmp_path, monkeypatch):
        """workflow_guard's import-failure branch: with the flag UNSET
        (default-on), a graph that cannot be checked must fail closed —
        not silently pass as not_applicable."""
        import json
        import workflow_guard as wg

        graph_path = tmp_path / "sprint-g4-wg.task_graph.json"
        graph_path.write_text(json.dumps({
            "sprint_id": "sprint-g4-wg",
            "plan_compile_required": True,
            "nodes": [{"id": "S1", "depends_on": []}],
        }), encoding="utf-8")
        monkeypatch.delenv("SOLAR_PLAN_VALIDATOR", raising=False)
        monkeypatch.setitem(sys.modules, "plan_validator", None)  # import fails
        ok, reason = wg._plan_certificate_ready(graph_path)
        assert ok is False, (ok, reason)
        assert "uncheckable" in reason, reason

    def test_uncheckable_validator_passes_open_when_killed(self, tmp_path, monkeypatch):
        import json
        import workflow_guard as wg

        graph_path = tmp_path / "sprint-g4-wg2.task_graph.json"
        graph_path.write_text(json.dumps({
            "sprint_id": "sprint-g4-wg2",
            "plan_compile_required": True,
            "nodes": [{"id": "S1", "depends_on": []}],
        }), encoding="utf-8")
        monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "0")
        monkeypatch.setitem(sys.modules, "plan_validator", None)
        ok, reason = wg._plan_certificate_ready(graph_path)
        assert ok is True
        assert reason == "not_applicable"


class TestNoOptInParsingRemains:
    """Repo-wide idiom pin: every runtime read of the two governed-spine flags
    must use opt-out semantics (a disabled-set membership test), never the
    old opt-in truthy-set. Guards future consumers."""

    _OPT_IN = re.compile(
        r'(SOLAR_PLAN_VALIDATOR|SOLAR_GATE_LEDGER)[^\n]*\n?[^\n]*in\s*\{\s*"1"',
    )

    def test_no_runtime_opt_in_truthy_parse(self):
        offenders = []
        for root in (_HARNESS / "lib", _HARNESS / "tools"):
            for path in root.rglob("*.py"):
                if "test" in path.name:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                for m in self._OPT_IN.finditer(text):
                    snippet = m.group(0)
                    if "environ" in snippet or "getenv" in snippet:
                        offenders.append(f"{path.relative_to(_HARNESS)}: {snippet[:120]}")
        assert not offenders, "opt-in truthy parsing of governed-spine flags remains:\n" + "\n".join(offenders)
