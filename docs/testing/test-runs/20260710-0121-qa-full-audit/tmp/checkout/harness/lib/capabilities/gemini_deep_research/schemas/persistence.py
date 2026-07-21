"""Append-only event persistence for Gemini Deep Research runs.

Events are the source of truth: controller state is reconstructed by replaying
them (C2/C4). One JSONL file per run_ref under a configurable base dir. No
secrets are ever written (NB1) — callers pass already-redacted payloads.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# Default event store. STATE.md forbids /tmp; keep under harness var/.
_DEFAULT_BASE = Path(
    os.environ.get(
        "GEMINI_DR_EVENT_DIR",
        str(Path.home() / ".solar" / "harness" / "var" / "gemini_deep_research" / "events"),
    )
)

_SECRET_KEYS = {"cookie", "token", "session", "password", "secret", "authorization"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Event:
    seq: int
    ts: str
    run_ref: str
    type: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "run_ref": self.run_ref,
            "type": self.type,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        return cls(
            seq=d["seq"],
            ts=d["ts"],
            run_ref=d["run_ref"],
            type=d["type"],
            payload=d.get("payload", {}),
        )


def _assert_no_secrets(payload: dict[str, Any]) -> None:
    for k in payload:
        if str(k).lower() in _SECRET_KEYS:
            raise ValueError(f"refusing to persist secret-like key: {k!r} (NB1)")


class EventLog:
    """Append-only JSONL event log keyed by run_ref."""

    def __init__(self, base_dir: str | os.PathLike[str] | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else _DEFAULT_BASE
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, run_ref: str) -> Path:
        safe = run_ref.replace("/", "_").replace("..", "_")
        return self.base_dir / f"{safe}.jsonl"

    def append(self, run_ref: str, event_type: str, payload: dict[str, Any] | None = None) -> Event:
        payload = dict(payload or {})
        _assert_no_secrets(payload)
        with self._lock:
            seq = sum(1 for _ in self.read(run_ref))
            ev = Event(seq=seq, ts=_now_iso(), run_ref=run_ref, type=event_type, payload=payload)
            with self._path(run_ref).open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
            return ev

    def read(self, run_ref: str) -> Iterator[Event]:
        p = self._path(run_ref)
        if not p.exists():
            return
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield Event.from_dict(json.loads(line))

    def read_all(self, run_ref: str) -> list[Event]:
        return list(self.read(run_ref))

    def list_runs(self) -> list[str]:
        return sorted(p.stem for p in self.base_dir.glob("*.jsonl"))
