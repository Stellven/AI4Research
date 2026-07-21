"""Filesystem lease helper for browser profile tasks.

Lease records are stored as JSON under a configurable directory and guarded by
per-profile lock files for atomic exclusive acquire/release.
"""
from __future__ import annotations

import datetime
import fcntl
import json
import os
from dataclasses import dataclass
from pathlib import Path
import uuid
from typing import Any


DEFAULT_LEASE_DIR_ENV = "BROWSER_PROFILE_LEASE_DIR"
HOME = Path.home()


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso8601(value: str | None) -> datetime.datetime:
    if not value:
        return datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)
    safe = str(value).rstrip("Z") + "+00:00"
    try:
        return datetime.datetime.fromisoformat(safe)
    except ValueError:
        return datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)


def _normalise_profile_id(profile_id: str) -> str:
    clean = str(profile_id or "").strip()
    if not clean:
        raise ValueError("profile_id is required")
    path = Path(clean)
    if path.is_absolute() or ".." in path.parts or any(part in {"", "."} for part in path.parts):
        raise ValueError(f"invalid profile_id: {profile_id!r}")
    return path.as_posix()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(f"{path.suffix}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


@dataclass
class ProfileLeaseRecord:
    """Structured lease record for a browser profile."""

    profile_id: str
    task_id: str
    runtime: str
    mode: str
    acquired_at: str
    expires_at: str
    allowed_attach: bool
    lease_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "task_id": self.task_id,
            "runtime": self.runtime,
            "mode": self.mode,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "allowed_attach": bool(self.allowed_attach),
            "lease_id": self.lease_id,
        }

    @property
    def is_expired(self) -> bool:
        return _parse_iso8601(self.expires_at) <= datetime.datetime.now(datetime.timezone.utc)


class ProfileLease:
    """Exclusive profile lease manager using lock-file protocol."""

    def __init__(self, root: str | Path | None = None, *, default_ttl_seconds: int = 1800) -> None:
        if root is None:
            root = os.environ.get(
                DEFAULT_LEASE_DIR_ENV,
                str(HOME / ".solar" / "browser-profiles" / "leases"),
            )
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.default_ttl_seconds = int(default_ttl_seconds)

    def lease_path(self, profile_id: str) -> Path:
        normalized = _normalise_profile_id(profile_id)
        parts = Path(normalized).parts
        if not parts:
            raise ValueError("profile_id is required")
        return self.root.joinpath(*parts[:-1], f"{parts[-1]}.json")

    def _lock_path(self, profile_id: str) -> Path:
        return self.lease_path(profile_id).with_suffix(".json.lock")

    def _read(self, profile_id: str) -> ProfileLeaseRecord | None:
        raw = _read_json(self.lease_path(profile_id))
        if not raw:
            return None
        try:
            return ProfileLeaseRecord(
                profile_id=str(raw["profile_id"]),
                task_id=str(raw["task_id"]),
                runtime=str(raw["runtime"]),
                mode=str(raw["mode"]),
                acquired_at=str(raw["acquired_at"]),
                expires_at=str(raw["expires_at"]),
                allowed_attach=bool(raw["allowed_attach"]),
                lease_id=str(raw.get("lease_id") or str(uuid.uuid4())),
            )
        except (TypeError, KeyError):
            return None

    def _write(self, record: ProfileLeaseRecord) -> None:
        _write_json_atomic(self.lease_path(record.profile_id), record.to_dict())

    def _delete(self, profile_id: str) -> None:
        path = self.lease_path(profile_id)
        if path.exists():
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def acquire(
        self,
        profile_id: str,
        task_id: str,
        runtime: str,
        mode: str,
        *,
        ttl_seconds: int | None = None,
        allowed_attach: bool = False,
    ) -> dict[str, Any]:
        """Try to acquire exclusive lease.

        Returns:
          {
            "acquired": bool,
            "lease": {..},
            "reason": optional reason when failed,
            "held_by": optional task id when already leased,
            "expires_at": optional existing expiry
          }
        """
        profile = _normalise_profile_id(profile_id)
        task = str(task_id or "").strip()
        now = _now_iso()
        lease_path = self.lease_path(profile)
        lock_path = self._lock_path(profile)
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        lock_fh = open(lock_path, "a")
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            lock_fh.close()
            return {
                "acquired": False,
                "reason": "contention",
                "profile_id": profile,
            }

        try:
            existing = self._read(profile)
            if existing and not existing.is_expired:
                return {
                    "acquired": False,
                    "reason": "already_acquired",
                    "profile_id": profile,
                    "task_id": task,
                    "held_by": existing.task_id,
                    "expires_at": existing.expires_at,
                }

            ttl = int(ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds)
            expires_at = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=max(0, ttl))
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

            record = ProfileLeaseRecord(
                profile_id=profile,
                task_id=task,
                runtime=str(runtime or "").strip() or "default",
                mode=str(mode or "").strip() or "default",
                acquired_at=now,
                expires_at=expires_at,
                allowed_attach=bool(allowed_attach),
                lease_id=str(uuid.uuid4()),
            )
            self._write(record)
            return {"acquired": True, "lease": record.to_dict()}
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)
            lock_fh.close()

    def release(self, profile_id: str, task_id: str) -> dict[str, Any]:
        """Release a lease if the task id matches."""
        profile = _normalise_profile_id(profile_id)
        lock_path = self._lock_path(profile)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fh = open(lock_path, "a")
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            current = self._read(profile)
            if current is None:
                self._delete(profile)
                return {"released": True, "reason": "already_released", "profile_id": profile}
            if current.task_id != task_id:
                return {
                    "released": False,
                    "reason": "task_mismatch",
                    "profile_id": profile,
                    "held_by": current.task_id,
                }
            self._delete(profile)
            return {"released": True, "reason": "released", "profile_id": profile}
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)
            lock_fh.close()

    def expire(self, profile_id: str | None = None) -> int:
        """Expire one lease or all expired leases.

        If profile_id is None, remove all expired lease files under the lease root.
        Returns number of removed lease files.
        """
        if profile_id:
            profile = _normalise_profile_id(profile_id)
            current = self._read(profile)
            if current is not None and current.is_expired:
                self._delete(profile)
                return 1
            return 0

        removed = 0
        for lease_file in sorted(self.root.rglob("*.json")):
            try:
                profile_id = lease_file.relative_to(self.root).with_suffix("").as_posix()
                current = self._read(profile_id)
            except Exception:
                continue
            if current and current.is_expired:
                self._delete(profile_id)
                removed += 1
        return removed

    def list_active(self) -> list[dict[str, Any]]:
        active: list[dict[str, Any]] = []
        for lease_file in sorted(self.root.rglob("*.json")):
            record = self._read(lease_file.relative_to(self.root).with_suffix("").as_posix())
            if not record or record.is_expired:
                continue
            active.append(record.to_dict())
        return active
