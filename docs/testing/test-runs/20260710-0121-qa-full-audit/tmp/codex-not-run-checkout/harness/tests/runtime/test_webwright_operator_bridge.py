"""Tests for Webwright operator browser profile bridge wiring."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OPERATOR = ROOT / "tools" / "webwright_operator.py"


def _write_isolated_operator_registry(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "operators": {
                    "op.browser.webwright.playwright.01": {
                        "state": {
                            "availability": "enabled",
                            "runtime_state": "idle",
                            "cooldown_until": None,
                        }
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_webwright_operator_applies_storage_state_bridge(tmp_path: Path) -> None:
    fake_adapter = tmp_path / "fake_adapter.py"
    env_capture = tmp_path / "env-capture.json"
    fake_adapter.write_text(
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
Path({str(env_capture)!r}).write_text(json.dumps({{
    "WEBWRIGHT_STORAGE_STATE_PATH": os.environ.get("WEBWRIGHT_STORAGE_STATE_PATH"),
    "WEBWRIGHT_BROWSER_PROFILE_ID": os.environ.get("WEBWRIGHT_BROWSER_PROFILE_ID"),
    "WEBWRIGHT_BROWSER_PROFILE_BRIDGE_MODE": os.environ.get("WEBWRIGHT_BROWSER_PROFILE_BRIDGE_MODE"),
    "LOCAL_BROWSER_USER_DATA_DIR": os.environ.get("LOCAL_BROWSER_USER_DATA_DIR"),
}}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({{"ok": True, "artifacts": {{}}, "mode": "fake"}}))
""",
        encoding="utf-8",
    )
    fake_adapter.chmod(0o755)

    profile_root = tmp_path / "profiles"
    state_path = tmp_path / "seed" / "storageState.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text('{"cookies":[]}', encoding="utf-8")
    profile_id = "chatgpt/example-user"
    meta_dir = profile_root / "chatgpt" / "example-user"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "meta.json").write_text(
        json.dumps(
            {
                "profile_id": profile_id,
                "storage_state_ref": str(state_path),
                "allowed_account_identifiers": ["browser-agent@example.com"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["BROWSER_PROFILE_REGISTRY_ROOT"] = str(profile_root)
    env["BROWSER_PROFILE_LEASE_DIR"] = str(tmp_path / "leases")
    env["TASK_DIR"] = str(tmp_path / "task")
    env["SOLAR_OPERATOR_ENVELOPE_JSON"] = str(tmp_path / "envelope.json")
    env["HARNESS_DIR"] = str(tmp_path / "isolated-harness")
    env["SOLAR_MULTI_TASK_OPERATORS"] = str(tmp_path / "isolated-harness" / "config" / "physical-operators.json")
    _write_isolated_operator_registry(Path(env["SOLAR_MULTI_TASK_OPERATORS"]))
    existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = (
        f"{ROOT / 'lib'}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(ROOT / "lib")
    )
    envelope = {
        "objective": "Inspect a website",
        "start_url": "https://example.com",
        "dispatch_id": "bridge-case",
        "timeout_seconds": 10,
        "browser_profile_id": profile_id,
        "profile_mode": "storage_state_clone",
    }
    Path(env["SOLAR_OPERATOR_ENVELOPE_JSON"]).write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    operator_code = OPERATOR.read_text(encoding="utf-8").replace(
        'DEFAULT_ADAPTER = ROOT / "lib" / "webwright_adapter.py"',
        f'DEFAULT_ADAPTER = Path({str(fake_adapter)!r})',
    )
    patched_operator = tmp_path / "patched_webwright_operator.py"
    patched_operator.write_text(operator_code, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(patched_operator)],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    assert "Webwright Execution Success" in proc.stdout
    captured = json.loads(env_capture.read_text(encoding="utf-8"))
    assert captured["WEBWRIGHT_BROWSER_PROFILE_ID"] == profile_id
    assert captured["WEBWRIGHT_BROWSER_PROFILE_BRIDGE_MODE"] == "storage_state_clone"
    assert captured["WEBWRIGHT_STORAGE_STATE_PATH"]
    assert captured["LOCAL_BROWSER_USER_DATA_DIR"] in {None, ""}
    assert (Path(env["TASK_DIR"]) / "browser-profile-bridge" / "browser-profile-bridge.json").exists()


def test_webwright_operator_applies_profile_fork_bridge(tmp_path: Path) -> None:
    fake_adapter = tmp_path / "fake_adapter.py"
    env_capture = tmp_path / "env-capture.json"
    fake_adapter.write_text(
        f"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
Path({str(env_capture)!r}).write_text(json.dumps({{
    "WEBWRIGHT_STORAGE_STATE_PATH": os.environ.get("WEBWRIGHT_STORAGE_STATE_PATH"),
    "WEBWRIGHT_BROWSER_PROFILE_ID": os.environ.get("WEBWRIGHT_BROWSER_PROFILE_ID"),
    "WEBWRIGHT_BROWSER_PROFILE_BRIDGE_MODE": os.environ.get("WEBWRIGHT_BROWSER_PROFILE_BRIDGE_MODE"),
    "LOCAL_BROWSER_USER_DATA_DIR": os.environ.get("LOCAL_BROWSER_USER_DATA_DIR"),
    "BROWSER_USER_DATA_DIR": os.environ.get("BROWSER_USER_DATA_DIR"),
    "BROWSER_MODE": os.environ.get("BROWSER_MODE"),
}}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({{"ok": True, "artifacts": {{}}, "mode": "fake"}}))
""",
        encoding="utf-8",
    )
    fake_adapter.chmod(0o755)

    profile_root = tmp_path / "profiles"
    profile_id = "gemini/google-main"
    source_profile = tmp_path / "seed" / "profile.browser-use"
    source_profile.mkdir(parents=True, exist_ok=True)
    (source_profile / "Preferences").write_text("{}", encoding="utf-8")
    meta_dir = profile_root / "gemini" / "google-main"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "meta.json").write_text(
        json.dumps(
            {
                "profile_id": profile_id,
                "profile_dir": str(source_profile),
                "allowed_account_identifiers": ["google-main@example.com"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["BROWSER_PROFILE_REGISTRY_ROOT"] = str(profile_root)
    env["BROWSER_PROFILE_LEASE_DIR"] = str(tmp_path / "leases")
    env["TASK_DIR"] = str(tmp_path / "task")
    env["SOLAR_OPERATOR_ENVELOPE_JSON"] = str(tmp_path / "envelope.json")
    env["HARNESS_DIR"] = str(tmp_path / "isolated-harness")
    env["SOLAR_MULTI_TASK_OPERATORS"] = str(tmp_path / "isolated-harness" / "config" / "physical-operators.json")
    _write_isolated_operator_registry(Path(env["SOLAR_MULTI_TASK_OPERATORS"]))
    existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = (
        f"{ROOT / 'lib'}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(ROOT / "lib")
    )
    envelope = {
        "objective": "Inspect a website",
        "start_url": "https://example.com",
        "dispatch_id": "bridge-fork-case",
        "timeout_seconds": 10,
        "browser_profile_id": profile_id,
        "profile_mode": "profile_fork",
    }
    Path(env["SOLAR_OPERATOR_ENVELOPE_JSON"]).write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    operator_code = OPERATOR.read_text(encoding="utf-8").replace(
        'DEFAULT_ADAPTER = ROOT / "lib" / "webwright_adapter.py"',
        f'DEFAULT_ADAPTER = Path({str(fake_adapter)!r})',
    )
    patched_operator = tmp_path / "patched_webwright_operator.py"
    patched_operator.write_text(operator_code, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(patched_operator)],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    assert "Webwright Execution Success" in proc.stdout
    captured = json.loads(env_capture.read_text(encoding="utf-8"))
    assert captured["WEBWRIGHT_BROWSER_PROFILE_ID"] == profile_id
    assert captured["WEBWRIGHT_BROWSER_PROFILE_BRIDGE_MODE"] == "profile_fork"
    assert captured["WEBWRIGHT_STORAGE_STATE_PATH"] in {None, ""}
    assert captured["LOCAL_BROWSER_USER_DATA_DIR"]
    assert captured["BROWSER_USER_DATA_DIR"] == captured["LOCAL_BROWSER_USER_DATA_DIR"]
    assert captured["BROWSER_MODE"] == "local"
    fork_dir = Path(str(captured["LOCAL_BROWSER_USER_DATA_DIR"]))
    assert (fork_dir / "Preferences").exists()
