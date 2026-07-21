"""
Operator Router — select, dispatch, and fallback operator execution.

Part of Solar Harness AI Influence operator consolidation (S03 N2).
Depends on: operator_registry_loader (N1).
"""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from operator_registry_loader import (
    _HARNESS_ROOT,
    get_line,
    load_registry,
)


class NoFallbackError(Exception):
    """Raised when primary operator fails and no fallback is available."""


@dataclass
class OperatorInfo:
    """Information about a selected operator."""

    line: str
    role: str  # "primary", "fallback", "control"
    script: str  # relative path to the operator script
    output_dir: str
    schedule: str


@dataclass
class DispatchResult:
    """Result of dispatching an operator."""

    line: str
    run_id: str
    role: str
    script: str
    returncode: int
    stdout: str
    stderr: str
    success: bool
    duration_s: float


@dataclass
class ControlComparisonResult:
    """Result of a dual-run (primary + control)."""

    line: str
    run_id: str
    primary: DispatchResult
    control: DispatchResult
    both_succeeded: bool


def select_operator(
    line: str,
    registry: dict[str, Any] | None = None,
) -> OperatorInfo:
    """
    Select the primary operator for a given line.

    Args:
        line: Operator line name (e.g., "github_trends").
        registry: Pre-loaded registry dict. If None, loads from default path.

    Returns:
        OperatorInfo for the primary operator.

    Raises:
        KeyError: If line not found in registry.
    """
    line_def = get_line(line, registry=registry)
    return OperatorInfo(
        line=line,
        role="primary",
        script=line_def["primary"],
        output_dir=line_def.get("output_dir", ""),
        schedule=line_def.get("schedule", "on_demand"),
    )


def _execute_script(
    script: str,
    run_id: str,
    line: str,
    role: str,
    harness_root: Path | None = None,
    timeout: int = 300,
) -> DispatchResult:
    """
    Execute an operator script via subprocess.

    Args:
        script: Relative path to the script.
        run_id: Unique run identifier.
        line: Operator line name.
        role: Role of the script (primary/fallback/control).
        harness_root: Root directory for resolving script paths.
        timeout: Max execution time in seconds.

    Returns:
        DispatchResult with execution details.
    """
    root = harness_root if harness_root is not None else _HARNESS_ROOT
    script_path = root / script

    env = {
        **os.environ,
        "OPERATOR_RUN_ID": run_id,
        "OPERATOR_LINE": line,
        "OPERATOR_ROLE": role,
    }

    start = time.monotonic()
    try:
        result = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(root),
            env=env,
        )
        duration = time.monotonic() - start
        return DispatchResult(
            line=line,
            run_id=run_id,
            role=role,
            script=script,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            success=result.returncode == 0,
            duration_s=round(duration, 3),
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        return DispatchResult(
            line=line,
            run_id=run_id,
            role=role,
            script=script,
            returncode=-1,
            stdout="",
            stderr=f"Timeout after {timeout}s",
            success=False,
            duration_s=round(duration, 3),
        )
    except FileNotFoundError:
        duration = time.monotonic() - start
        return DispatchResult(
            line=line,
            run_id=run_id,
            role=role,
            script=script,
            returncode=-2,
            stdout="",
            stderr=f"Script not found: {script_path}",
            success=False,
            duration_s=round(duration, 3),
        )


def dispatch(
    line: str,
    run_id: str,
    registry: dict[str, Any] | None = None,
    harness_root: str | Path | None = None,
    timeout: int = 300,
) -> DispatchResult:
    """
    Dispatch an operator: run primary, auto-fallback on failure.

    Args:
        line: Operator line name.
        run_id: Unique run identifier.
        registry: Pre-loaded registry. If None, loads from default.
        harness_root: Override harness root for script resolution.
        timeout: Max execution time per script in seconds.

    Returns:
        DispatchResult from the successful execution (primary or fallback).

    Raises:
        NoFallbackError: If primary fails and no fallback is available or all fail.
    """
    line_def = get_line(line, registry=registry)
    root = Path(harness_root) if harness_root else _HARNESS_ROOT

    # Try primary
    primary_result = _execute_script(
        script=line_def["primary"],
        run_id=run_id,
        line=line,
        role="primary",
        harness_root=root,
        timeout=timeout,
    )

    if primary_result.success:
        return primary_result

    # Primary failed -- try fallback scripts in order
    fallbacks = line_def.get("fallback", [])
    if not fallbacks:
        raise NoFallbackError(
            f"Primary operator '{line_def['primary']}' failed for line '{line}' "
            f"(rc={primary_result.returncode}) and no fallback is configured. "
            f"stderr: {primary_result.stderr[:200]}"
        )

    last_fb_result = None
    for fb_script in fallbacks:
        fb_result = _execute_script(
            script=fb_script,
            run_id=run_id,
            line=line,
            role="fallback",
            harness_root=root,
            timeout=timeout,
        )
        if fb_result.success:
            return fb_result
        last_fb_result = fb_result

    # All fallbacks failed
    raise NoFallbackError(
        f"Primary and all {len(fallbacks)} fallback(s) failed for line '{line}'. "
        f"Primary rc={primary_result.returncode}, "
        f"last fallback stderr: {last_fb_result.stderr[:200] if last_fb_result else 'N/A'}"
    )


def dispatch_with_control(
    line: str,
    run_id: str,
    registry: dict[str, Any] | None = None,
    harness_root: str | Path | None = None,
    timeout: int = 300,
) -> ControlComparisonResult:
    """
    Dual-run dispatch: execute both primary and control operator, return comparison.

    Designed for lines with dual_run.enabled=true (e.g., github_trends).

    Args:
        line: Operator line name.
        run_id: Unique run identifier.
        registry: Pre-loaded registry. If None, loads from default.
        harness_root: Override harness root for script resolution.
        timeout: Max execution time per script in seconds.

    Returns:
        ControlComparisonResult with both results and comparison flag.

    Raises:
        ValueError: If line has no control operators defined.
    """
    if registry is None:
        registry = load_registry()
    line_def = get_line(line, registry=registry)
    root = Path(harness_root) if harness_root else _HARNESS_ROOT

    control_scripts = line_def.get("control", [])
    if not control_scripts:
        raise ValueError(
            f"Line '{line}' has no control operators defined. "
            f"dispatch_with_control requires at least one control script."
        )

    # Run primary
    primary_result = _execute_script(
        script=line_def["primary"],
        run_id=run_id,
        line=line,
        role="primary",
        harness_root=root,
        timeout=timeout,
    )

    # Run first control script
    control_result = _execute_script(
        script=control_scripts[0],
        run_id=run_id,
        line=line,
        role="control",
        harness_root=root,
        timeout=timeout,
    )

    return ControlComparisonResult(
        line=line,
        run_id=run_id,
        primary=primary_result,
        control=control_result,
        both_succeeded=primary_result.success and control_result.success,
    )
