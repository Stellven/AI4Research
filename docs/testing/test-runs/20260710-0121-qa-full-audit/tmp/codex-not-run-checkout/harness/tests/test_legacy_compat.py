"""Tests for legacy_adapter.py — wake/dispatch/status dual-write + LR-01~LR-06.

S03 N5 acceptance:
  1. legacy_adapter.py contains wake/dispatch/status 3 dual-write APIs
  2. import-time does NOT trigger broker (lazy import)
  3. LR-01~LR-06 smoke tests all PASS
  4. Old wake/dispatch/status interfaces still work (signature unchanged)
  5. pytest tests/test_legacy_compat.py all PASS
  6. py_compile compat/*.py passes
"""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from harness.lib.compat.legacy_adapter import dispatch, status, wake


@pytest.fixture
def harness_env(tmp_path):
    """Provide a temporary harness environment with sprints dir."""
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    return {"base_dir": str(tmp_path), "sprints_dir": sprints}


def _make_status(harness_env, sprint_id, data):
    p = harness_env["sprints_dir"] / f"{sprint_id}.status.json"
    p.write_text(json.dumps(data))


def _read_status(harness_env, sprint_id):
    p = harness_env["sprints_dir"] / f"{sprint_id}.status.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


# ---------------------------------------------------------------------------
# AC1: wake / dispatch / status 3 APIs
# ---------------------------------------------------------------------------


class TestAPIsExist:
    def test_wake_callable(self):
        assert callable(wake)

    def test_dispatch_callable(self):
        assert callable(dispatch)

    def test_status_callable(self):
        assert callable(status)

    def test_wake_signature(self, harness_env):
        result = wake("sprint-test", base_dir=harness_env["base_dir"])
        assert "sprint_id" in result
        assert "status" in result

    def test_dispatch_signature(self, harness_env):
        result = dispatch("sprint-test", "N1", base_dir=harness_env["base_dir"])
        assert "sprint_id" in result
        assert "node_id" in result
        assert result["dispatched"] is True

    def test_status_signature(self, harness_env):
        result = status("sprint-test", base_dir=harness_env["base_dir"])
        assert "sprint_id" in result
        assert "status" in result


# ---------------------------------------------------------------------------
# AC2 + AC3: import-time does NOT trigger broker (LR-01~LR-06)
# ---------------------------------------------------------------------------


class TestLazyImport:
    def test_import_does_not_load_execution_broker(self):
        """LR-01/LR-06: importing legacy_adapter must not import execution_broker."""
        script = (
            "import sys; "
            "import harness.lib.compat.legacy_adapter; "
            "raise SystemExit(1 if 'execution_broker' in sys.modules else 0)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(Path(__file__).resolve().parents[2]),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_import_does_not_load_event_ledger_at_module_level(self):
        """LR-03/LR-06: event_ledger must only be imported inside functions."""
        source = Path(__file__).parent.parent / "lib" / "compat" / "legacy_adapter.py"
        tree = ast.parse(source.read_text())
        top_imports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [n.name for n in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module]
                )
                for n in names:
                    if n and ("event_ledger" in n or "execution_broker" in n):
                        top_imports.append((node.lineno, n))
        assert top_imports == [], f"top-level broker/ledger imports found: {top_imports}"

    def test_lr06_all_harness_imports_are_function_level(self):
        """LR-06: all harness.lib imports must be inside functions (lazy)."""
        source = Path(__file__).parent.parent / "lib" / "compat" / "legacy_adapter.py"
        tree = ast.parse(source.read_text())
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [n.name for n in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module]
                )
                for n in names:
                    if n and n.startswith("harness.lib"):
                        pytest.fail(
                            f"LR-06 violation: top-level import of {n} at line {node.lineno}"
                        )


# ---------------------------------------------------------------------------
# AC4: old interfaces still work
# ---------------------------------------------------------------------------


class TestWakeLegacy:
    def test_wake_writes_status_json(self, harness_env):
        wake("sprint-wake", base_dir=harness_env["base_dir"])
        data = _read_status(harness_env, "sprint-wake")
        assert data["sprint_id"] == "sprint-wake"
        assert data["status"] == "drafting"
        assert "woke_at" in data

    def test_wake_preserves_existing_status(self, harness_env):
        _make_status(harness_env, "sprint-exist", {"status": "running", "nodes": {"N1": {"status": "done"}}})
        wake("sprint-exist", base_dir=harness_env["base_dir"])
        data = _read_status(harness_env, "sprint-exist")
        assert data["status"] == "running"
        assert data["nodes"]["N1"]["status"] == "done"


class TestDispatchLegacy:
    def test_dispatch_updates_node_status(self, harness_env):
        dispatch("sprint-disp", "N1", base_dir=harness_env["base_dir"])
        data = _read_status(harness_env, "sprint-disp")
        assert data["nodes"]["N1"]["status"] == "dispatched"


class TestStatusLegacy:
    def test_status_reads_json(self, harness_env):
        _make_status(harness_env, "sprint-st", {"status": "reviewing", "nodes": {"N1": {"status": "passed"}}})
        result = status("sprint-st", base_dir=harness_env["base_dir"])
        assert result["status"] == "reviewing"
        assert result["nodes"]["N1"]["status"] == "passed"

    def test_status_missing_json(self, harness_env):
        result = status("nonexistent", base_dir=harness_env["base_dir"])
        assert result["status"] == "unknown"
        assert result["status_json_found"] is False


# ---------------------------------------------------------------------------
# Dual-write with ledger
# ---------------------------------------------------------------------------


class TestDualWrite:
    def test_wake_writes_ledger_when_available(self, harness_env):
        result = wake("sprint-dw", base_dir=harness_env["base_dir"])
        assert result["ledger_written"] is True

    def test_dispatch_writes_ledger_when_available(self, harness_env):
        result = dispatch("sprint-dw", "N1", base_dir=harness_env["base_dir"])
        assert result["ledger_written"] is True

    def test_status_reads_ledger_event_count(self, harness_env):
        wake("sprint-st-dw", base_dir=harness_env["base_dir"])
        dispatch("sprint-st-dw", "N1", base_dir=harness_env["base_dir"])
        result = status("sprint-st-dw", base_dir=harness_env["base_dir"])
        assert result["ledger_event_count"] == 2

    def test_wake_survives_ledger_failure(self, harness_env):
        """When ledger run/ is unwritable, wake still succeeds."""
        run_dir = Path(harness_env["base_dir"]) / "run"
        run_dir.mkdir()
        # Pre-create an events.db and lock it
        db = run_dir / "events.db"
        db.write_text("not a db")
        os.chmod(str(db), 0o000)
        result = wake("sprint-nolegger", base_dir=harness_env["base_dir"])
        os.chmod(str(db), 0o644)
        db.unlink(missing_ok=True)
        assert result["status_json_written"] is True
        assert result["ledger_written"] is False


# ---------------------------------------------------------------------------
# AC6: py_compile
# ---------------------------------------------------------------------------


class TestCompile:
    def test_py_compile_legacy_adapter(self):
        result = subprocess.run(
            ["python3", "-m", "py_compile",
             str(Path(__file__).parent.parent / "lib" / "compat" / "legacy_adapter.py")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_py_compile_compat_init(self):
        result = subprocess.run(
            ["python3", "-m", "py_compile",
             str(Path(__file__).parent.parent / "lib" / "compat" / "__init__.py")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
