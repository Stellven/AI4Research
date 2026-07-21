#!/usr/bin/env python3
"""Run a Solar operator task through Reasonix non-interactively.

The daemon materializes the dispatch into DISPATCH_FILE. This wrapper keeps
Reasonix invocation consistent across physical-operator registry entries and
stores a transcript next to the canonical operator result artifacts.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path


AUTH_FAILURE_MARKERS = (
    "authentication failed",
    "authentication fails",
    "api key is invalid",
    "api key is rejected",
    "deepseek 401",
    "认证失败",
)


def _read_dispatch() -> str:
    dispatch_file = os.environ.get("DISPATCH_FILE") or os.environ.get("SOLAR_MULTI_TASK_DISPATCH_FILE")
    if dispatch_file:
        path = Path(dispatch_file).expanduser()
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()


def _write_pm_result_if_needed(task_dir: Path, dispatch: str, output: str, exit_code: int) -> None:
    result_path = os.environ.get("PM_RESULT_PATH") or os.environ.get("RESULT_PATH")
    if not result_path:
        return
    path = Path(result_path).expanduser()
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = output.strip()
    if len(trimmed) > 20000:
        trimmed = trimmed[:20000] + "\n\n[truncated]"
    path.write_text(
        (
            f"# PM Task Result — {os.environ.get('TASK_ID', 'reasonix-operator')}\n\n"
            "## 已完成\n"
            "- Reasonix command backend 已执行 PM dispatch。\n\n"
            "## 已验证\n"
            f"- reasonix exit_code={exit_code}。\n"
            f"- transcript_dir={task_dir}\n\n"
            "## 结论摘要\n"
            f"{trimmed or 'N/A'}\n\n"
            "## 风险/限制\n"
            "- 该结果由 Reasonix wrapper 从 stdout 转写；如 stdout 未列出真实文件修改和测试证据，Evaluator 必须继续拦截。\n\n"
            "## 后续建议\n"
            "- 按 dispatch Definition of Done 复核文件变更、命令输出和测试证据。\n"
        ),
        encoding="utf-8",
    )


def _load_deepseek_key() -> None:
    """Prefer Solar's local key file over stale shell startup exports."""
    key_file = Path(os.environ.get("DEEPSEEK_API_KEY_FILE") or Path.home() / ".config" / "llm-keys" / "deepseek")
    if not key_file.exists():
        return
    try:
        value = key_file.read_text(encoding="utf-8").strip()
    except Exception:
        return
    if value:
        os.environ["DEEPSEEK_API_KEY"] = value


def _auth_failed(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in AUTH_FAILURE_MARKERS)


def main() -> int:
    _load_deepseek_key()
    dispatch = _read_dispatch().strip()
    if not dispatch:
        print("ERROR: empty dispatch for Reasonix operator", file=sys.stderr)
        return 64

    task_dir = Path(os.environ.get("TASK_DIR") or ".").expanduser()
    task_dir.mkdir(parents=True, exist_ok=True)
    transcript = task_dir / "reasonix-transcript.jsonl"

    model = os.environ.get("REASONIX_MODEL", "deepseek-v4-pro").strip() or "deepseek-v4-pro"
    effort = os.environ.get("REASONIX_EFFORT", "high").strip() or "high"
    budget = os.environ.get("REASONIX_BUDGET_USD", "").strip()

    system_prompt = os.environ.get(
        "REASONIX_SYSTEM_PROMPT",
        (
            "You are a Solar-Harness development operator. Execute the dispatch "
            "against the current repository when tools are available. Be concrete: "
            "identify files changed, commands run, test results, unresolved risks, "
            "and do not claim completion without evidence."
        ),
    )

    cmd = [
        "reasonix",
        "run",
        "--model",
        model,
        "--effort",
        effort,
        "--system",
        system_prompt,
        "--transcript",
        str(transcript),
    ]
    if budget:
        cmd.extend(["--budget", budget])
    cmd.append(dispatch)

    print("reasonix_operator: invoking " + " ".join(shlex.quote(part) for part in cmd[:-1]) + " <dispatch>")
    proc = subprocess.run(cmd, text=True, capture_output=True, env=os.environ.copy())
    combined = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")
    if _auth_failed(combined):
        return 77
    if proc.returncode == 0:
        _write_pm_result_if_needed(task_dir, dispatch, combined, int(proc.returncode))
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
