"""Research-node lease adapter over the existing operator runtime lease store.

The native ``operator_runtime`` functions are used when they are importable and
point at the requested harness root.  Windows cannot currently import that
module because it depends on ``fcntl``; in that case this module writes the
same core lease fields under the same store while protecting them with a
portable process-safe claim: Windows uses a kernel byte-range lock that is
released automatically on process exit, while Unix uses an atomic directory
with owner identity for stale recovery.

The claim protocol prevents cooperating processes from racing.  It cannot
protect against an unrelated process that bypasses both canonical and research
locks, registry changes between fallback validation and write, or hostile
hardlink/reparse-point mutation of the lease directory.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import importlib
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any


ACTIVE_STATES = frozenset({"leased", "running", "draining"})
RECOVERABLE_STATES = frozenset({"stale", "crashed"})
_CREDENTIAL_VALUE = re.compile(
    r"(?:\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]{8,}|\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|client[_-]?secret|secret)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
_SAFE_NUMERIC_METADATA_FIELDS = frozenset(
    {
        "attempt",
        "attempt_count",
        "duration_ms",
        "timeout_seconds",
        "token_budget",
    }
)
_SAFE_TEXT_METADATA_FIELDS = frozenset(
    {
        "correlation_id",
        "label",
        "model_name",
        "provider_name",
        "secretariat_notes",
        "stage",
        "status",
        "topic",
        "trace_id",
    }
)


class ResearchLeaseAdapter:
    """Coordinate research nodes through the canonical operator lease store."""

    def __init__(
        self,
        harness_root: str | Path,
        *,
        clock: Any | None = None,
        operator_runtime_api: Any | None = None,
        operator_registry_path: str | Path | None = None,
        claim_timeout_seconds: float = 10.0,
        abandoned_claim_seconds: float = 30.0,
    ) -> None:
        self.harness_root = Path(harness_root).resolve()
        self.lease_dir = self.harness_root / "run" / "operator-leases"
        self.status_dir = self.harness_root / "run" / "operator-status"
        self.clock = clock or (lambda: _dt.datetime.now(_dt.timezone.utc))
        self.claim_timeout_seconds = max(0.1, float(claim_timeout_seconds))
        self.abandoned_claim_seconds = max(1.0, float(abandoned_claim_seconds))
        self.operator_runtime = (
            None
            if operator_runtime_api is False
            else (
                operator_runtime_api
                if operator_runtime_api is not None
                else _load_matching_operator_runtime(self.harness_root)
            )
        )
        self.operator_registry_path = (
            Path(operator_registry_path).resolve()
            if operator_registry_path is not None
            else self.harness_root / "config" / "physical-operators.json"
        )

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
        secret_values: Sequence[str] | None = None,
        safe_metadata_fields: Sequence[str] | None = None,
        recover_stale: bool = False,
    ) -> dict[str, Any]:
        self._validate_identity(run_id, node_id, operator_id)
        _mkdir(self.lease_dir)

        with self._exclusive(run_id, node_id, operator_id) as claims_acquired:
            if not claims_acquired:
                return self._blocked(
                    "lease_claim_busy",
                    {"run_id": run_id, "node_id": node_id, "operator_id": operator_id},
                )
            explicit_secrets = _normalize_secret_values(secret_values)
            registry_blocker = self._fallback_registry_blocker(
                run_id, node_id, operator_id
            )
            if registry_blocker:
                return registry_blocker
            existing_for_node = self._active_for_run_node(run_id, node_id)
            if existing_for_node:
                if self.is_stale(existing_for_node):
                    if recover_stale:
                        self._mark_recovered(
                            str(existing_for_node.get("operator_id") or ""),
                            existing_for_node,
                            "acquire_recovered_stale",
                            explicit_secrets,
                        )
                    else:
                        return self._blocked("stale_lease_requires_recovery", existing_for_node)
                else:
                    return self._blocked("run_node_already_active", existing_for_node)

            operator_lease = self._read_lease(operator_id)
            if operator_lease and self._is_active(operator_lease):
                if self.is_stale(operator_lease):
                    if recover_stale:
                        self._mark_recovered(
                            operator_id,
                            operator_lease,
                            "acquire_recovered_operator_stale",
                            explicit_secrets,
                        )
                    else:
                        return self._blocked("operator_has_stale_lease", operator_lease)
                else:
                    return self._blocked("operator_busy", operator_lease)
            elif operator_lease and operator_lease.get("corrupt"):
                if recover_stale:
                    self._mark_recovered(
                        operator_id,
                        operator_lease,
                        "acquire_recovered_corrupt",
                        explicit_secrets,
                    )
                else:
                    return self._blocked("corrupt_lease_requires_recovery", operator_lease)

            now = self._now()
            ttl = max(1, int(ttl_seconds))
            extension = {
                "run_id": run_id,
                "research_run_id": run_id,
                "lease_id": str(uuid.uuid4()),
                "heartbeat_at": _format_time(now),
                "heartbeat_timeout_seconds": max(1, int(heartbeat_timeout_seconds)),
            }
            if metadata:
                cleaned = _sanitize_research_metadata(
                    metadata,
                    explicit_secrets,
                    safe_metadata_fields=safe_metadata_fields,
                )
                if cleaned:
                    extension["research_metadata"] = cleaned
                    extension["research_metadata_policy"] = "explicit_safe_scalars.v1"

            if self.operator_runtime is not None:
                try:
                    lease = self.operator_runtime.acquire_operator_lease(
                        operator_id=operator_id,
                        task_id=task_id or f"{run_id}:{node_id}",
                        sprint_id=run_id,
                        node_id=node_id,
                        ttl_seconds=ttl,
                        initial_state="leased",
                    )
                    lease = self.operator_runtime.update_operator_lease_metadata(
                        operator_id, **extension
                    )
                except Exception as exc:
                    return self._blocked_from_native_exception(exc, run_id, node_id, operator_id)
            else:
                lease = {
                    "operator_id": operator_id,
                    "task_id": task_id or f"{run_id}:{node_id}",
                    "sprint_id": run_id,
                    "node_id": node_id,
                    "leased_at": _format_time(now),
                    "expires_at": _format_time(now + _dt.timedelta(seconds=ttl)),
                    "state": "leased",
                    **extension,
                }
                self._write_lease(operator_id, lease)
            return {
                "acquired": True,
                "lease": _sanitize_metadata(lease, explicit_secrets),
                "blocker": None,
            }

    def heartbeat(
        self,
        run_id: str,
        node_id: str,
        operator_id: str,
        *,
        lease_id: str | None = None,
        ttl_seconds: int = 900,
        state: str = "running",
        secret_values: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        with self._exclusive(run_id, node_id, operator_id) as claims_acquired:
            if not claims_acquired:
                return self._blocked(
                    "lease_claim_busy",
                    {"run_id": run_id, "node_id": node_id, "operator_id": operator_id},
                )
            explicit_secrets = _normalize_secret_values(secret_values)
            lease = self._read_lease(operator_id)
            if not lease:
                return self._blocked(
                    "lease_missing",
                    {"run_id": run_id, "node_id": node_id, "operator_id": operator_id},
                )
            mismatch = self._identity_blocker(lease, run_id, node_id, lease_id)
            if mismatch:
                return mismatch
            if self.is_stale(lease):
                return self._blocked("lease_stale", lease)

            now = self._now()
            normalized_state = state if state in ACTIVE_STATES else "running"
            updates = {
                "heartbeat_at": _format_time(now),
                "expires_at": _format_time(
                    now + _dt.timedelta(seconds=max(1, int(ttl_seconds)))
                ),
            }
            if self.operator_runtime is not None:
                lease = self.operator_runtime.update_operator_lease_state(
                    operator_id, normalized_state
                )
                sanitized_metadata = _sanitize_lease_record(
                    lease, explicit_secrets
                )
                lease = self.operator_runtime.update_operator_lease_metadata(
                    operator_id,
                    **updates,
                    research_metadata=sanitized_metadata.get("research_metadata"),
                    research_metadata_policy=sanitized_metadata.get(
                        "research_metadata_policy"
                    ),
                )
                try:
                    self.operator_runtime.set_operator_status(
                        operator_id, normalized_state, ttl_seconds=max(1, int(ttl_seconds))
                    )
                except AttributeError:
                    pass
            else:
                lease.update(updates)
                lease["state"] = normalized_state
                self._write_lease(operator_id, lease)
                self._write_compatible_status(operator_id, lease)
            return {
                "ok": True,
                "lease": _sanitize_metadata(lease, explicit_secrets),
                "blocker": None,
            }

    def release(
        self,
        run_id: str,
        node_id: str,
        operator_id: str,
        *,
        lease_id: str | None = None,
        reason: str = "completed",
        secret_values: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        with self._exclusive(run_id, node_id, operator_id) as claims_acquired:
            if not claims_acquired:
                return self._blocked(
                    "lease_claim_busy",
                    {"run_id": run_id, "node_id": node_id, "operator_id": operator_id},
                )
            explicit_secrets = _normalize_secret_values(secret_values)
            lease = self._read_lease(operator_id)
            if not lease:
                return {"released": False, "reason": "lease_missing"}
            mismatch = self._identity_blocker(lease, run_id, node_id, lease_id)
            if mismatch:
                return mismatch
            lease["state"] = "released"
            lease["released_at"] = _format_time(self._now())
            safe_reason = _safe_reason(reason, explicit_secrets)
            lease["release_reason"] = safe_reason
            self._archive_lease(operator_id, lease, explicit_secrets)
            if self.operator_runtime is not None:
                released = bool(
                    self.operator_runtime.release_operator_lease(operator_id, safe_reason)
                )
            else:
                released = _unlink_if_exists(self._lease_path(operator_id))
            return {
                "released": released,
                "lease": _sanitize_metadata(lease, explicit_secrets),
            }

    def is_stale(
        self, lease_or_run_id: dict[str, Any] | str, node_id: str | None = None
    ) -> bool:
        if isinstance(lease_or_run_id, dict):
            return self._lease_is_stale(lease_or_run_id)
        if node_id is None:
            raise ValueError("node_id is required when checking by run_id")
        lease = self._active_for_run_node(lease_or_run_id, node_id)
        return bool(lease and self._lease_is_stale(lease))

    def recover_stale(
        self,
        run_id: str,
        node_id: str,
        *,
        reason: str = "stale_recovered",
        secret_values: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        explicit_secrets = _normalize_secret_values(secret_values)
        recovered: list[dict[str, Any]] = []
        self.lease_dir.mkdir(parents=True, exist_ok=True)
        candidates = sorted(self.lease_dir.glob("*.json"))
        for path in candidates:
            observed = self._read_json(path)
            if not observed or not self._matches(observed, run_id, node_id):
                continue
            operator_id = str(observed.get("operator_id") or path.stem)
            with self._exclusive(run_id, node_id, operator_id) as claims_acquired:
                if not claims_acquired:
                    return self._blocked("lease_claim_busy", observed)
                lease = self._read_lease(operator_id)
                if not lease or not self._matches(lease, run_id, node_id):
                    continue
                if self._is_active(lease) and not self._lease_is_stale(lease):
                    return self._blocked("active_lease_not_recovered", lease)
                self._mark_recovered(
                    operator_id,
                    lease,
                    _safe_reason(reason, explicit_secrets),
                    explicit_secrets,
                )
                recovered.append(
                    _sanitize_metadata(
                        _sanitize_lease_record(lease, explicit_secrets),
                        explicit_secrets,
                    )
                )
        return {"recovered": bool(recovered), "leases": recovered}

    def _lease_is_stale(self, lease: dict[str, Any]) -> bool:
        if lease.get("corrupt"):
            return True
        if str(lease.get("state") or "").lower() in RECOVERABLE_STATES:
            return True
        expires_at = _parse_time(str(lease.get("expires_at") or ""))
        if expires_at and expires_at <= self._now():
            return True
        heartbeat_at = _parse_time(
            str(lease.get("heartbeat_at") or lease.get("leased_at") or "")
        )
        timeout = int(
            lease.get("heartbeat_timeout_seconds")
            or lease.get("heartbeat_timeout_sec")
            or 0
        )
        if heartbeat_at and timeout > 0:
            return (self._now() - heartbeat_at).total_seconds() > timeout
        return False

    def _active_for_run_node(self, run_id: str, node_id: str) -> dict[str, Any] | None:
        for path in sorted(self.lease_dir.glob("*.json")):
            lease = self._read_json(path)
            if lease and self._matches(lease, run_id, node_id) and self._is_active(lease):
                return lease
        return None

    @staticmethod
    def _is_active(lease: Mapping[str, Any]) -> bool:
        return str(lease.get("state") or "").lower() in ACTIVE_STATES

    @staticmethod
    def _matches(lease: Mapping[str, Any], run_id: str, node_id: str) -> bool:
        lease_run = str(
            lease.get("research_run_id")
            or lease.get("run_id")
            or lease.get("sprint_id")
            or ""
        )
        return lease_run == run_id and str(lease.get("node_id") or "") == node_id

    def _read_lease(self, operator_id: str) -> dict[str, Any] | None:
        current = self._lease_path(operator_id)
        lease = self._read_json(current)
        if lease is not None:
            return _sanitize_lease_record(lease)

        # c54a728a and earlier used a lossy sanitized filename.  Read and
        # migrate it only when the record identity exactly matches, so a
        # colliding identity can never consume another operator's lease.
        legacy = self.lease_dir / f"{_legacy_safe_name(operator_id)}.json"
        if legacy == current:
            return None
        lease = self._read_json(legacy)
        if lease and str(lease.get("operator_id") or "") == operator_id:
            lease = _sanitize_lease_record(lease)
            _atomic_write_json(current, lease)
            _unlink_if_exists(legacy)
            return lease
        return None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not _exists(path):
            return None
        try:
            data = json.loads(_read_text(path))
            return data if isinstance(data, dict) else None
        except Exception:
            return {"operator_id": path.stem, "state": "stale", "corrupt": True}

    def _write_lease(self, operator_id: str, lease: Mapping[str, Any]) -> None:
        _atomic_write_json(self._lease_path(operator_id), lease)

    def _write_compatible_status(
        self, operator_id: str, lease: Mapping[str, Any]
    ) -> None:
        status = {
            "operator_id": operator_id,
            "runtime_state": lease.get("state", "running"),
            "updated_at": lease.get("heartbeat_at"),
            "expires_at": lease.get("expires_at"),
        }
        _atomic_write_json(
            self.status_dir / f"{_identity_filename(operator_id)}.json", status
        )

    def _mark_recovered(
        self,
        operator_id: str,
        lease: dict[str, Any],
        reason: str,
        secret_values: Sequence[str] = (),
    ) -> None:
        lease = _sanitize_lease_record(lease, secret_values)
        lease["state"] = "stale"
        lease["recovered_at"] = _format_time(self._now())
        lease["recovery_reason"] = _safe_reason(reason, secret_values)
        self._archive_lease(operator_id, lease, secret_values)
        if self.operator_runtime is not None:
            self.operator_runtime.release_operator_lease(operator_id, reason)
        else:
            _unlink_if_exists(self._lease_path(operator_id))

    def _archive_lease(
        self,
        operator_id: str,
        lease: Mapping[str, Any],
        secret_values: Sequence[str] = (),
    ) -> None:
        archive_dir = self.lease_dir / "archive"
        lease_id = _identity_filename(str(lease.get("lease_id") or uuid.uuid4()))
        _atomic_write_json(
            archive_dir / f"{_identity_filename(operator_id)}-{lease_id}.json",
            _sanitize_metadata(
                _sanitize_lease_record(lease, secret_values), secret_values
            ),
        )

    def _lease_path(self, operator_id: str) -> Path:
        return self.lease_dir / f"{_identity_filename(operator_id)}.json"

    def _fallback_registry_blocker(
        self, run_id: str, node_id: str, operator_id: str
    ) -> dict[str, Any] | None:
        if self.operator_runtime is not None:
            return None
        if not _exists(self.operator_registry_path):
            return self._blocked(
                "operator_registry_missing",
                {"run_id": run_id, "node_id": node_id, "operator_id": operator_id},
            )
        try:
            registry = json.loads(_read_text(self.operator_registry_path))
            operators = registry["operators"]
            if not isinstance(operators, Mapping):
                raise ValueError("operators must be an object")
        except Exception:
            return self._blocked(
                "operator_registry_invalid",
                {"run_id": run_id, "node_id": node_id, "operator_id": operator_id},
            )
        config = operators.get(operator_id)
        if not isinstance(config, Mapping):
            return self._blocked(
                "operator_not_found",
                {"run_id": run_id, "node_id": node_id, "operator_id": operator_id},
            )
        if config.get("enabled", True) is False:
            return self._blocked(
                "operator_disabled",
                {
                    "run_id": run_id,
                    "node_id": node_id,
                    "operator_id": operator_id,
                    "state": "disabled",
                },
            )
        return None

    def _now(self) -> _dt.datetime:
        value = self.clock()
        if isinstance(value, (int, float)):
            return _dt.datetime.fromtimestamp(float(value), tz=_dt.timezone.utc)
        if isinstance(value, _dt.datetime):
            return value if value.tzinfo else value.replace(tzinfo=_dt.timezone.utc)
        raise ValueError("clock must return datetime or seconds")

    def _identity_blocker(
        self,
        lease: dict[str, Any],
        run_id: str,
        node_id: str,
        lease_id: str | None,
    ) -> dict[str, Any] | None:
        if not self._matches(lease, run_id, node_id):
            return self._blocked("lease_identity_mismatch", lease)
        if lease_id and lease.get("lease_id") != lease_id:
            return self._blocked("lease_id_mismatch", lease)
        return None

    def _blocked_from_native_exception(
        self, exc: Exception, run_id: str, node_id: str, operator_id: str
    ) -> dict[str, Any]:
        reason = str(getattr(exc, "reason", "") or "operator_lease_rejected")
        return self._blocked(
            _legacy_safe_name(reason),
            {
                "run_id": run_id,
                "node_id": node_id,
                "operator_id": operator_id,
                "state": str(getattr(exc, "state", "")),
            },
        )

    @staticmethod
    def _blocked(reason: str, lease: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "acquired": False,
            "ok": False,
            "blocker": {
                "type": "lease_conflict",
                "reason": reason,
                "run_id": str(
                    lease.get("research_run_id")
                    or lease.get("run_id")
                    or lease.get("sprint_id")
                    or ""
                ),
                "node_id": str(lease.get("node_id") or ""),
                "operator_id": str(lease.get("operator_id") or ""),
                "state": str(lease.get("state") or ""),
                "lease_id": str(lease.get("lease_id") or ""),
            },
        }

    @staticmethod
    def _validate_identity(run_id: str, node_id: str, operator_id: str) -> None:
        if not run_id or not node_id or not operator_id:
            raise ValueError("run_id, node_id, and operator_id are required")

    @contextmanager
    def _exclusive(
        self, run_id: str, node_id: str, operator_id: str
    ) -> Iterator[bool]:
        claims = sorted(
            [
                self._run_node_claim_path(run_id, node_id),
                self._operator_claim_path(operator_id),
            ],
            key=lambda path: str(path).casefold(),
        )
        with ExitStack() as stack:
            for claim in claims:
                acquired = stack.enter_context(self._claim(claim))
                if not acquired:
                    yield False
                    return
            yield True

    def _run_node_claim(self, run_id: str, node_id: str) -> Any:
        return self._claim(self._run_node_claim_path(run_id, node_id))

    def _operator_claim(self, operator_id: str) -> Any:
        return self._claim(self._operator_claim_path(operator_id))

    def _run_node_claim_path(self, run_id: str, node_id: str) -> Path:
        return self.lease_dir / (
            f".research-run-{_identity_filename(run_id)}-{_identity_filename(node_id)}.claim"
        )

    def _operator_claim_path(self, operator_id: str) -> Path:
        return self.lease_dir / (
            f".research-operator-{_identity_filename(operator_id)}.claim"
        )

    @contextmanager
    def _claim(self, claim_path: Path) -> Iterator[bool]:
        if os.name == "nt":
            with _windows_file_claim(
                claim_path,
                timeout_seconds=self.claim_timeout_seconds,
                abandoned_claim_seconds=self.abandoned_claim_seconds,
            ) as acquired:
                yield acquired
            return

        _mkdir(claim_path.parent)
        token = str(uuid.uuid4())
        deadline = time.monotonic() + self.claim_timeout_seconds
        while True:
            try:
                claim_path.mkdir()
            except FileExistsError:
                if _remove_abandoned_claim(
                    claim_path, self.abandoned_claim_seconds
                ):
                    continue
                if time.monotonic() >= deadline:
                    yield False
                    return
                time.sleep(0.01)
                continue
            owner = {
                "pid": os.getpid(),
                "process_identity": _process_identity(os.getpid()),
                "token": token,
                "created_at_epoch": time.time(),
            }
            _atomic_write_json(claim_path / "owner.json", owner)
            break
        try:
            yield True
        finally:
            owner = self._read_json(claim_path / "owner.json")
            if owner and owner.get("token") == token:
                _remove_claim_owned(claim_path, token)


def _load_matching_operator_runtime(harness_root: Path) -> Any | None:
    """Load the canonical API only when it already targets this harness root."""

    try:
        module = importlib.import_module("operator_runtime")
    except (ImportError, ModuleNotFoundError):
        return None
    try:
        configured = Path(module.HARNESS_DIR).resolve()
    except Exception:
        return None
    return module if configured == harness_root else None


def _fs_path(path: Path) -> str:
    resolved = str(Path(path).resolve(strict=False))
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved


def _mkdir(path: Path) -> None:
    os.makedirs(_fs_path(path), exist_ok=True)


def _exists(path: Path) -> bool:
    return os.path.exists(_fs_path(path))


def _read_text(path: Path) -> str:
    with open(_fs_path(path), "r", encoding="utf-8") as handle:
        return handle.read()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _mkdir(path.parent)
    fd, raw_tmp = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=_fs_path(path.parent)
    )
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(_fs_path(tmp), _fs_path(path))
    finally:
        _unlink_if_exists(tmp)


@contextmanager
def _windows_file_claim(
    legacy_claim_path: Path,
    *,
    timeout_seconds: float,
    abandoned_claim_seconds: float,
) -> Iterator[bool]:
    """Use a kernel-managed byte-range lock; Windows releases it on process exit."""

    import msvcrt

    deadline = time.monotonic() + timeout_seconds
    _mkdir(legacy_claim_path.parent)
    while _exists(legacy_claim_path):
        if _remove_abandoned_claim(legacy_claim_path, abandoned_claim_seconds):
            continue
        if time.monotonic() >= deadline:
            yield False
            return
        time.sleep(0.01)

    lock_path = legacy_claim_path.with_name(f"{legacy_claim_path.name}.lock")
    handle = open(_fs_path(lock_path), "a+b", buffering=0)
    acquired = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
        while True:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    yield False
                    return
                time.sleep(0.01)
        yield True
    finally:
        if acquired:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        handle.close()


def _read_claim_owner(path: Path) -> dict[str, Any] | None:
    try:
        owner = json.loads(_read_text(path / "owner.json"))
    except Exception:
        return None
    return owner if isinstance(owner, dict) else None


def _claim_owner_is_abandoned(owner: Mapping[str, Any], stale_seconds: float) -> bool:
    pid = owner.get("pid") if isinstance(owner, dict) else None
    expected_identity = str(owner.get("process_identity") or "") if isinstance(owner, dict) else ""
    try:
        created_at = float(owner.get("created_at_epoch", 0.0))
    except (TypeError, ValueError, AttributeError):
        created_at = 0.0
    if isinstance(pid, int) and pid > 0:
        if not _pid_exists(pid):
            return True
        current_identity = _process_identity(pid)
        if expected_identity and current_identity:
            return current_identity != expected_identity
        return False
    return created_at > 0 and time.time() - created_at >= stale_seconds


def _remove_abandoned_claim(path: Path, stale_seconds: float) -> bool:
    owner = _read_claim_owner(path)
    if owner is None:
        try:
            if time.time() - os.stat(_fs_path(path)).st_mtime < stale_seconds:
                return False
            # Ownerless compatibility claims are removed only when empty.  If
            # an owner appears concurrently, rmdir fails instead of stealing.
            os.rmdir(_fs_path(path))
            return True
        except (FileNotFoundError, OSError):
            return False
    if not _claim_owner_is_abandoned(owner, stale_seconds):
        return False
    token = str(owner.get("token") or "")
    if not token:
        return False

    quarantine = path.with_name(f"{path.name}.reap-{uuid.uuid4().hex}")
    try:
        os.replace(_fs_path(path), _fs_path(quarantine))
    except (FileNotFoundError, OSError):
        return False
    moved_owner = _read_claim_owner(quarantine)
    if moved_owner is None or str(moved_owner.get("token") or "") != token:
        try:
            if not _exists(path):
                os.replace(_fs_path(quarantine), _fs_path(path))
        except OSError:
            pass
        return False
    try:
        shutil.rmtree(_fs_path(quarantine))
        return True
    except (FileNotFoundError, OSError):
        return False


def _process_identity(pid: int) -> str:
    """Return a PID-reuse-resistant process birth marker when the OS exposes one."""

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return ""
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        try:
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return ""
            value = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
            return f"windows-filetime:{value}"
        finally:
            kernel32.CloseHandle(handle)
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        # Field 22 is process start time.  Split after the final ')' because
        # process names may contain spaces and parentheses.
        tail = stat_path.read_text(encoding="utf-8").rsplit(")", 1)[1].split()
        return f"proc-start:{tail[19]}"
    except Exception:
        return ""


def _remove_claim_owned(path: Path, token: str) -> bool:
    """Best-effort Windows-safe cleanup that never removes another owner's claim."""

    for _attempt in range(20):
        try:
            owner = json.loads(_read_text(path / "owner.json"))
        except FileNotFoundError:
            return not _exists(path)
        except Exception:
            return False
        if not isinstance(owner, Mapping) or owner.get("token") != token:
            return False
        try:
            shutil.rmtree(_fs_path(path))
            return True
        except FileNotFoundError:
            return True
        except OSError:
            time.sleep(0.01)
    return False


def _pid_exists(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if os.name == "nt":
        # ``os.kill(pid, 0)`` is not a harmless existence probe on Windows:
        # signal 0 is CTRL_C_EVENT and can interrupt the whole console group.
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if handle:
            exit_code = wintypes.DWORD()
            try:
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    # A successful OpenProcess already proves that this PID is
                    # owned. Fail closed if its state cannot be queried.
                    return True
                return int(exit_code.value) == still_active
            finally:
                kernel32.CloseHandle(handle)
        # Access denied still proves that a process owns the PID.
        return ctypes.get_last_error() == 5
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _sanitize_lease_record(
    lease: Mapping[str, Any], secret_values: Sequence[str] = ()
) -> dict[str, Any]:
    cleaned = dict(lease)
    metadata = cleaned.get("research_metadata")
    if not isinstance(metadata, Mapping):
        cleaned.pop("research_metadata", None)
        cleaned.pop("research_metadata_policy", None)
        return cleaned
    policy = str(cleaned.get("research_metadata_policy") or "")
    explicit_fields: list[str] = []
    if policy == "explicit_safe_scalars.v1":
        allowed = _SAFE_TEXT_METADATA_FIELDS | _SAFE_NUMERIC_METADATA_FIELDS
        explicit_fields = [str(key) for key in metadata if str(key) in allowed]
    sanitized = _sanitize_research_metadata(
        metadata,
        secret_values,
        safe_metadata_fields=explicit_fields,
    )
    if sanitized:
        cleaned["research_metadata"] = sanitized
        cleaned["research_metadata_policy"] = "explicit_safe_scalars.v1"
    else:
        cleaned.pop("research_metadata", None)
        cleaned.pop("research_metadata_policy", None)
    return cleaned


def _sanitize_research_metadata(
    metadata: Mapping[str, Any],
    secret_values: Sequence[str],
    *,
    safe_metadata_fields: Sequence[str] | None,
) -> dict[str, Any]:
    """Persist only documented scalar telemetry or explicitly safe text fields.

    Free-form nested structures are intentionally omitted.  Text fields must
    be named in ``safe_metadata_fields`` and still pass credential/value
    scrubbing; callers should use ``secret_values`` for opaque provider values.
    """

    explicit: set[str] = set()
    if safe_metadata_fields is not None:
        if isinstance(safe_metadata_fields, (str, bytes, bytearray)):
            raise ValueError("safe_metadata_fields must be a sequence of field names")
        for field in safe_metadata_fields:
            if not isinstance(field, str) or not field:
                raise ValueError("safe_metadata_fields must contain non-empty strings")
            if field not in _SAFE_TEXT_METADATA_FIELDS | _SAFE_NUMERIC_METADATA_FIELDS:
                raise ValueError(f"unsupported safe metadata field: {field}")
            explicit.add(field)

    cleaned: dict[str, Any] = {}
    for raw_key, raw_value in metadata.items():
        key = str(raw_key)
        if _is_sensitive_key(key):
            continue
        if (
            key in _SAFE_NUMERIC_METADATA_FIELDS
            and isinstance(raw_value, (int, float))
            and not isinstance(raw_value, bool)
        ):
            cleaned[key] = raw_value
            continue
        if key not in explicit or isinstance(raw_value, (Mapping, list, tuple, set, frozenset)):
            continue
        if raw_value is None or isinstance(raw_value, (str, bool, int, float)):
            cleaned[key] = _sanitize_metadata(raw_value, secret_values)
    return cleaned


def _sanitize_metadata(value: Any, secret_values: Sequence[str] = ()) -> Any:
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                continue
            cleaned[key] = _sanitize_metadata(raw_value, secret_values)
        return cleaned
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize_metadata(item, secret_values) for item in value]
    if isinstance(value, str):
        cleaned = value
        for secret in sorted(secret_values, key=len, reverse=True):
            cleaned = cleaned.replace(secret, "[REDACTED]")
        return _CREDENTIAL_VALUE.sub("[REDACTED]", cleaned)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _safe_reason(reason: str, secret_values: Sequence[str] = ()) -> str:
    return str(_sanitize_metadata(str(reason), secret_values))[:200]


def _is_sensitive_key(key: str) -> bool:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    tokens = [part for part in re.split(r"[^A-Za-z0-9]+", separated.casefold()) if part]
    if any(
        token in {"authorization", "credential", "credentials", "password", "passwd", "secret"}
        for token in tokens
    ):
        return True
    if any(left == "api" and right == "key" for left, right in zip(tokens, tokens[1:])):
        return True
    if tokens == ["token"]:
        return True
    if "token" not in tokens:
        return False
    token_context = set(tokens)
    noncredential_token_words = {
        "token",
        "budget",
        "count",
        "limit",
        "input",
        "output",
        "usage",
        "max",
        "total",
        "estimated",
    }
    return not token_context <= noncredential_token_words


def _normalize_secret_values(values: Sequence[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes, bytearray)):
        raise ValueError("secret_values must be a sequence of strings")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("secret_values must contain strings")
        if value:
            normalized.append(value)
    return tuple(dict.fromkeys(normalized))


def _legacy_safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()) or "unknown"


def _identity_filename(value: str) -> str:
    raw = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]+", raw) and raw not in {".", ".."} and len(raw) <= 96:
        return raw
    prefix = _legacy_safe_name(raw).strip(".-")[:48] or "identity"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}--{digest}"


def _unlink_if_exists(path: Path) -> bool:
    try:
        os.unlink(_fs_path(path))
        return True
    except FileNotFoundError:
        return False


def _format_time(value: _dt.datetime) -> str:
    return value.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: str) -> _dt.datetime | None:
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            _dt.timezone.utc
        )
    except Exception:
        return None
