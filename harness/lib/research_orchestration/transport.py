"""Bounded JSON subprocess transport for research node workers."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, BinaryIO

try:
    from operator_runtime import scrub_secrets as _runtime_scrub_secrets
except Exception:  # pragma: no cover - import depends on caller sys.path
    _runtime_scrub_secrets = None


DEFAULT_MAX_STDOUT_BYTES = 1_048_576
DEFAULT_MAX_STDERR_BYTES = 65_536
DEFAULT_MAX_DIAGNOSTIC_CHARS = 8_192
_READ_CHUNK_BYTES = 4_096
_SECRET_KEY_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "api_secret",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "password",
    "passwd",
    "private_key",
    "pwd",
    "refresh_token",
    "secret",
    "token",
}
_BODY_KEYS = {
    "body",
    "input",
    "inputs",
    "messages",
    "payload",
    "prompt",
    "request",
    "request_body",
    "research_node_request",
}
_SECRET_METADATA_KEYS = {
    "no_secrets_observed",
    "redaction_review",
    "secret_redaction_assertion",
}
_SECRET_PATTERNS = (
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "[SCRUBBED]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"), "[SCRUBBED]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[SCRUBBED]"),
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/=]{8,}"),
        "Bearer [SCRUBBED]",
    ),
    (
        re.compile(
            r"(?i)([\"']?(?:api[_-]?key|apikey|api[_-]?secret|access[_-]?token|"
            r"auth(?:orization)?|credential|private[_-]?key|refresh[_-]?token|secret|"
            r"password|passwd|pwd|token)[\"']?\s*[=:]\s*)[\"'][^\"']{4,}[\"']"
        ),
        r"\1\"[SCRUBBED]\"",
    ),
    (
        re.compile(
            r"(?i)(api[_-]?key|apikey|api[_-]?secret|access[_-]?token|auth(?:orization)?|"
            r"credential|private[_-]?key|refresh[_-]?token|secret|password|passwd|pwd|token)"
            r"(\s*[=:]\s*|\s+)[^\s,;\"']{4,}"
        ),
        r"\1=[SCRUBBED]",
    ),
)


class ResearchTransportError(RuntimeError):
    """Structured subprocess transport failure with bounded diagnostics."""

    def __init__(
        self,
        error_type: str,
        message: str,
        *,
        exit_code: int | None = None,
        stdout: str = "",
        stderr: str = "",
        details: dict[str, Any] | None = None,
        secret_values: Iterable[str] = (),
    ) -> None:
        secrets = tuple(str(value) for value in secret_values if str(value))
        self.error_type = _bounded_text(sanitize_text(str(error_type), secrets), 120)
        self.message = _bounded_text(sanitize_text(str(message), secrets), 500)
        super().__init__(self.message)
        self.exit_code = exit_code
        self.stdout = _bounded_text(
            sanitize_text(_coerce_text(stdout), secrets), DEFAULT_MAX_DIAGNOSTIC_CHARS
        )
        self.stderr = _bounded_text(
            sanitize_text(_coerce_text(stderr), secrets), DEFAULT_MAX_DIAGNOSTIC_CHARS
        )
        sanitized_details = sanitize_diagnostic_value(
            details or {},
            explicit_secret_values=secrets,
            omit_request_bodies=True,
        )
        self.details = sanitized_details if isinstance(sanitized_details, dict) else {}

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
    secret_values: Iterable[str] = (),
) -> dict:
    """Run a JSON worker while bounding streams before they enter memory."""

    secrets = tuple(str(value) for value in secret_values if str(value))
    if not isinstance(command, list) or not command or not all(
        isinstance(part, str) and part for part in command
    ):
        raise ResearchTransportError(
            "invalid_command", "command must be a non-empty list of strings", secret_values=secrets
        )
    if not isinstance(request, dict):
        raise ResearchTransportError(
            "invalid_request", "request must be a dictionary", secret_values=secrets
        )
    workdir = Path(cwd)
    if not workdir.is_dir():
        raise ResearchTransportError(
            "invalid_cwd", f"cwd does not exist: {workdir}", secret_values=secrets
        )
    if timeout_seconds < 1:
        raise ResearchTransportError(
            "invalid_timeout", "timeout_seconds must be at least 1", secret_values=secrets
        )
    if max_stdout_bytes < 1 or max_stderr_bytes < 1:
        raise ResearchTransportError(
            "invalid_output_limit", "output limits must be positive", secret_values=secrets
        )

    stdin_text = json.dumps(request, ensure_ascii=False, sort_keys=True)
    stdin_payload = stdin_text.encode("utf-8")
    diagnostic_secrets = (
        *secrets,
        stdin_text,
        *_collect_request_body_strings(request),
    )
    child_env = _build_env(env, env_allowlist)
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(workdir),
            env=child_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            shell=False,
            **_process_group_kwargs(),
        )
    except Exception as exc:
        raise ResearchTransportError(
            "spawn_failed",
            f"{type(exc).__name__}: {exc}",
            secret_values=diagnostic_secrets,
        ) from exc

    assert proc.stdout is not None
    assert proc.stderr is not None
    assert proc.stdin is not None
    stop_reading = threading.Event()
    limit_breach = threading.Event()
    stream_results: dict[str, dict[str, Any]] = {}
    readers = [
        threading.Thread(
            target=_read_bounded_stream,
            args=("stdout", proc.stdout, max_stdout_bytes, stream_results, limit_breach, stop_reading),
            daemon=True,
        ),
        threading.Thread(
            target=_read_bounded_stream,
            args=("stderr", proc.stderr, max_stderr_bytes, stream_results, limit_breach, stop_reading),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    writer_error: list[Exception] = []
    writer = threading.Thread(
        target=_write_stdin,
        args=(proc.stdin, stdin_payload, writer_error),
        daemon=True,
    )
    writer.start()

    deadline = time.monotonic() + timeout_seconds
    failure_type: str | None = None
    while proc.poll() is None:
        if limit_breach.is_set():
            failure_type = "oversized_output"
            _terminate_process_tree(proc)
            break
        if time.monotonic() >= deadline:
            failure_type = "timeout"
            _terminate_process_tree(proc)
            break
        time.sleep(0.01)

    if proc.poll() is None:
        _terminate_process_tree(proc)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    writer.join(timeout=1)
    if writer.is_alive():
        try:
            proc.stdin.close()
        except Exception:
            pass
        writer.join(timeout=1)
    for reader in readers:
        reader.join(timeout=2)
    if any(reader.is_alive() for reader in readers):
        stop_reading.set()
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except Exception:
                pass
        for reader in readers:
            reader.join(timeout=1)

    if failure_type is None and any(
        stream_results.get(name, {}).get("exceeded") for name in ("stdout", "stderr")
    ):
        failure_type = "oversized_output"

    stdout_bytes = bytes(stream_results.get("stdout", {}).get("data", b""))
    stderr_bytes = bytes(stream_results.get("stderr", {}).get("data", b""))
    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace")

    if failure_type == "oversized_output":
        breached = next(
            (name for name in ("stdout", "stderr") if stream_results.get(name, {}).get("exceeded")),
            "output",
        )
        info = stream_results.get(breached, {})
        raise ResearchTransportError(
            "oversized_output",
            f"{breached} exceeded its configured byte limit",
            exit_code=proc.returncode,
            stdout=stdout_text,
            stderr=stderr_text,
            details={
                "stream": breached,
                "observed_bytes": info.get("observed_bytes", 0),
                "max_bytes": max_stdout_bytes if breached == "stdout" else max_stderr_bytes,
            },
            secret_values=diagnostic_secrets,
        )
    if failure_type == "timeout":
        raise ResearchTransportError(
            "timeout",
            f"worker timed out after {timeout_seconds} seconds",
            exit_code=proc.returncode,
            stdout=stdout_text,
            stderr=stderr_text,
            secret_values=diagnostic_secrets,
        )
    if writer_error and proc.returncode == 0:
        raise ResearchTransportError(
            "stdin_write_failed",
            f"worker stdin write failed: {type(writer_error[0]).__name__}",
            exit_code=proc.returncode,
            stdout=stdout_text,
            stderr=stderr_text,
            secret_values=diagnostic_secrets,
        )
    if proc.returncode != 0:
        raise ResearchTransportError(
            "nonzero_exit",
            f"worker exited with code {proc.returncode}",
            exit_code=proc.returncode,
            stdout=stdout_text,
            stderr=stderr_text,
            secret_values=diagnostic_secrets,
        )
    return _parse_single_json(stdout_text, secret_values=diagnostic_secrets)


def sanitize_text(text: str, explicit_secret_values: Iterable[str] = ()) -> str:
    """Scrub common credential forms plus caller-supplied secret canaries."""

    scrubbed = str(text)
    if _runtime_scrub_secrets is not None:
        try:
            scrubbed = str(_runtime_scrub_secrets(scrubbed))
        except Exception:
            pass
    secrets = sorted(
        {str(value) for value in explicit_secret_values if str(value)}, key=len, reverse=True
    )
    for secret in secrets:
        scrubbed = scrubbed.replace(secret, "[SCRUBBED]")
    for pattern, replacement in _SECRET_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed


def sanitize_diagnostic_value(
    value: Any,
    *,
    explicit_secret_values: Iterable[str] = (),
    omit_request_bodies: bool = False,
    max_depth: int = 6,
    max_items: int = 50,
    max_string_chars: int = 2_048,
    max_nodes: int = 250,
) -> Any:
    """Recursively scrub and bound data intended only for diagnostics."""

    secrets = tuple(str(item) for item in explicit_secret_values if str(item))
    remaining_nodes = [max(1, int(max_nodes))]

    def _walk(item: Any, depth: int) -> Any:
        remaining_nodes[0] -= 1
        if remaining_nodes[0] < 0:
            return "[TRUNCATED]"
        if depth > max_depth:
            return "[TRUNCATED]"
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for index, (raw_key, raw_value) in enumerate(item.items()):
                if index >= max_items:
                    result["[TRUNCATED]"] = f"{len(item) - max_items} additional entries"
                    break
                key = _bounded_text(sanitize_text(str(raw_key), secrets), 200)
                normalized = key.casefold().replace("-", "_")
                if _is_sensitive_key(normalized):
                    result[key] = "[SCRUBBED]"
                elif omit_request_bodies and normalized in _BODY_KEYS:
                    result[key] = "[OMITTED_REQUEST_BODY]"
                else:
                    result[key] = _walk(raw_value, depth + 1)
            return result
        if isinstance(item, (list, tuple, set, frozenset)):
            values = list(item)
            output = [_walk(entry, depth + 1) for entry in values[:max_items]]
            if len(values) > max_items:
                output.append(f"[TRUNCATED {len(values) - max_items} ITEMS]")
            return output
        if isinstance(item, bytes):
            item = item.decode("utf-8", errors="replace")
        if isinstance(item, str):
            return _bounded_text(sanitize_text(item, secrets), max_string_chars)
        if item is None or isinstance(item, (bool, int, float)):
            return item
        return _bounded_text(sanitize_text(repr(item), secrets), max_string_chars)

    return _walk(value, 0)


def contains_sensitive_diagnostic(
    value: Any, *, explicit_secret_values: Iterable[str] = ()
) -> bool:
    """Return true when scrubbing would change a diagnostic payload."""

    secrets = tuple(str(item) for item in explicit_secret_values if str(item))

    def _contains(item: Any) -> bool:
        if isinstance(item, Mapping):
            for raw_key, raw_value in item.items():
                key = str(raw_key)
                if key.casefold() not in _SECRET_METADATA_KEYS and _is_sensitive_key(key) and raw_value not in (
                    None,
                    "",
                    "[SCRUBBED]",
                    "[REDACTED]",
                ):
                    return True
                if _contains(raw_value):
                    return True
            return False
        if isinstance(item, (list, tuple, set, frozenset)):
            return any(_contains(entry) for entry in item)
        if isinstance(item, bytes):
            item = item.decode("utf-8", errors="replace")
        if isinstance(item, str):
            return sanitize_text(item, secrets) != item
        return False

    return _contains(value)


def _read_bounded_stream(
    name: str,
    stream: BinaryIO,
    max_bytes: int,
    results: dict[str, dict[str, Any]],
    limit_breach: threading.Event,
    stop_reading: threading.Event,
) -> None:
    captured = bytearray()
    observed = 0
    exceeded = False
    try:
        while not stop_reading.is_set():
            chunk = stream.read(_READ_CHUNK_BYTES)
            if not chunk:
                break
            observed += len(chunk)
            remaining = max(0, max_bytes - len(captured))
            if remaining:
                captured.extend(chunk[:remaining])
            if observed > max_bytes:
                exceeded = True
                limit_breach.set()
                break
    finally:
        results[name] = {
            "data": bytes(captured),
            "observed_bytes": observed,
            "exceeded": exceeded,
        }
        try:
            stream.close()
        except Exception:
            pass


def _write_stdin(stream: BinaryIO, payload: bytes, errors: list[Exception]) -> None:
    try:
        stream.write(payload)
        stream.flush()
    except (BrokenPipeError, OSError) as exc:
        errors.append(exc)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _build_env(env: dict[str, str] | None, env_allowlist: set[str] | None) -> dict[str, str]:
    allowlist = {str(key) for key in (env_allowlist or set())}
    match_key = (lambda key: key.casefold()) if sys.platform == "win32" else (lambda key: key)
    allowed_by_match = {match_key(key): key for key in allowlist}
    child: dict[str, str] = {}
    for key in _minimal_env_keys():
        value = os.environ.get(key)
        if value is not None:
            child[key] = value
    for source_key, value in os.environ.items():
        matched = allowed_by_match.get(match_key(source_key))
        if matched is not None:
            child[matched] = value
    for key, value in (env or {}).items():
        matched = allowed_by_match.get(match_key(str(key)))
        if matched is not None:
            child[matched] = str(value)
    return child


def _minimal_env_keys() -> set[str]:
    if sys.platform == "win32":
        return {"PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}
    return {"PATH", "LANG", "LC_ALL"}


def _process_group_kwargs() -> dict[str, Any]:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _terminate_process_tree(proc: subprocess.Popen[bytes]) -> None:
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


def _bounded_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...[TRUNCATED]"


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
    if normalized in _SECRET_KEY_NAMES:
        return True
    return any(
        normalized.endswith(f"_{suffix}")
        for suffix in ("api_key", "api_secret", "access_token", "private_key", "refresh_token")
    )


def _collect_request_body_strings(request: Mapping[str, Any]) -> tuple[str, ...]:
    typed_inputs = request.get("typed_inputs")
    if not isinstance(typed_inputs, Mapping):
        return ()
    payload = typed_inputs.get("payload")
    collected: list[str] = []

    def _walk(value: Any, depth: int = 0) -> None:
        if depth > 10 or len(collected) >= 200:
            return
        if isinstance(value, Mapping):
            for nested in value.values():
                _walk(nested, depth + 1)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                _walk(nested, depth + 1)
        elif isinstance(value, str) and len(value) >= 4:
            collected.append(value)

    _walk(payload)
    return tuple(collected)


def _parse_single_json(stdout: str, *, secret_values: Iterable[str] = ()) -> dict:
    text = stdout.strip()
    if not text:
        raise ResearchTransportError(
            "empty_stdout", "worker emitted empty stdout", secret_values=secret_values
        )
    decoder = json.JSONDecoder()
    try:
        payload, index = decoder.raw_decode(text)
    except json.JSONDecodeError as exc:
        raise ResearchTransportError(
            "invalid_json",
            f"stdout is not valid JSON: {exc.msg}",
            secret_values=secret_values,
        ) from exc
    trailing = text[index:].strip()
    if trailing:
        try:
            decoder.raw_decode(trailing)
        except json.JSONDecodeError:
            raise ResearchTransportError(
                "invalid_json",
                "stdout has trailing non-JSON content",
                secret_values=secret_values,
            )
        raise ResearchTransportError(
            "multiple_json_values",
            "stdout contains multiple JSON values",
            secret_values=secret_values,
        )
    if not isinstance(payload, dict):
        raise ResearchTransportError(
            "invalid_json_type",
            "worker JSON stdout must be an object",
            secret_values=secret_values,
        )
    return payload
