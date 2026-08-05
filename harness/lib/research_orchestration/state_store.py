"""Atomic JSON state store for Solar research orchestration."""

from __future__ import annotations

import json
import os
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


class ResearchStateStoreError(ValueError):
    """Raised when run state cannot be loaded or saved safely."""


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class ResearchStateStore:
    """Persist run states below one caller-supplied root."""

    def __init__(self, state_root: Path, clock: Callable[[], str] | None = None) -> None:
        self.state_root = Path(state_root).expanduser().resolve()
        self.clock = clock or _default_clock
        self._write_lock = threading.Lock()
        self.state_root.mkdir(parents=True, exist_ok=True)

    def load(self, run_id: str) -> dict | None:
        path = self._state_path(run_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ResearchStateStoreError(f"state JSON is corrupted: {path}") from exc
        if not isinstance(payload, dict):
            raise ResearchStateStoreError(f"state JSON must be an object: {path}")
        return payload

    def save(self, state: dict) -> Path:
        if not isinstance(state, dict):
            raise ResearchStateStoreError("state must be an object")
        run_id = state.get("run_id")
        if not isinstance(run_id, str):
            raise ResearchStateStoreError("state.run_id must be a string")
        path = self._state_path(run_id)
        payload = deepcopy(state)
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        temp_path = self._temp_path(path)
        with self._write_lock:
            try:
                temp_path.write_text(encoded, encoding="utf-8")
                os.replace(temp_path, path)
            finally:
                if temp_path.exists():
                    temp_path.unlink()
        return path

    def create(self, initial_state: dict) -> Path:
        if not isinstance(initial_state, dict):
            raise ResearchStateStoreError("initial_state must be an object")
        return self.save(initial_state)

    def _state_path(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not run_id:
            raise ResearchStateStoreError("run_id must be a non-empty string")
        if not _RUN_ID_RE.match(run_id) or Path(run_id).name != run_id:
            raise ResearchStateStoreError("run_id contains unsafe path characters")
        path = (self.state_root / f"{run_id}.research_run_state.json").resolve()
        try:
            path.relative_to(self.state_root)
        except ValueError as exc:
            raise ResearchStateStoreError("state path escapes state_root") from exc
        return path

    def _temp_path(self, path: Path) -> Path:
        suffix = f".{os.getpid()}.{threading.get_ident()}.tmp"
        temp_path = path.with_name(path.name + suffix).resolve()
        try:
            temp_path.relative_to(self.state_root)
        except ValueError as exc:
            raise ResearchStateStoreError("temp path escapes state_root") from exc
        return temp_path


def _default_clock() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
