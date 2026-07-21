"""
Unit tests for operator_router.py

Covers >= 3 scenarios (actually 7):
  1. select_operator — returns correct primary OperatorInfo by line
  2. select_operator — unknown line raises KeyError
  3. dispatch — normal execution: primary succeeds
  4. dispatch — primary fails, auto-fallback to successful fallback
  5. dispatch — primary fails, no fallback configured → NoFallbackError
  6. dispatch_with_control — dual-run primary + control, both succeed
  7. dispatch_with_control — no control defined → ValueError
  8. dispatch_with_control — primary fails, control succeeds (both_succeeded=False)
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure lib/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from operator_registry_loader import clear_cache, load_registry
from operator_router import (
    ControlComparisonResult,
    DispatchResult,
    NoFallbackError,
    OperatorInfo,
    dispatch,
    dispatch_with_control,
    select_operator,
)


# --- Helpers ---


def _make_registry_with_fallback() -> dict:
    """Registry with a line that has fallback configured."""
    return {
        "schema_version": "solar.operator_registry.v1",
        "lines": {
            "test_line": {
                "primary": "scripts/primary_op.py",
                "executors": [],
                "fallback": ["scripts/fallback_op.py"],
                "schedule": "daily",
                "output_dir": "reports/test/",
            }
        },
    }


def _make_registry_no_fallback() -> dict:
    """Registry with a line that has no fallback."""
    return {
        "schema_version": "solar.operator_registry.v1",
        "lines": {
            "test_line": {
                "primary": "scripts/primary_op.py",
                "executors": [],
                "fallback": [],
                "schedule": "daily",
                "output_dir": "reports/test/",
            }
        },
    }


def _make_registry_with_control() -> dict:
    """Registry with a line that has control + dual_run."""
    return {
        "schema_version": "solar.operator_registry.v1",
        "lines": {
            "github_trends": {
                "primary": "scripts/github_trends_digest.py",
                "executors": [],
                "fallback": [],
                "control": ["tools/github_intelligence/pipeline.py"],
                "schedule": "daily",
                "output_dir": "reports/github/",
                "dual_run": {
                    "enabled": True,
                    "comparison_view": True,
                },
            }
        },
    }


def _write_registry(tmpdir: Path, data: dict) -> Path:
    """Write registry JSON to a temp file and return its path."""
    config_dir = tmpdir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    rpath = config_dir / "operator_registry.json"
    rpath.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return rpath


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear loader cache before each test."""
    clear_cache()
    yield
    clear_cache()


# --- Test 1: select_operator returns correct primary ---


class TestSelectOperator:
    def test_returns_correct_primary(self, tmp_path):
        data = _make_registry_with_fallback()
        rpath = _write_registry(tmp_path, data)
        reg = load_registry(registry_path=rpath, harness_root=tmp_path)

        info = select_operator("test_line", registry=reg)

        assert isinstance(info, OperatorInfo)
        assert info.line == "test_line"
        assert info.role == "primary"
        assert info.script == "scripts/primary_op.py"
        assert info.output_dir == "reports/test/"
        assert info.schedule == "daily"

    def test_unknown_line_raises_key_error(self, tmp_path):
        data = _make_registry_with_fallback()
        rpath = _write_registry(tmp_path, data)
        reg = load_registry(registry_path=rpath, harness_root=tmp_path)

        with pytest.raises(KeyError, match="no_such_line"):
            select_operator("no_such_line", registry=reg)


# --- Test 2: dispatch normal execution ---


class TestDispatchNormal:
    def test_primary_success(self, tmp_path):
        data = _make_registry_with_fallback()
        rpath = _write_registry(tmp_path, data)
        reg = load_registry(registry_path=rpath, harness_root=tmp_path)

        # Create a real script that succeeds
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "primary_op.py").write_text(
            'import sys; print("ok"); sys.exit(0)',
            encoding="utf-8",
        )

        result = dispatch(
            "test_line", "run-001", registry=reg, harness_root=tmp_path
        )

        assert isinstance(result, DispatchResult)
        assert result.success is True
        assert result.role == "primary"
        assert result.returncode == 0
        assert "ok" in result.stdout
        assert result.run_id == "run-001"
        assert result.line == "test_line"
        assert result.duration_s >= 0


# --- Test 3: dispatch fallback ---


class TestDispatchFallback:
    def test_primary_fails_fallback_succeeds(self, tmp_path):
        data = _make_registry_with_fallback()
        rpath = _write_registry(tmp_path, data)
        reg = load_registry(registry_path=rpath, harness_root=tmp_path)

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        # Primary fails
        (scripts_dir / "primary_op.py").write_text(
            'import sys; print("fail", file=sys.stderr); sys.exit(1)',
            encoding="utf-8",
        )
        # Fallback succeeds
        (scripts_dir / "fallback_op.py").write_text(
            'import sys; print("fallback ok"); sys.exit(0)',
            encoding="utf-8",
        )

        result = dispatch(
            "test_line", "run-002", registry=reg, harness_root=tmp_path
        )

        assert result.success is True
        assert result.role == "fallback"
        assert result.script == "scripts/fallback_op.py"
        assert "fallback ok" in result.stdout

    def test_primary_fails_no_fallback_raises(self, tmp_path):
        data = _make_registry_no_fallback()
        rpath = _write_registry(tmp_path, data)
        reg = load_registry(registry_path=rpath, harness_root=tmp_path)

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "primary_op.py").write_text(
            "import sys; sys.exit(1)",
            encoding="utf-8",
        )

        with pytest.raises(NoFallbackError, match="no fallback"):
            dispatch(
                "test_line", "run-003", registry=reg, harness_root=tmp_path
            )


# --- Test 4: dispatch_with_control ---


class TestDispatchWithControl:
    def test_dual_run_both_succeed(self, tmp_path):
        data = _make_registry_with_control()
        rpath = _write_registry(tmp_path, data)
        reg = load_registry(registry_path=rpath, harness_root=tmp_path)

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "github_trends_digest.py").write_text(
            'print("primary output")',
            encoding="utf-8",
        )

        tools_dir = tmp_path / "tools" / "github_intelligence"
        tools_dir.mkdir(parents=True, exist_ok=True)
        (tools_dir / "pipeline.py").write_text(
            'print("control output")',
            encoding="utf-8",
        )

        result = dispatch_with_control(
            "github_trends", "run-004", registry=reg, harness_root=tmp_path
        )

        assert isinstance(result, ControlComparisonResult)
        assert result.both_succeeded is True
        assert result.primary.role == "primary"
        assert result.control.role == "control"
        assert "primary output" in result.primary.stdout
        assert "control output" in result.control.stdout
        assert result.line == "github_trends"
        assert result.run_id == "run-004"

    def test_no_control_raises_value_error(self, tmp_path):
        data = _make_registry_no_fallback()  # no control field
        rpath = _write_registry(tmp_path, data)
        reg = load_registry(registry_path=rpath, harness_root=tmp_path)

        with pytest.raises(ValueError, match="no control"):
            dispatch_with_control(
                "test_line", "run-005", registry=reg, harness_root=tmp_path
            )

    def test_dual_run_primary_fails_control_succeeds(self, tmp_path):
        data = _make_registry_with_control()
        rpath = _write_registry(tmp_path, data)
        reg = load_registry(registry_path=rpath, harness_root=tmp_path)

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "github_trends_digest.py").write_text(
            "import sys; sys.exit(1)",
            encoding="utf-8",
        )

        tools_dir = tmp_path / "tools" / "github_intelligence"
        tools_dir.mkdir(parents=True, exist_ok=True)
        (tools_dir / "pipeline.py").write_text(
            'print("control ok")',
            encoding="utf-8",
        )

        result = dispatch_with_control(
            "github_trends", "run-006", registry=reg, harness_root=tmp_path
        )

        assert result.both_succeeded is False
        assert result.primary.success is False
        assert result.control.success is True
        assert "control ok" in result.control.stdout
