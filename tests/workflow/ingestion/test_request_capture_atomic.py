"""Executable Phase 22 atomic tests for Workflow / Ingestion / Request Capture."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess


DRIVER = Path(__file__).with_name("request_capture_atomic_driver.sh")


def _wsl_path(path: Path) -> str:
    resolved = str(path.resolve())
    drive, tail = resolved[0].lower(), resolved[2:].replace("\\", "/")
    return f"/mnt/{drive}{tail}"


def _run_case(case_name: str) -> None:
    if os.name == "nt":
        command = ["wsl.exe", "-e", "bash", _wsl_path(DRIVER), case_name]
    else:
        command = ["bash", str(DRIVER), case_name]
    subprocess.run(command, cwd=DRIVER.parents[3], check=True, timeout=120)


def test_atomic_request_capture__direct_text() -> None:
    _run_case("direct_text")


def test_atomic_request_capture__file() -> None:
    _run_case("file")


def test_atomic_request_capture__stdin() -> None:
    _run_case("stdin")


def test_atomic_request_capture__no_dispatch() -> None:
    _run_case("no_dispatch")


def test_atomic_request_capture__successful_dispatch() -> None:
    _run_case("successful_dispatch")


def test_atomic_request_capture__empty_input() -> None:
    _run_case("empty_input")


def test_atomic_request_capture__missing_file() -> None:
    _run_case("missing_file")


def test_atomic_request_capture__and_workspace_mismatch() -> None:
    _run_case("workspace_mismatch")
