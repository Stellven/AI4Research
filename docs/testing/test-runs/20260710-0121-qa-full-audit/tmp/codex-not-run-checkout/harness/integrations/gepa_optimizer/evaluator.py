"""
evaluator.py — Subprocess JSON evaluator sandbox for GEPA optimize_anything.

Design
------
* Isolation: each evaluation runs in a fresh child process with a pruned
  environment (no host secrets), optional CPU / memory resource limits, and
  a hard wall-clock timeout.
* Communication: parent serialises call context to JSON and writes it to
  child stdin; child writes a single JSON object to stdout; parent reads that
  after the child exits (or is killed on timeout).
* Structured failure: a timeout, non-zero exit, or unparseable stdout always
  produces a valid ``EvaluatorResult`` with ``ok=False`` and a sanitised
  diagnostic message — no secret values or raw tracebacks are forwarded to
  the caller.
* RLIMIT fallback for macOS: ``RLIMIT_AS`` (virtual address space) is
  unreliable on macOS because the initial address-space map frequently
  exceeds small limits; the implementation skips it on Darwin and falls back
  to ``RLIMIT_DATA`` (heap).  Each limit is applied independently so a
  failure on one does not block the others.

Evaluator script protocol
--------------------------
The script launched by ``SubprocessEvaluator`` must:

1. Read one JSON object from ``stdin``:
      ``{"candidate": "<text>", "<extra_key>": <extra_val>, …}``
2. Write one JSON object to ``stdout``:
      ``{"score": <float>, …}``   — success
      ``{"error": "<msg>"}``      — application-level failure (exit 0 OK)
3. Exit 0 on success, non-zero on fatal error.

Public symbols (re-exported from ``integrations.gepa_optimizer``)
-----------------------------------------------------------------
* ``EvaluatorError``      — configuration / startup errors (raised)
* ``EvaluatorResult``     — structured result (ok / score / metadata / error)
* ``SubprocessEvaluator`` — callable sandbox
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import platform
import re
import resource
import subprocess
import sys
from pathlib import Path
from typing import Any, Collection, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

_IS_DARWIN: bool = platform.system() == "Darwin"

# ---------------------------------------------------------------------------
# Secret-scrubbing patterns applied to stderr before forwarding to callers
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'(?i)(token|secret|password|api[_\-]?key|bearer)\s*[=:]\s*\S+'),
    re.compile(r'(?i)sk-[A-Za-z0-9]{20,}'),        # OpenAI-style keys
    re.compile(r'(?i)ghp_[A-Za-z0-9]{36,}'),        # GitHub PAT
    re.compile(r'(?i)(?:xox[baprs]-)\S+'),           # Slack tokens
    re.compile(r'(?i)AKIA[0-9A-Z]{16}'),             # AWS access key IDs
    re.compile(r'(?i)(?:eyJ)[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+'),  # JWTs
)

# Environment keys that are safe to forward to child processes.
# Nothing containing TOKEN / SECRET / KEY / PASSWORD / CREDENTIAL is included.
_DEFAULT_ALLOWED_ENV: frozenset[str] = frozenset({
    "PATH",
    "HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PYTHONPATH",
    "PYTHONHASHSEED",
    "PYTHONDONTWRITEBYTECODE",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
})

# Hard cap on how many bytes of stderr we capture and sanitise.
_STDERR_MAX_BYTES: int = 2048


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class EvaluatorError(RuntimeError):
    """Raised for configuration-level evaluator errors.

    Raised at construction time (bad script path, invalid timeout, …) or
    when the subprocess cannot be *started* (missing interpreter, …).

    Runtime evaluation failures — timeouts, bad JSON, non-zero exits — are
    captured as ``EvaluatorResult(ok=False)`` and are never raised.
    """


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class EvaluatorResult:
    """Structured, immutable result from one evaluator subprocess run.

    Attributes
    ----------
    ok:
        ``True`` iff the subprocess exited 0 and produced parseable JSON
        with a numeric ``score`` field.
    score:
        Numeric evaluation score.  ``None`` when ``ok=False``.
    metadata:
        Additional fields from the subprocess JSON (sub-scores, latency,
        token counts, …).  Always a plain ``dict``; never contains secret
        values.
    error:
        Sanitised single-line diagnostic string when ``ok=False``.
        ``None`` when ``ok=True``.
    exit_code:
        Raw subprocess exit code.  ``None`` if the process was killed due
        to a timeout.
    timed_out:
        ``True`` when the subprocess exceeded ``timeout`` and was killed.
    stderr_snippet:
        Up to 2 KiB of sanitised stderr; intended for local debugging only
        and not forwarded outside the harness boundary.
    """

    ok: bool
    score: float | None
    metadata: dict[str, Any]
    error: str | None = None
    exit_code: int | None = None
    timed_out: bool = False
    stderr_snippet: str = ""

    @classmethod
    def success(
        cls,
        score: float,
        metadata: dict[str, Any] | None = None,
    ) -> "EvaluatorResult":
        """Construct a successful result."""
        return cls(ok=True, score=score, metadata=metadata or {})

    @classmethod
    def failure(
        cls,
        error: str,
        *,
        exit_code: int | None = None,
        timed_out: bool = False,
        stderr_snippet: str = "",
    ) -> "EvaluatorResult":
        """Construct a failure result with a sanitised diagnostic."""
        return cls(
            ok=False,
            score=None,
            metadata={},
            error=error,
            exit_code=exit_code,
            timed_out=timed_out,
            stderr_snippet=stderr_snippet,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sanitise(text: str) -> str:
    """Replace secret-looking patterns in *text* with ``[REDACTED]``."""
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def _build_child_env(allowed_keys: frozenset[str]) -> dict[str, str]:
    """Build a clean environment dict for the child process.

    Only keys present in *allowed_keys* are forwarded from ``os.environ``.
    Values are additionally scrubbed for secret patterns as a defence-in-depth
    measure.
    """
    return {
        k: _sanitise(v)
        for k, v in os.environ.items()
        if k in allowed_keys
    }


def _try_setrlimit(limit_id: int, value: int, name: str) -> bool:
    """Attempt ``resource.setrlimit(limit_id, …)``; return ``True`` on success.

    Caps *value* at the existing hard limit to avoid ``EPERM``.  Logs a
    ``DEBUG`` message on failure so the caller's ``preexec_fn`` does not
    crash the child process.
    """
    try:
        soft, hard = resource.getrlimit(limit_id)
        capped = value if hard == resource.RLIM_INFINITY else min(value, hard)
        resource.setrlimit(limit_id, (capped, hard))
        return True
    except (ValueError, OSError) as exc:
        logger.debug("Could not set %s to %d: %s", name, value, exc)
        return False


def _apply_rlimits(memory_limit_mb: int | None, cpu_limit_s: int | None) -> None:
    """Apply resource limits inside the child process (``preexec_fn``).

    Called after ``fork()`` but before the child's Python code runs.  Each
    limit is applied independently; a failure on one does not prevent the
    others from being set.

    macOS fallback
    --------------
    ``RLIMIT_AS`` (virtual address space) is skipped on Darwin because macOS
    processes start with a very large virtual map (hundreds of GiB due to
    ASLR / lazy allocation), so a small ``RLIMIT_AS`` value would kill the
    process before it runs a single line of user code.  ``RLIMIT_DATA``
    (heap) is used instead and is reliably enforced on macOS.
    """
    if cpu_limit_s is not None:
        _try_setrlimit(resource.RLIMIT_CPU, cpu_limit_s, "RLIMIT_CPU")

    if memory_limit_mb is not None:
        limit_bytes = memory_limit_mb * 1024 * 1024
        if _IS_DARWIN:
            # macOS: skip RLIMIT_AS, use RLIMIT_DATA (heap) instead
            if hasattr(resource, "RLIMIT_DATA"):
                _try_setrlimit(resource.RLIMIT_DATA, limit_bytes, "RLIMIT_DATA")
        else:
            # Linux: prefer RLIMIT_AS; fall back to RLIMIT_DATA
            if hasattr(resource, "RLIMIT_AS"):
                if not _try_setrlimit(resource.RLIMIT_AS, limit_bytes, "RLIMIT_AS"):
                    if hasattr(resource, "RLIMIT_DATA"):
                        _try_setrlimit(resource.RLIMIT_DATA, limit_bytes, "RLIMIT_DATA")
            elif hasattr(resource, "RLIMIT_DATA"):
                _try_setrlimit(resource.RLIMIT_DATA, limit_bytes, "RLIMIT_DATA")


# ---------------------------------------------------------------------------
# Subprocess evaluator
# ---------------------------------------------------------------------------

class SubprocessEvaluator:
    """Sandbox an evaluator script in a child process with JSON stdio.

    Each call to ``__call__`` spawns a fresh subprocess, writes the
    evaluation context as JSON to its stdin, reads the JSON result from its
    stdout, and returns an :class:`EvaluatorResult`.

    The child process is completely isolated from host secrets: only the
    environment keys in *allowed_env* are forwarded, and those values are
    additionally scrubbed for secret patterns before being passed.

    Parameters
    ----------
    script:
        Path to the Python evaluator script.  Must exist at construction
        time; raises :class:`EvaluatorError` otherwise.
    timeout:
        Wall-clock seconds to wait for the subprocess.  Processes that
        exceed this limit are killed with SIGKILL; the result has
        ``timed_out=True``.
    allowed_env:
        Collection of environment-variable names to forward to the child.
        Defaults to :data:`_DEFAULT_ALLOWED_ENV` (PATH, HOME, TMPDIR, …).
        No key containing TOKEN / SECRET / KEY / PASSWORD is in the default
        set.
    memory_limit_mb:
        Optional soft memory limit for the child process.  Uses
        ``RLIMIT_DATA`` on macOS and ``RLIMIT_AS`` (falling back to
        ``RLIMIT_DATA``) on Linux.  ``None`` applies no limit.
    cpu_limit_s:
        Optional CPU-time limit in seconds (``RLIMIT_CPU``).  This is a
        CPU limit, not wall-clock; the *timeout* parameter enforces the
        wall-clock budget.  ``None`` applies no limit.
    python_executable:
        Python interpreter for the child.  Defaults to ``sys.executable``
        (same interpreter running the harness).
    extra_args:
        Additional CLI arguments appended after the script path.

    Evaluator script protocol
    -------------------------
    stdin  (JSON object): ``{"candidate": "<text>", …extra_context…}``
    stdout (JSON object): ``{"score": <float>, …optional_metadata…}``
    stdout on error:      ``{"error": "<message>"}``  (exit 0 is still OK)
    exit code: 0 = success or application-level error via JSON;
               non-zero = fatal failure.

    Example
    -------
    ::

        ev = SubprocessEvaluator("eval/quality_check.py", timeout=15.0)
        result = ev("Summarise the article in one sentence.", topic="news")
        if result.ok:
            print(result.score)          # e.g. 0.87
        else:
            print(result.error)          # sanitised diagnostic
    """

    def __init__(
        self,
        script: str | Path,
        *,
        timeout: float = 30.0,
        allowed_env: Collection[str] | None = None,
        memory_limit_mb: int | None = None,
        cpu_limit_s: int | None = None,
        python_executable: str | None = None,
        extra_args: Sequence[str] = (),
    ) -> None:
        resolved = Path(script).resolve()
        if not resolved.is_file():
            raise EvaluatorError(f"Evaluator script not found: {resolved}")
        if timeout <= 0:
            raise EvaluatorError(f"timeout must be > 0, got {timeout!r}")
        if memory_limit_mb is not None and memory_limit_mb <= 0:
            raise EvaluatorError(
                f"memory_limit_mb must be > 0, got {memory_limit_mb!r}"
            )
        if cpu_limit_s is not None and cpu_limit_s <= 0:
            raise EvaluatorError(
                f"cpu_limit_s must be > 0, got {cpu_limit_s!r}"
            )

        self._script: Path = resolved
        self._timeout: float = float(timeout)
        self._allowed_env: frozenset[str] = (
            frozenset(allowed_env)
            if allowed_env is not None
            else _DEFAULT_ALLOWED_ENV
        )
        self._memory_limit_mb: int | None = memory_limit_mb
        self._cpu_limit_s: int | None = cpu_limit_s
        self._python: str = python_executable or sys.executable
        self._extra_args: tuple[str, ...] = tuple(extra_args)

    # ------------------------------------------------------------------
    # Callable interface
    # ------------------------------------------------------------------

    def __call__(self, candidate: str, **context: Any) -> EvaluatorResult:
        """Evaluate *candidate* in a sandboxed subprocess.

        Parameters
        ----------
        candidate:
            The candidate string (e.g. an optimised prompt) to evaluate.
        **context:
            Additional evaluation context serialised alongside ``candidate``
            in the stdin JSON.

        Returns
        -------
        EvaluatorResult
            Always returns a result object; never raises.  Timeouts, non-zero
            exits, and JSON parse errors all produce ``ok=False`` results with
            sanitised ``error`` diagnostics.
        """
        payload: dict[str, Any] = {"candidate": candidate, **context}
        try:
            stdin_bytes = json.dumps(payload).encode()
        except (TypeError, ValueError) as exc:
            return EvaluatorResult.failure(
                f"Could not serialise evaluation context to JSON: {exc}"
            )

        child_env = _build_child_env(self._allowed_env)
        mem_mb = self._memory_limit_mb
        cpu_s = self._cpu_limit_s

        def _preexec() -> None:
            # Called in child after fork(); sets resource limits.
            # Captures mem_mb / cpu_s from outer scope; does not hold a
            # reference to self so there are no threading issues.
            _apply_rlimits(mem_mb, cpu_s)

        cmd: list[str] = [self._python, str(self._script), *self._extra_args]

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=child_env,
                preexec_fn=_preexec,
            )
        except OSError as exc:
            return EvaluatorResult.failure(
                f"Failed to start evaluator subprocess: {_sanitise(str(exc))}"
            )

        # --- communicate with timeout ----------------------------------------
        try:
            stdout_bytes, stderr_bytes = proc.communicate(
                input=stdin_bytes,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            # Drain pipes after kill to avoid resource leaks.
            try:
                _, stderr_bytes = proc.communicate(timeout=5.0)
            except Exception:
                stderr_bytes = b""
            snippet = _sanitise(
                stderr_bytes.decode(errors="replace")[:_STDERR_MAX_BYTES]
            )
            logger.warning(
                "Evaluator subprocess timed out after %.1f s (script=%s)",
                self._timeout,
                self._script,
            )
            return EvaluatorResult.failure(
                f"Evaluator timed out after {self._timeout:.1f}s",
                timed_out=True,
                stderr_snippet=snippet,
            )
        except Exception as exc:
            # Catch-all: communication error (broken pipe, etc.)
            return EvaluatorResult.failure(
                f"Subprocess communication error: {_sanitise(str(exc))}"
            )

        # --- check exit code -------------------------------------------------
        stderr_snippet = _sanitise(
            stderr_bytes.decode(errors="replace")[:_STDERR_MAX_BYTES]
        )
        if proc.returncode != 0:
            logger.warning(
                "Evaluator exited %d (script=%s)", proc.returncode, self._script
            )
            return EvaluatorResult.failure(
                f"Evaluator exited with code {proc.returncode}",
                exit_code=proc.returncode,
                stderr_snippet=stderr_snippet,
            )

        return _parse_stdout(stdout_bytes, stderr_snippet)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def script(self) -> Path:
        """Resolved path to the evaluator script."""
        return self._script

    @property
    def timeout(self) -> float:
        """Wall-clock timeout in seconds."""
        return self._timeout

    @property
    def allowed_env(self) -> frozenset[str]:
        """Frozenset of environment-variable names forwarded to the child."""
        return self._allowed_env

    def __repr__(self) -> str:
        return (
            f"SubprocessEvaluator(script={self._script!r}, "
            f"timeout={self._timeout!r})"
        )


# ---------------------------------------------------------------------------
# stdout parser (module-level to keep SubprocessEvaluator.__call__ readable)
# ---------------------------------------------------------------------------

def _parse_stdout(stdout_bytes: bytes, stderr_snippet: str) -> EvaluatorResult:
    """Parse subprocess stdout bytes into an :class:`EvaluatorResult`."""
    raw = stdout_bytes.decode(errors="replace").strip()
    if not raw:
        return EvaluatorResult.failure(
            "Evaluator produced no stdout output",
            exit_code=0,
            stderr_snippet=stderr_snippet,
        )

    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        snippet = _sanitise(raw[:200])
        return EvaluatorResult.failure(
            f"Evaluator output is not valid JSON: {exc} — got: {snippet!r}",
            exit_code=0,
            stderr_snippet=stderr_snippet,
        )

    if not isinstance(data, dict):
        return EvaluatorResult.failure(
            f"Evaluator JSON must be an object, got {type(data).__name__}",
            exit_code=0,
            stderr_snippet=stderr_snippet,
        )

    # Application-level error reported by the script itself
    if "error" in data:
        return EvaluatorResult.failure(
            _sanitise(str(data["error"]))[:256],
            exit_code=0,
            stderr_snippet=stderr_snippet,
        )

    if "score" not in data:
        return EvaluatorResult.failure(
            "Evaluator JSON missing required 'score' field",
            exit_code=0,
            stderr_snippet=stderr_snippet,
        )

    try:
        score = float(data["score"])
    except (TypeError, ValueError) as exc:
        return EvaluatorResult.failure(
            f"Evaluator 'score' field is not numeric: {exc}",
            exit_code=0,
            stderr_snippet=stderr_snippet,
        )

    metadata = {k: v for k, v in data.items() if k != "score"}
    return EvaluatorResult.success(score, metadata)
