"""actor_mailbox.py — File-based mailbox for actor task protocol.

P0 implementation: file mailbox under ~/.solar/harness/actors/<actor_id>/.
Inbox for task envelopes, outbox for machine-readable results.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
ACTORS_BASE = HARNESS_DIR / "actors"


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ActorMailbox:
    """File-based mailbox for a single actor."""

    def __init__(self, actor_id: str, base_dir: Optional[Path] = None):
        self.actor_id = actor_id
        self.base = (base_dir or ACTORS_BASE) / actor_id
        self.inbox = self.base / "inbox"
        self.outbox = self.base / "outbox"
        self.logs = self.base / "logs"
        self.state_json = self.base / "state.json"
        self.heartbeat_json = self.base / "heartbeat.json"

    def ensure_dirs(self) -> None:
        for d in (self.inbox, self.outbox, self.logs):
            d.mkdir(parents=True, exist_ok=True)

    def submit_task(self, task_envelope: Dict[str, Any]) -> str:
        """Write task_envelope to inbox. Returns task file path."""
        self.ensure_dirs()
        task_id = task_envelope.get("task_id", str(uuid.uuid4()))
        ts = _now_iso().replace(":", "-").replace("T", "_")
        filename = f"task-{task_id}-{ts}.json"
        path = self.inbox / filename
        path.write_text(json.dumps(task_envelope, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def read_inbox(self) -> List[Dict[str, Any]]:
        """Read all task envelopes from inbox."""
        if not self.inbox.exists():
            return []
        tasks = []
        for f in sorted(self.inbox.glob("task-*.json")):
            try:
                tasks.append(json.loads(f.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return tasks

    def write_result(self, task_id: str, result: Dict[str, Any]) -> str:
        """Write machine-readable result to outbox."""
        self.ensure_dirs()
        uid = str(uuid.uuid4())[:8]
        ts = _now_iso().replace(":", "-").replace("T", "_")
        filename = f"result-{task_id}-{ts}-{uid}.json"
        path = self.outbox / filename
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def read_results(self, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Read results from outbox, optionally filtered by task_id."""
        if not self.outbox.exists():
            return []
        results = []
        for f in sorted(self.outbox.glob("result-*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if task_id is None or data.get("task_id") == task_id:
                    results.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return results

    def write_heartbeat(self, status: str, metadata: Optional[Dict] = None) -> None:
        self.ensure_dirs()
        data = {
            "actor_id": self.actor_id,
            "status": status,
            "timestamp": _now_iso(),
            "metadata": metadata or {},
        }
        self.heartbeat_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def read_heartbeat(self) -> Optional[Dict[str, Any]]:
        if not self.heartbeat_json.exists():
            return None
        try:
            return json.loads(self.heartbeat_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
