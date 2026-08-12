#!/usr/bin/env python3
"""Run a Solar PM dispatch through Codex CLI non-interactively."""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
try:
    from developer_observability import observe as _observe, stable_id as _observation_id  # noqa: E402
except Exception:  # Observability must never become a CLI dependency.
    def _observe(*_args, **_kwargs) -> bool:
        return False

    def _observation_id(kind: str, *parts) -> str:
        return f"{kind}-unavailable"


def _read_dispatch() -> str:
    dispatch_file = os.environ.get("DISPATCH_FILE") or os.environ.get("SOLAR_MULTI_TASK_DISPATCH_FILE")
    if dispatch_file:
        path = Path(dispatch_file).expanduser()
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()


def _write_pm_result(task_dir: Path, output_file: Path, output: str, exit_code: int) -> None:
    result_path = os.environ.get("PM_RESULT_PATH") or os.environ.get("RESULT_PATH")
    if not result_path:
        return
    path = Path(result_path).expanduser()
    if path.exists() and path.stat().st_size > 0:
        return
    text = output.strip()
    if not text and output_file.exists():
        text = output_file.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) > 20000:
        text = text[:20000] + "\n\n[truncated]"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            f"# PM Task Result — {os.environ.get('TASK_ID', 'codex-operator')}\n\n"
            "## 已完成\n"
            "- Codex CLI command backend 已执行 PM dispatch。\n\n"
            "## 已验证\n"
            f"- codex exec exit_code={exit_code}。\n"
            f"- output_file={output_file}\n"
            f"- task_dir={task_dir}\n\n"
            "## 结论摘要\n"
            f"{text or 'N/A'}\n\n"
            "## 风险/限制\n"
            "- 该结果由 Codex wrapper 从最后消息/stdout 转写；仍需 evaluator 复核真实文件修改和测试证据。\n\n"
            "## 后续建议\n"
            "- 按 dispatch Definition of Done 复核文件变更、命令输出和测试证据。\n"
        ),
        encoding="utf-8",
    )


def _timeout_seconds() -> float:
    raw = (
        os.environ.get("CODEX_OPERATOR_TIMEOUT_SECONDS")
        or os.environ.get("SOLAR_CODEX_OPERATOR_TIMEOUT_SECONDS")
        or "900"
    )
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 900.0


def _truthy_env(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in {"0", "false", "off", "no", ""}


def _prepend_env_path(env: dict[str, str], name: str, entries: list[Path | str]) -> None:
    existing = [part for part in env.get(name, "").split(os.pathsep) if part]
    prefix = [str(Path(part).expanduser()) for part in entries if str(part)]
    seen: set[str] = set()
    merged: list[str] = []
    for part in prefix + existing:
        if part and part not in seen:
            merged.append(part)
            seen.add(part)
    env[name] = os.pathsep.join(merged)


def _install_harness_command_shims(task_dir: Path, harness_dir: Path) -> Path:
    shim_dir = task_dir / "cmd-shims"
    shim_dir.mkdir(parents=True, exist_ok=True)
    solar_harness = shim_dir / "solar-harness"
    solar_harness.write_text(
        (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "exec \"${HARNESS_DIR}/solar-harness.sh\" \"$@\"\n"
        ),
        encoding="utf-8",
    )
    solar_harness.chmod(0o755)
    return shim_dir


def _codex_exec_env(task_dir: Path) -> dict[str, str]:
    """Build a deterministic environment for non-interactive Codex operator runs.

    The strict wrapper later gives each run a harness-owned CODEX_HOME and
    exposes the user's auth/config through read-only symlinks. SQLite/app-server
    state therefore stays inside the harness. The model shell must also resolve
    Solar helper commands from this active harness, not from any installed
    ~/.solar runtime left on the developer machine.
    """
    env = os.environ.copy()
    harness_dir = Path(env.get("HARNESS_DIR") or Path.home() / ".solar" / "harness").expanduser().resolve(strict=False)
    shim_dir = _install_harness_command_shims(task_dir, harness_dir)
    state_home = Path(
        env.get("CODEX_SQLITE_HOME")
        or env.get("SOLAR_CODEX_STATE_HOME")
        or harness_dir / "run" / "codex-state"
    ).expanduser()
    state_home.mkdir(parents=True, exist_ok=True)
    configured_codex_home = env.get("SOLAR_CODEX_SOURCE_HOME")
    source_codex_home = Path(configured_codex_home).expanduser() if configured_codex_home else Path.home() / ".codex"
    sprints_dir = Path(
        env.get("SPRINTS_DIR")
        or env.get("HARNESS_SPRINTS_DIR")
        or harness_dir / "sprints"
    ).expanduser().resolve(strict=False)
    env["HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_HARNESS_DIR"] = str(harness_dir)
    env["SPRINTS_DIR"] = str(sprints_dir)
    env["HARNESS_SPRINTS_DIR"] = str(sprints_dir)
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(sprints_dir)
    env["SOLAR_HARNESS_CMD"] = str(shim_dir / "solar-harness")
    env["SOLAR_CODEX_SOURCE_HOME"] = str(source_codex_home)
    env["CODEX_SQLITE_HOME"] = str(state_home)
    _prepend_env_path(env, "PATH", [shim_dir, harness_dir / "bin", harness_dir])
    _prepend_env_path(env, "PYTHONPATH", [harness_dir / "lib", harness_dir / "tools"])
    return env


def _codex_live_search_requested() -> bool:
    """Project the dashboard's search setting onto the safe CLI capability.

    ``SOLAR_CODEX_EXTRA_FLAGS`` is assembled by ``solar-harness.sh`` for
    interactive panes, but the operator backend must not blindly forward that
    shell-shaped string.  Codex exposes live search as a global option, so the
    only supported projection here is the exact ``--search`` token placed
    before ``exec``.  Reasoning effort already has its own typed argument.
    """
    raw = os.environ.get("SOLAR_CODEX_EXTRA_FLAGS", "").strip()
    if not raw:
        return False
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return False
    return "--search" in tokens


def _codex_exec_command(model: str, effort: str, cwd: str, output_file: Path) -> list[str]:
    cmd = ["codex"]
    if _codex_live_search_requested():
        cmd.append("--search")
    cmd.append("exec")
    if _truthy_env("SOLAR_CODEX_OPERATOR_EPHEMERAL", "1"):
        cmd.append("--ephemeral")
    cmd.extend([
        "--model",
        model,
        "--config",
        f"model_reasoning_effort={effort}",
        "--config",
        'cli_auth_credentials_store="file"',
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd",
        cwd,
        "--output-last-message",
        str(output_file),
        "-",
    ])
    return cmd


def _existing_paths(values: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        resolved = value.expanduser().resolve(strict=False)
        key = str(resolved)
        if resolved.exists() and key not in seen:
            result.append(resolved)
            seen.add(key)
    return result


def _filesystem_isolated_command(
    command: list[str],
    *,
    task_dir: Path,
    cwd: Path,
    env: dict[str, str],
) -> tuple[list[str], dict[str, object]]:
    """Wrap a strict Solar operator in a kernel-enforced filesystem allowlist."""
    strict = _truthy_env("SOLAR_OPERATOR_STRICT_FS_SCOPE", "0")
    mode = env.get("SOLAR_CODEX_OPERATOR_FS_ISOLATION", "landlock").strip().lower()
    if mode in {"0", "off", "disabled", "none"}:
        if strict:
            raise RuntimeError("strict operator filesystem scope cannot disable Landlock")
        return command, {"mode": "disabled", "strict": False}
    if sys.platform != "linux":
        if strict:
            raise RuntimeError("strict operator filesystem scope requires Linux Landlock")
        return command, {"mode": "unsupported", "strict": False}

    harness_dir = Path(env["HARNESS_DIR"]).expanduser().resolve(strict=False)
    state_root = Path(
        env.get("SOLAR_CODEX_OPERATOR_STATE_ROOT")
        or f"/tmp/solar-codex-operator-state-{os.getuid()}"
    ).expanduser()
    state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_root.chmod(0o700)
    state_home = Path(tempfile.mkdtemp(prefix=f"{os.getpid()}-", dir=state_root))
    atexit.register(shutil.rmtree, state_home, ignore_errors=True)
    env["CODEX_SQLITE_HOME"] = str(state_home)
    tmp_dir = task_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(tmp_dir)
    env["TMP"] = str(tmp_dir)
    env["TEMP"] = str(tmp_dir)

    source_codex_home = Path(env["SOLAR_CODEX_SOURCE_HOME"]).expanduser()
    codex_home = state_home / "home"
    codex_home.mkdir(parents=True, exist_ok=True)
    source = source_codex_home / "auth.json"
    destination = codex_home / "auth.json"
    if source.is_file():
        shutil.copyfile(source, destination)
        destination.chmod(0o600)
    config = codex_home / "config.toml"
    config.write_text('cli_auth_credentials_store = "file"\n', encoding="utf-8")
    config.chmod(0o600)
    env["CODEX_HOME"] = str(codex_home)
    codex_arg0_dir = codex_home / "tmp" / "arg0"
    codex_arg0_dir.mkdir(parents=True, exist_ok=True)
    codex_binary = Path(shutil.which("codex", path=env.get("PATH")) or "codex")
    resolved_binary = codex_binary.resolve(strict=False)
    # WSL resolves /etc/resolv.conf into /mnt/wsl. Landlock authorizes the
    # resolved inode, so /etc by itself is insufficient for DNS/token refresh.
    resolved_system_network_files = [
        path.resolve(strict=False)
        for path in (
            Path("/etc/resolv.conf"),
            Path("/etc/hosts"),
            Path("/etc/nsswitch.conf"),
            Path("/etc/gai.conf"),
        )
        if path.exists()
    ]
    read_only = _existing_paths(
        [
            Path("/usr"),
            Path("/bin"),
            Path("/sbin"),
            Path("/lib"),
            Path("/lib64"),
            Path("/etc"),
            codex_binary,
            resolved_binary.parent,
            *resolved_system_network_files,
            harness_dir,
        ]
    )
    try:
        declared_outputs = json.loads(env.get("SOLAR_OPERATOR_ALLOWED_OUTPUTS_JSON") or "[]")
    except (TypeError, ValueError):
        declared_outputs = []
    exact_outputs = [
        Path(str(value)).expanduser()
        for value in declared_outputs
        if isinstance(value, str) and value.strip()
    ]
    read_write = _existing_paths(
        [
            cwd,
            task_dir,
            state_home,
            tmp_dir,
            Path("/dev/null"),
            Path("/dev/urandom"),
            Path("/dev/random"),
            codex_arg0_dir,
            *exact_outputs,
        ]
    )
    wrapper = Path(__file__).with_name("landlock_exec.py").resolve(strict=False)
    if not wrapper.is_file():
        raise RuntimeError(f"Landlock wrapper is missing: {wrapper}")
    wrapped = [sys.executable, str(wrapper)]
    for path in read_only:
        wrapped.extend(["--read-only", str(path)])
    for path in read_write:
        wrapped.extend(["--read-write", str(path)])
    wrapped.extend(["--", *command])
    return wrapped, {
        "mode": "landlock",
        "strict": strict,
        "read_only": [str(path) for path in read_only],
        "read_write": [str(path) for path in read_write],
    }


def _pm_result_ready(started_wall: float) -> bool:
    result_path = os.environ.get("PM_RESULT_PATH") or os.environ.get("RESULT_PATH")
    if not result_path:
        return False
    path = Path(result_path).expanduser()
    try:
        return path.exists() and path.stat().st_size > 0 and path.stat().st_mtime >= started_wall
    except OSError:
        return False


def _terminate_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            return


def _register_codex_process_group(pid: int) -> bool:
    """Give the run registry ownership of Codex's detached session.

    The operatord owns its outer worker, but Codex is intentionally launched
    in a separate session so task timeouts can terminate the complete CLI
    group. Register that second boundary before sending the dispatch; otherwise
    product teardown can kill the outer wrapper and orphan Codex.
    """
    harness_dir = Path(
        os.environ.get("HARNESS_DIR")
        or os.environ.get("SOLAR_HARNESS_DIR")
        or Path.home() / ".solar" / "harness"
    ).expanduser()
    lib_dir = Path(__file__).resolve().parents[1] / "lib"
    lib_text = str(lib_dir)
    if lib_text not in sys.path:
        sys.path.insert(0, lib_text)
    try:
        import run_process_registry as registry

        registry.register(
            "harness",
            "operator-task-child",
            int(pid),
            meta={
                "task_id": str(os.environ.get("TASK_ID") or ""),
                "sprint_id": str(os.environ.get("SID") or ""),
                "node_id": str(os.environ.get("NODE_ID") or ""),
                "backend": "codex",
            },
            harness_dir=harness_dir,
            signal_scope="process_group",
        )
        return True
    except Exception as exc:
        print(
            f"ERROR: unable to register Codex process group pid={pid}: {exc}",
            file=sys.stderr,
        )
        return False


def main() -> int:
    dispatch = _read_dispatch().strip()
    if not dispatch:
        print("ERROR: empty dispatch for Codex operator", file=sys.stderr)
        return 64

    task_dir = Path(os.environ.get("TASK_DIR") or ".").expanduser()
    task_dir.mkdir(parents=True, exist_ok=True)
    output_file = task_dir / "codex-last-message.md"
    model = os.environ.get("CODEX_MODEL", "gpt-5.5").strip() or "gpt-5.5"
    effort = os.environ.get("CODEX_REASONING_EFFORT", "medium").strip() or "medium"
    cwd = str(Path(os.environ.get("CODEX_WORKDIR") or os.environ.get("WORK_DIR") or os.getcwd()).expanduser())
    if not Path(cwd).is_dir():
        print(f"ERROR: Codex work_dir does not exist: {cwd}", file=sys.stderr)
        return 72

    codex_env = _codex_exec_env(task_dir)
    raw_cmd = _codex_exec_command(model, effort, cwd, output_file)
    try:
        cmd, fs_scope = _filesystem_isolated_command(
            raw_cmd,
            task_dir=task_dir,
            cwd=Path(cwd),
            env=codex_env,
        )
    except RuntimeError as exc:
        print(f"ERROR: Codex operator filesystem isolation refused: {exc}", file=sys.stderr)
        return 78
    timeout_seconds = _timeout_seconds()
    pm_result_grace = float(os.environ.get("CODEX_PM_RESULT_GRACE_SECONDS", "20"))
    invocation_id = str(uuid.uuid4())
    dispatch_id = os.environ.get("DISPATCH_ID") or os.environ.get("TASK_ID") or "dispatch-unknown"
    attempt_id = os.environ.get("ATTEMPT_ID") or "1"
    operation_id = _observation_id("operation", dispatch_id, attempt_id, invocation_id, "codex-cli")
    span_id = _observation_id("span", operation_id)
    observation_ids = {
        "sprint_id": os.environ.get("SID") or os.environ.get("SPRINT_ID"),
        "node_id": os.environ.get("NODE_ID"),
        "task_id": os.environ.get("TASK_ID"),
        "dispatch_id": dispatch_id,
        "attempt_id": attempt_id,
        "invocation_id": invocation_id,
        "correlation_id": os.environ.get("CORRELATION_ID") or os.environ.get("TASK_ID"),
        "causation_id": os.environ.get("CAUSATION_ID") or dispatch_id,
        "span_id": span_id,
        "parent_span_id": os.environ.get("SOLAR_OBSERVABILITY_SPAN_ID"),
    }
    started = time.monotonic()
    terminal_emitted = False

    def _complete_invocation(status: str, exit_code: int | None, **extra) -> None:
        nonlocal terminal_emitted
        if terminal_emitted:
            return
        terminal_emitted = True
        _observe(
            "codex_cli.invocation.completed",
            component="codex_operator",
            operation="codex_cli_invocation",
            operation_id=operation_id,
            phase="completed",
            terminal=True,
            status=status,
            identifiers=observation_ids,
            data={
                "exit_code": exit_code,
                "codex_cli_elapsed_ms": (time.monotonic() - started) * 1000,
                "provider_latency_ms": None,
                "model_latency_ms": None,
                "input_tokens": None,
                "output_tokens": None,
                "tool_calls": None,
                **extra,
            },
            provenance="observed",
        )

    atexit.register(_complete_invocation, "wrapper_exit", None)

    _observe(
        "codex_cli.invocation.started",
        component="codex_operator",
        operation="codex_cli_invocation",
        operation_id=operation_id,
        phase="started",
        identifiers=observation_ids,
        data={
            "provider": "openai",
            "model": model,
            "reasoning_effort": effort,
            "dispatch_bytes": len(dispatch.encode("utf-8", errors="replace")),
            "dispatch_sha256": hashlib.sha256(
                dispatch.encode("utf-8", errors="replace")
            ).hexdigest(),
            "structured_stream": False,
            "structured_stream_reason": "json_mode_parity_not_verified",
            "provider_latency_ms": None,
            "model_latency_ms": None,
        },
        provenance="observed",
    )
    print(
        "codex_operator: env "
        f"cwd={shlex.quote(cwd)} "
        f"task_dir={shlex.quote(str(task_dir))} "
        f"CODEX_HOME={shlex.quote(codex_env.get('CODEX_HOME') or str(Path.home() / '.codex'))} "
        f"CODEX_SQLITE_HOME={shlex.quote(codex_env.get('CODEX_SQLITE_HOME') or '')}"
    )
    print(
        "codex_operator: filesystem_scope "
        f"mode={fs_scope.get('mode')} strict={str(bool(fs_scope.get('strict'))).lower()} "
        f"ro={len(fs_scope.get('read_only', []))} rw={len(fs_scope.get('read_write', []))}"
    )
    print("codex_operator: invoking " + " ".join(shlex.quote(part) for part in cmd[:-1]) + " <dispatch>")
    cli_log = task_dir / "codex-cli-output.log"
    started_wall = time.time()
    with open(cli_log, "w", encoding="utf-8") as log_f:
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
                env=codex_env,
            )
        except Exception as exc:
            _complete_invocation("spawn_error", None, failure_class=type(exc).__name__)
            raise
        _observe(
            "codex_cli.process.started",
            component="codex_operator",
            operation="codex_cli_invocation",
            operation_id=operation_id,
            phase="progress",
            identifiers=observation_ids,
            data={"pid": int(proc.pid), "provider": "openai", "model": model},
            provenance="observed",
        )
        if not _register_codex_process_group(proc.pid):
            _terminate_process_group(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
                proc.wait(timeout=5)
            _complete_invocation("registration_failed", 75)
            return 75
        try:
            assert proc.stdin is not None
            proc.stdin.write(dispatch)
            proc.stdin.close()
        except BrokenPipeError:
            pass

        pm_ready_since: float | None = None
        first_output_observed = False
        while True:
            if not first_output_observed:
                try:
                    first_output_observed = cli_log.stat().st_size > 0
                except OSError:
                    first_output_observed = False
                if first_output_observed:
                    _observe(
                        "codex_cli.first_output",
                        component="codex_operator",
                        operation="codex_cli_invocation",
                        operation_id=operation_id,
                        phase="progress",
                        identifiers=observation_ids,
                        data={"elapsed_ms": (time.monotonic() - started) * 1000},
                        provenance="observed",
                    )
            if proc.poll() is not None:
                break
            elapsed = time.monotonic() - started
            if _pm_result_ready(started_wall):
                pm_ready_since = pm_ready_since or time.monotonic()
                if (time.monotonic() - pm_ready_since) >= pm_result_grace:
                    print(
                        f"codex_operator: PM result ready; terminating lingering codex exec after {pm_result_grace:.0f}s grace"
                    )
                    _terminate_process_group(proc)
                    _observe(
                        "codex_cli.termination_requested",
                        component="codex_operator",
                        operation="codex_cli_invocation",
                        operation_id=operation_id,
                        phase="progress",
                        status="pm_result_ready",
                        identifiers=observation_ids,
                        data={
                            "signal": "SIGTERM",
                            "grace_seconds": pm_result_grace,
                            "elapsed_ms": (time.monotonic() - started) * 1000,
                        },
                        provenance="observed",
                    )
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except Exception:
                            proc.kill()
                        proc.wait(timeout=5)
                    _complete_invocation(
                        "pm_result_ready",
                        int(proc.returncode or 0),
                        first_output_observed=first_output_observed,
                    )
                    return 0
            if timeout_seconds > 0 and elapsed >= timeout_seconds:
                _terminate_process_group(proc)
                _observe(
                    "codex_cli.termination_requested",
                    component="codex_operator",
                    operation="codex_cli_invocation",
                    operation_id=operation_id,
                    phase="progress",
                    status="timeout",
                    identifiers=observation_ids,
                    data={"signal": "SIGTERM", "elapsed_ms": elapsed * 1000},
                    provenance="observed",
                )
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except Exception:
                        proc.kill()
                    proc.wait(timeout=5)
                combined = cli_log.read_text(encoding="utf-8", errors="replace") if cli_log.exists() else ""
                combined = "\n".join(
                    part
                    for part in [
                        combined,
                        f"ERROR: codex exec timed out after {elapsed:.1f}s",
                    ]
                    if part
                )
                print(combined, file=sys.stderr)
                _write_pm_result(task_dir, output_file, combined, 124)
                _complete_invocation("timeout", 124, first_output_observed=first_output_observed)
                return 124
            time.sleep(1)

    combined = cli_log.read_text(encoding="utf-8", errors="replace") if cli_log.exists() else ""
    if combined:
        print(combined, end="" if combined.endswith("\n") else "\n")
    if proc.returncode == 0:
        _write_pm_result(task_dir, output_file, combined, int(proc.returncode))
    _complete_invocation(
        "completed" if proc.returncode == 0 else "failed",
        int(proc.returncode or 0),
        first_output_observed=first_output_observed,
        structured_stream=False,
    )
    return int(proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
