"""Bounded JSON subprocess transport for research node workers."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from operator_runtime import scrub_secrets as _runtime_scrub_secrets
except Exception:  # pragma: no cover - import depends on caller sys.path
    _runtime_scrub_secrets = None


DEFAULT_MAX_STDOUT_BYTES = 1_048_576
DEFAULT_MAX_STDERR_BYTES = 65_536


class ResearchTransportError(RuntimeError):
    """Structured subprocess transport failure."""

    def __init__(
        self,
        error_type: str,
        message: str,
        *,
        exit_code: int | None = None,
        stdout: str = "",
        stderr: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(_scrub(str(message)))
        self.error_type = str(error_type)
        self.message = _scrub(str(message))
        self.exit_code = exit_code
        self.stdout = _scrub(stdout)
        self.stderr = _scrub(stderr)
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error_type": self.error_type,
            "message": self.message,
        }
        if self.exit_code is not None:
            payload["exit_code"] = self.exit_code
        if self.stdout:
            payload["stdout"] = self.stdout
        if self.stderr:
            payload["stderr"] = self.stderr
        if self.details:
            payload["details"] = self.details
        return payload


def run_json_worker(
    command: list[str],
    request: dict,
    *,
    cwd: Path,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
    env_allowlist: set[str] | None = None,
    max_stdout_bytes: int = DEFAULT_MAX_STDOUT_BYTES,
    max_stderr_bytes: int = DEFAULT_MAX_STDERR_BYTES,
) -> dict:
    """Run a bounded worker that accepts one JSON request on stdin."""

    if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
        raise ResearchTransportError("invalid_command", "command must be a non-empty list of strings")
    if not isinstance(request, dict):
        raise ResearchTransportError("invalid_request", "request must be a dictionary")
    workdir = Path(cwd)
    if not workdir.is_dir():
        raise ResearchTransportError("invalid_cwd", f"cwd does not exist: {workdir}")
    if timeout_seconds < 1:
        raise ResearchTransportError("invalid_timeout", "timeout_seconds must be at least 1")
    if max_stdout_bytes < 1 or max_stderr_bytes < 1:
        raise ResearchTransportError("invalid_output_limit", "output limits must be positive")

    stdin_payload = json.dumps(request, ensure_ascii=False, sort_keys=True)
    child_env = _build_env(env, env_allowlist)
    popen_kwargs = _process_group_kwargs()

    try:
        proc = subprocess.Popen(
            command,
            cwd=str(workdir),
            env=child_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            **popen_kwargs,
        )
    except Exception as exc:
        raise ResearchTransportError(
            "spawn_failed",
            f"{type(exc).__name__}: {exc}",
        ) from exc

    try:
        stdout, stderr = proc.communicate(stdin_payload, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            stdout, stderr = exc.output or "", exc.stderr or ""
        raise ResearchTransportError(
            "timeout",
            f"worker timed out after {timeout_seconds} seconds",
            exit_code=proc.returncode,
            stdout=_coerce_text(stdout),
            stderr=_coerce_text(stderr),
        ) from exc

    stdout_text = _coerce_text(stdout)
    stderr_text = _coerce_text(stderr)
    _enforce_output_limit("stdout", stdout_text, max_stdout_bytes)
    _enforce_output_limit("stderr", stderr_text, max_stderr_bytes)

    if proc.returncode != 0:
        raise ResearchTransportError(
            "nonzero_exit",
            f"worker exited with code {proc.returncode}",
            exit_code=proc.returncode,
            stdout=stdout_text,
            stderr=stderr_text,
        )

    return _parse_single_json(stdout_text)


def _scrub(text: str) -> str:
    if _runtime_scrub_secrets is not None:
        try:
            return str(_runtime_scrub_secrets(text))
        except Exception:
            pass
    scrubbed = text
    import re

    patterns = [
        (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[SCRUBBED]"),
        (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "[SCRUBBED]"),
        (re.compile(r"AKIA[0-9A-Z]{16}"), "[SCRUBBED]"),
        (re.compile(r"Bearer [A-Za-z0-9\-._~+/=]{20,}"), "Bearer [SCRUBBED]"),
        (re.compile(r"(?i)(api[_-]?key|apikey|api_secret|token|secret|password)\s*[=:]\s*[^\s\"']{4,}"), r"\1=[SCRUBBED]"),
    ]
    for pattern, replacement in patterns:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed


def _build_env(env: dict[str, str] | None, env_allowlist: set[str] | None) -> dict[str, str]:
    allowlist = {str(key) for key in (env_allowlist or set())}
    child: dict[str, str] = {}
    for key in _minimal_env_keys():
        value = os.environ.get(key)
        if value is not None:
            child[key] = value
    for key in allowlist:
        value = os.environ.get(key)
        if value is not None:
            child[key] = value
    for key, value in (env or {}).items():
        key_text = str(key)
        if key_text in allowlist:
            child[key_text] = str(value)
    return child


def _minimal_env_keys() -> set[str]:
    keys = {"PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TMP", "TEMP", "TMPDIR"}
    if sys.platform != "win32":
        keys.update({"HOME", "LANG", "LC_ALL"})
    return keys


def _process_group_kwargs() -> dict[str, Any]:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if proc.poll() is None:
            proc.kill()
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        proc.kill()


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _enforce_output_limit(name: str, text: str, max_bytes: int) -> None:
    size = len(text.encode("utf-8", errors="replace"))
    if size > max_bytes:
        raise ResearchTransportError(
            "oversized_output",
            f"{name} exceeded {max_bytes} bytes",
            details={"stream": name, "size_bytes": size, "max_bytes": max_bytes},
        )


def _parse_single_json(stdout: str) -> dict:
    text = stdout.strip()
    if not text:
        raise ResearchTransportError("empty_stdout", "worker emitted empty stdout")
    decoder = json.JSONDecoder()
    try:
        payload, index = decoder.raw_decode(text)
    except json.JSONDecodeError as exc:
        raise ResearchTransportError("invalid_json", f"stdout is not valid JSON: {exc.msg}") from exc
    trailing = text[index:].strip()
    if trailing:
        try:
            decoder.raw_decode(trailing)
        except json.JSONDecodeError:
            raise ResearchTransportError("invalid_json", "stdout has trailing non-JSON content")
        raise ResearchTransportError("multiple_json_values", "stdout contains multiple JSON values")
    if not isinstance(payload, dict):
        raise ResearchTransportError("invalid_json_type", "worker JSON stdout must be an object")
    return payload
