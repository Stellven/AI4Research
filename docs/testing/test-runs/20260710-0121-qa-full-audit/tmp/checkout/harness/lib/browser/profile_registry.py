"""Browser profile registry for local login/session profile state.

The registry stores per-profile metadata and runtime state under a configurable
root directory. Directory layout (per profile):

  <root>/<profile_id>/
    meta.json                # profile metadata / allowlist
    health.json              # profile health snapshot
    cdp.last.json            # last successful CDP payload
    evidence/                # evidence files for profile-specific runs
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_ROOT_ENV = "BROWSER_PROFILE_REGISTRY_ROOT"
HOME = Path.home()


def _now_iso() -> str:
    """Return current UTC timestamp in compact ISO-8601 format."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalise_profile_id(profile_id: str) -> str:
    clean = str(profile_id or "").strip()
    if not clean:
        raise ValueError("profile_id is required")
    path = Path(clean)
    if path.is_absolute() or ".." in path.parts or any(part in {"", "."} for part in path.parts):
        raise ValueError(f"invalid profile_id: {profile_id!r}")
    return path.as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f"{path.suffix}.tmp")
    temp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _normalise_identifier_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        val = str(value or "").strip()
        if not val:
            continue
        lower = val.lower()
        if lower not in normalized:
            normalized.append(lower)
    return normalized


class ProfileRegistry:
    """Filesystem-backed profile registry.

    This class keeps profile metadata and health snapshots in a simple JSON
    layout so that each profile can be inspected and recovered independently.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        default_root = Path(os.environ.get(DEFAULT_ROOT_ENV, HOME / ".solar" / "browser-profiles"))
        self.root = Path(root or default_root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def profile_dir(self, profile_id: str) -> Path:
        return self.root / _normalise_profile_id(profile_id)

    def meta_path(self, profile_id: str) -> Path:
        return self.profile_dir(profile_id) / "meta.json"

    def health_path(self, profile_id: str) -> Path:
        return self.profile_dir(profile_id) / "health.json"

    def cdp_last_path(self, profile_id: str) -> Path:
        return self.profile_dir(profile_id) / "cdp.last.json"

    def evidence_dir(self, profile_id: str) -> Path:
        path = self.profile_dir(profile_id) / "evidence"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def read_meta(self, profile_id: str) -> dict[str, Any]:
        return _read_json(self.meta_path(profile_id))

    def write_meta(self, profile_id: str, meta: dict[str, Any]) -> dict[str, Any]:
        profile = self.read_meta(profile_id)
        merged = {**profile, **(meta or {})}
        merged.setdefault("profile_id", _normalise_profile_id(profile_id))
        merged["updated_at"] = _now_iso()
        _write_json_atomic(self.meta_path(profile_id), merged)
        return merged

    def write_health(self, profile_id: str, health: dict[str, Any]) -> dict[str, Any]:
        payload = dict(health or {})
        payload["profile_id"] = _normalise_profile_id(profile_id)
        payload["updated_at"] = _now_iso()
        _write_json_atomic(self.health_path(profile_id), payload)
        return payload

    def read_health(self, profile_id: str) -> dict[str, Any]:
        return _read_json(self.health_path(profile_id))

    def write_cdp_last(self, profile_id: str, cdp_state: dict[str, Any]) -> dict[str, Any]:
        payload = dict(cdp_state or {})
        payload["profile_id"] = _normalise_profile_id(profile_id)
        payload["updated_at"] = _now_iso()
        _write_json_atomic(self.cdp_last_path(profile_id), payload)
        return payload

    def read_cdp_last(self, profile_id: str) -> dict[str, Any]:
        return _read_json(self.cdp_last_path(profile_id))

    def get_storage_state_ref(self, profile_id: str) -> str | None:
        return self.read_meta(profile_id).get("storage_state_ref")

    def set_storage_state_ref(self, profile_id: str, storage_state_ref: str | None) -> str | None:
        payload = self.write_meta(
            profile_id,
            {"storage_state_ref": str(storage_state_ref or "").strip() or None},
        )
        return payload.get("storage_state_ref")

    def get_allowed_account_identifiers(self, profile_id: str) -> list[str]:
        raw = self.read_meta(profile_id).get("allowed_account_identifiers")
        if not isinstance(raw, list):
            return []
        return _normalise_identifier_list([str(item) for item in raw])

    def set_allowed_account_identifiers(
        self, profile_id: str, identifiers: list[str] | tuple[str, ...] | None
    ) -> list[str]:
        normalized = _normalise_identifier_list(list(identifiers or []))
        payload = self.write_meta(profile_id, {"allowed_account_identifiers": normalized})
        return _normalise_identifier_list(
            [str(item) for item in payload.get("allowed_account_identifiers", [])]
        )
