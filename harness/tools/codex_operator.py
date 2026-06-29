#!/usr/bin/env python3
"""Run a Solar PM dispatch through Codex CLI non-interactively."""
from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path


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


def _codex_exec_env(task_dir: Path) -> dict[str, str]:
    """Build a deterministic environment for non-interactive Codex operator runs.

    Keep the user's CODEX_HOME/Auth as-is, but give Codex's SQLite/app-server
    state a harness-owned writable home by default. Without this, daemonized
    runs can inherit a cwd/sandbox context where Codex fails before the model
    starts with read-only filesystem errors.
    """
    env = os.environ.copy()
    harness_dir = Path(env.get("HARNESS_DIR") or Path.home() / ".solar" / "harness").expanduser()
    state_home = Path(
        env.get("CODEX_SQLITE_HOME")
        or env.get("SOLAR_CODEX_STATE_HOME")
        or harness_dir / "run" / "codex-state"
    ).expanduser()
    state_home.mkdir(parents=True, exist_ok=True)
    env["CODEX_SQLITE_HOME"] = str(state_home)
    return env


def _codex_exec_command(model: str, effort: str, cwd: str, output_file: Path) -> list[str]:
    cmd = [
        "codex",
        "exec",
    ]
    if _truthy_env("SOLAR_CODEX_OPERATOR_EPHEMERAL", "1"):
        cmd.append("--ephemeral")
    cmd.extend([
        "--model",
        model,
        "--config",
        f"model_reasoning_effort={effort}",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd",
        cwd,
        "--output-last-message",
        str(output_file),
        "-",
    ])
    return cmd


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
    cmd = _codex_exec_command(model, effort, cwd, output_file)
    timeout_seconds = _timeout_seconds()
    pm_result_grace = float(os.environ.get("CODEX_PM_RESULT_GRACE_SECONDS", "20"))
    print(
        "codex_operator: env "
        f"cwd={shlex.quote(cwd)} "
        f"task_dir={shlex.quote(str(task_dir))} "
        f"CODEX_HOME={shlex.quote(codex_env.get('CODEX_HOME') or str(Path.home() / '.codex'))} "
        f"CODEX_SQLITE_HOME={shlex.quote(codex_env.get('CODEX_SQLITE_HOME') or '')}"
    )
    print("codex_operator: invoking " + " ".join(shlex.quote(part) for part in cmd[:-1]) + " <dispatch>")
    cli_log = task_dir / "codex-cli-output.log"
    started = time.monotonic()
    started_wall = time.time()
    with open(cli_log, "w", encoding="utf-8") as log_f:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            env=codex_env,
        )
        try:
            assert proc.stdin is not None
            proc.stdin.write(dispatch)
            proc.stdin.close()
        except BrokenPipeError:
            pass

        pm_ready_since: float | None = None
        while True:
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
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except Exception:
                            proc.kill()
                        proc.wait(timeout=5)
                    return 0
            if timeout_seconds > 0 and elapsed >= timeout_seconds:
                _terminate_process_group(proc)
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
                return 124
            time.sleep(1)

    combined = cli_log.read_text(encoding="utf-8", errors="replace") if cli_log.exists() else ""
    if combined:
        print(combined, end="" if combined.endswith("\n") else "\n")
    if proc.returncode == 0:
        _write_pm_result(task_dir, output_file, combined, int(proc.returncode))
    return int(proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
