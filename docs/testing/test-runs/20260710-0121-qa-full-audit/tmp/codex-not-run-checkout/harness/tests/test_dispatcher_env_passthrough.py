#!/usr/bin/env python3
"""test_dispatcher_env_passthrough.py — N2: SOLAR_BROKER_* env forwarding to child subprocesses.

Acceptance criteria:
  - child subprocess receives SOLAR_BROKER_ENABLED and SOLAR_BROKER_SPRINT_ID
  - graph_scheduler.py public signature diff = 0 (LR-04)
  - SOLAR_BROKER_ENABLED=0 unchanged dispatch path
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

HARNESS_LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph(tmp_path: Path, sid: str) -> dict:
    sprints = tmp_path / "sprints"
    sprints.mkdir(exist_ok=True)
    graph = {
        "sprint_id": sid,
        "nodes": [
            {
                "id": "N1",
                "goal": "test goal",
                "depends_on": [],
                "write_scope": ["harness/lib/foo.py"],
                "required_skills": ["python"],
                "acceptance": ["pytest foo"],
                "status": "pending",
            }
        ],
    }
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps(graph, indent=2))
    (sprints / f"{sid}.contract.md").write_text("# Contract\n")
    return graph


# ---------------------------------------------------------------------------
# Tests: _broker_env
# ---------------------------------------------------------------------------

class TestBrokerEnv:
    def setup_method(self):
        import importlib
        import graph_node_dispatcher as _mod
        self.mod = _mod

    def test_defaults_when_env_empty(self, monkeypatch):
        monkeypatch.delenv("SOLAR_BROKER_ENABLED", raising=False)
        monkeypatch.delenv("SOLAR_BROKER_SPRINT_ID", raising=False)
        env = self.mod._broker_env()
        assert env["SOLAR_BROKER_ENABLED"] == "0"
        assert "SOLAR_BROKER_SPRINT_ID" not in env

    def test_sprint_id_set_when_not_in_env(self, monkeypatch):
        monkeypatch.delenv("SOLAR_BROKER_SPRINT_ID", raising=False)
        env = self.mod._broker_env("sprint-test-123")
        assert env["SOLAR_BROKER_SPRINT_ID"] == "sprint-test-123"

    def test_sprint_id_not_overridden_if_in_env(self, monkeypatch):
        monkeypatch.setenv("SOLAR_BROKER_SPRINT_ID", "existing-sprint")
        env = self.mod._broker_env("sprint-test-123")
        assert env["SOLAR_BROKER_SPRINT_ID"] == "existing-sprint"

    def test_broker_enabled_forwarded_as_1(self, monkeypatch):
        monkeypatch.setenv("SOLAR_BROKER_ENABLED", "1")
        env = self.mod._broker_env("sprint-abc")
        assert env["SOLAR_BROKER_ENABLED"] == "1"
        assert env["SOLAR_BROKER_SPRINT_ID"] == "sprint-abc"

    def test_broker_enabled_zero_forwarded(self, monkeypatch):
        monkeypatch.setenv("SOLAR_BROKER_ENABLED", "0")
        env = self.mod._broker_env("sprint-abc")
        assert env["SOLAR_BROKER_ENABLED"] == "0"

    def test_returns_copy_not_same_reference(self, monkeypatch):
        env1 = self.mod._broker_env("sprint-x")
        env2 = self.mod._broker_env("sprint-y")
        assert env1 is not env2
        assert env1 is not os.environ


# ---------------------------------------------------------------------------
# Tests: child subprocess receives both env vars
# ---------------------------------------------------------------------------

class TestInjectDispatchContextEnvPassthrough:
    """Verify _inject_dispatch_context passes broker env to child subprocesses."""

    def setup_method(self):
        import graph_node_dispatcher as _mod
        self.mod = _mod

    def test_solar_skills_subprocess_receives_broker_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SOLAR_BROKER_ENABLED", "1")
        monkeypatch.setenv("SOLAR_BROKER_SPRINT_ID", "sprint-passthrough-test")

        injector = tmp_path / "solar_skills.py"
        injector.write_text("# stub")
        instruction = tmp_path / "dispatch.md"
        instruction.write_text("# dispatch")

        monkeypatch.setattr(self.mod, "HARNESS_DIR", tmp_path)
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir(exist_ok=True)
        injector_lib = lib_dir / "solar_skills.py"
        injector_lib.write_text("# stub")

        captured_envs: list[dict] = []

        def fake_run(*args, **kwargs):
            captured_envs.append(kwargs.get("env") or {})
            result = MagicMock()
            result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=fake_run):
            self.mod._inject_dispatch_context(
                instruction,
                sid="sprint-passthrough-test",
                pane="solar-harness:0.1",
                dispatch_id="test-dispatch-001",
            )

        assert len(captured_envs) >= 1, "Expected at least one subprocess call"
        for env in captured_envs:
            assert env.get("SOLAR_BROKER_ENABLED") == "1", f"Missing SOLAR_BROKER_ENABLED in env: {env}"
            assert env.get("SOLAR_BROKER_SPRINT_ID") == "sprint-passthrough-test", \
                f"Missing SOLAR_BROKER_SPRINT_ID in env: {env}"

    def test_runtime_context_inject_subprocess_receives_broker_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SOLAR_BROKER_ENABLED", "1")
        monkeypatch.setenv("SOLAR_BROKER_SPRINT_ID", "sprint-runtime-test")

        monkeypatch.setattr(self.mod, "HARNESS_DIR", tmp_path)
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir(exist_ok=True)
        injector_lib = lib_dir / "solar_skills.py"
        injector_lib.write_text("# stub")
        runtime_injector = lib_dir / "runtime_context_inject.py"
        runtime_injector.write_text("# stub")

        instruction = tmp_path / "dispatch.md"
        instruction.write_text("# dispatch")

        captured_envs: list[dict] = []

        def fake_run(*args, **kwargs):
            captured_envs.append(kwargs.get("env") or {})
            result = MagicMock()
            result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=fake_run):
            self.mod._inject_dispatch_context(
                instruction,
                sid="sprint-runtime-test",
                pane="solar-harness:0.1",
                dispatch_id="test-dispatch-002",
            )

        runtime_envs = [e for e in captured_envs if e.get("SOLAR_BROKER_SPRINT_ID") == "sprint-runtime-test"]
        assert len(runtime_envs) >= 1
        for env in runtime_envs:
            assert env["SOLAR_BROKER_ENABLED"] == "1"


# ---------------------------------------------------------------------------
# Tests: SOLAR_BROKER_ENABLED=0 unchanged dispatch path (LR-04)
# ---------------------------------------------------------------------------

class TestBrokerEnabledZeroDispatchPath:
    """Verify SOLAR_BROKER_ENABLED=0 does not alter dispatch behavior."""

    def setup_method(self):
        import graph_node_dispatcher as _mod
        self.mod = _mod

    def test_dispatch_path_broker_disabled(self, tmp_path, monkeypatch):
        """With SOLAR_BROKER_ENABLED=0, dispatch completes without broker-specific changes."""
        monkeypatch.setenv("SOLAR_BROKER_ENABLED", "0")
        monkeypatch.delenv("SOLAR_BROKER_SPRINT_ID", raising=False)

        monkeypatch.setattr(self.mod, "HARNESS_DIR", tmp_path)
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir(exist_ok=True)

        instruction = tmp_path / "dispatch.md"
        instruction.write_text("# dispatch")

        captured_envs: list[dict] = []

        def fake_run(*args, **kwargs):
            captured_envs.append(kwargs.get("env") or {})
            result = MagicMock()
            result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=fake_run):
            self.mod._inject_dispatch_context(
                instruction,
                sid="sprint-disabled-test",
                pane="solar-harness:0.1",
                dispatch_id="test-dispatch-003",
            )

        for env in captured_envs:
            assert env.get("SOLAR_BROKER_ENABLED") == "0"

    def test_broker_env_zero_does_not_block_env_copy(self, monkeypatch):
        """_broker_env with SOLAR_BROKER_ENABLED=0 returns full os.environ copy."""
        import graph_node_dispatcher as mod
        monkeypatch.setenv("SOLAR_BROKER_ENABLED", "0")
        monkeypatch.setenv("HOME", "/test-home")

        env = mod._broker_env("sprint-zero-test")
        assert env["SOLAR_BROKER_ENABLED"] == "0"
        assert env.get("HOME") == "/test-home", "os.environ should be copied wholesale"


# ---------------------------------------------------------------------------
# Tests: graph_scheduler.py public signature unchanged (LR-04)
# ---------------------------------------------------------------------------

class TestGraphSchedulerSignatureUnchanged:
    """N2 must not modify graph_scheduler.py public signatures (LR-04)."""

    def _get_public_functions(self, mod) -> set[str]:
        import inspect
        return {
            name for name, obj in inspect.getmembers(mod, inspect.isfunction)
            if not name.startswith("_")
        }

    def test_graph_scheduler_public_functions_present(self):
        import graph_scheduler
        public_fns = self._get_public_functions(graph_scheduler)
        required = {
            "load_graph",
            "save_graph",
            "validate_graph",
            "topo_order",
            "topo_layers",
            "critical_path",
            "ready_nodes",
            "make_batches",
            "assign_workers",
            "assign_ready",
            "mark_node_result",
            "set_node_status",
            "enqueue_ready",
            "parent_ready_check",
            "node_status",
            "write_scope_conflict",
            "blocked_external_prerequisites",
        }
        missing = required - public_fns
        assert not missing, f"graph_scheduler missing public functions: {missing}"

    def test_graph_scheduler_signature_load_graph(self):
        import inspect
        import graph_scheduler
        sig = inspect.signature(graph_scheduler.load_graph)
        params = list(sig.parameters.keys())
        assert "path" in params

    def test_graph_scheduler_signature_ready_nodes(self):
        import inspect
        import graph_scheduler
        sig = inspect.signature(graph_scheduler.ready_nodes)
        params = list(sig.parameters.keys())
        assert "graph" in params

    def test_graph_scheduler_signature_assign_ready(self):
        import inspect
        import graph_scheduler
        sig = inspect.signature(graph_scheduler.assign_ready)
        params = list(sig.parameters.keys())
        assert "graph" in params
        assert "workers" in params
