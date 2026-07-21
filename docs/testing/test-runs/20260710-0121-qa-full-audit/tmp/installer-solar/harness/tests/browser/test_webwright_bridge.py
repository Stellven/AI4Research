"""Tests for Webwright browser profile bridge helpers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

from browser.executors.webwright_bridge import (  # noqa: E402
    apply_webwright_bridge_env,
    prepare_webwright_bridge,
)
from browser.profile_registry import ProfileRegistry  # noqa: E402


def test_prepare_webwright_bridge_storage_state_clone(tmp_path: Path) -> None:
    registry = ProfileRegistry(root=tmp_path / "profiles")
    profile_id = "chatgpt/example-user"
    source_state = tmp_path / "source" / "storageState.json"
    source_state.parent.mkdir(parents=True, exist_ok=True)
    source_state.write_text('{"cookies":[]}', encoding="utf-8")
    registry.write_meta(
        profile_id,
        {
            "storage_state_ref": str(source_state),
            "profile_dir": str(tmp_path / "source" / "profile.browser-use"),
        },
    )

    manifest = prepare_webwright_bridge(
        profile_id=profile_id,
        run_dir=tmp_path / "run",
        mode="storage_state_clone",
        registry=registry,
    )
    assert manifest["ok"] is True
    clone_path = Path(str(manifest["cloned_storage_state_ref"]))
    assert clone_path.exists()
    env = apply_webwright_bridge_env({}, manifest)
    assert env["WEBWRIGHT_STORAGE_STATE_PATH"] == str(clone_path)


def test_prepare_webwright_bridge_profile_fork(tmp_path: Path) -> None:
    registry = ProfileRegistry(root=tmp_path / "profiles")
    profile_id = "gemini/google-main"
    source_profile = tmp_path / "source" / "profile.browser-use"
    source_profile.mkdir(parents=True, exist_ok=True)
    (source_profile / "Preferences").write_text("{}", encoding="utf-8")
    registry.write_meta(
        profile_id,
        {
            "profile_dir": str(source_profile),
        },
    )

    manifest = prepare_webwright_bridge(
        profile_id=profile_id,
        run_dir=tmp_path / "run",
        mode="profile_fork",
        registry=registry,
    )
    assert manifest["ok"] is True
    fork_path = Path(str(manifest["forked_profile_dir"]))
    assert (fork_path / "Preferences").exists()
    env = apply_webwright_bridge_env({}, manifest)
    assert env["LOCAL_BROWSER_USER_DATA_DIR"] == str(fork_path)
    assert env["BROWSER_MODE"] == "local"
