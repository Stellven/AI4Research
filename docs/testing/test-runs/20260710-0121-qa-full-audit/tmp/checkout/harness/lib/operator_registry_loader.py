"""
Operator Registry Loader — loads, validates, caches, and audits operator_registry.json.

Part of Solar Harness AI Influence operator consolidation (S03 N1).
"""

import json
import os
import time
from pathlib import Path
from typing import Any


_HARNESS_ROOT = Path(os.environ.get("SOLAR_HARNESS_DIR", os.path.expanduser("~/.solar/harness")))
_DEFAULT_REGISTRY_PATH = _HARNESS_ROOT / "config" / "operator_registry.json"

EXPECTED_SCHEMA_VERSION = "solar.operator_registry.v1"
REQUIRED_LINE_FIELDS = {"primary", "executors", "fallback"}
VALID_SCHEDULES = {"daily", "on_demand", "weekly", "hourly"}

# Simple in-memory cache
_cache: dict[str, Any] = {}
_cache_mtime: dict[str, float] = {}


class RegistryValidationError(Exception):
    """Raised when operator_registry.json fails schema validation."""


class RegistryLoadError(Exception):
    """Raised when operator_registry.json cannot be read or parsed."""


def _resolve_path(relative_path: str, root: Path | None = None) -> Path:
    """Resolve operator file path relative to harness root."""
    base = root if root is not None else _HARNESS_ROOT
    return base / relative_path


def load_registry(
    registry_path: str | Path | None = None,
    harness_root: str | Path | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """
    Load and validate operator_registry.json.

    Args:
        registry_path: Path to registry JSON. Defaults to config/operator_registry.json.
        harness_root: Override harness root for file existence checks.
        use_cache: If True, return cached result when file hasn't changed.

    Returns:
        Validated registry dict.

    Raises:
        RegistryLoadError: If file cannot be read or parsed.
        RegistryValidationError: If schema validation fails.
    """
    rpath = Path(registry_path) if registry_path else _DEFAULT_REGISTRY_PATH
    root = Path(harness_root) if harness_root else _HARNESS_ROOT
    cache_key = str(rpath)

    # Cache check: return cached if file mtime unchanged
    if use_cache and cache_key in _cache:
        try:
            current_mtime = rpath.stat().st_mtime
            if current_mtime == _cache_mtime.get(cache_key):
                return _cache[cache_key]
        except OSError:
            pass

    # Load JSON
    try:
        raw = rpath.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RegistryLoadError(f"Registry file not found: {rpath}")
    except OSError as e:
        raise RegistryLoadError(f"Cannot read registry file: {e}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RegistryLoadError(f"Invalid JSON in registry: {e}")

    # Validate
    _validate_registry(data)

    # Cache
    try:
        _cache_mtime[cache_key] = rpath.stat().st_mtime
    except OSError:
        _cache_mtime[cache_key] = time.time()
    _cache[cache_key] = data

    return data


def _validate_registry(data: dict[str, Any]) -> None:
    """
    Validate registry structure against expected schema.

    Raises RegistryValidationError on any failure.
    """
    errors: list[str] = []

    # schema_version
    sv = data.get("schema_version")
    if sv is None:
        errors.append("Missing required field: schema_version")
    elif sv != EXPECTED_SCHEMA_VERSION:
        errors.append(f"Unsupported schema_version: {sv!r} (expected {EXPECTED_SCHEMA_VERSION!r})")

    # lines
    lines = data.get("lines")
    if lines is None:
        errors.append("Missing required field: lines")
    elif not isinstance(lines, dict):
        errors.append(f"'lines' must be an object, got {type(lines).__name__}")
    elif len(lines) == 0:
        errors.append("'lines' must contain at least one operator line")
    else:
        for line_name, line_def in lines.items():
            if not isinstance(line_def, dict):
                errors.append(f"Line '{line_name}': definition must be an object")
                continue

            for field in REQUIRED_LINE_FIELDS:
                if field not in line_def:
                    errors.append(f"Line '{line_name}': missing required field '{field}'")

            # primary must be a string
            primary = line_def.get("primary")
            if primary is not None and not isinstance(primary, str):
                errors.append(f"Line '{line_name}': 'primary' must be a string")

            # executors, fallback, control must be lists
            for list_field in ("executors", "fallback", "control", "helper"):
                val = line_def.get(list_field)
                if val is not None and not isinstance(val, list):
                    errors.append(f"Line '{line_name}': '{list_field}' must be a list")

            # schedule validation
            schedule = line_def.get("schedule")
            if schedule is not None and schedule not in VALID_SCHEDULES:
                errors.append(f"Line '{line_name}': invalid schedule '{schedule}' (valid: {VALID_SCHEDULES})")

    if errors:
        raise RegistryValidationError(
            f"Registry validation failed with {len(errors)} error(s):\n" +
            "\n".join(f"  - {e}" for e in errors)
        )


def audit_file_existence(
    registry: dict[str, Any] | None = None,
    harness_root: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Audit all operator files referenced in the registry for existence.

    Args:
        registry: Pre-loaded registry dict. If None, loads from default path.
        harness_root: Override harness root for resolving paths.

    Returns:
        Dict mapping line_name -> {
            "primary": {"path": str, "exists": bool},
            "executors": [{"path": str, "exists": bool}, ...],
            "fallback": [{"path": str, "exists": bool}, ...],
            "control": [{"path": str, "exists": bool}, ...],
            "helper": [{"path": str, "exists": bool}, ...],
        }
    """
    if registry is None:
        registry = load_registry(harness_root=harness_root)

    root = Path(harness_root) if harness_root else _HARNESS_ROOT
    report: dict[str, dict[str, Any]] = {}

    for line_name, line_def in registry.get("lines", {}).items():
        entry: dict[str, Any] = {}

        # Primary
        primary = line_def.get("primary", "")
        p = _resolve_path(primary, root)
        entry["primary"] = {"path": primary, "exists": p.is_file()}

        # List fields
        for role in ("executors", "fallback", "control", "helper"):
            items = line_def.get(role, [])
            entry[role] = [
                {"path": item, "exists": _resolve_path(item, root).is_file()}
                for item in items
            ]

        report[line_name] = entry

    return report


def get_line(
    line_name: str,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get a single line definition from the registry.

    Args:
        line_name: Name of the operator line.
        registry: Pre-loaded registry. If None, loads from default path.

    Returns:
        Line definition dict.

    Raises:
        KeyError: If line not found.
    """
    if registry is None:
        registry = load_registry()
    lines = registry.get("lines", {})
    if line_name not in lines:
        raise KeyError(f"Operator line '{line_name}' not found in registry. Available: {list(lines.keys())}")
    return lines[line_name]


def list_lines(registry: dict[str, Any] | None = None) -> list[str]:
    """Return all line names from the registry."""
    if registry is None:
        registry = load_registry()
    return list(registry.get("lines", {}).keys())


def clear_cache() -> None:
    """Clear the in-memory registry cache."""
    _cache.clear()
    _cache_mtime.clear()
