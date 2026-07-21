"""actor_lease.py — Lease broker for AgentActor lease management.

Implements atomic lease acquisition/release with filesystem locks.
Lease state: actor_id, lease_id, task_id, sprint_id, node_id,
acquired_at, expires_at, renewable, preemptible, heartbeat_timeout_sec, evidence_path.
"""
from __future__ import annotations

import datetime
import fcntl
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
LEASE_DIR = HARNESS_DIR / "run" / "actor-leases"

# Canonical state machine states
READY = "READY"
LEASED = "LEASED"
RUNNING = "RUNNING"
FINALIZING = "FINALIZING"

# Exception states
STALE = "STALE"
QUOTA_BLOCKED = "QUOTA_BLOCKED"
AUTH_BLOCKED = "AUTH_BLOCKED"
POLICY_BLOCKED = "POLICY_BLOCKED"
HUMAN_REQUIRED = "HUMAN_REQUIRED"
CRASHED = "CRASHED"
DRAINING = "DRAINING"
DISABLED = "DISABLED"

NORMAL_STATES = {READY, LEASED, RUNNING, FINALIZING}
EXCEPTION_STATES = {STALE, QUOTA_BLOCKED, AUTH_BLOCKED, POLICY_BLOCKED, HUMAN_REQUIRED, CRASHED, DRAINING, DISABLED}
ALL_STATES = NORMAL_STATES | EXCEPTION_STATES

TRANSITIONS = {
    READY: {LEASED, DISABLED},
    LEASED: {RUNNING, STALE, QUOTA_BLOCKED, AUTH_BLOCKED, POLICY_BLOCKED, READY},
    RUNNING: {FINALIZING, CRASHED, STALE, DRAINING},
    FINALIZING: {READY, CRASHED},
    STALE: {READY, DISABLED},
    QUOTA_BLOCKED: {READY, DISABLED},
    AUTH_BLOCKED: {READY, DISABLED},
    POLICY_BLOCKED: {READY, DISABLED, HUMAN_REQUIRED},
    HUMAN_REQUIRED: {READY, DISABLED},
    CRASHED: {READY, DISABLED},
    DRAINING: {READY, CRASHED, DISABLED},
    DISABLED: {READY},
}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LeaseState:
    """Represents a single actor lease with all required fields."""

    __slots__ = (
        "actor_id", "lease_id", "task_id", "sprint_id", "node_id",
        "acquired_at", "expires_at", "renewable", "preemptible",
        "heartbeat_timeout_sec", "evidence_path", "state",
    )

    def __init__(
        self,
        actor_id: str,
        lease_id: Optional[str] = None,
        task_id: Optional[str] = None,
        sprint_id: Optional[str] = None,
        node_id: Optional[str] = None,
        acquired_at: Optional[str] = None,
        expires_at: Optional[str] = None,
        renewable: bool = True,
        preemptible: bool = False,
        heartbeat_timeout_sec: int = 120,
        evidence_path: Optional[str] = None,
        state: str = READY,
    ):
        self.actor_id = actor_id
        self.lease_id = lease_id
        self.task_id = task_id
        self.sprint_id = sprint_id
        self.node_id = node_id
        self.acquired_at = acquired_at
        self.expires_at = expires_at
        self.renewable = renewable
        self.preemptible = preemptible
        self.heartbeat_timeout_sec = heartbeat_timeout_sec
        self.evidence_path = evidence_path
        self.state = state

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "lease_id": self.lease_id,
            "task_id": self.task_id,
            "sprint_id": self.sprint_id,
            "node_id": self.node_id,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "renewable": self.renewable,
            "preemptible": self.preemptible,
            "heartbeat_timeout_sec": self.heartbeat_timeout_sec,
            "evidence_path": self.evidence_path,
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LeaseState":
        return cls(**{k: d[k] for k in cls.__slots__ if k in d})


class LeaseBroker:
    """Atomic lease broker using filesystem locks."""

    def __init__(self, lease_dir: Optional[Path] = None):
        self.lease_dir = lease_dir or LEASE_DIR
        self.lease_dir.mkdir(parents=True, exist_ok=True)

    def _lease_path(self, actor_id: str) -> Path:
        return self.lease_dir / f"{actor_id}.json"

    def acquire(
        self,
        actor_id: str,
        task_id: str,
        sprint_id: str,
        node_id: str,
        ttl_sec: int = 2700,
        renewable: bool = True,
        preemptible: bool = False,
        heartbeat_timeout_sec: int = 120,
        evidence_path: Optional[str] = None,
    ) -> Optional[LeaseState]:
        """Attempt to acquire a lease for actor_id. Returns LeaseState or None."""
        path = self._lease_path(actor_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        lock_path = path.with_suffix(".lock")
        lock_fd = open(lock_path, "w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            lock_fd.close()
            return None

        try:
            current = self._read(path)
            if current and current.state not in {READY, STALE, CRASHED}:
                return None

            now = _now()
            expires = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=ttl_sec)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

            lease = LeaseState(
                actor_id=actor_id,
                lease_id=str(uuid.uuid4()),
                task_id=task_id,
                sprint_id=sprint_id,
                node_id=node_id,
                acquired_at=now,
                expires_at=expires,
                renewable=renewable,
                preemptible=preemptible,
                heartbeat_timeout_sec=heartbeat_timeout_sec,
                evidence_path=evidence_path,
                state=LEASED,
            )
            path.write_text(json.dumps(lease.to_dict(), indent=2), encoding="utf-8")
            return lease
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    def transition(self, actor_id: str, new_state: str) -> Optional[LeaseState]:
        """Transition actor to new_state. Returns updated LeaseState or None."""
        path = self._lease_path(actor_id)
        lock_path = path.with_suffix(".lock")
        lock_fd = open(lock_path, "w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            lock_fd.close()
            return None

        try:
            current = self._read(path)
            if not current:
                return None
            allowed = TRANSITIONS.get(current.state, set())
            if new_state not in allowed:
                return None
            current.state = new_state
            if new_state == READY:
                current.lease_id = None
                current.task_id = None
                current.sprint_id = None
                current.node_id = None
                current.acquired_at = None
                current.expires_at = None
            path.write_text(json.dumps(current.to_dict(), indent=2), encoding="utf-8")
            return current
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    def check_stale(self, actor_id: str) -> bool:
        """Check if lease has expired (stale)."""
        path = self._lease_path(actor_id)
        lease = self._read(path)
        if not lease or lease.state != LEASED:
            return False
        if not lease.expires_at:
            return False
        now = datetime.datetime.now(datetime.timezone.utc)
        exp = datetime.datetime.fromisoformat(lease.expires_at.replace("Z", "+00:00"))
        return now > exp

    def get(self, actor_id: str) -> Optional[LeaseState]:
        return self._read(self._lease_path(actor_id))

    def _read(self, path: Path) -> Optional[LeaseState]:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return LeaseState.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None
