"""Webwright storage-state/profile bridge helpers."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..profile_registry import ProfileRegistry


def executor_descriptor() -> dict[str, object]:
    return {
        "kind": "webwright_storage_state_bridge",
        "runtime_owner": "webwright",
        "capabilities": ["storage_state_clone", "profile_fork", "long_horizon_bridge"],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _copy_if_exists(src: str | Path | None, dst: Path) -> str | None:
    raw = str(src or "").strip()
    if not raw:
        return None
    source = Path(raw).expanduser()
    if not source.exists() or not source.is_file():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dst)
    return str(dst)


def _copytree_if_exists(src: str | Path | None, dst: Path) -> str | None:
    raw = str(src or "").strip()
    if not raw:
        return None
    source = Path(raw).expanduser()
    if not source.exists() or not source.is_dir():
        return None
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dst)
    return str(dst)


def prepare_webwright_bridge(
    *,
    profile_id: str,
    run_dir: str | Path,
    mode: str = "storage_state_clone",
    registry: ProfileRegistry | None = None,
) -> dict[str, Any]:
    """Prepare a task-local Webwright bridge from a main browser profile."""
    bridge_mode = str(mode or "storage_state_clone").strip().lower()
    if bridge_mode not in {"storage_state_clone", "profile_fork", "direct_main"}:
        raise ValueError(f"unsupported webwright bridge mode: {mode}")

    registry = registry or ProfileRegistry()
    run_path = Path(run_dir).expanduser()
    bridge_root = run_path / "browser-profile-bridge"
    bridge_root.mkdir(parents=True, exist_ok=True)

    meta = registry.read_meta(profile_id)
    storage_state_ref = str(meta.get("storage_state_ref") or "").strip() or None
    profile_dir = str(meta.get("profile_dir") or "").strip() or None

    cloned_storage_state: str | None = None
    forked_profile_dir: str | None = None
    bridge_ok = False
    reason = "missing_profile_assets"

    if bridge_mode == "storage_state_clone":
        cloned_storage_state = _copy_if_exists(
            storage_state_ref,
            bridge_root / "storageState.clone.json",
        )
        bridge_ok = bool(cloned_storage_state)
        reason = "storage_state_cloned" if bridge_ok else "storage_state_missing"
    elif bridge_mode == "profile_fork":
        forked_profile_dir = _copytree_if_exists(
            profile_dir,
            bridge_root / "profile.browser-use-fork",
        )
        bridge_ok = bool(forked_profile_dir)
        reason = "profile_forked" if bridge_ok else "profile_dir_missing"
    elif bridge_mode == "direct_main":
        forked_profile_dir = profile_dir
        bridge_ok = bool(forked_profile_dir)
        reason = "direct_main_profile" if bridge_ok else "profile_dir_missing"

    manifest = {
        "schema": "browser.webwright_bridge.v1",
        "profile_id": profile_id,
        "mode": bridge_mode,
        "ok": bridge_ok,
        "reason": reason,
        "source_storage_state_ref": storage_state_ref,
        "source_profile_dir": profile_dir,
        "cloned_storage_state_ref": cloned_storage_state,
        "forked_profile_dir": forked_profile_dir,
    }
    _write_json(bridge_root / "browser-profile-bridge.json", manifest)
    return manifest


def apply_webwright_bridge_env(env: dict[str, str], manifest: dict[str, Any]) -> dict[str, str]:
    """Overlay bridge-aware environment for downstream Webwright execution."""
    updated = dict(env)
    updated["WEBWRIGHT_BROWSER_PROFILE_BRIDGE_MODE"] = str(manifest.get("mode") or "")
    updated["WEBWRIGHT_BROWSER_PROFILE_ID"] = str(manifest.get("profile_id") or "")
    if manifest.get("cloned_storage_state_ref"):
        updated["WEBWRIGHT_STORAGE_STATE_PATH"] = str(manifest["cloned_storage_state_ref"])
    if manifest.get("forked_profile_dir"):
        updated["LOCAL_BROWSER_USER_DATA_DIR"] = str(manifest["forked_profile_dir"])
        updated["BROWSER_USER_DATA_DIR"] = str(manifest["forked_profile_dir"])
        updated.setdefault("BROWSER_MODE", "local")
    return updated
