"""Research-node lease adapter over the existing operator runtime lease store.

The native ``operator_runtime`` functions are used when they are importable and
point at the requested harness root.  Windows cannot currently import that
module because it depends on ``fcntl``; in that case this module writes the
same core lease fields under the same store while protecting them with a
portable, process-safe atomic-directory claim.

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
            operator_runtime_api
            if operator_runtime_api is not None
            else _load_matching_operator_runtime(self.harness_root)
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
        recover_stale: bool = False,
    ) -> dict[str, Any]:
        self._validate_identity(run_id, node_id, operator_id)
        self.lease_dir.mkdir(parents=True, exist_ok=True)

        with self._exclusive(run_id, node_id, operator_id):
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
                cleaned = _sanitize_metadata(metadata, explicit_secrets)
                if cleaned:
                    extension["research_metadata"] = cleaned

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
        with self._exclusive(run_id, node_id, operator_id):
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
                lease = self.operator_runtime.update_operator_lease_metadata(
                    operator_id, **updates
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
        with self._exclusive(run_id, node_id, operator_id):
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
            with self._exclusive(run_id, node_id, operator_id):
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
                recovered.append(_sanitize_metadata(lease, explicit_secrets))
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
            return lease

        # c54a728a and earlier used a lossy sanitized filename.  Read and
        # migrate it only when the record identity exactly matches, so a
        # colliding identity can never consume another operator's lease.
        legacy = self.lease_dir / f"{_legacy_safe_name(operator_id)}.json"
        if legacy == current:
            return None
        lease = self._read_json(legacy)
        if lease and str(lease.get("operator_id") or "") == operator_id:
            _atomic_write_json(current, lease)
            _unlink_if_exists(legacy)
            return lease
        return None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
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
            _sanitize_metadata(lease, secret_values),
        )

    def _lease_path(self, operator_id: str) -> Path:
        return self.lease_dir / f"{_identity_filename(operator_id)}.json"

    def _fallback_registry_blocker(
        self, run_id: str, node_id: str, operator_id: str
    ) -> dict[str, Any] | None:
        if self.operator_runtime is not None or not self.operator_registry_path.exists():
            return None
        try:
            registry = json.loads(
                self.operator_registry_path.read_text(encoding="utf-8")
            )
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
    ) -> Iterator[None]:
        claims = sorted(
            [
                self._run_node_claim_path(run_id, node_id),
                self._operator_claim_path(operator_id),
            ],
            key=lambda path: str(path).casefold(),
        )
        with ExitStack() as stack:
            for claim in claims:
                stack.enter_context(self._claim(claim))
            yield

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
    def _claim(self, claim_path: Path) -> Iterator[None]:
        claim_path.parent.mkdir(parents=True, exist_ok=True)
        token = str(uuid.uuid4())
        deadline = time.monotonic() + self.claim_timeout_seconds
        while True:
            try:
                claim_path.mkdir()
            except FileExistsError:
                if _claim_is_abandoned(claim_path, self.abandoned_claim_seconds):
                    try:
                        shutil.rmtree(claim_path)
                    except (FileNotFoundError, OSError):
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out acquiring runtime claim: {claim_path.name}")
                time.sleep(0.01)
                continue
            owner = {
                "pid": os.getpid(),
                "token": token,
                "created_at_epoch": time.time(),
            }
            _atomic_write_json(claim_path / "owner.json", owner)
            break
        try:
            yield
        finally:
            owner = self._read_json(claim_path / "owner.json")
            if owner and owner.get("token") == token:
                try:
                    shutil.rmtree(claim_path)
                except FileNotFoundError:
                    pass


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


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _claim_is_abandoned(path: Path, stale_seconds: float) -> bool:
    try:
        owner = json.loads((path / "owner.json").read_text(encoding="utf-8"))
    except Exception:
        try:
            return time.time() - path.stat().st_mtime >= stale_seconds
        except FileNotFoundError:
            return False
    pid = owner.get("pid") if isinstance(owner, dict) else None
    try:
        created_at = float(owner.get("created_at_epoch", 0.0))
    except (TypeError, ValueError, AttributeError):
        created_at = 0.0
    if isinstance(pid, int) and pid > 0:
        return not _pid_exists(pid)
    return created_at > 0 and time.time() - created_at >= stale_seconds


def _pid_exists(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if os.name == "nt":
        # ``os.kill(pid, 0)`` is not a harmless existence probe on Windows:
        # signal 0 is CTRL_C_EVENT and can interrupt the whole console group.
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
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
        path.unlink()
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
