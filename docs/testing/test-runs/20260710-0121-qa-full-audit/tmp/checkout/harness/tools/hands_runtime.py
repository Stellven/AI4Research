"""Solar Harness — Hands Runtime.

Disposable execution runtime adapters: mock, shell, pane, remote.
All adapters implement the HandRuntime protocol from runtime_interfaces.py.

Every execute() takes an idempotency_key — repeating the same key
will not duplicate side effects.
"""
from __future__ import annotations

import json
import os
import re
import hashlib
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
SANDBOX_ROOT = Path(HARNESS_DIR) / "run" / "hands-sandbox"
EVIDENCE_ROOT = Path(HARNESS_DIR) / "reports" / "hands-sandbox-evidence"

# Import interfaces for type hints
sys.path.insert(0, os.path.dirname(__file__))
from runtime_interfaces import (
    CapabilityPolicy,
    CommandEnvelope,
    HandRef,
    HandType,
    ResultEnvelope,
    ResultStatus,
)
from activity_runtime import ActivityRuntime

# Shell deny-list: commands that must never be executed
_SHELL_DENYLIST = frozenset({
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=/dev/zero",
    "chmod -R 777 /", "shutdown", "reboot", "halt",
    ":(){ :|:& };:", "fork bomb",
})

_SHELL_DESTRUCTIVE_PATTERN = re.compile(
    r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\s*$|"
    r"chmod\s+(-R\s+)?[0-7]{3,4}\s+/\s*$|"
    r"mkfs|dd\s+if=|shutdown|reboot|halt",
    re.IGNORECASE,
)


def _activity_id(hand_ref: HandRef, command_name: str, idempotency_key: str) -> str:
    safe_key = re.sub(r"[^A-Za-z0-9_.:-]+", "-", idempotency_key)[-80:]
    safe_cmd = re.sub(r"[^A-Za-z0-9_.:-]+", "-", command_name)[:40]
    return f"{hand_ref.hand_id}:{safe_cmd}:{safe_key}"


def _record_activity_start(
    hand_ref: HandRef,
    command_name: str,
    input_data: Dict[str, Any],
    idempotency_key: str,
) -> Optional[tuple[ActivityRuntime, str]]:
    """Best-effort command_issued/activity_started event emission."""
    try:
        session_id = str(input_data.get("session_id") or input_data.get("_session_id") or f"hand-{hand_ref.hand_id}")
        sprint_id = str(input_data.get("sprint_id") or input_data.get("_sprint_id") or session_id)
        act_id = str(input_data.get("activity_id") or input_data.get("_activity_id") or _activity_id(hand_ref, command_name, idempotency_key))
        rt = ActivityRuntime(sprint_id=sprint_id, session_id=session_id)
        rt.command_issued(
            act_id,
            actor="hand-runtime",
            target=hand_ref.hand_type.value,
            payload={
                "command_name": command_name,
                "hand_id": hand_ref.hand_id,
                "hand_type": hand_ref.hand_type.value,
                "idempotency_key": idempotency_key,
            },
        )
        rt.activity_started(
            act_id,
            actor=f"hand:{hand_ref.hand_type.value}",
            payload={"hand_id": hand_ref.hand_id, "command_name": command_name},
        )
        return rt, act_id
    except Exception:
        return None


def _record_activity_terminal(
    ctx: Optional[tuple[ActivityRuntime, str]],
    result: ResultEnvelope,
) -> ResultEnvelope:
    if ctx is None:
        return result
    rt, act_id = ctx
    try:
        payload = {
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "side_effects": result.side_effects,
            "metadata": result.metadata,
        }
        if result.status == ResultStatus.OK:
            rt.activity_succeeded(act_id, actor="hand-runtime", payload=payload)
        elif result.status == ResultStatus.CANCELLED:
            rt.activity_cancelled(act_id, actor="hand-runtime", reason=result.error or "cancelled", payload=payload)
        elif result.status != ResultStatus.DUPLICATE_SUPPRESSED:
            rt.activity_failed(act_id, actor="hand-runtime", error=result.error or payload["status"], payload=payload)
    except Exception:
        pass
    return result


class MockHand:
    """In-memory mock hand for testing. No real side effects."""

    def __init__(self, policy: Optional[CapabilityPolicy] = None) -> None:
        self._seen_keys: set[str] = set()
        self._provisioned: List[HandRef] = []
        self._disposed: List[str] = []
        self.policy = policy or CapabilityPolicy()

    def provision(
        self,
        *,
        capabilities: Optional[List[str]] = None,
        location: Optional[str] = None,
    ) -> HandRef:
        from uuid import uuid4
        ref = HandRef(
            hand_id=f"mock-{uuid4().hex[:8]}",
            hand_type=HandType.MOCK,
            provisioned_at=_now_ts(),
            capabilities=capabilities or [],
            location=location or "memory",
        )
        self._provisioned.append(ref)
        return ref

    def execute(
        self,
        hand_ref: HandRef,
        command_name: str,
        input_data: Dict[str, Any],
        *,
        idempotency_key: str,
        timeout_seconds: Optional[int] = None,
    ) -> ResultEnvelope:
        if idempotency_key in self._seen_keys:
            return ResultEnvelope(
                status=ResultStatus.DUPLICATE_SUPPRESSED,
                output={"message": "duplicate suppressed"},
                metadata={"hand_id": hand_ref.hand_id},
            )
        self._seen_keys.add(idempotency_key)
        activity_ctx = _record_activity_start(hand_ref, command_name, input_data, idempotency_key)
        return _record_activity_terminal(activity_ctx, ResultEnvelope(
            status=ResultStatus.OK,
            output={"command": command_name, "input": input_data, "mock": True},
            side_effects=[f"mock:{command_name}"],
            metadata={"hand_id": hand_ref.hand_id},
        ))

    def dispose(self, hand_ref: HandRef, *, reason: str = "completed") -> ResultEnvelope:
        self._disposed.append(hand_ref.hand_id)
        return ResultEnvelope(
            status=ResultStatus.OK,
            output={"disposed": hand_ref.hand_id, "reason": reason},
            metadata={"hand_id": hand_ref.hand_id},
        )


class ShellHand:
    """Local subprocess hand. Executes safe commands only."""

    def __init__(self, policy: Optional[CapabilityPolicy] = None) -> None:
        self._seen_keys: set[str] = set()
        self._provisioned: List[HandRef] = []
        self._disposed: List[str] = []
        self.policy = policy or CapabilityPolicy()

    def provision(
        self,
        *,
        capabilities: Optional[List[str]] = None,
        location: Optional[str] = None,
    ) -> HandRef:
        from uuid import uuid4
        ref = HandRef(
            hand_id=f"shell-{uuid4().hex[:8]}",
            hand_type=HandType.SHELL,
            provisioned_at=_now_ts(),
            capabilities=capabilities or [],
            location=location or "local",
        )
        self._provisioned.append(ref)
        return ref

    def execute(
        self,
        hand_ref: HandRef,
        command_name: str,
        input_data: Dict[str, Any],
        *,
        idempotency_key: str,
        timeout_seconds: Optional[int] = None,
    ) -> ResultEnvelope:
        if idempotency_key in self._seen_keys:
            return ResultEnvelope(
                status=ResultStatus.DUPLICATE_SUPPRESSED,
                output={"message": "duplicate suppressed"},
                metadata={"hand_id": hand_ref.hand_id},
            )
        self._seen_keys.add(idempotency_key)
        activity_ctx = _record_activity_start(hand_ref, command_name, input_data, idempotency_key)

        cmd = input_data.get("command", "")
        if self._is_denied(cmd):
            return _record_activity_terminal(activity_ctx, ResultEnvelope(
                status=ResultStatus.ERROR,
                error=f"command denied by policy: {cmd[:80]}",
                metadata={"hand_id": hand_ref.hand_id},
            ))

        timeout = timeout_seconds or self.policy.max_duration_seconds
        try:
            t0 = time.monotonic()
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=min(timeout, 60),
            )
            elapsed_ms = (time.monotonic() - t0) * 1000
            if result.returncode != 0:
                return _record_activity_terminal(activity_ctx, ResultEnvelope(
                    status=ResultStatus.ERROR,
                    error=result.stderr.strip() or f"exit code {result.returncode}",
                    duration_ms=round(elapsed_ms, 1),
                    side_effects=[f"shell:{command_name}"],
                    metadata={"hand_id": hand_ref.hand_id},
                ))
            output = result.stdout.strip()
            redacted = self._redact_secrets(output)
            return _record_activity_terminal(activity_ctx, ResultEnvelope(
                status=ResultStatus.OK,
                output=redacted,
                duration_ms=round(elapsed_ms, 1),
                side_effects=[f"shell:{command_name}"],
                redacted_secrets=self._find_secrets(output),
                metadata={"hand_id": hand_ref.hand_id},
            ))
        except subprocess.TimeoutExpired:
            return _record_activity_terminal(activity_ctx, ResultEnvelope(
                status=ResultStatus.TIMEOUT,
                error=f"command timed out after {timeout}s",
                side_effects=[f"shell:{command_name}"],
                metadata={"hand_id": hand_ref.hand_id},
            ))

    def dispose(self, hand_ref: HandRef, *, reason: str = "completed") -> ResultEnvelope:
        self._disposed.append(hand_ref.hand_id)
        return ResultEnvelope(
            status=ResultStatus.OK,
            output={"disposed": hand_ref.hand_id, "reason": reason},
            metadata={"hand_id": hand_ref.hand_id},
        )

    def _is_denied(self, cmd: str) -> bool:
        for denied in self.policy.denied_commands:
            if denied in cmd:
                return True
        if _SHELL_DESTRUCTIVE_PATTERN.search(cmd):
            return True
        return False

    def _redact_secrets(self, text: str) -> str:
        redacted = text
        for pattern in self.policy.secret_patterns:
            redacted = re.sub(pattern, "[REDACTED]", redacted, flags=re.IGNORECASE)
        return redacted

    def _find_secrets(self, text: str) -> List[str]:
        found = []
        for pattern in self.policy.secret_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            found.extend(matches)
        return list(set(found))


class SandboxHand:
    """Disposable local sandbox hand.

    Each provision gets a private workspace and HOME.  Execute runs with an
    explicit env allowlist plus optional secret_refs.  Evidence is collected
    outside the workspace before dispose removes the workspace.
    """

    BASE_ENV_ALLOW = ("PATH", "LANG", "LC_ALL")

    def __init__(self, policy: Optional[CapabilityPolicy] = None) -> None:
        self._seen_keys: set[str] = set()
        self._provisioned: Dict[str, HandRef] = {}
        self._disposed: List[str] = []
        self.policy = policy or CapabilityPolicy()

    def provision(
        self,
        *,
        capabilities: Optional[List[str]] = None,
        location: Optional[str] = None,
    ) -> HandRef:
        from uuid import uuid4
        hand_id = f"sandbox-{uuid4().hex[:8]}"
        base = Path(location) if location else SANDBOX_ROOT / hand_id
        workspace = base / "workspace"
        home = base / "home"
        evidence_dir = EVIDENCE_ROOT / hand_id
        workspace.mkdir(parents=True, exist_ok=True)
        home.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        ref = HandRef(
            hand_id=hand_id,
            hand_type=HandType.SANDBOX,
            provisioned_at=_now_ts(),
            capabilities=capabilities or [],
            location=str(workspace),
            metadata={
                "sandbox_root": str(base),
                "workspace": str(workspace),
                "home": str(home),
                "evidence_dir": str(evidence_dir),
                "disposable": True,
            },
        )
        self._provisioned[hand_id] = ref
        return ref

    def execute(
        self,
        hand_ref: HandRef,
        command_name: str,
        input_data: Dict[str, Any],
        *,
        idempotency_key: str,
        timeout_seconds: Optional[int] = None,
    ) -> ResultEnvelope:
        if idempotency_key in self._seen_keys:
            return ResultEnvelope(
                status=ResultStatus.DUPLICATE_SUPPRESSED,
                output={"message": "duplicate suppressed"},
                metadata={"hand_id": hand_ref.hand_id},
            )
        self._seen_keys.add(idempotency_key)
        activity_ctx = _record_activity_start(hand_ref, command_name, input_data, idempotency_key)

        command_display, popen_args, shell_mode = self._command_invocation(input_data)
        if self._is_denied(command_display):
            result = ResultEnvelope(
                status=ResultStatus.ERROR,
                error=f"command denied by policy: {command_display[:80]}",
                metadata={"hand_id": hand_ref.hand_id, "sandbox": hand_ref.metadata},
            )
            self._write_evidence(
                hand_ref,
                command_name,
                input_data,
                result,
                env_allow=[],
                secret_names=[],
                secret_values=[],
                execution_mode="shell" if shell_mode else "argv",
                command_display=command_display,
                write_guard={},
            )
            return _record_activity_terminal(activity_ctx, result)

        env, env_allow, secret_names, secret_values = self._build_env(hand_ref, input_data)
        write_guard = self._prepare_write_guard(hand_ref, input_data)
        before_guard = self._snapshot_write_guard(write_guard)
        timeout = timeout_seconds or self.policy.max_duration_seconds
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                popen_args,
                shell=shell_mode,
                cwd=hand_ref.location or None,
                env=env,
                text=True,
                capture_output=True,
                timeout=min(timeout, 120),
            )
            elapsed_ms = (time.monotonic() - t0) * 1000
            stdout = self._redact(proc.stdout or "", secret_values)
            stderr = self._redact(proc.stderr or "", secret_values)
            if proc.returncode == 0:
                status = ResultStatus.OK
                error = None
            else:
                status = ResultStatus.ERROR
                error = stderr.strip() or f"exit code {proc.returncode}"
            after_guard = self._snapshot_write_guard(write_guard)
            guard_violations = self._write_guard_violations(before_guard, after_guard)
            if guard_violations:
                status = ResultStatus.ERROR
                error = "write guard violation outside sandbox workspace"
            result = ResultEnvelope(
                status=status,
                output=stdout.strip(),
                error=error,
                duration_ms=round(elapsed_ms, 1),
                side_effects=[f"sandbox:{hand_ref.hand_id}:{command_name}"],
                redacted_secrets=secret_names,
                metadata={
                    "hand_id": hand_ref.hand_id,
                    "sandbox": hand_ref.metadata,
                    "env_allow": env_allow,
                    "secret_names": secret_names,
                    "stderr": stderr.strip()[:4000],
                    "execution_mode": "shell" if shell_mode else "argv",
                    "write_guard": {
                        "enabled": bool(write_guard),
                        "violations": guard_violations[:20],
                    },
                },
            )
            self._write_evidence(
                hand_ref,
                command_name,
                input_data,
                result,
                env_allow=env_allow,
                secret_names=secret_names,
                secret_values=secret_values,
                execution_mode="shell" if shell_mode else "argv",
                command_display=command_display,
                write_guard={
                    "enabled": bool(write_guard),
                    "roots": [str(p) for p in write_guard.get("roots", [])],
                    "allowed_roots": [str(p) for p in write_guard.get("allowed_roots", [])],
                    "violations": guard_violations[:50],
                },
            )
            return _record_activity_terminal(activity_ctx, result)
        except subprocess.TimeoutExpired:
            result = ResultEnvelope(
                status=ResultStatus.TIMEOUT,
                error=f"command timed out after {timeout}s",
                side_effects=[f"sandbox:{hand_ref.hand_id}:{command_name}"],
                metadata={"hand_id": hand_ref.hand_id, "sandbox": hand_ref.metadata, "env_allow": env_allow, "secret_names": secret_names},
            )
            self._write_evidence(
                hand_ref,
                command_name,
                input_data,
                result,
                env_allow=env_allow,
                secret_names=secret_names,
                secret_values=secret_values,
                execution_mode="shell" if shell_mode else "argv",
                command_display=command_display,
                write_guard={
                    "enabled": bool(write_guard),
                    "roots": [str(p) for p in write_guard.get("roots", [])],
                    "allowed_roots": [str(p) for p in write_guard.get("allowed_roots", [])],
                    "violations": [],
                },
            )
            return _record_activity_terminal(activity_ctx, result)

    def dispose(self, hand_ref: HandRef, *, reason: str = "completed") -> ResultEnvelope:
        self._disposed.append(hand_ref.hand_id)
        root = hand_ref.metadata.get("sandbox_root", "")
        removed = False
        if root:
            shutil.rmtree(root, ignore_errors=True)
            removed = not Path(root).exists()
        return ResultEnvelope(
            status=ResultStatus.OK,
            output={"disposed": hand_ref.hand_id, "reason": reason, "workspace_removed": removed},
            metadata={
                "hand_id": hand_ref.hand_id,
                "sandbox_root": root,
                "evidence_dir": hand_ref.metadata.get("evidence_dir", ""),
            },
        )

    def collect_evidence(self, hand_ref: HandRef) -> Dict[str, Any]:
        workspace = Path(hand_ref.metadata.get("workspace") or hand_ref.location or "")
        files = []
        if workspace.exists():
            for path in sorted(p for p in workspace.rglob("*") if p.is_file())[:500]:
                try:
                    data = path.read_bytes()
                    files.append({
                        "path": str(path.relative_to(workspace)),
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    })
                except OSError:
                    continue
        return {
            "hand_id": hand_ref.hand_id,
            "workspace": str(workspace),
            "files": files,
            "file_count": len(files),
            "collected_at": _now_ts(),
        }

    def _build_env(self, hand_ref: HandRef, input_data: Dict[str, Any]) -> tuple[Dict[str, str], List[str], List[str], List[str]]:
        env: Dict[str, str] = {}
        for key in self.BASE_ENV_ALLOW:
            if key in os.environ:
                env[key] = os.environ[key]
        env["HOME"] = str(hand_ref.metadata.get("home") or Path(hand_ref.location or ".") / ".home")
        env["TMPDIR"] = str(Path(hand_ref.location or ".") / ".tmp")
        env["SOLAR_SANDBOX"] = "1"
        Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)

        env_allow = []
        for key in input_data.get("env_allow", []) or []:
            key_s = str(key)
            if not re.match(r"^[A-Z_][A-Z0-9_]*$", key_s):
                continue
            if re.search(r"(TOKEN|SECRET|PASSWORD|CREDENTIAL|API[_-]?KEY|ACCESS[_-]?KEY)", key_s, re.IGNORECASE):
                continue
            if key_s in os.environ:
                env[key_s] = os.environ[key_s]
                env_allow.append(key_s)

        secret_names = []
        secret_values = []
        secret_refs = input_data.get("secret_refs", {}) or {}
        if isinstance(secret_refs, dict):
            for out_name, ref in secret_refs.items():
                out = str(out_name)
                if not re.match(r"^[A-Z_][A-Z0-9_]*$", out):
                    continue
                value = self._resolve_secret_ref(str(ref))
                if value is None:
                    continue
                env[out] = value
                secret_names.append(out)
                secret_values.append(value)
        return env, env_allow, secret_names, secret_values

    def _command_invocation(self, input_data: Dict[str, Any]) -> tuple[str, Any, bool]:
        argv = input_data.get("argv")
        if isinstance(argv, list) and argv:
            args = [str(item) for item in argv]
            return " ".join(shlex.quote(item) for item in args), args, False
        cmd = str(input_data.get("command", ""))
        return cmd, cmd, True

    def _prepare_write_guard(self, hand_ref: HandRef, input_data: Dict[str, Any]) -> Dict[str, Any]:
        roots_raw = input_data.get("write_guard_roots", []) or []
        if isinstance(roots_raw, str):
            roots_raw = [roots_raw]
        roots = []
        for raw in roots_raw:
            try:
                roots.append(Path(str(raw)).expanduser().resolve())
            except OSError:
                continue
        if not roots:
            return {}
        workspace = Path(hand_ref.metadata.get("workspace") or hand_ref.location or "").resolve()
        home = Path(hand_ref.metadata.get("home") or workspace / ".home").resolve()
        allowed_raw = input_data.get("write_allowed_roots", []) or []
        if isinstance(allowed_raw, str):
            allowed_raw = [allowed_raw]
        allowed = [workspace, home]
        for raw in allowed_raw:
            try:
                allowed.append(Path(str(raw)).expanduser().resolve())
            except OSError:
                continue
        return {"roots": roots, "allowed_roots": allowed}

    def _snapshot_write_guard(self, guard: Dict[str, Any]) -> Dict[str, tuple[int, int]]:
        if not guard:
            return {}
        roots = guard.get("roots", [])
        allowed_roots = guard.get("allowed_roots", [])
        snapshot: Dict[str, tuple[int, int]] = {}
        for root in roots:
            if not root.exists():
                continue
            paths = [root] if root.is_file() else sorted(root.rglob("*"))
            for path in paths:
                try:
                    resolved = path.resolve()
                    if any(self._is_relative_to(resolved, allowed) for allowed in allowed_roots):
                        continue
                    if not resolved.is_file():
                        continue
                    st = resolved.stat()
                    snapshot[str(resolved)] = (int(st.st_mtime_ns), int(st.st_size))
                except OSError:
                    continue
        return snapshot

    def _write_guard_violations(self, before: Dict[str, tuple[int, int]], after: Dict[str, tuple[int, int]]) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []
        before_keys = set(before)
        after_keys = set(after)
        for path in sorted(after_keys - before_keys):
            violations.append({"path": path, "type": "created"})
        for path in sorted(before_keys - after_keys):
            violations.append({"path": path, "type": "deleted"})
        for path in sorted(before_keys & after_keys):
            if before[path] != after[path]:
                violations.append({"path": path, "type": "modified"})
        return violations

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _resolve_secret_ref(self, ref: str) -> Optional[str]:
        if ref.startswith("env:"):
            return os.environ.get(ref.split(":", 1)[1])
        if ref.startswith("file:"):
            path = Path(ref.split(":", 1)[1]).expanduser()
            secrets_root = Path(HARNESS_DIR) / "secrets"
            try:
                resolved = path.resolve()
                if secrets_root.resolve() not in resolved.parents and resolved != secrets_root.resolve():
                    return None
                return resolved.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                return None
        return None

    def _write_evidence(
        self,
        hand_ref: HandRef,
        command_name: str,
        input_data: Dict[str, Any],
        result: ResultEnvelope,
        *,
        env_allow: List[str],
        secret_names: List[str],
        secret_values: List[str],
        execution_mode: str = "shell",
        command_display: str = "",
        write_guard: Optional[Dict[str, Any]] = None,
    ) -> None:
        evidence_dir = Path(hand_ref.metadata.get("evidence_dir") or EVIDENCE_ROOT / hand_ref.hand_id)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence = {
            "hand_id": hand_ref.hand_id,
            "hand_type": hand_ref.hand_type.value,
            "command_name": command_name,
            "command": self._redact(command_display or str(input_data.get("command", "")), secret_values),
            "execution_mode": execution_mode,
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "error": result.error,
            "duration_ms": result.duration_ms,
            "side_effects": result.side_effects,
            "env_allow": env_allow,
            "secret_names": secret_names,
            "write_guard": write_guard or {},
            "workspace": hand_ref.metadata.get("workspace", ""),
            "workspace_manifest": self.collect_evidence(hand_ref),
            "recorded_at": _now_ts(),
        }
        path = evidence_dir / "evidence.json"
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result.metadata["evidence_file"] = str(path)

    def _is_denied(self, cmd: str) -> bool:
        for denied in self.policy.denied_commands:
            if denied in cmd:
                return True
        return bool(_SHELL_DESTRUCTIVE_PATTERN.search(cmd))

    def _redact(self, text: str, secret_values: List[str]) -> str:
        redacted = text
        for value in secret_values:
            if value:
                redacted = redacted.replace(value, "[REDACTED]")
        for pattern in self.policy.secret_patterns:
            redacted = re.sub(pattern, "[REDACTED]", redacted, flags=re.IGNORECASE)
        return redacted


class PaneHand:
    """Tmux pane hand. Dispatches via tmux send-keys."""

    def __init__(self, policy: Optional[CapabilityPolicy] = None) -> None:
        self._seen_keys: set[str] = set()
        self._provisioned: List[HandRef] = []
        self._disposed: List[str] = []
        self.policy = policy or CapabilityPolicy()

    def provision(
        self,
        *,
        capabilities: Optional[List[str]] = None,
        location: Optional[str] = None,
    ) -> HandRef:
        from uuid import uuid4
        pane_id = location or "0"
        ref = HandRef(
            hand_id=f"pane-{pane_id}-{uuid4().hex[:8]}",
            hand_type=HandType.PANE,
            provisioned_at=_now_ts(),
            capabilities=capabilities or [],
            location=pane_id,
        )
        self._provisioned.append(ref)
        return ref

    def execute(
        self,
        hand_ref: HandRef,
        command_name: str,
        input_data: Dict[str, Any],
        *,
        idempotency_key: str,
        timeout_seconds: Optional[int] = None,
    ) -> ResultEnvelope:
        if idempotency_key in self._seen_keys:
            return ResultEnvelope(
                status=ResultStatus.DUPLICATE_SUPPRESSED,
                output={"message": "duplicate suppressed"},
                metadata={"hand_id": hand_ref.hand_id},
            )
        self._seen_keys.add(idempotency_key)
        activity_ctx = _record_activity_start(hand_ref, command_name, input_data, idempotency_key)

        pane = hand_ref.location or "0"
        cmd_text = input_data.get("command", input_data.get("text", ""))

        try:
            import subprocess
            # Write command to pane
            subprocess.run(
                ["tmux", "send-keys", "-t", f"solar:{pane}", cmd_text, "Enter"],
                capture_output=True, text=True, timeout=10,
            )
            return _record_activity_terminal(activity_ctx, ResultEnvelope(
                status=ResultStatus.OK,
                output={"pane": pane, "command_sent": cmd_text[:200]},
                side_effects=[f"pane:{pane}:{command_name}"],
                metadata={"hand_id": hand_ref.hand_id},
            ))
        except Exception as exc:
            return _record_activity_terminal(activity_ctx, ResultEnvelope(
                status=ResultStatus.ERROR,
                error=f"pane dispatch failed: {exc}",
                metadata={"hand_id": hand_ref.hand_id},
            ))

    def dispose(self, hand_ref: HandRef, *, reason: str = "completed") -> ResultEnvelope:
        self._disposed.append(hand_ref.hand_id)
        return ResultEnvelope(
            status=ResultStatus.OK,
            output={"disposed": hand_ref.hand_id, "reason": reason},
            metadata={"hand_id": hand_ref.hand_id},
        )


class RemoteHand:
    """Remote Mac mini hand. Executes via SSH manifest."""

    def __init__(self, policy: Optional[CapabilityPolicy] = None) -> None:
        self._seen_keys: set[str] = set()
        self._provisioned: List[HandRef] = []
        self._disposed: List[str] = []
        self.policy = policy or CapabilityPolicy()
        self._remote_host = os.environ.get("SOLAR_REMOTE_HOST", "mac-mini")

    def provision(
        self,
        *,
        capabilities: Optional[List[str]] = None,
        location: Optional[str] = None,
    ) -> HandRef:
        from uuid import uuid4
        ref = HandRef(
            hand_id=f"remote-{uuid4().hex[:8]}",
            hand_type=HandType.REMOTE,
            provisioned_at=_now_ts(),
            capabilities=capabilities or [],
            location=location or self._remote_host,
        )
        self._provisioned.append(ref)
        return ref

    def execute(
        self,
        hand_ref: HandRef,
        command_name: str,
        input_data: Dict[str, Any],
        *,
        idempotency_key: str,
        timeout_seconds: Optional[int] = None,
    ) -> ResultEnvelope:
        if idempotency_key in self._seen_keys:
            return ResultEnvelope(
                status=ResultStatus.DUPLICATE_SUPPRESSED,
                output={"message": "duplicate suppressed"},
                metadata={"hand_id": hand_ref.hand_id},
            )
        self._seen_keys.add(idempotency_key)
        activity_ctx = _record_activity_start(hand_ref, command_name, input_data, idempotency_key)

        host = hand_ref.location or self._remote_host
        cmd = input_data.get("command", "")

        # Remote hand validates manifest/checksum if provided
        manifest = input_data.get("manifest")
        if manifest and not manifest.get("checksum"):
            return _record_activity_terminal(activity_ctx, ResultEnvelope(
                status=ResultStatus.ERROR,
                error="remote hand requires manifest checksum",
                metadata={"hand_id": hand_ref.hand_id, "host": host},
            ))

        try:
            timeout = timeout_seconds or self.policy.max_duration_seconds
            result = subprocess.run(
                ["ssh", host, cmd], capture_output=True, text=True,
                timeout=min(timeout, 120),
            )
            if result.returncode != 0:
                return _record_activity_terminal(activity_ctx, ResultEnvelope(
                    status=ResultStatus.ERROR,
                    error=result.stderr.strip() or f"remote exit {result.returncode}",
                    metadata={"hand_id": hand_ref.hand_id, "host": host},
                ))
            return _record_activity_terminal(activity_ctx, ResultEnvelope(
                status=ResultStatus.OK,
                output=result.stdout.strip(),
                side_effects=[f"remote:{host}:{command_name}"],
                metadata={"hand_id": hand_ref.hand_id, "host": host},
            ))
        except subprocess.TimeoutExpired:
            return _record_activity_terminal(activity_ctx, ResultEnvelope(
                status=ResultStatus.TIMEOUT,
                error=f"remote command timed out after {timeout}s",
                metadata={"hand_id": hand_ref.hand_id, "host": host},
            ))
        except FileNotFoundError:
            return _record_activity_terminal(activity_ctx, ResultEnvelope(
                status=ResultStatus.ERROR,
                error=f"ssh not found or host {host} unreachable",
                metadata={"hand_id": hand_ref.hand_id, "host": host},
            ))

    def dispose(self, hand_ref: HandRef, *, reason: str = "completed") -> ResultEnvelope:
        self._disposed.append(hand_ref.hand_id)
        return ResultEnvelope(
            status=ResultStatus.OK,
            output={"disposed": hand_ref.hand_id, "reason": reason},
            metadata={"hand_id": hand_ref.hand_id},
        )


# ------------------------------------------------------------------
# Hand registry
# ------------------------------------------------------------------

_HAND_REGISTRY: Dict[HandType, type] = {
    HandType.MOCK: MockHand,
    HandType.SHELL: ShellHand,
    HandType.SANDBOX: SandboxHand,
    HandType.PANE: PaneHand,
    HandType.REMOTE: RemoteHand,
}


def get_hand(hand_type: HandType, policy: Optional[CapabilityPolicy] = None):
    """Factory for hand instances."""
    cls = _HAND_REGISTRY.get(hand_type)
    if cls is None:
        raise ValueError(f"Unknown hand type: {hand_type}")
    return cls(policy=policy)


def available_hand_types() -> List[HandType]:
    return list(_HAND_REGISTRY.keys())


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
