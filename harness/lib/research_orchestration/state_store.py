"""Atomic, conflict-detecting JSON state store for research orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Callable, Iterator


class ResearchStateStoreError(ValueError):
    """Raised when run state cannot be loaded or saved safely."""


class ResearchStateConflictError(ResearchStateStoreError):
    """Raised when a stale writer attempts to overwrite newer state."""


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_ANY_REVISION = object()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class ResearchStateStore:
    """Persist run state and accepted node records below one supplied root.

    State files retain the Phase 0 ``research_run_state.v1`` shape.  Node
    result/evaluator details live in real sidecar files referenced by
    ``node_states.*.result_ref``.  Writes use a process lock plus optimistic
    revision checks so two orchestrators cannot silently overwrite each other.
    """

    def __init__(self, state_root: Path, clock: Callable[[], str] | None = None) -> None:
        self.state_root = Path(state_root).expanduser().resolve()
        self.clock = clock or _default_clock
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._records_root = (self.state_root / "node-records").resolve()
        self._records_root.mkdir(parents=True, exist_ok=True)

    def load(self, run_id: str) -> dict | None:
        payload, _revision = self.load_with_revision(run_id)
        return payload

    def load_with_revision(self, run_id: str) -> tuple[dict | None, str | None]:
        path = self._state_path(run_id)
        with self._run_lock(run_id):
            if not path.exists():
                return None, None
            encoded = path.read_bytes()
        return self._decode_state(encoded, path), _sha256(encoded)

    def revision(self, run_id: str) -> str | None:
        _payload, revision = self.load_with_revision(run_id)
        return revision

    def save(self, state: dict, *, expected_revision: str | None | object = _ANY_REVISION) -> Path:
        path, _revision = self.save_with_revision(state, expected_revision=expected_revision)
        return path

    def save_with_revision(
        self,
        state: dict,
        *,
        expected_revision: str | None | object = _ANY_REVISION,
    ) -> tuple[Path, str]:
        run_id, encoded = self._encode_state(state)
        path = self._state_path(run_id)
        with self._run_lock(run_id):
            current_revision = _sha256(path.read_bytes()) if path.exists() else None
            if expected_revision is not _ANY_REVISION and current_revision != expected_revision:
                raise ResearchStateConflictError(
                    f"state revision conflict for {run_id}: expected {expected_revision!r}, "
                    f"found {current_revision!r}"
                )
            self._atomic_write(path, encoded)
        return path, _sha256(encoded)

    def create(self, initial_state: dict) -> Path:
        path, _revision = self.create_with_revision(initial_state)
        return path

    def create_with_revision(self, initial_state: dict) -> tuple[Path, str]:
        return self.save_with_revision(initial_state, expected_revision=None)

    def store_node_record(
        self,
        *,
        run_id: str,
        node_id: str,
        result: dict,
        evaluation: dict,
    ) -> str:
        """Persist accepted/sanitized node evidence and return an existing path."""

        self._validate_id(run_id, "run_id")
        self._validate_id(node_id, "node_id")
        record = {
            "schema": "research_orchestration_node_record.v1",
            "run_id": run_id,
            "node_id": node_id,
            "recorded_at": self.clock(),
            "result": deepcopy(result),
            "evaluation": deepcopy(evaluation),
        }
        encoded = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
        # Immutable, content-addressed records ensure a stale writer can leave
        # only an unreferenced sidecar; it cannot replace evidence referenced
        # by a state commit that won the optimistic revision race.
        record_digest = _sha256(encoded)
        path = (self._records_root / f"{record_digest}.json").resolve()
        self._assert_below(path, self._records_root, "node record path escapes record root")
        with self._run_lock(run_id):
            self._atomic_write(path, encoded)
        if not path.is_file():
            raise ResearchStateStoreError(f"node record was not persisted: {path}")
        return str(path)

    def load_node_record(
        self,
        result_ref: str,
        *,
        expected_run_id: str | None = None,
        expected_node_id: str | None = None,
    ) -> dict:
        if not isinstance(result_ref, str) or not result_ref.strip():
            raise ResearchStateStoreError("result_ref must be a non-empty string")
        path = Path(result_ref).expanduser().resolve()
        self._assert_below(path, self._records_root, "result_ref escapes record root")
        if not path.is_file():
            raise ResearchStateStoreError(f"node record does not exist: {path}")
        encoded = path.read_bytes()
        try:
            payload = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResearchStateStoreError(f"node record JSON is corrupted: {path}") from exc
        if not isinstance(payload, dict) or payload.get("schema") != "research_orchestration_node_record.v1":
            raise ResearchStateStoreError(f"invalid node record: {path}")
        run_id = payload.get("run_id")
        node_id = payload.get("node_id")
        self._validate_id(run_id, "record.run_id")
        self._validate_id(node_id, "record.node_id")
        digest = _sha256(encoded)
        expected_name = f"{digest}.json"
        if path.name != expected_name:
            raise ResearchStateStoreError("node record content digest does not match content-addressed filename")
        if expected_run_id is not None and run_id != expected_run_id:
            raise ResearchStateStoreError("node record run_id does not match requested identity")
        if expected_node_id is not None and node_id != expected_node_id:
            raise ResearchStateStoreError("node record node_id does not match requested identity")
        return payload

    def _encode_state(self, state: dict) -> tuple[str, bytes]:
        if not isinstance(state, dict):
            raise ResearchStateStoreError("state must be an object")
        run_id = state.get("run_id")
        if not isinstance(run_id, str):
            raise ResearchStateStoreError("state.run_id must be a string")
        payload = deepcopy(state)
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        return run_id, encoded

    def _decode_state(self, encoded: bytes, path: Path) -> dict:
        try:
            payload = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResearchStateStoreError(f"state JSON is corrupted: {path}") from exc
        if not isinstance(payload, dict):
            raise ResearchStateStoreError(f"state JSON must be an object: {path}")
        return payload

    def _atomic_write(self, path: Path, encoded: bytes) -> None:
        temp_path = self._temp_path(path)
        try:
            temp_path.write_bytes(encoded)
            for attempt in range(8):
                try:
                    os.replace(temp_path, path)
                    break
                except PermissionError:
                    if os.name != "nt" or attempt == 7:
                        raise
                    time.sleep(0.01 * (attempt + 1))
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @contextmanager
    def _run_lock(self, run_id: str) -> Iterator[None]:
        self._validate_id(run_id, "run_id")
        lock_path = (self.state_root / f".{run_id}.lock").resolve()
        self._assert_below(lock_path, self.state_root, "lock path escapes state_root")
        key = str(lock_path).casefold()
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+b") as handle:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                _lock_file(handle)
                try:
                    yield
                finally:
                    handle.seek(0)
                    _unlock_file(handle)

    def _state_path(self, run_id: str) -> Path:
        self._validate_id(run_id, "run_id")
        path = (self.state_root / f"{run_id}.research_run_state.json").resolve()
        self._assert_below(path, self.state_root, "state path escapes state_root")
        return path

    def _temp_path(self, path: Path) -> Path:
        suffix = f".{os.getpid()}.{threading.get_ident()}.tmp"
        temp_path = path.with_name(path.name + suffix).resolve()
        self._assert_below(temp_path, path.parent, "temp path escapes target directory")
        return temp_path

    @staticmethod
    def _validate_id(value: str, field: str) -> None:
        if not isinstance(value, str) or not value:
            raise ResearchStateStoreError(f"{field} must be a non-empty string")
        if not _RUN_ID_RE.match(value) or Path(value).name != value:
            raise ResearchStateStoreError(f"{field} contains unsafe path characters")

    @staticmethod
    def _assert_below(path: Path, parent: Path, message: str) -> None:
        try:
            path.relative_to(parent)
        except ValueError as exc:
            raise ResearchStateStoreError(message) from exc


def _lock_file(handle: object) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]


def _unlock_file(handle: object) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _default_clock() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
