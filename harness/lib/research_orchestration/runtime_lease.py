"""Research lease adapter backed by existing operator lease state."""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ACTIVE_STATES = frozenset({"leased", "running", "draining"})
RECOVERABLE_STATES = frozenset({"stale", "crashed"})
_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class ResearchLeaseAdapter:
    """Adapter over ``run/operator-leases``; it does not create a new lease store."""

    def __init__(self, harness_root: str | Path, *, clock: Any | None = None) -> None:
        self.harness_root = Path(harness_root)
        self.lease_dir = self.harness_root / "run" / "operator-leases"
        self.status_dir = self.harness_root / "run" / "operator-status"
        self.clock = clock or (lambda: _dt.datetime.now(_dt.timezone.utc))

    def acquire(
        self,
        run_id: str,
        node_id: str,
        operator_id: str,
        *,
        task_id: str | None = None,
        ttl_seconds: int = 900,
        heartbeat_timeout_seconds: int = 120,
        metadata: dict[str, Any] | None = None,
        recover_stale: bool = False,
    ) -> dict[str, Any]:
        self._validate_identity(run_id, node_id, operator_id)
        self.lease_dir.mkdir(parents=True, exist_ok=True)
        self.status_dir.mkdir(parents=True, exist_ok=True)

        with self._run_node_lock(run_id, node_id):
            existing_for_node = self._active_for_run_node(run_id, node_id)
            if existing_for_node:
                if self.is_stale(existing_for_node):
                    if recover_stale:
                        stale_operator = str(existing_for_node.get("operator_id") or "")
                        self._mark_recovered(stale_operator, existing_for_node, "acquire_recovered_stale")
                    else:
                        return self._blocked("stale_lease_requires_recovery", existing_for_node)
                else:
                    return self._blocked("run_node_already_active", existing_for_node)

            operator_lease = self._read_lease(operator_id)
            if operator_lease and self._is_active(operator_lease):
                if self.is_stale(operator_lease):
                    if recover_stale:
                        self._mark_recovered(operator_id, operator_lease, "acquire_recovered_operator_stale")
                    else:
                        return self._blocked("operator_has_stale_lease", operator_lease)
                else:
                    return self._blocked("operator_busy", operator_lease)

            now = self._now()
            lease = {
                "schema": "research_operator_lease.v1",
                "operator_id": operator_id,
                "task_id": task_id or f"{run_id}:{node_id}",
                "sprint_id": run_id,
                "run_id": run_id,
                "research_run_id": run_id,
                "node_id": node_id,
                "lease_id": str(uuid.uuid4()),
                "leased_at": _format_time(now),
                "heartbeat_at": _format_time(now),
                "expires_at": _format_time(now + _dt.timedelta(seconds=max(1, int(ttl_seconds)))),
                "heartbeat_timeout_seconds": int(max(1, heartbeat_timeout_seconds)),
                "state": "leased",
            }
            if metadata:
                lease["metadata"] = self._safe_metadata(metadata)
            self._write_lease(operator_id, lease)
            return {"acquired": True, "lease": lease, "blocker": None}

    def heartbeat(
        self,
        run_id: str,
        node_id: str,
        operator_id: str,
        *,
        lease_id: str | None = None,
        ttl_seconds: int = 900,
        state: str = "running",
    ) -> dict[str, Any]:
        lease = self._read_lease(operator_id)
        if not lease:
            return self._blocked("lease_missing", {"run_id": run_id, "node_id": node_id, "operator_id": operator_id})
        if not self._matches(lease, run_id, node_id):
            return self._blocked("lease_identity_mismatch", lease)
        if lease_id and lease.get("lease_id") != lease_id:
            return self._blocked("lease_id_mismatch", lease)
        if self.is_stale(lease):
            return self._blocked("lease_stale", lease)
        now = self._now()
        lease["heartbeat_at"] = _format_time(now)
        lease["expires_at"] = _format_time(now + _dt.timedelta(seconds=max(1, int(ttl_seconds))))
        lease["state"] = state if state in ACTIVE_STATES else "running"
        self._write_lease(operator_id, lease)
        self._write_status(operator_id, lease)
        return {"ok": True, "lease": lease, "blocker": None}

    def release(
        self,
        run_id: str,
        node_id: str,
        operator_id: str,
        *,
        lease_id: str | None = None,
        reason: str = "completed",
    ) -> dict[str, Any]:
        lease = self._read_lease(operator_id)
        if not lease:
            return {"released": False, "reason": "lease_missing"}
        if not self._matches(lease, run_id, node_id):
            return self._blocked("lease_identity_mismatch", lease)
        if lease_id and lease.get("lease_id") != lease_id:
            return self._blocked("lease_id_mismatch", lease)
        lease["state"] = "released"
        lease["released_at"] = _format_time(self._now())
        lease["release_reason"] = reason
        self._archive_lease(operator_id, lease)
        self._lease_path(operator_id).unlink(missing_ok=True)
        return {"released": True, "lease": lease}

    def is_stale(self, lease_or_run_id: dict[str, Any] | str, node_id: str | None = None) -> bool:
        if isinstance(lease_or_run_id, dict):
            return self._lease_is_stale(lease_or_run_id)
        if node_id is None:
            raise ValueError("node_id is required when checking by run_id")
        lease = self._active_for_run_node(lease_or_run_id, node_id)
        return bool(lease and self._lease_is_stale(lease))

    def recover_stale(self, run_id: str, node_id: str, *, reason: str = "stale_recovered") -> dict[str, Any]:
        recovered: list[dict[str, Any]] = []
        self.lease_dir.mkdir(parents=True, exist_ok=True)
        with self._run_node_lock(run_id, node_id):
            for path in sorted(self.lease_dir.glob("*.json")):
                lease = self._read_json(path)
                if not lease or not self._matches(lease, run_id, node_id):
                    continue
                if self._is_active(lease) and not self._lease_is_stale(lease):
                    return self._blocked("active_lease_not_recovered", lease)
                self._mark_recovered(str(lease.get("operator_id") or path.stem), lease, reason)
                recovered.append(lease)
        return {"recovered": bool(recovered), "leases": recovered}

    def _lease_is_stale(self, lease: dict[str, Any]) -> bool:
        if str(lease.get("state") or "").lower() in RECOVERABLE_STATES:
            return True
        expires_at = _parse_time(str(lease.get("expires_at") or ""))
        if expires_at and expires_at <= self._now():
            return True
        heartbeat_at = _parse_time(str(lease.get("heartbeat_at") or lease.get("leased_at") or ""))
        timeout = int(lease.get("heartbeat_timeout_seconds") or lease.get("heartbeat_timeout_sec") or 0)
        if heartbeat_at and timeout > 0:
            return (self._now() - heartbeat_at).total_seconds() > timeout
        return False

    def _active_for_run_node(self, run_id: str, node_id: str) -> dict[str, Any] | None:
        for path in sorted(self.lease_dir.glob("*.json")):
            lease = self._read_json(path)
            if lease and self._matches(lease, run_id, node_id) and self._is_active(lease):
                return lease
        return None

    def _is_active(self, lease: dict[str, Any]) -> bool:
        return str(lease.get("state") or "").lower() in ACTIVE_STATES

    def _matches(self, lease: dict[str, Any], run_id: str, node_id: str) -> bool:
        return (
            str(lease.get("research_run_id") or lease.get("run_id") or lease.get("sprint_id") or "") == run_id
            and str(lease.get("node_id") or "") == node_id
        )

    def _read_lease(self, operator_id: str) -> dict[str, Any] | None:
        return self._read_json(self._lease_path(operator_id))

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return {"operator_id": path.stem, "state": "stale", "corrupt": True}

    def _write_lease(self, operator_id: str, lease: dict[str, Any]) -> None:
        path = self._lease_path(operator_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(lease, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    def _write_status(self, operator_id: str, lease: dict[str, Any]) -> None:
        path = self.status_dir / f"{operator_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        status = {
            "operator_id": operator_id,
            "runtime_state": lease.get("state", "running"),
            "state": lease.get("state", "running"),
            "current_task_id": lease.get("task_id"),
            "run_id": lease.get("run_id"),
            "node_id": lease.get("node_id"),
            "heartbeat_at": lease.get("heartbeat_at"),
            "expires_at": lease.get("expires_at"),
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    def _mark_recovered(self, operator_id: str, lease: dict[str, Any], reason: str) -> None:
        lease["state"] = "stale"
        lease["recovered_at"] = _format_time(self._now())
        lease["recovery_reason"] = reason
        self._archive_lease(operator_id, lease)
        self._lease_path(operator_id).unlink(missing_ok=True)

    def _archive_lease(self, operator_id: str, lease: dict[str, Any]) -> None:
        archive_dir = self.lease_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        lease_id = _safe_name(str(lease.get("lease_id") or uuid.uuid4()))
        path = archive_dir / f"{_safe_name(operator_id)}-{lease_id}.json"
        path.write_text(json.dumps(lease, indent=2, sort_keys=True), encoding="utf-8")

    def _lease_path(self, operator_id: str) -> Path:
        return self.lease_dir / f"{_safe_name(operator_id)}.json"

    def _now(self) -> _dt.datetime:
        value = self.clock()
        if isinstance(value, (int, float)):
            return _dt.datetime.fromtimestamp(float(value), tz=_dt.timezone.utc)
        if isinstance(value, _dt.datetime):
            return value if value.tzinfo else value.replace(tzinfo=_dt.timezone.utc)
        raise ValueError("clock must return datetime or seconds")

    def _safe_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        blocked = {"body", "request_body", "prompt", "secret", "token", "api_key", "authorization"}
        return {
            str(key): value
            for key, value in metadata.items()
            if str(key).lower() not in blocked
        }

    def _blocked(self, reason: str, lease: dict[str, Any]) -> dict[str, Any]:
        return {
            "acquired": False,
            "ok": False,
            "blocker": {
                "type": "lease_conflict",
                "reason": reason,
                "run_id": str(lease.get("research_run_id") or lease.get("run_id") or lease.get("sprint_id") or ""),
                "node_id": str(lease.get("node_id") or ""),
                "operator_id": str(lease.get("operator_id") or ""),
                "state": str(lease.get("state") or ""),
                "lease_id": str(lease.get("lease_id") or ""),
            },
        }

    def _validate_identity(self, run_id: str, node_id: str, operator_id: str) -> None:
        if not run_id or not node_id or not operator_id:
            raise ValueError("run_id, node_id, and operator_id are required")

    @contextmanager
    def _run_node_lock(self, run_id: str, node_id: str) -> Iterator[None]:
        lock_path = self.lease_dir / f".research-{_safe_name(run_id)}-{_safe_name(node_id)}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        thread_lock = _thread_lock_for(lock_path)
        with thread_lock:
            with open(lock_path, "a", encoding="utf-8") as handle:
                try:
                    import fcntl  # type: ignore
                except ImportError:
                    yield
                    return
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()) or "unknown"


def _thread_lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[key] = lock
        return lock


def _format_time(value: _dt.datetime) -> str:
    return value.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: str) -> _dt.datetime | None:
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(_dt.timezone.utc)
    except Exception:
        return None
