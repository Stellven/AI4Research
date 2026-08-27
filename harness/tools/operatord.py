#!/usr/bin/env python3
"""operatord — Solar Harness operator daemon CLI.

Launches a Solar operator process: resolves the operator config from the
physical-operators registry, loads the appropriate persona and evaluator
protocol, applies the tmux pane title, then emits a structured ready signal.

Usage
-----
    operatord run --operator <id> [options]
    operatord run --help
    operatord list
    operatord --help

Subcommands
-----------
run     Bootstrap one operator instance (persona load + pane title).
list    Print enabled operators from the registry.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import shutil
import sys
import re
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
SPRINTS_DIR = Path(
    os.environ.get("SOLAR_HARNESS_SPRINTS_DIR")
    or os.environ.get("HARNESS_SPRINTS_DIR")
    or HARNESS_DIR / "sprints"
)
PERSONAS_DIR = HARNESS_DIR / "personas"
OPERATOR_DAEMON_DIR = HARNESS_DIR / "run" / "operator-daemons"
PHYSICAL_OPERATORS_PATH = Path(
    os.environ.get(
        "SOLAR_MULTI_TASK_OPERATORS",
        HARNESS_DIR / "config" / "physical-operators.json",
    )
)

# Force the sibling lib directory to the FRONT of sys.path. The tools dir is
# sys.path[0] when operatord runs as a script and shadows shared-name lib
# modules with stale copies; an inherited PYTHONPATH that merely CONTAINS
# harness/lib (the live-e2e sandbox env) used to satisfy the membership guard
# here without granting precedence, so `from operator_runtime import ...`
# resolved the tools copy — the one whose write_result has no route-record
# hook (P2 smoke-4: zero 'completed' route records).
_LIB_DIR = Path(__file__).resolve().parent.parent / "lib"
if sys.path and sys.path[0] != str(_LIB_DIR):
    while str(_LIB_DIR) in sys.path:
        sys.path.remove(str(_LIB_DIR))
    sys.path.insert(0, str(_LIB_DIR))

import file_lock_compat as fcntl  # noqa: E402
try:
    from developer_observability import (  # noqa: E402
        enabled as _observability_enabled,
        observe as _observe,
        stable_id as _observation_id,
    )
except Exception:  # Observability must never become a worker dependency.
    def _observe(*_args: Any, **_kwargs: Any) -> bool:
        return False

    def _observation_id(kind: str, *parts: Any) -> str:
        return f"{kind}-unavailable"

    def _observability_enabled() -> bool:
        return False

from operator_persona import (  # noqa: E402  (import after path setup)
    EVALUATOR_PROTOCOL_FILENAME,
    resolve_persona,
)

# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def _load_registry() -> dict[str, Any]:
    if not PHYSICAL_OPERATORS_PATH.exists():
        return {"version": 1, "operators": {}}
    try:
        return json.loads(PHYSICAL_OPERATORS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        _die(f"Cannot read operator registry {PHYSICAL_OPERATORS_PATH}: {exc}")


def _get_operator(operator_id: str) -> dict[str, Any]:
    registry = _load_registry()
    operators = registry.get("operators", {})
    if operator_id not in operators:
        available = ", ".join(sorted(operators.keys())) or "(none)"
        _die(
            f"Operator '{operator_id}' not found in registry.\n"
            f"Available: {available}"
        )
    return dict(operators[operator_id])


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _die(msg: str) -> None:
    print(f"[operatord] ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def _info(msg: str) -> None:
    print(f"[operatord] {msg}", flush=True)


def _daemon_lock_path(operator_id: str) -> Path:
    OPERATOR_DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    return OPERATOR_DAEMON_DIR / f"{operator_id}.lock"


def _daemon_pid_path(operator_id: str) -> Path:
    OPERATOR_DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    return OPERATOR_DAEMON_DIR / f"{operator_id}.json"


def _acquire_daemon_slot(operator_id: str, *, once: bool) -> tuple[Any | None, Path]:
    lock_path = _daemon_lock_path(operator_id)
    pid_path = _daemon_pid_path(operator_id)
    lock_fh = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        owner = {}
        try:
            owner = json.loads(pid_path.read_text(encoding="utf-8"))
        except Exception:
            owner = {}
        owner_pid = owner.get("pid", "unknown")
        owner_mode = "once" if owner.get("once") else "daemon"
        _info(
            f"Another operatord instance is already active for {operator_id} "
            f"(pid={owner_pid}, mode={owner_mode})"
        )
        lock_fh.close()
        return None, pid_path

    pid_payload = {
        "operator_id": operator_id,
        "pid": os.getpid(),
        "once": bool(once),
        "started_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    pid_path.write_text(json.dumps(pid_payload, indent=2), encoding="utf-8")
    return lock_fh, pid_path


def _release_daemon_slot(lock_fh: Any | None, pid_path: Path) -> None:
    try:
        if pid_path.exists():
            try:
                payload = json.loads(pid_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            if str(payload.get("pid") or "") == str(os.getpid()):
                pid_path.unlink()
    finally:
        if lock_fh is not None:
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                lock_fh.close()
            except Exception:
                pass


def _read_status_snapshot(operator_id: str) -> dict[str, Any]:
    path = HARNESS_DIR / "run" / "operator-status" / f"{operator_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Daemon helpers
# ---------------------------------------------------------------------------


def _configured_launch_command(config: dict) -> str:
    surface = config.get("surface")
    if isinstance(surface, dict):
        launch_cmd = str(surface.get("launch_cmd") or "").strip()
        if launch_cmd:
            return launch_cmd
    return str(config.get("launch_cmd") or "").strip()


def _configured_launch_argv(config: dict) -> list[str]:
    """Return an optional shell-free command declared by a physical operator."""
    surface = config.get("surface")
    raw = surface.get("launch_argv") if isinstance(surface, dict) else None
    if raw is None:
        raw = config.get("launch_argv")
    if isinstance(raw, list) and raw and all(isinstance(part, str) and part for part in raw):
        return list(raw)
    return []


def _is_codex_command_operator(config: dict[str, Any]) -> bool:
    """Return whether a command-backend profile is backed by Codex CLI."""
    if str(config.get("backend") or "").strip().lower() != "command":
        return False
    haystack = " ".join(
        str(config.get(key) or "")
        for key in (
            "profile",
            "provider",
            "base_url",
            "model_config",
            "command",
            "command_path",
        )
    ).lower()
    return "codex" in haystack


def _command_operator_environment(config: dict[str, Any]) -> dict[str, str]:
    """Materialize platform-neutral environment declared by command profiles."""
    if not _is_codex_command_operator(config):
        return {}
    model = str(config.get("model") or "").strip()
    effort = str(config.get("reasoning_effort") or "").strip()
    if not effort:
        match = re.search(
            r"(?:^|[;,\s])reasoning(?:_effort)?=([A-Za-z0-9_-]+)",
            str(config.get("model_config") or ""),
            re.IGNORECASE,
        )
        effort = match.group(1) if match else "medium"
    env = {
        "CODEX_REASONING_EFFORT": effort,
        "PYTHONUTF8": "1",
    }
    if model:
        env["CODEX_MODEL"] = model
    return env


def _claude_model_arg(model: str) -> str:
    value = str(model or "sonnet").strip().lower()
    if value in {"glm", "glm-5", "glm-5.1", "zhipu", "zhipu-glm-5.1"}:
        return "opus"
    if "opus" in value:
        return "opus"
    if "sonnet" in value or value in {"claude", "anthropic"}:
        return "sonnet"
    return value or "sonnet"


def _model_route_metadata(config: dict[str, Any]) -> dict[str, str]:
    requested_model = str(config.get("model") or "").strip()
    provider = str(config.get("provider") or config.get("vendor") or "").strip().lower()
    backend = str(config.get("backend") or "").strip().lower()
    routing_model = requested_model
    effective_provider = provider or str(config.get("backend") or "").strip()
    effective_model = requested_model

    if backend == "claude-cli":
        routing_model = _claude_model_arg(requested_model)
        if provider in {"glm", "zhipu", "zhipuai"}:
            effective_provider = "zhipu"
            effective_model = "glm-5.1"
        elif provider in {"anthropic", "claude"}:
            effective_provider = "anthropic"
            effective_model = requested_model or routing_model

    return {
        "requested_model": requested_model or "N/A",
        "routing_model": routing_model or "N/A",
        "effective_provider": effective_provider or "N/A",
        "effective_model": effective_model or "N/A",
    }


_ANTIGRAVITY_NONFINAL_RE = re.compile(
    r"^\s*(i\s+will|i'll|i\s+am\s+going\s+to|let\s+me|i\s+need\s+to|i'll\s+now)\b",
    re.I,
)
_ANTIGRAVITY_PLACEHOLDER_RE = re.compile(r"^\s*#*\s*(handoff|completed|done)\s*#*\s*$", re.I)


def _antigravity_output_is_nonfinal(log_lines: list[str]) -> bool:
    content = [
        line.strip()
        for line in log_lines
        if line.strip() and not line.startswith("[solar-harness agy-multimodal] cmd=")
    ]
    if not content:
        return True
    first = content[0]
    joined = " ".join(content)
    if len(content) == 1 and _ANTIGRAVITY_PLACEHOLDER_RE.match(first):
        return True
    if _ANTIGRAVITY_NONFINAL_RE.match(first) and not re.search(
        r"\b(completed|verified|done|image_unsupported|smoke_ok|handoff)\b",
        joined,
        re.I,
    ):
        return True
    return False


def _dispatch_file_for_env(result_dir: Path, envelope: dict[str, Any]) -> Path | None:
    dispatch_text = str(envelope.get("dispatch_text") or "").strip()
    if dispatch_text:
        dispatch_file = result_dir / "dispatch.md"
        dispatch_file.write_text(dispatch_text, encoding="utf-8")
        return dispatch_file

    dispatch_file_value = str(envelope.get("dispatch_file") or "").strip()
    if not dispatch_file_value:
        return None

    dispatch_path = Path(dispatch_file_value).expanduser()
    if dispatch_path.exists():
        # Keep a local copy next to result.json for auditability while still
        # pointing the task at the canonical dispatch file.
        try:
            (result_dir / "dispatch.md").write_text(
                dispatch_path.read_text(encoding="utf-8", errors="replace"),
                encoding="utf-8",
            )
        except Exception:
            pass
        return dispatch_path
    return dispatch_path


def _materialize_envelope_context(result_dir: Path, envelope: dict) -> dict[str, str]:
    env: dict[str, str] = {}
    dispatch_file = _dispatch_file_for_env(result_dir, envelope)
    if dispatch_file is not None:
        env["SOLAR_MULTI_TASK_DISPATCH_FILE"] = str(dispatch_file)
        env["DISPATCH_FILE"] = str(dispatch_file)
    envelope_file = result_dir / "envelope.json"
    envelope_file.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    env["SOLAR_OPERATOR_ENVELOPE_JSON"] = str(envelope_file)
    handoff_path = str(envelope.get("handoff_path") or "").strip()
    if handoff_path:
        env["HANDOFF"] = handoff_path
    graph_path = str(envelope.get("graph_path") or "").strip()
    if graph_path:
        env["GRAPH"] = graph_path
    if bool(envelope.get("strict_filesystem_boundaries")):
        env["SOLAR_OPERATOR_STRICT_FS_SCOPE"] = "1"
    if isinstance(envelope.get("read_scope"), list):
        env["SOLAR_OPERATOR_READ_SCOPE_JSON"] = json.dumps(envelope["read_scope"], ensure_ascii=False)
    if isinstance(envelope.get("write_scope"), list):
        env["SOLAR_OPERATOR_WRITE_SCOPE_JSON"] = json.dumps(envelope["write_scope"], ensure_ascii=False)
    work_dir = str(envelope.get("work_dir") or "").strip()
    if not work_dir:
        sid = str(envelope.get("sprint_id") or "").strip()
        if sid:
            work_dir = str(HARNESS_DIR / "sprints" / sid / "workdir")
    if work_dir:
        try:
            Path(work_dir).expanduser().mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        env["WORK_DIR"] = work_dir
        env["CODEX_WORKDIR"] = work_dir
    if str(envelope.get("node_id") or "").strip():
        env["NODE_ID"] = str(envelope["node_id"])
    if str(envelope.get("task_id") or "").strip():
        env["TASK_ID"] = str(envelope["task_id"])
    if str(envelope.get("sprint_id") or "").strip():
        env["SID"] = str(envelope["sprint_id"])
    if _observability_enabled():
        identity_environment = {
            "DISPATCH_ID": envelope.get("dispatch_id"),
            "ATTEMPT_ID": envelope.get("attempt_id"),
            "CORRELATION_ID": envelope.get("correlation_id"),
            "CAUSATION_ID": envelope.get("causation_id"),
            "SOLAR_OBSERVABILITY_SPAN_ID": envelope.get("span_id"),
            "SOLAR_OBSERVABILITY_PARENT_SPAN_ID": envelope.get("parent_span_id"),
        }
        for name, value in identity_environment.items():
            if value not in {None, ""}:
                env[name] = str(value)

    allowed_output_roots = [
        HARNESS_DIR.expanduser().resolve(strict=False),
        SPRINTS_DIR.expanduser().resolve(strict=False),
        result_dir.expanduser().resolve(strict=False),
    ]
    if work_dir:
        allowed_output_roots.append(Path(work_dir).expanduser().resolve(strict=False))

    def authorized_output(raw: str) -> Path:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = result_dir / path
        resolved = path.resolve(strict=False)
        if not any(resolved == root or resolved.is_relative_to(root) for root in allowed_output_roots):
            raise ValueError(f"operator output outside Solar-authorized roots: {resolved}")
        return resolved

    result_path = str(envelope.get("result_path") or "").strip()
    if result_path:
        result_file = authorized_output(result_path)
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.touch(exist_ok=True)
        result_path = str(result_file)
        env["RESULT_PATH"] = result_path
        env["PM_RESULT_PATH"] = result_path
    allowed_outputs: list[str] = []
    output_publish_map: list[dict[str, str]] = []
    direct_write_roots = [result_dir.expanduser().resolve(strict=False)]
    if work_dir:
        direct_write_roots.append(Path(work_dir).expanduser().resolve(strict=False))
    for index, raw in enumerate(envelope.get("expected_artifacts") or []):
        if not str(raw or "").strip():
            continue
        path = authorized_output(str(raw).strip())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        if any(path == root or path.is_relative_to(root) for root in direct_write_roots):
            allowed_outputs.append(str(path))
            continue

        # Control-plane files such as task_graph.json are atomically replaced
        # while an operator is running. Landlock file rules follow the inode,
        # so an exact-path grant silently becomes read-only after replacement.
        # Give the worker a stable task-local inode and publish it only after
        # the sandboxed process has exited successfully.
        staging_dir = result_dir / "declared-outputs"
        staging_dir.mkdir(parents=True, exist_ok=True)
        staging_path = _staging_output_path(staging_dir, index, path)
        if path.is_file():
            shutil.copyfile(path, staging_path)
        else:
            staging_path.touch(exist_ok=True)
        allowed_outputs.append(str(staging_path))
        output_publish_map.append(
            {
                "write_path": str(staging_path),
                "publish_path": str(path),
                "initial_sha256": hashlib.sha256(staging_path.read_bytes()).hexdigest(),
            }
        )
    if result_path:
        allowed_outputs.append(str(Path(result_path).expanduser()))
    if allowed_outputs:
        env["SOLAR_OPERATOR_ALLOWED_OUTPUTS_JSON"] = json.dumps(
            sorted(set(allowed_outputs)), ensure_ascii=False
        )
    if output_publish_map:
        env["SOLAR_OPERATOR_OUTPUT_PUBLISH_MAP_JSON"] = json.dumps(
            output_publish_map, ensure_ascii=False
        )
    pm_context = str(envelope.get("pm_context") or "").strip()
    if pm_context:
        env["PM_CONTEXT"] = pm_context
    env["TASK_DIR"] = str(result_dir)
    env["OUTPUT_LOG"] = str(result_dir / "output.log")
    env["HARNESS_DIR"] = str(HARNESS_DIR)
    env["SPRINTS_DIR"] = str(SPRINTS_DIR)
    return env


def _staging_output_path(staging_dir: Path, index: int, publish_path: Path) -> Path:
    """Keep staged output paths below conservative Windows path-length limits."""
    candidate = staging_dir / f"{index:02d}-{publish_path.name}"
    if len(str(candidate)) < 240:
        return candidate
    digest = hashlib.sha256(str(publish_path).encode("utf-8")).hexdigest()[:16]
    suffix = publish_path.suffix[-12:] or ".out"
    shortened = staging_dir / f"{index:02d}-{digest}{suffix}"
    if len(str(shortened)) < 240:
        return shortened
    return staging_dir / str(index)


def _publish_staged_outputs(exec_env: dict[str, str]) -> list[str]:
    """Publish task-local declared outputs after the sandbox exits cleanly."""
    raw = exec_env.get("SOLAR_OPERATOR_OUTPUT_PUBLISH_MAP_JSON") or "[]"
    mappings = json.loads(raw)
    if not isinstance(mappings, list):
        raise ValueError("operator output publish map must be a list")

    published: list[str] = []
    for index, item in enumerate(mappings):
        if not isinstance(item, dict):
            raise ValueError("operator output publish map entries must be objects")
        write_path = Path(str(item.get("write_path") or "")).expanduser()
        publish_path = Path(str(item.get("publish_path") or "")).expanduser()
        if not write_path.is_file() or write_path.stat().st_size <= 0:
            raise ValueError(f"declared output was not materialized: {write_path}")
        initial_sha256 = str(item.get("initial_sha256") or "").strip()
        current_sha256 = hashlib.sha256(write_path.read_bytes()).hexdigest()
        if initial_sha256 and current_sha256 == initial_sha256:
            raise ValueError(f"declared output was not updated: {write_path}")
        publish_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = publish_path.with_name(
            f".{publish_path.name}.operator-publish-{os.getpid()}-{index}.tmp"
        )
        try:
            shutil.copyfile(write_path, temporary)
            os.replace(temporary, publish_path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        published.append(str(publish_path))
    return published


def _claude_print_command(config: dict[str, Any]) -> list[str]:
    model = _claude_model_arg(str(config.get("model") or "sonnet"))
    empty_mcp = HARNESS_DIR / "config" / "empty-mcp.json"
    provider = str(config.get("provider") or "").strip().lower()
    provider_env: list[str] = []
    if provider in {"glm", "zhipu", "zhipuai"}:
        provider_env = [
            'source "$HARNESS_DIR/model-config.sh" 2>/dev/null || true',
            'export ANTHROPIC_BASE_URL="${ZHIPU_BASE_URL:-https://api.z.ai/api/anthropic}"',
            'export ANTHROPIC_API_KEY="${ZHIPU_API_KEY:-${ZHIPU_AUTH_TOKEN:-}}"',
            'export ANTHROPIC_DEFAULT_OPUS_MODEL="${ZHIPU_MODEL:-GLM-5.1}"',
        ]
    command = "\n".join([
        *provider_env,
        "export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
        "export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1",
        "export DISABLE_NON_ESSENTIAL_MODEL_CALLS=1",
        "export CLAUDE_CODE_MAX_OUTPUT_TOKENS=${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-12000}",
        (
            "claude --dangerously-skip-permissions "
            "--permission-mode bypassPermissions "
            f"--model {shlex.quote(model)} "
            f"--add-dir {shlex.quote(str(HARNESS_DIR))} "
            f"--strict-mcp-config --mcp-config {shlex.quote(str(empty_mcp))} "
            '-p "$(cat "$DISPATCH_FILE")"'
        ),
    ])
    return ["bash", "-lc", command]



def _register_worker_process(pid: int, envelope: dict) -> None:
    """Register a spawned task worker in the harness run registry.

    G4-lite run 2: workers are spawned with start_new_session=True (their own
    session — deliberate, so a worker survives an operatord restart mid-task),
    which also means no teardown owned them: the repair builder (PID 572280)
    outlived `solar-harness kill` and kept writing after the sprint's truthful
    terminal. Registration hands ownership to the ONE existing teardown
    (run_process_registry.teardown --run-id harness), with a cmdline snapshot
    for identity-safe kills. Best-effort by design: a terminal run refuses
    registration (the respawn-past-teardown guard) and no registry failure
    may break task execution."""
    try:
        import run_process_registry as _rpr

        _rpr.register(
            "harness",
            "operator-task",
            int(pid),
            meta={
                "operator_id": str(envelope.get("operator_id") or ""),
                "task_id": str(envelope.get("task_id") or ""),
                "sprint_id": str(envelope.get("sprint_id") or ""),
                "node_id": str(envelope.get("node_id") or ""),
            },
            harness_dir=HARNESS_DIR,
        )
    except Exception as exc:
        _info(f"worker registry registration skipped: {exc}")


def _build_command(
    config: dict,
    envelope: dict,
    exec_env: dict[str, str] | None = None,
) -> list[str]:
    """Return the shell command list to execute for this task.

    If the envelope carries an explicit ``command`` override, or if a command
    backend provides a configured launch command, operatord executes that
    command through a shell adapter. For any unsupported backend we still
    default to a safe echo so the daemon can be exercised without credentials
    in test/CI environments.
    """
    backend: str = str(config.get("backend", "local")).lower()

    # Explicit command in the envelope takes highest priority.
    cmd_val = envelope.get("command")
    # A scheduler envelope normally repeats the registry command.  Perform
    # native-Windows translation before treating that repeated value as an
    # arbitrary shell override; otherwise the POSIX snippet expands
    # ``$HARNESS_DIR`` under the wrong shell and bypasses the native branch
    # below.
    effective_command = str(cmd_val or config.get("command") or "").strip()
    if os.name == "nt" and _is_codex_command_operator(config) and "codex_operator.py" in effective_command:
        return [sys.executable, str(HARNESS_DIR / "tools" / "codex_operator.py")]
    if (
        os.name == "nt"
        and backend == "command"
        and "plugins/autosci/bin/autosci_bridge.py" in effective_command.replace("\\", "/")
    ):
        envelope_path = str((exec_env or {}).get("SOLAR_OPERATOR_ENVELOPE_JSON") or "").strip()
        action_match = re.search(r"--action\s+[\"']?([A-Za-z0-9_-]+)", effective_command)
        if not envelope_path or action_match is None:
            return [
                sys.executable,
                "-c",
                "import sys; print('AutoSci bridge action or envelope is unavailable', file=sys.stderr); raise SystemExit(127)",
            ]
        return [
            str(os.environ.get("SOLAR_AUTOSCI_PYTHON") or sys.executable),
            str(HARNESS_DIR / "plugins" / "autosci" / "bin" / "autosci_bridge.py"),
            "run",
            "--action",
            action_match.group(1),
            "--envelope",
            envelope_path,
        ]
    if (
        os.name == "nt"
        and backend == "command"
        and "plugins/autosci/bin/fixed_research_node_adapter.py" in effective_command.replace("\\", "/")
    ):
        envelope_path = str((exec_env or {}).get("SOLAR_OPERATOR_ENVELOPE_JSON") or "").strip()
        if not envelope_path:
            return [
                sys.executable,
                "-c",
                "import sys; print('fixed research envelope path is unavailable', file=sys.stderr); raise SystemExit(127)",
            ]
        return [
            str(os.environ.get("SOLAR_AUTOSCI_PYTHON") or sys.executable),
            str(HARNESS_DIR / "plugins" / "autosci" / "bin" / "fixed_research_node_adapter.py"),
            "--envelope",
            envelope_path,
        ]
    if backend == "research_operator_registry":
        envelope_path = str((exec_env or {}).get("SOLAR_OPERATOR_ENVELOPE_JSON") or "").strip()
        adapter = HARNESS_DIR / "tools" / "research_operator_registry_adapter.py"
        if not envelope_path or not adapter.is_file():
            reason = "registry envelope path is unavailable" if not envelope_path else "registry adapter is unavailable"
            return [
                sys.executable,
                "-c",
                f"import sys; print({reason!r}, file=sys.stderr); raise SystemExit(127)",
            ]
        return [
            str(os.environ.get("SOLAR_AUTOSCI_PYTHON") or sys.executable),
            str(adapter),
            "--envelope",
            envelope_path,
        ]
    if cmd_val:
        if isinstance(cmd_val, list):
            return [str(c) for c in cmd_val]
        command_text = str(cmd_val)
        env_ref = re.fullmatch(
            r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))",
            command_text,
        )
        if env_ref:
            variable = env_ref.group(1) or env_ref.group(2)
            command_text = os.environ.get(variable, "").strip()
            if not command_text:
                return [
                    sys.executable,
                    "-c",
                    (
                        "import sys; "
                        f"print('operator command environment variable {variable} is not set', file=sys.stderr); "
                        "raise SystemExit(127)"
                    ),
                ]
        try:
            command_argv = json.loads(command_text)
        except json.JSONDecodeError:
            command_argv = None
        if isinstance(command_argv, list) and command_argv and all(
            isinstance(part, str) and part for part in command_argv
        ):
            return command_argv
        # An explicit envelope command executes in the environment materialized
        # by Solar.  A login shell may source user startup files that replace or
        # unset those variables (including a bounded command indirection such
        # as ``$COMMAND_AGENT``), turning the task into an empty successful
        # command. Resolve an exact environment-variable indirection once so
        # shell quoting in its value is honored, then preserve the task
        # environment for execution. Configured provider launches retain their
        # existing login-shell behavior below.
        return ["bash", "-c", command_text]

    # A physical operator may declare argv directly when shell translation is
    # undesirable (notably native Windows paths being handed to WSL bash).
    launch_argv = _configured_launch_argv(config)
    if backend == "command" and launch_argv:
        return launch_argv

    # The physical-operator registry is shared with macOS and historically
    # stores Codex launches as POSIX shell snippets.  On native Windows those
    # snippets cannot execute (``VAR=x``, ``$HARNESS_DIR``, ``python3``, and
    # ``/opt/homebrew/bin`` are all POSIX-specific).  Launch the same provider
    # wrapper directly with the active Python runtime; the wrapper resolves the
    # installed ``codex.exe`` and consumes the dispatch/envelope environment.
    if os.name == "nt" and _is_codex_command_operator(config):
        return [sys.executable, str(HARNESS_DIR / "tools" / "codex_operator.py")]

    configured_command = str(config.get("command") or "").strip()
    if (
        os.name == "nt"
        and backend == "command"
        and "plugins/autosci/bin/fixed_research_node_adapter.py" in configured_command.replace("\\", "/")
    ):
        envelope_path = str((exec_env or {}).get("SOLAR_OPERATOR_ENVELOPE_JSON") or "").strip()
        if not envelope_path:
            return [
                sys.executable,
                "-c",
                "import sys; print('fixed research envelope path is unavailable', file=sys.stderr); raise SystemExit(127)",
            ]
        return [
            str(os.environ.get("SOLAR_AUTOSCI_PYTHON") or sys.executable),
            str(HARNESS_DIR / "plugins" / "autosci" / "bin" / "fixed_research_node_adapter.py"),
            "--envelope",
            envelope_path,
        ]

    launch_cmd = _configured_launch_command(config)
    if backend == "command" and launch_cmd:
        return ["bash", "-lc", launch_cmd]
    if backend == "command":
        if configured_command:
            return ["bash", "-lc", configured_command]

    if backend == "claude-cli":
        return _claude_print_command(config)

    task_id: str = str(envelope.get("task_id", "unknown"))
    objective: str = str(envelope.get("objective", ""))[:120]

    if backend in ("local", "dummy", "echo"):
        return [
            sys.executable,
            "-c",
            (
                "import time; "
                f"print({f'operatord: task={task_id}'!r}, flush=True); "
                f"print({f'objective={objective}'!r}, flush=True); "
                "time.sleep(0.05); "
                "print('operatord: completed', flush=True)"
            ),
        ]

    # Real backends (claude-cli, agy, etc.) in non-interactive daemon context:
    # emit a safe placeholder so the daemon lifecycle can be validated without
    # actually spawning an AI process.
    return [
        "sh",
        "-c",
        (
            f"echo 'operatord: backend={backend} task={task_id}'; "
            "echo 'operatord: local-stub exit 0'; "
            "sleep 0.05"
        ),
    ]


def _is_pm_dispatch_task(envelope: dict[str, Any]) -> bool:
    task_id = str(envelope.get("task_id") or "").strip()
    result_path = str(envelope.get("result_path") or "").strip()
    return task_id.startswith("pm-") or result_path.endswith(".pm-result.md")


def _pm_result_path(envelope: dict[str, Any]) -> Path | None:
    value = str(envelope.get("result_path") or "").strip()
    if not value:
        return None
    return Path(value).expanduser()


def _pm_dispatch_complete_command(task_id: str) -> list[str]:
    return [sys.executable, str(HARNESS_DIR / "tools" / "pm_dispatch.py"), "complete", "--task-id", task_id]


def _pm_dispatch_fail_command(task_id: str, status: str, reason: str) -> list[str]:
    return [
        sys.executable,
        str(HARNESS_DIR / "tools" / "pm_dispatch.py"),
        "fail",
        "--task-id",
        task_id,
        "--status",
        status,
        "--reason",
        reason[:2000],
    ]


def _parse_utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _int_value(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _failure_flow_control_settings(config: dict[str, Any], envelope: dict[str, Any]) -> dict[str, int]:
    flow_control = dict(config.get("flow_control") or {})
    return {
        "rate_limit_cooldown_seconds": _int_value(
            envelope.get("rate_limit_cooldown_seconds")
            or os.environ.get("SOLAR_OPERATOR_RATE_LIMIT_COOLDOWN_SECONDS")
            or flow_control.get("rate_limit_cooldown_seconds"),
            3600,
        ),
        "auth_cooldown_seconds": _int_value(
            envelope.get("auth_cooldown_seconds")
            or os.environ.get("SOLAR_OPERATOR_AUTH_COOLDOWN_SECONDS")
            or flow_control.get("auth_cooldown_seconds"),
            21600,
        ),
    }


def _apply_failure_runtime_override(
    *,
    operator_id: str,
    config: dict[str, Any],
    envelope: dict[str, Any],
    task_dir: Path,
    failure_text: str,
) -> dict[str, Any]:
    import operator_flow_control as ofc  # noqa: E402

    settings = _failure_flow_control_settings(config, envelope)
    return ofc.apply_failure_flow_control(
        task_dir,
        operator_id=operator_id,
        failure_text=failure_text,
        rate_limit_cooldown_seconds=int(settings["rate_limit_cooldown_seconds"]),
        auth_cooldown_seconds=int(settings["auth_cooldown_seconds"]),
        defer_on_cooldown=False,
        defer_on_auth=False,
    )


_TERMINAL_EXCEPTION_RE = re.compile(
    r"^(?:[A-Za-z_][A-Za-z0-9_]*\.)*[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception):\s*"
)


def _failure_runtime_override_skip_reason(failure_text: str) -> str:
    """Keep local closeout/orchestration failures from poisoning operator health.

    A worker log can contain a recoverable provider error before a later local
    scheduler, path, or configuration exception.  Failure flow-control scans
    the whole tail, so without this causal guard that stale provider text can
    put an otherwise healthy operator into cooldown.  A terminal provider
    exception still reaches the normal classifier.
    """
    terminal_exception = ""
    for line in reversed(str(failure_text or "").splitlines()):
        candidate = line.strip()
        if _TERMINAL_EXCEPTION_RE.match(candidate):
            terminal_exception = candidate
            break
    if not terminal_exception:
        return ""

    import operator_flow_control as ofc  # noqa: E402

    if ofc.classify_failure_state(terminal_exception):
        return ""
    return "terminal_local_failure"


# ---------------------------------------------------------------------------
# Subcommand: daemon
# ---------------------------------------------------------------------------


def cmd_daemon(args: argparse.Namespace) -> int:
    """Run the operator as a persistent daemon (or process one task with --once)."""
    import selectors
    import signal
    import subprocess
    import time

    from operator_runtime import (  # noqa: E402
        acquire_operator_lease,
        get_operator_lease,
        get_operator_runtime_state,
        list_inbox_tasks,
        release_operator_lease,
        update_operator_lease_metadata,
        update_operator_lease_state,
        write_heartbeat,
        write_result,
        HARNESS_DIR as _RT_HARNESS_DIR,
        OPERATOR_RESULTS_DIR,
    )

    operator_id: str = args.operator
    once: bool = args.once
    poll_interval: float = args.poll_interval
    once_max_wait_seconds: float = float(args.once_max_wait_seconds)
    task_timeout_seconds: float = float(
        os.environ.get("SOLAR_OPERATORD_TASK_TIMEOUT_SECONDS", "3600")
    )
    shutdown_request_value = os.environ.get("SOLAR_OPERATORD_SHUTDOWN_FILE", "").strip()
    shutdown_request_path = Path(shutdown_request_value) if shutdown_request_value else None
    config = _get_operator(operator_id)

    if not config.get("enabled", False) and not args.force:
        _info(
            f"Operator '{operator_id}' is disabled. "
            "Pass --force to proceed anyway."
        )
        return 1

    resolved_persona: str = config.get("persona") or config.get("role", "")
    model_route = _model_route_metadata(config)

    # ── Signal handling ───────────────────────────────────────────────────────
    _state: dict[str, Any] = {
        "drain": False,
        "current_state": "idle",
        "current_proc": None,
        "current_task_id": None,
        "drain_signal": None,
    }

    def _pid_exists(pid: int | None) -> bool:
        if not pid or pid <= 0:
            return False
        if os.name == "nt":
            import _winapi

            try:
                handle = _winapi.OpenProcess(0x1000, False, int(pid))
            except OSError:
                return False
            try:
                return _winapi.GetExitCodeProcess(handle) == 259
            finally:
                _winapi.CloseHandle(handle)
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _terminate_worker(pid: int | None, *, reason: str) -> bool:
        if not _pid_exists(pid):
            return False
        if os.name == "nt":
            import _winapi

            current_proc = _state.get("current_proc")
            if current_proc is not None and int(current_proc.pid) == int(pid):
                try:
                    current_proc.terminate()
                except OSError as exc:
                    _info(f"Unable to terminate Windows worker pid={pid} ({reason}): {exc}")
                    return False
                _info(f"Terminated Windows worker pid={pid} ({reason})")
                return True
            try:
                handle = _winapi.OpenProcess(0x0001, False, int(pid))
            except OSError as exc:
                _info(f"Unable to open Windows worker pid={pid} ({reason}): {exc}")
                return False
            try:
                _winapi.TerminateProcess(handle, 1)
            finally:
                _winapi.CloseHandle(handle)
            _info(f"Terminated stale Windows worker pid={pid} ({reason})")
            return True
        try:
            os.killpg(pid, signal.SIGTERM)
            _info(f"Sent SIGTERM to worker process group pid={pid} ({reason})")
            _observe(
                "operator.teardown.term_sent",
                component="operatord",
                operator=operator_id,
                operation="operator_teardown",
                operation_id=_observation_id("operation", operator_id, pid, reason, "teardown"),
                phase="point",
                status="sent",
                data={"pid": int(pid), "signal": "SIGTERM", "reason": reason, "target_kind": "process_group"},
                provenance="observed",
            )
            return True
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
                _info(f"Sent SIGTERM to worker pid={pid} ({reason})")
                _observe(
                    "operator.teardown.term_sent",
                    component="operatord",
                    operator=operator_id,
                    operation="operator_teardown",
                    operation_id=_observation_id("operation", operator_id, pid, reason, "teardown"),
                    phase="point",
                    status="sent",
                    data={"pid": int(pid), "signal": "SIGTERM", "reason": reason, "target_kind": "process"},
                    provenance="observed",
                )
                return True
            except Exception as exc:
                _info(f"Unable to terminate worker pid={pid} ({reason}): {exc}")
                return False

    def _kill_worker_force(pid: int | None, *, reason: str) -> bool:
        if not _pid_exists(pid):
            return False
        if os.name == "nt":
            return _terminate_worker(pid, reason=reason)
        try:
            os.killpg(pid, signal.SIGKILL)
            _info(f"Sent SIGKILL to worker process group pid={pid} ({reason})")
            _observe(
                "operator.teardown.kill_sent",
                component="operatord",
                operator=operator_id,
                operation="operator_teardown",
                operation_id=_observation_id("operation", operator_id, pid, reason, "teardown"),
                phase="point",
                status="sent",
                data={"pid": int(pid), "signal": "SIGKILL", "reason": reason, "target_kind": "process_group"},
                provenance="observed",
            )
            return True
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
                _info(f"Sent SIGKILL to worker pid={pid} ({reason})")
                _observe(
                    "operator.teardown.kill_sent",
                    component="operatord",
                    operator=operator_id,
                    operation="operator_teardown",
                    operation_id=_observation_id("operation", operator_id, pid, reason, "teardown"),
                    phase="point",
                    status="sent",
                    data={"pid": int(pid), "signal": "SIGKILL", "reason": reason, "target_kind": "process"},
                    provenance="observed",
                )
                return True
            except Exception as exc:
                _info(f"Unable to force kill worker pid={pid} ({reason}): {exc}")
                return False

    def _handle_signal(signum: int, frame: Any) -> None:
        _info(f"Signal {signum} received — transitioning to draining")
        _state["drain"] = True
        _state["drain_signal"] = int(signum)
        _state["current_state"] = "draining"
        proc = _state.get("current_proc")
        if proc is not None:
            try:
                _terminate_worker(int(proc.pid), reason=f"signal:{signum}")
            except Exception:
                pass
        write_heartbeat(
            operator_id,
            "draining",
            current_task_id=_state.get("current_task_id"),
            worker_pid=int(proc.pid) if proc is not None else None,
            resolved_persona=resolved_persona,
            model_route=model_route,
        )

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handle_signal)

    def _consume_shutdown_request() -> bool:
        if shutdown_request_path is None or not shutdown_request_path.is_file():
            return False
        try:
            shutdown_request_path.unlink()
        except FileNotFoundError:
            return False
        _handle_signal(signal.SIGTERM, None)
        return True

    _info(
        f"Daemon starting — operator_id={operator_id} "
        f"once={once} poll_interval={poll_interval}s"
    )
    daemon_lock_fh, daemon_pid_path = _acquire_daemon_slot(operator_id, once=once)
    if daemon_lock_fh is None:
        return 0
    write_heartbeat(operator_id, "idle", resolved_persona=resolved_persona, model_route=model_route)
    _state["current_state"] = "idle"

    processed: int = 0
    loop_started_at = time.monotonic()

    def _once_wait_expired() -> bool:
        if not once or processed > 0:
            return False
        if once_max_wait_seconds <= 0:
            return False
        return (time.monotonic() - loop_started_at) >= once_max_wait_seconds

    try:
        while True:
            _consume_shutdown_request()
            # ── Drain check ───────────────────────────────────────────────────────
            if _state["drain"]:
                _info("Drain flag set — exiting daemon loop")
                write_heartbeat(operator_id, "idle", resolved_persona=resolved_persona, model_route=model_route)
                break

            lease_for_telemetry = get_operator_lease(operator_id)
            telemetry_task_id = None
            if lease_for_telemetry and _state["current_state"] != "running":
                telemetry_task_id = str(lease_for_telemetry.get("task_id") or "") or None

            # ── Heartbeat ─────────────────────────────────────────────────────────
            write_heartbeat(
                operator_id,
                _state["current_state"],
                current_task_id=telemetry_task_id,
                worker_pid=int(lease_for_telemetry.get("worker_pid")) if lease_for_telemetry and str(lease_for_telemetry.get("worker_pid") or "").isdigit() else None,
                resolved_persona=resolved_persona,
                model_route=model_route,
            )

            # ── Poll inbox ────────────────────────────────────────────────────────
            tasks = list_inbox_tasks(operator_id)

            if not tasks:
                if once:
                    if processed > 0:
                        # Already processed the one task; exit normally.
                        break
                    if _once_wait_expired():
                        _info(
                            f"Once mode max wait exceeded with no inbox task "
                            f"(operator_id={operator_id}, waited={once_max_wait_seconds}s)"
                        )
                        break
                    # Nothing yet — keep waiting.
                time.sleep(poll_interval)
                continue

            # ── Claim first available task ────────────────────────────────────────
            # If we already hold a lease for a specific task, prioritise that task
            # from the inbox so a stale head (leftover from a previous failed run)
            # cannot block the queue forever.
            lease = get_operator_lease(operator_id)
            leased_task_id = lease.get("task_id") if lease else None

            if leased_task_id and leased_task_id != tasks[0][0]:
                # Active lease is for a task that is NOT at the head.
                matching = [(tid, env, p) for tid, env, p in tasks if tid == leased_task_id]
                if matching:
                    # Re-order: leased task first.
                    tasks = matching + [t for t in tasks if t[0] != leased_task_id]
                    _info(
                        f"Leased task {leased_task_id} is not inbox head; "
                        f"re-ordered tasks to process leased task first"
                    )
                else:
                    # Orphaned lease — leased task is absent from inbox (already
                    # processed or never arrived).  Release the stale lease so the
                    # head can be claimed on the next cycle.
                    _info(
                        f"Releasing orphaned lease for task {leased_task_id} "
                        f"(task not found in inbox)"
                    )
                    release_operator_lease(operator_id, reason="orphaned_lease_absent_task")
                    lease = None
                    leased_task_id = None

            task_id, envelope, envelope_path = tasks[0]
            observation_ids = {
                "sprint_id": str(envelope.get("sprint_id") or "") or None,
                "node_id": str(envelope.get("node_id") or "") or None,
                "task_id": task_id,
                "dispatch_id": str(envelope.get("dispatch_id") or task_id),
                "attempt_id": str(envelope.get("attempt_id") or "1"),
                "correlation_id": str(envelope.get("correlation_id") or task_id),
                "causation_id": str(envelope.get("causation_id") or envelope.get("dispatch_id") or task_id),
            }
            task_operation_id = _observation_id(
                "operation",
                observation_ids["dispatch_id"],
                observation_ids["attempt_id"],
                "operatord-task",
            )
            task_span_id = _observation_id("span", task_operation_id)
            observation_ids["span_id"] = task_span_id
            observation_ids["parent_span_id"] = str(envelope.get("span_id") or "") or None

            if lease is None or lease.get("task_id") != task_id:
                recovered_lease = None
                if lease is None:
                    try:
                        recovered_lease = acquire_operator_lease(
                            operator_id=operator_id,
                            task_id=task_id,
                            sprint_id=str(envelope.get("sprint_id") or ""),
                            node_id=str(envelope.get("node_id") or ""),
                            ttl_seconds=int(envelope.get("lease_ttl_seconds") or 3600),
                            initial_state="leased",
                        )
                        lease = recovered_lease
                        _info(f"Recovered missing/expired lease for task {task_id}")
                    except Exception as exc:
                        _info(f"Lease recovery failed for task {task_id}: {exc}")
                # Lease missing or for a different task; skip and wait.
                if lease is not None and lease.get("task_id") == task_id:
                    pass
                else:
                    _info(
                        f"No valid lease found for task {task_id} "
                        f"(current lease task: {lease.get('task_id') if lease else 'none'})"
                    )
                    if _once_wait_expired():
                        _info(
                            f"Once mode max wait exceeded while waiting for valid lease "
                            f"(operator_id={operator_id}, task_id={task_id})"
                        )
                        break
                    time.sleep(poll_interval)
                    continue

            if lease.get("state") == "running":
                status_snapshot = _read_status_snapshot(operator_id)
                status_state = str(status_snapshot.get("state") or "").strip().lower()
                status_task_id = str(status_snapshot.get("current_task_id") or "").strip()
                worker_pid_raw = lease.get("worker_pid")
                daemon_pid_raw = lease.get("daemon_pid")
                try:
                    worker_pid = int(worker_pid_raw) if worker_pid_raw is not None else None
                except Exception:
                    worker_pid = None
                try:
                    daemon_pid = int(daemon_pid_raw) if daemon_pid_raw is not None else None
                except Exception:
                    daemon_pid = None

                stale_reasons: list[str] = []
                if status_state != "running":
                    stale_reasons.append(f"status.state={status_state or 'N/A'}")
                if status_task_id != task_id:
                    stale_reasons.append(f"status.current_task_id={status_task_id or 'N/A'}")
                if worker_pid is not None and not _pid_exists(worker_pid):
                    stale_reasons.append(f"worker_pid_dead={worker_pid}")
                if daemon_pid is not None and not _pid_exists(daemon_pid):
                    stale_reasons.append(f"daemon_pid_dead={daemon_pid}")

                if stale_reasons:
                    _info(
                        f"Recovering stale running lease for task {task_id} "
                        f"({' ; '.join(stale_reasons)})"
                    )
                    if worker_pid is not None and _pid_exists(worker_pid):
                        _terminate_worker(worker_pid, reason="stale_running_lease_recovery")
                    try:
                        update_operator_lease_metadata(
                            operator_id,
                            worker_pid=None,
                            daemon_pid=None,
                        )
                        update_operator_lease_state(operator_id, "leased")
                    except RuntimeError as exc:
                        _info(f"Unable to recover stale running lease: {exc}")
                    else:
                        time.sleep(poll_interval)
                        continue

            if lease.get("state") not in ("leased",):
                _info(f"Task {task_id} lease state={lease.get('state')} — skipping")
                if _once_wait_expired():
                    _info(
                        f"Once mode max wait exceeded while lease state remained "
                        f"{lease.get('state')} for task {task_id}"
                    )
                    break
                time.sleep(poll_interval)
                continue

            _info(f"Claiming task {task_id}")
            claim_started_ns = time.monotonic_ns()
            try:
                update_operator_lease_state(operator_id, "running")
            except RuntimeError as exc:
                _info(f"Cannot transition lease to running: {exc}")
                if _once_wait_expired():
                    _info(
                        f"Once mode max wait exceeded while transitioning to running "
                        f"(operator_id={operator_id}, task_id={task_id})"
                    )
                    break
                time.sleep(poll_interval)
                continue

            _observe(
                "operator.task.claimed",
                component="operatord",
                operator=operator_id,
                operation="operator_task",
                operation_id=task_operation_id,
                phase="started",
                identifiers=observation_ids,
                data={
                    "lease_state": "running",
                    "claim_duration_ms": (time.monotonic_ns() - claim_started_ns) / 1_000_000,
                    "provider": model_route.get("effective_provider"),
                    "model": model_route.get("effective_model"),
                },
                provenance="observed",
            )

            _state["current_state"] = "running"
            write_heartbeat(
                operator_id,
                "running",
                current_task_id=task_id,
                resolved_persona=resolved_persona,
                model_route=model_route,
            )

            # ── Execute ───────────────────────────────────────────────────────────
            sprint_id: str = str(envelope.get("sprint_id", ""))
            node_id: str = str(envelope.get("node_id", ""))
            started_at: str = _now_utc()
            result_status: str = "failed"
            exit_code: int = -1
            log_lines: list[str] = []
            worker_operation_id = _observation_id("operation", task_operation_id, "worker")
            worker_span_id = _observation_id("span", worker_operation_id)
            worker_ids = dict(observation_ids)
            worker_ids["span_id"] = worker_span_id
            worker_ids["parent_span_id"] = task_span_id
            worker_started = False
            worker_terminal_emitted = False

            result_dir = OPERATOR_RESULTS_DIR / operator_id / task_id
            result_dir.mkdir(parents=True, exist_ok=True)
            log_path = result_dir / "output.log"
            exec_env = os.environ.copy()
            child_envelope = dict(envelope)
            if _observability_enabled():
                child_envelope["span_id"] = worker_span_id
                child_envelope["parent_span_id"] = task_span_id
                child_envelope["causation_id"] = observation_ids["dispatch_id"]
            try:
                exec_env.update(_materialize_envelope_context(result_dir, child_envelope))
            except Exception as exc:
                failure = f"operator envelope materialization failed: {type(exc).__name__}: {exc}"
                _info(failure)
                log_path.write_text(f"[ERROR] {failure}\n", encoding="utf-8")
                finished_at = _now_utc()
                result_path = write_result(
                    operator_id=operator_id,
                    task_id=task_id,
                    sprint_id=sprint_id,
                    node_id=node_id,
                    status="failed_envelope_materialization",
                    exit_code=78,
                    started_at=started_at,
                    finished_at=finished_at,
                    log_tail=f"[ERROR] {failure}",
                    model_route=model_route,
                    graph_path=envelope.get("graph_path"),
                )
                _info(f"Result written: {result_path}")
                try:
                    envelope_path.unlink()
                except Exception:
                    pass
                try:
                    release_operator_lease(operator_id, reason="failed_envelope_materialization")
                except Exception:
                    pass
                _state["current_proc"] = None
                _state["current_task_id"] = None
                _state["current_state"] = "idle"
                processed += 1
                write_heartbeat(
                    operator_id,
                    "idle",
                    resolved_persona=resolved_persona,
                    model_route=model_route,
                )
                if once:
                    break
                time.sleep(poll_interval)
                continue
            exec_env.update(_command_operator_environment(config))
            pm_result_path = _pm_result_path(envelope) if _is_pm_dispatch_task(envelope) else None
            if pm_result_path is not None:
                try:
                    pm_result_path.parent.mkdir(parents=True, exist_ok=True)
                    # Keep the exact output inode present for kernel-enforced
                    # Landlock scopes.  Removing it here makes the later
                    # file-level rule unusable because creating the directory
                    # entry would require write access to the whole sprints
                    # directory.  Truncation still clears stale content and
                    # refreshes mtime without widening the operator's scope.
                    pm_result_path.write_text("", encoding="utf-8")
                except Exception as exc:
                    _info(f"Unable to prepare pm result {pm_result_path}: {exc}")

            cmd = _build_command(config, envelope, exec_env)
            _info(f"Executing: {' '.join(shlex.quote(part) for part in cmd[:8])}")

            try:
                timed_out = False
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=exec_env,
                    start_new_session=os.name != "nt",
                )
                worker_started_ns = time.monotonic_ns()
                first_output_observed = False
                worker_started = True
                _state["current_proc"] = proc
                _state["current_task_id"] = task_id
                _register_worker_process(proc.pid, envelope)
                update_operator_lease_metadata(
                    operator_id,
                    worker_pid=int(proc.pid),
                    daemon_pid=int(os.getpid()),
                )
                write_heartbeat(
                    operator_id,
                    "running",
                    current_task_id=task_id,
                    worker_pid=int(proc.pid),
                    resolved_persona=resolved_persona,
                    model_route=model_route,
                )
                _observe(
                    "operator.worker.started",
                    component="operatord",
                    operator=operator_id,
                    operation="operator_worker",
                    operation_id=worker_operation_id,
                    phase="started",
                    identifiers=worker_ids,
                    data={
                        "pid": int(proc.pid),
                        "provider": model_route.get("effective_provider"),
                        "model": model_route.get("effective_model"),
                    },
                    provenance="observed",
                )

                with open(log_path, "w", encoding="utf-8") as log_f:
                    assert proc.stdout is not None
                    proc_started_at = time.monotonic()
                    last_runtime_heartbeat_at = proc_started_at

                    line_queue = None
                    reader_thread = None
                    selector = None
                    if os.name == "nt":
                        # Windows selectors only accept sockets, not subprocess
                        # pipe handles.  A bounded reader thread keeps the same
                        # streaming/heartbeat behavior without WSAStartup errors.
                        import queue
                        import threading

                        line_queue = queue.Queue()

                        def _read_output() -> None:
                            assert proc.stdout is not None
                            for output_line in proc.stdout:
                                line_queue.put(output_line)
                            line_queue.put(None)

                        reader_thread = threading.Thread(target=_read_output, daemon=True)
                        reader_thread.start()
                    else:
                        selector = selectors.DefaultSelector()
                        selector.register(proc.stdout, selectors.EVENT_READ)

                    while True:
                        _consume_shutdown_request()
                        now_monotonic = time.monotonic()
                        if now_monotonic - last_runtime_heartbeat_at >= 15:
                            write_heartbeat(
                                operator_id,
                                "running",
                                current_task_id=task_id,
                                worker_pid=int(proc.pid),
                                resolved_persona=resolved_persona,
                                model_route=model_route,
                            )
                            last_runtime_heartbeat_at = now_monotonic

                        if task_timeout_seconds > 0 and (time.monotonic() - proc_started_at) >= task_timeout_seconds:
                            timed_out = True
                            log_lines.append(
                                f"[ERROR] task timeout after {int(task_timeout_seconds)}s"
                            )
                            _terminate_worker(int(proc.pid), reason="task_timeout")
                            try:
                                proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                _kill_worker_force(int(proc.pid), reason="task_timeout_escalation")
                                try:
                                    proc.wait(timeout=5)
                                finally:
                                    survivor = _pid_exists(int(proc.pid))
                                    _observe(
                                        "operator.teardown.survivors_measured",
                                        component="operatord",
                                        operator=operator_id,
                                        operation="operator_teardown",
                                        operation_id=_observation_id("operation", operator_id, proc.pid, "task_timeout", "teardown"),
                                        phase="point",
                                        status="survivors" if survivor else "clear",
                                        data={"survivor_count": int(survivor), "survivor_pids": [int(proc.pid)] if survivor else []},
                                        provenance="observed",
                                    )
                            else:
                                _observe(
                                    "operator.teardown.survivors_measured",
                                    component="operatord",
                                    operator=operator_id,
                                    operation="operator_teardown",
                                    operation_id=_observation_id("operation", operator_id, proc.pid, "task_timeout", "teardown"),
                                    phase="point",
                                    status="clear",
                                    data={"survivor_count": 0, "survivor_pids": []},
                                    provenance="observed",
                                )
                            break

                        if line_queue is not None:
                            try:
                                line = line_queue.get(timeout=0.5)
                            except queue.Empty:
                                if proc.poll() is not None and reader_thread is not None and not reader_thread.is_alive():
                                    break
                                continue
                            if line is None:
                                break
                            lines = [line]
                        else:
                            assert selector is not None
                            events = selector.select(timeout=0.5)
                            if not events:
                                if proc.poll() is not None:
                                    break
                                continue
                            lines = [key.fileobj.readline() for key, _mask in events]

                        saw_eof = False
                        for line in lines:
                            if not line:
                                saw_eof = True
                                continue
                            if not first_output_observed:
                                first_output_observed = True
                                _observe(
                                    "operator.worker.first_output",
                                    component="operatord",
                                    operator=operator_id,
                                    operation="operator_worker",
                                    operation_id=worker_operation_id,
                                    phase="progress",
                                    identifiers=worker_ids,
                                    data={
                                        "elapsed_ms": (
                                            time.monotonic_ns() - worker_started_ns
                                        )
                                        / 1_000_000,
                                    },
                                    provenance="observed",
                                )
                            from operator_runtime import scrub_secrets  # noqa: E402
                            scrubbed = scrub_secrets(line)
                            log_f.write(scrubbed)
                            log_f.flush()
                            log_lines.append(scrubbed.rstrip())

                        # A short-lived worker can exit after filling the pipe but
                        # before the daemon consumes it.  ``poll()`` only says the
                        # process is terminal; buffered output (including quota or
                        # auth errors) may still be unread.  Stop only after EOF so
                        # failure flow-control classifies the actual trailing error.
                        if saw_eof and proc.poll() is not None:
                            break

                proc.wait()
                exit_code = proc.returncode if proc.returncode is not None else -1
                if timed_out:
                    exit_code = 124
                    result_status = "failed_timeout"
                else:
                    result_status = "completed" if exit_code == 0 else "failed"
                _observe(
                    "operator.worker.exited",
                    component="operatord",
                    operator=operator_id,
                    operation="operator_worker",
                    operation_id=worker_operation_id,
                    phase="completed",
                    terminal=True,
                    identifiers=worker_ids,
                    data={
                        "exit_code": exit_code,
                        "status": result_status,
                        "timed_out": timed_out,
                        "active_duration_ms": (
                            time.monotonic_ns() - worker_started_ns
                        )
                        / 1_000_000,
                        "first_output_observed": first_output_observed,
                    },
                    provenance="observed",
                )
                worker_terminal_emitted = True

            except Exception as exc:
                _info(f"Execution error: {exc}")
                log_lines.append(f"[ERROR] {exc}")
                result_status = "error"
            finally:
                if worker_started and not worker_terminal_emitted:
                    _observe(
                        "operator.worker.exited",
                        component="operatord",
                        operator=operator_id,
                        operation="operator_worker",
                        operation_id=worker_operation_id,
                        phase="completed",
                        terminal=True,
                        status="error",
                        identifiers=worker_ids,
                        data={
                            "exit_code": exit_code,
                            "status": "error",
                            "timed_out": False,
                            "active_duration_ms": (
                                time.monotonic_ns() - worker_started_ns
                            ) / 1_000_000,
                        },
                        provenance="observed",
                    )
                _state["current_proc"] = None
                _state["current_task_id"] = None

            if _state["drain"]:
                # ``draining`` is a daemon lifecycle state, not a durable task
                # result. Persisting it here leaves PM inbox records in
                # ``submitted`` forever because no failure closeout runs.
                result_status = "failed_interrupted"
                if exit_code == 0:
                    exit_code = 130
                log_lines.append(
                    f"[ERROR] operator task interrupted while daemon was draining "
                    f"(signal={_state.get('drain_signal')})"
                )
                _state["current_state"] = "draining"

            finished_at: str = _now_utc()

            if (
                result_status == "completed"
                and "antigravity" in operator_id.lower()
                and _antigravity_output_is_nonfinal(log_lines)
            ):
                log_lines.append("[ERROR] Antigravity output was placeholder/non-final; refusing false completed status")
                result_status = "failed_nonfinal_output"
                exit_code = exit_code or 65

            if result_status == "completed":
                try:
                    for published_path in _publish_staged_outputs(exec_env):
                        log_lines.append(f"[output-publish] {published_path}")
                except Exception as exc:
                    log_lines.append(f"[ERROR] declared output publish failed: {exc}")
                    result_status = "failed_contract_closeout"
                    exit_code = exit_code or 67

            if result_status == "completed" and pm_result_path is not None:
                if not pm_result_path.exists():
                    log_lines.append(f"[ERROR] missing pm_result: {pm_result_path}")
                    result_status = "failed_missing_pm_result"
                    exit_code = exit_code or 65
                else:
                    try:
                        started_dt = _parse_utc(started_at)
                        result_dt = dt.datetime.fromtimestamp(
                            pm_result_path.stat().st_mtime,
                            tz=dt.timezone.utc,
                        )
                        if result_dt < started_dt:
                            log_lines.append(f"[ERROR] stale pm_result predates current run: {pm_result_path}")
                            result_status = "failed_stale_pm_result"
                            exit_code = exit_code or 66
                    except Exception:
                        pass

            if result_status == "completed" and pm_result_path is not None:
                closeout_started_ns = time.monotonic_ns()
                closeout_operation_id = _observation_id("operation", task_operation_id, "closeout")
                closeout_ids = dict(observation_ids)
                closeout_ids["span_id"] = _observation_id("span", closeout_operation_id)
                closeout_ids["parent_span_id"] = task_span_id
                _observe(
                    "operator.closeout.started",
                    component="operatord",
                    operator=operator_id,
                    operation="operator_closeout",
                    operation_id=closeout_operation_id,
                    phase="started",
                    identifiers=closeout_ids,
                    data={"hook": "pm_dispatch.complete"},
                    provenance="observed",
                )
                try:
                    completed = subprocess.run(
                        _pm_dispatch_complete_command(task_id),
                        capture_output=True,
                        text=True,
                        env=exec_env,
                        timeout=30,
                    )
                    stdout = completed.stdout.strip()
                    stderr = completed.stderr.strip()
                    if stdout:
                        log_lines.append(stdout)
                    if stderr:
                        log_lines.append(stderr)
                    if completed.returncode != 0:
                        log_lines.append(
                            f"[WARN] pm_dispatch complete returned {completed.returncode} for {task_id}"
                        )
                        result_status = "failed_contract_closeout"
                        exit_code = exit_code or 67
                except Exception as exc:
                    log_lines.append(f"[WARN] pm_dispatch complete hook failed: {exc}")
                    result_status = "failed_contract_closeout"
                    exit_code = exit_code or 67
                _observe(
                    "operator.closeout.completed",
                    component="operatord",
                    operator=operator_id,
                    operation="operator_closeout",
                    operation_id=closeout_operation_id,
                    phase="completed",
                    terminal=True,
                    identifiers=closeout_ids,
                    data={
                        "hook": "pm_dispatch.complete",
                        "status": result_status,
                        "duration_ms": (
                            time.monotonic_ns() - closeout_started_ns
                        )
                        / 1_000_000,
                    },
                    provenance="observed",
                )

            # ── Write result artifact ─────────────────────────────────────────────
            log_tail = "\n".join(log_lines[-50:])
            flow_control_decision: dict[str, Any] | None = None
            if result_status != "completed" and log_tail.strip():
                skip_reason = _failure_runtime_override_skip_reason(log_tail)
                if skip_reason:
                    flow_control_decision = {
                        "runtime_state": "",
                        "task_control": None,
                        "skipped": True,
                        "reason": skip_reason,
                    }
                    log_lines.append(f"[flow-control] skipped={skip_reason}")
                else:
                    try:
                        flow_control_decision = _apply_failure_runtime_override(
                            operator_id=operator_id,
                            config=config,
                            envelope=envelope,
                            task_dir=result_dir,
                            failure_text=log_tail,
                        )
                    except Exception as exc:
                        log_lines.append(f"[WARN] failure flow control hook failed: {exc}")
                    else:
                        runtime_state = str((flow_control_decision or {}).get("runtime_state") or "").strip()
                        if runtime_state:
                            log_lines.append(f"[flow-control] runtime_state={runtime_state}")
                        task_control = (flow_control_decision or {}).get("task_control")
                        action = (
                            str(task_control.get("action") or "defer")
                            if isinstance(task_control, dict)
                            else "operator_blocked_no_defer"
                            if runtime_state in {"cooldown", "auth_expired"}
                            else "no_retry"
                        )
                        flow_operation_id = _observation_id(
                            "operation", observation_ids.get("dispatch_id"), observation_ids.get("attempt_id"), "flow-control"
                        )
                        _observe(
                            "flow_control.decision",
                            component="operatord",
                            operator=operator_id,
                            operation="flow_control",
                            operation_id=flow_operation_id,
                            phase="point",
                            status=runtime_state or "unclassified",
                            identifiers={
                                **observation_ids,
                                "span_id": _observation_id("span", flow_operation_id),
                                "parent_span_id": worker_span_id,
                            },
                            data={"runtime_state": runtime_state or "unclassified", "decision": action},
                            provenance="observed",
                        )
                log_tail = "\n".join(log_lines[-50:])
            result_path = write_result(
                operator_id=operator_id,
                task_id=task_id,
                sprint_id=sprint_id,
                node_id=node_id,
                status=result_status,
                exit_code=exit_code,
                started_at=started_at,
                finished_at=finished_at,
                log_tail=log_tail,
                model_route=model_route,
                graph_path=envelope.get("graph_path"),
            )
            _info(f"Result written: {result_path}")
            _observe(
                "operator.result.persisted",
                component="operatord",
                operator=operator_id,
                identifiers=observation_ids,
                data={
                    "status": result_status,
                    "exit_code": exit_code,
                    "result_filename": Path(result_path).name,
                },
                provenance="observed",
            )

            if pm_result_path is not None and result_status != "completed":
                try:
                    failed = subprocess.run(
                        _pm_dispatch_fail_command(task_id, result_status, log_tail or result_status),
                        capture_output=True,
                        text=True,
                        env=exec_env,
                        timeout=30,
                    )
                    stdout = failed.stdout.strip()
                    stderr = failed.stderr.strip()
                    if stdout:
                        log_lines.append(stdout)
                    if stderr:
                        log_lines.append(stderr)
                    if failed.returncode != 0:
                        log_lines.append(
                            f"[WARN] pm_dispatch fail returned {failed.returncode} for {task_id}"
                        )
                except Exception as exc:
                    log_lines.append(f"[WARN] pm_dispatch fail hook failed: {exc}")

            # ── Cleanup ───────────────────────────────────────────────────────────
            try:
                envelope_path.unlink()
            except Exception:
                pass

            try:
                update_operator_lease_metadata(
                    operator_id,
                    worker_pid=None,
                    daemon_pid=None,
                )
            except Exception:
                pass

            try:
                release_operator_lease(operator_id, reason=result_status)
            except Exception:
                pass
            else:
                _observe(
                    "operator.lease.released",
                    component="operatord",
                    operator=operator_id,
                    identifiers=observation_ids,
                    data={"reason": result_status},
                    provenance="observed",
                )

            _observe(
                "operator.task.completed",
                component="operatord",
                operator=operator_id,
                operation="operator_task",
                operation_id=task_operation_id,
                phase="completed",
                terminal=True,
                status=result_status,
                identifiers=observation_ids,
                data={"exit_code": exit_code, "result_status": result_status},
                provenance="observed",
            )

            processed += 1
            _state["current_state"] = "idle"
            write_heartbeat(operator_id, "idle", resolved_persona=resolved_persona, model_route=model_route)
            _info(f"Task {task_id} done: {result_status} (exit={exit_code})")

            if once:
                break

            if _state["drain"]:
                break

            time.sleep(poll_interval)
    finally:
        write_heartbeat(operator_id, "idle", resolved_persona=resolved_persona, model_route=model_route)
        _release_daemon_slot(daemon_lock_fh, daemon_pid_path)

    return 0


def _now_utc() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    """Bootstrap an operator: load persona, apply pane title, emit ready."""
    # Lazy import to keep top-level clean
    try:
        from operator_naming import (  # type: ignore[import]
            canonical_operator_id,
            pane_title,
            apply_pane_title,
        )
    except ImportError:
        # Fallback if run from outside tools/ directory
        _tools_dir = Path(__file__).parent
        sys.path.insert(0, str(_tools_dir))
        from operator_naming import (  # type: ignore[import]
            canonical_operator_id,
            pane_title,
            apply_pane_title,
        )

    operator_id: str = args.operator
    config = _get_operator(operator_id)

    role: str = config.get("role", "builder")
    model: str = config.get("model", "")
    enabled: bool = config.get("enabled", False)

    # Warn but do not block on disabled operators (useful for testing)
    if not enabled and not args.force:
        _info(
            f"Operator '{operator_id}' is marked disabled "
            f"(reason: {config.get('disabled_reason', 'unknown')}). "
            "Pass --force to proceed anyway."
        )
        return 1

    # ── Canonical ID ─────────────────────────────────────────────────────────
    canon_id = canonical_operator_id(operator_id, config)
    _info(f"canonical_id  = {canon_id}")
    _info(f"role          = {role}")
    _info(f"model         = {model or '(unknown)'}")
    _info(f"display_name  = {config.get('display_name', operator_id)}")

    # ── Persona & evaluator protocol ──────────────────────────────────────────
    pr = None
    try:
        pr = resolve_persona(operator_id, config, PERSONAS_DIR)
    except RuntimeError as exc:
        _info(f"persona       = (not found: {exc})")

    if pr is not None:
        _info(f"persona       = {pr.persona_path}")
        if args.print_persona:
            print("\n" + "─" * 60)
            print(f"# Persona: {pr.persona_name}")
            print("─" * 60)
            print(pr.persona_text)
            print("─" * 60 + "\n")

        if pr.eval_protocol_loaded:
            _info(f"eval_protocol = {pr.eval_protocol_path}")
            if args.print_persona:
                print("\n" + "─" * 60)
                print("# Evaluator Verification Protocol")
                print("─" * 60)
                print(pr.eval_protocol_text)
                print("─" * 60 + "\n")
        elif pr.persona_name == "evaluator":
            _info(f"eval_protocol = (not found: {EVALUATOR_PROTOCOL_FILENAME})")

    # ── Pane title ────────────────────────────────────────────────────────────
    title = pane_title(
        operator_id=operator_id,
        role=role,
        config=config,
    )
    _info(f"pane_title    = {title}")
    pane_target = args.pane_id or os.environ.get("TMUX_PANE")
    apply_pane_title(title, pane_id=pane_target)

    # ── Ready signal ──────────────────────────────────────────────────────────
    ready: dict[str, Any] = {
        "status": "ready",
        "operator_id": operator_id,
        "canonical_id": canon_id,
        "role": role,
        "model": model,
        "persona_loaded": pr is not None,
        "eval_protocol_loaded": pr is not None and pr.eval_protocol_loaded,
        "pane_title": title,
    }
    if args.json:
        print(json.dumps(ready, indent=2))

    return 0


# ---------------------------------------------------------------------------
# Subcommand: list
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    registry = _load_registry()
    operators = registry.get("operators", {})
    if not operators:
        _info("No operators registered.")
        return 0

    if args.json:
        print(json.dumps(operators, indent=2))
        return 0

    fmt = "  {:<42} {:<12} {:<14} {:<8}"
    print(fmt.format("ID", "ROLE", "VENDOR/BACKEND", "ENABLED"))
    print("  " + "-" * 80)
    for oid, cfg in sorted(operators.items()):
        print(
            fmt.format(
                oid[:42],
                str(cfg.get("role", "?"))[:12],
                str(cfg.get("backend", cfg.get("provider", "?")))[:14],
                "yes" if cfg.get("enabled") else "no",
            )
        )
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="operatord",
        description="Solar Harness operator daemon — bootstrap and manage operator instances.",
    )
    sub = parser.add_subparsers(dest="subcommand", metavar="<subcommand>")

    # ── run ──────────────────────────────────────────────────────────────────
    run_p = sub.add_parser(
        "run",
        help="Bootstrap an operator instance (load persona, apply pane title).",
        description=(
            "Bootstrap a Solar Harness operator: resolve config from the physical-operators "
            "registry, load the operator persona file, load the evaluator verification protocol "
            "when the role is 'evaluator', apply the tmux pane title, and emit a ready signal."
        ),
    )
    run_p.add_argument(
        "--operator",
        required=True,
        metavar="ID",
        help="Operator ID from physical-operators.json (e.g. mini-claude-sonnet-builder).",
    )
    run_p.add_argument(
        "--harness-dir",
        metavar="PATH",
        default=str(HARNESS_DIR),
        help=f"Path to the Solar Harness root directory (default: {HARNESS_DIR}).",
    )
    run_p.add_argument(
        "--pane-id",
        metavar="PANE",
        default=None,
        help="Explicit tmux pane target (e.g. %%3). Defaults to $TMUX_PANE.",
    )
    run_p.add_argument(
        "--force",
        action="store_true",
        help="Run even if the operator is disabled in the registry.",
    )
    run_p.add_argument(
        "--print-persona",
        action="store_true",
        help="Print the full persona and evaluator protocol text to stdout.",
    )
    run_p.add_argument(
        "--json",
        action="store_true",
        help="Emit the ready signal as JSON.",
    )

    # ── list ─────────────────────────────────────────────────────────────────
    list_p = sub.add_parser(
        "list",
        help="List operators registered in physical-operators.json.",
    )
    list_p.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON.",
    )

    # ── daemon ───────────────────────────────────────────────────────────────
    daemon_p = sub.add_parser(
        "daemon",
        help="Run the operator as a persistent daemon that polls its inbox.",
        description=(
            "Bootstrap the operator and enter a polling loop. "
            "When a task envelope appears in run/operator-inbox/<id>/, the daemon "
            "claims it, executes the backend command, writes result artifacts, "
            "and returns to idle. Use --once to process exactly one task then exit."
        ),
    )
    daemon_p.add_argument(
        "--operator",
        required=True,
        metavar="ID",
        help="Operator ID from physical-operators.json.",
    )
    daemon_p.add_argument(
        "--once",
        action="store_true",
        help="Process one task then exit (useful for testing and CI).",
    )
    daemon_p.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        metavar="SECS",
        help="Seconds between inbox polls (default: 1.0).",
    )
    daemon_p.add_argument(
        "--once-max-wait-seconds",
        type=float,
        default=float(os.environ.get("SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS", "15")),
        metavar="SECS",
        help="Maximum seconds a --once daemon waits before exiting if it never claims work (default: 15).",
    )
    daemon_p.add_argument(
        "--force",
        action="store_true",
        help="Run even if the operator is disabled in the registry.",
    )
    daemon_p.add_argument(
        "--harness-dir",
        metavar="PATH",
        default=str(HARNESS_DIR),
        help=f"Path to the Solar Harness root directory (default: {HARNESS_DIR}).",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Update HARNESS_DIR from --harness-dir if provided by run subcommand
    if hasattr(args, "harness_dir") and args.harness_dir:
        global HARNESS_DIR, PERSONAS_DIR, PHYSICAL_OPERATORS_PATH
        HARNESS_DIR = Path(args.harness_dir)
        PERSONAS_DIR = HARNESS_DIR / "personas"
        PHYSICAL_OPERATORS_PATH = Path(
            os.environ.get(
                "SOLAR_MULTI_TASK_OPERATORS",
                HARNESS_DIR / "config" / "physical-operators.json",
            )
        )

    if args.subcommand == "run":
        return cmd_run(args)
    elif args.subcommand == "list":
        return cmd_list(args)
    elif args.subcommand == "daemon":
        return cmd_daemon(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
