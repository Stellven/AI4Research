"""
Unit tests for operator_registry_loader.py

Covers:
  1. Normal load — valid registry loads and returns correct structure
  2. Missing field — registry with missing required field raises RegistryValidationError
  3. File existence audit — loader correctly marks existing/missing operator files
  4. Invalid JSON — raises RegistryLoadError
  5. Cache behavior — second load returns cached result
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure lib/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from operator_registry_loader import (
    RegistryLoadError,
    RegistryValidationError,
    audit_file_existence,
    clear_cache,
    get_line,
    list_lines,
    load_registry,
)


def _make_valid_registry() -> dict:
    """Return a minimal valid registry dict."""
    return {
        "schema_version": "solar.operator_registry.v1",
        "lines": {
            "test_line": {
                "primary": "scripts/test_op.py",
                "executors": [],
                "fallback": [],
                "schedule": "daily",
                "output_dir": "reports/test/",
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


# --- Test 1: Normal load ---

class TestNormalLoad:
    def test_load_valid_registry(self, tmp_path):
        data = _make_valid_registry()
        rpath = _write_registry(tmp_path, data)

        result = load_registry(registry_path=rpath, harness_root=tmp_path)

        assert result["schema_version"] == "solar.operator_registry.v1"
        assert "test_line" in result["lines"]
        assert result["lines"]["test_line"]["primary"] == "scripts/test_op.py"

    def test_list_lines(self, tmp_path):
        data = _make_valid_registry()
        data["lines"]["second_line"] = {
            "primary": "scripts/second.py",
            "executors": [],
            "fallback": [],
        }
        rpath = _write_registry(tmp_path, data)

        reg = load_registry(registry_path=rpath, harness_root=tmp_path)
        lines = list_lines(registry=reg)

        assert set(lines) == {"test_line", "second_line"}

    def test_get_line(self, tmp_path):
        data = _make_valid_registry()
        rpath = _write_registry(tmp_path, data)

        reg = load_registry(registry_path=rpath, harness_root=tmp_path)
        line = get_line("test_line", registry=reg)

        assert line["primary"] == "scripts/test_op.py"
        assert line["schedule"] == "daily"

    def test_get_line_not_found(self, tmp_path):
        data = _make_valid_registry()
        rpath = _write_registry(tmp_path, data)

        reg = load_registry(registry_path=rpath, harness_root=tmp_path)
        with pytest.raises(KeyError, match="no_such_line"):
            get_line("no_such_line", registry=reg)


# --- Test 2: Missing field / validation errors ---

class TestValidationErrors:
    def test_missing_schema_version(self, tmp_path):
        data = _make_valid_registry()
        del data["schema_version"]
        rpath = _write_registry(tmp_path, data)

        with pytest.raises(RegistryValidationError, match="schema_version"):
            load_registry(registry_path=rpath, harness_root=tmp_path)

    def test_wrong_schema_version(self, tmp_path):
        data = _make_valid_registry()
        data["schema_version"] = "wrong.version"
        rpath = _write_registry(tmp_path, data)

        with pytest.raises(RegistryValidationError, match="Unsupported schema_version"):
            load_registry(registry_path=rpath, harness_root=tmp_path)

    def test_missing_lines(self, tmp_path):
        data = {"schema_version": "solar.operator_registry.v1"}
        rpath = _write_registry(tmp_path, data)

        with pytest.raises(RegistryValidationError, match="lines"):
            load_registry(registry_path=rpath, harness_root=tmp_path)

    def test_missing_primary_in_line(self, tmp_path):
        data = _make_valid_registry()
        del data["lines"]["test_line"]["primary"]
        rpath = _write_registry(tmp_path, data)

        with pytest.raises(RegistryValidationError, match="primary"):
            load_registry(registry_path=rpath, harness_root=tmp_path)

    def test_missing_executors_in_line(self, tmp_path):
        data = _make_valid_registry()
        del data["lines"]["test_line"]["executors"]
        rpath = _write_registry(tmp_path, data)

        with pytest.raises(RegistryValidationError, match="executors"):
            load_registry(registry_path=rpath, harness_root=tmp_path)

    def test_missing_fallback_in_line(self, tmp_path):
        data = _make_valid_registry()
        del data["lines"]["test_line"]["fallback"]
        rpath = _write_registry(tmp_path, data)

        with pytest.raises(RegistryValidationError, match="fallback"):
            load_registry(registry_path=rpath, harness_root=tmp_path)

    def test_empty_lines(self, tmp_path):
        data = {"schema_version": "solar.operator_registry.v1", "lines": {}}
        rpath = _write_registry(tmp_path, data)

        with pytest.raises(RegistryValidationError, match="at least one"):
            load_registry(registry_path=rpath, harness_root=tmp_path)


# --- Test 3: File existence audit ---

class TestFileExistenceAudit:
    def test_existing_file_marked_true(self, tmp_path):
        # Create the operator file
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "test_op.py").write_text("# operator", encoding="utf-8")

        data = _make_valid_registry()
        rpath = _write_registry(tmp_path, data)

        reg = load_registry(registry_path=rpath, harness_root=tmp_path)
        report = audit_file_existence(registry=reg, harness_root=tmp_path)

        assert report["test_line"]["primary"]["exists"] is True
        assert report["test_line"]["primary"]["path"] == "scripts/test_op.py"

    def test_missing_file_marked_false(self, tmp_path):
        data = _make_valid_registry()
        rpath = _write_registry(tmp_path, data)

        reg = load_registry(registry_path=rpath, harness_root=tmp_path)
        report = audit_file_existence(registry=reg, harness_root=tmp_path)

        # scripts/test_op.py does not exist in tmp_path
        assert report["test_line"]["primary"]["exists"] is False

    def test_executor_existence(self, tmp_path):
        # Create executor file
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "helper.py").write_text("# helper", encoding="utf-8")

        data = _make_valid_registry()
        data["lines"]["test_line"]["executors"] = ["tools/helper.py", "tools/missing.py"]
        rpath = _write_registry(tmp_path, data)

        reg = load_registry(registry_path=rpath, harness_root=tmp_path)
        report = audit_file_existence(registry=reg, harness_root=tmp_path)

        executors = report["test_line"]["executors"]
        assert len(executors) == 2
        assert executors[0]["path"] == "tools/helper.py"
        assert executors[0]["exists"] is True
        assert executors[1]["path"] == "tools/missing.py"
        assert executors[1]["exists"] is False

    def test_audit_all_roles(self, tmp_path):
        data = _make_valid_registry()
        data["lines"]["test_line"]["control"] = ["tools/control_op.py"]
        data["lines"]["test_line"]["helper"] = ["scripts/run.sh"]
        rpath = _write_registry(tmp_path, data)

        reg = load_registry(registry_path=rpath, harness_root=tmp_path)
        report = audit_file_existence(registry=reg, harness_root=tmp_path)

        entry = report["test_line"]
        assert "primary" in entry
        assert "executors" in entry
        assert "fallback" in entry
        assert "control" in entry
        assert "helper" in entry
        # All missing since we didn't create any files
        assert entry["primary"]["exists"] is False
        assert entry["control"][0]["exists"] is False
        assert entry["helper"][0]["exists"] is False


# --- Test 4: Load errors ---

class TestLoadErrors:
    def test_file_not_found(self, tmp_path):
        with pytest.raises(RegistryLoadError, match="not found"):
            load_registry(registry_path=tmp_path / "nonexistent.json")

    def test_invalid_json(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        bad_file = config_dir / "operator_registry.json"
        bad_file.write_text("{invalid json!!!", encoding="utf-8")

        with pytest.raises(RegistryLoadError, match="Invalid JSON"):
            load_registry(registry_path=bad_file)


# --- Test 5: Cache behavior ---

class TestCacheBehavior:
    def test_cache_returns_same_object(self, tmp_path):
        data = _make_valid_registry()
        rpath = _write_registry(tmp_path, data)

        r1 = load_registry(registry_path=rpath, harness_root=tmp_path, use_cache=True)
        r2 = load_registry(registry_path=rpath, harness_root=tmp_path, use_cache=True)

        assert r1 is r2  # Same object from cache

    def test_no_cache_returns_fresh(self, tmp_path):
        data = _make_valid_registry()
        rpath = _write_registry(tmp_path, data)

        r1 = load_registry(registry_path=rpath, harness_root=tmp_path, use_cache=True)
        clear_cache()
        r2 = load_registry(registry_path=rpath, harness_root=tmp_path, use_cache=False)

        assert r1 is not r2  # Different objects
        assert r1 == r2  # Same content
