"""Tests for browser profile control CLI helpers."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "browser_profile_control.py"


def test_browser_profile_control_doctor(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["BROWSER_PROFILE_REGISTRY_ROOT"] = str(tmp_path / "profiles")
    env["BROWSER_PROFILE_LEASE_DIR"] = str(tmp_path / "leases")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "doctor"],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["active_lease_count"] == 0


def test_browser_profile_control_profile_init(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["BROWSER_PROFILE_REGISTRY_ROOT"] = str(tmp_path / "profiles")
    env["BROWSER_PROFILE_LEASE_DIR"] = str(tmp_path / "leases")
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "profile-init",
            "--service",
            "chatgpt",
            "--profile",
            "example-user",
            "--account",
            "browser-agent@example.com",
            "--headed",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["profile_id"] == "chatgpt/example-user"
    assert payload["meta"]["headed_required_for_first_login"] is True
