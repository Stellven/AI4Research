"""Solar Harness — Worker Runtime.

Worker pool management: register, heartbeat, lease acquisition/release.
Uses file-based persistence (no new daemon dependency).

Workers can be local panes, remote Mac mini, or future sandboxes.
Each worker declares capabilities and location, and holds leases
for activity execution.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
WORKERS_DIR = os.path.join(HARNESS_DIR, "state", "workers")

sys_path_inserted = False
if not sys_path_inserted:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    sys_path_inserted = True

from runtime_interfaces import LeaseInfo, LeaseStatus, WorkerInfo

_DEFAULT_LEASE_TTL = 3600  # 1 hour
_HEARTBEAT_STALE_SECONDS = 300  # 5 minutes


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _worker_path(worker_id: str) -> str:
    return os.path.join(WORKERS_DIR, f"{worker_id}.json")


def _leases_path() -> str:
    return os.path.join(WORKERS_DIR, "leases.json")


class WorkerRuntime:
    """File-based worker registry with heartbeat and lease management."""

    def __init__(self, *, harness_dir: Optional[str] = None) -> None:
        global WORKERS_DIR
        base = harness_dir or HARNESS_DIR
        WORKERS_DIR = os.path.join(base, "state", "workers")
        os.makedirs(WORKERS_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        worker_id: str,
        *,
        capabilities: Optional[List[str]] = None,
        location: str = "local",
        lease_ttl_seconds: int = _DEFAULT_LEASE_TTL,
    ) -> WorkerInfo:
        info = WorkerInfo(
            worker_id=worker_id,
            capabilities=capabilities or [],
            location=location,
            registered_at=_now_ts(),
            last_heartbeat=_now_ts(),
        )
        path = _worker_path(worker_id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({
                "worker_id": info.worker_id,
                "capabilities": info.capabilities,
                "location": info.location,
                "registered_at": info.registered_at,
                "last_heartbeat": info.last_heartbeat,
                "lease_ttl": lease_ttl_seconds,
            }, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        return info

    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        path = _worker_path(worker_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            return WorkerInfo(
                worker_id=data["worker_id"],
                capabilities=data.get("capabilities", []),
                location=data.get("location", "local"),
                registered_at=data.get("registered_at", ""),
                last_heartbeat=data.get("last_heartbeat", ""),
                lease=data.get("lease"),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def list_workers(self, *, active_only: bool = False) -> List[WorkerInfo]:
        workers: List[WorkerInfo] = []
        if not os.path.exists(WORKERS_DIR):
            return workers
        for fname in os.listdir(WORKERS_DIR):
            if not fname.endswith(".json") or fname == "leases.json":
                continue
            wid = fname[:-5]
            info = self.get_worker(wid)
            if info is None:
                continue
            if active_only and self._is_stale(info):
                continue
            workers.append(info)
        return workers

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def heartbeat(self, worker_id: str) -> bool:
        info = self.get_worker(worker_id)
        if info is None:
            return False
        info.last_heartbeat = _now_ts()
        path = _worker_path(worker_id)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return False
        data["last_heartbeat"] = info.last_heartbeat
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        return True

    def _is_stale(self, info: WorkerInfo) -> bool:
        if not info.last_heartbeat:
            return True
        try:
            hb_dt = datetime.strptime(
                info.last_heartbeat, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            return True
        age = (datetime.now(timezone.utc) - hb_dt).total_seconds()
        return age > _HEARTBEAT_STALE_SECONDS

    # ------------------------------------------------------------------
    # Leases
    # ------------------------------------------------------------------

    def acquire_lease(
        self,
        worker_id: str,
        session_id: str,
        activity_id: str,
        *,
        ttl_seconds: int = _DEFAULT_LEASE_TTL,
    ) -> Optional[LeaseInfo]:
        info = self.get_worker(worker_id)
        if info is None:
            return None
        if self._is_stale(info):
            return None

        leases = self._load_leases()

        # Check: worker already has an active lease?
        existing = self._find_worker_lease(worker_id, leases)
        if existing and existing["status"] == LeaseStatus.ACTIVE.value:
            return None  # Cannot hold two leases

        # Check: activity already leased?
        for l in leases:
            if (l.get("activity_id") == activity_id
                    and l.get("status") == LeaseStatus.ACTIVE.value):
                return None  # Activity already leased

        now = datetime.now(timezone.utc)
        import uuid
        lease_id = str(uuid.uuid4())[:8]
        new_lease = {
            "lease_id": lease_id,
            "worker_id": worker_id,
            "session_id": session_id,
            "activity_id": activity_id,
            "acquired_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at": (now + __import__('datetime').timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": LeaseStatus.ACTIVE.value,
        }
        leases.append(new_lease)
        self._save_leases(leases)

        # Update worker info with lease
        info.lease = new_lease
        self._update_worker_lease(worker_id, new_lease)

        return LeaseInfo(
            lease_id=lease_id,
            worker_id=worker_id,
            session_id=session_id,
            activity_id=activity_id,
            acquired_at=new_lease["acquired_at"],
            expires_at=new_lease["expires_at"],
            status=LeaseStatus.ACTIVE,
        )

    def release_lease(
        self,
        worker_id: str,
        activity_id: str,
        *,
        reason: str = "completed",
    ) -> bool:
        leases = self._load_leases()
        found = False
        for l in leases:
            if (l.get("worker_id") == worker_id
                    and l.get("activity_id") == activity_id
                    and l.get("status") == LeaseStatus.ACTIVE.value):
                l["status"] = LeaseStatus.RELEASED.value
                l["released_at"] = _now_ts()
                l["release_reason"] = reason
                found = True
                break
        if not found:
            return False
        self._save_leases(leases)
        self._update_worker_lease(worker_id, None)
        return True

    def expire_leases(self) -> List[str]:
        """Expire all leases past their expires_at timestamp. Return expired lease IDs."""
        leases = self._load_leases()
        now = datetime.now(timezone.utc)
        expired_ids: List[str] = []
        for l in leases:
            if l.get("status") != LeaseStatus.ACTIVE.value:
                continue
            exp_str = l.get("expires_at", "")
            if not exp_str:
                continue
            try:
                exp_dt = datetime.strptime(exp_str, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue
            if now >= exp_dt:
                l["status"] = LeaseStatus.EXPIRED.value
                l["expired_at"] = _now_ts()
                expired_ids.append(l.get("lease_id", ""))
        if expired_ids:
            self._save_leases(leases)
        return expired_ids

    def get_active_leases(self) -> List[LeaseInfo]:
        leases = self._load_leases()
        active: List[LeaseInfo] = []
        for l in leases:
            if l.get("status") == LeaseStatus.ACTIVE.value:
                active.append(LeaseInfo(
                    lease_id=l.get("lease_id", ""),
                    worker_id=l.get("worker_id", ""),
                    session_id=l.get("session_id", ""),
                    activity_id=l.get("activity_id", ""),
                    acquired_at=l.get("acquired_at", ""),
                    expires_at=l.get("expires_at", ""),
                    status=LeaseStatus.ACTIVE,
                ))
        return active

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_leases(self) -> List[Dict[str, Any]]:
        path = _leases_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return []

    def _save_leases(self, leases: List[Dict[str, Any]]) -> None:
        path = _leases_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(leases, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)

    def _find_worker_lease(
        self, worker_id: str, leases: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        for l in leases:
            if (l.get("worker_id") == worker_id
                    and l.get("status") == LeaseStatus.ACTIVE.value):
                return l
        return None

    def _update_worker_lease(
        self, worker_id: str, lease: Optional[Dict[str, Any]]
    ) -> None:
        path = _worker_path(worker_id)
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return
        data["lease"] = lease
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
