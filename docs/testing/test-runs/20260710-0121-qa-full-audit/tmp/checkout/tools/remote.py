#!/usr/bin/env python3
"""Approval-gated remote/local experiment helper for AutoSci parity routes."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def emit(command: str, status: str, payload: dict[str, Any], *, ok: bool = False) -> int:
    out = {"schema": "autosci_remote_cli.v1", "command": command, "status": status, "ok": ok, **payload}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 1 if status == "failed" else 0


def load_allowlists(paths: list[str]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for raw in paths:
        if not raw:
            continue
        path = Path(raw).expanduser()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"commands": [line.strip() for line in text.splitlines() if line.strip()]}
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def command_allowlisted(command: list[str], allowlists: list[dict[str, Any]]) -> tuple[bool, str]:
    if not command:
        return False, "empty command"
    command_text = " ".join(command)
    quoted_command_text = shlex.join(command)
    executable = Path(command[0]).name
    for payload in allowlists:
        executables = [str(item) for item in payload.get("executables", []) if str(item).strip()]
        if command[0] in executables or executable in executables:
            return True, f"executable allowlisted: {executable}"
        for key in ("commands", "allowed_commands"):
            values = [str(item) for item in payload.get(key, []) if str(item).strip()]
            if command_text in values or quoted_command_text in values:
                return True, f"command allowlisted by {key}"
        prefixes = [str(item) for item in payload.get("allowed_prefixes", []) if str(item).strip()]
        if any(command_text.startswith(prefix) or quoted_command_text.startswith(prefix) for prefix in prefixes):
            return True, "command allowlisted by prefix"
    return False, f"command is not allowlisted: {command_text}"


def result_paths(run_dir: Path) -> list[Path]:
    names = ("results.json", "result.json", "metrics.json", "status.json", "run_log.json")
    return [run_dir / name for name in names if (run_dir / name).exists()]


def load_result_summary(paths: list[Path]) -> dict[str, Any]:
    summary: dict[str, Any] = {"metrics": [], "outcome": "", "logs": []}
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        outcome = payload.get("outcome") or result.get("outcome") or payload.get("status")
        if outcome and not summary["outcome"]:
            summary["outcome"] = str(outcome)
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), list) else result.get("metrics")
        if isinstance(metrics, list):
            summary["metrics"].extend(item for item in metrics if isinstance(item, dict))
        logs = payload.get("logs") if isinstance(payload.get("logs"), list) else []
        summary["logs"].extend(str(item) for item in logs if str(item).strip())
    return summary


def parse_status_value(stdout: str) -> str:
    text = stdout.strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        for key in ("remote_state", "state", "job_state", "status", "phase"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
    for line in text.splitlines():
        value = line.strip()
        if value:
            return value
    return ""


def write_runtime_evidence(
    *,
    args: argparse.Namespace,
    command_run: str,
    exit_code: int,
    status: str,
    checks: list[dict[str, Any]],
    artifacts: list[dict[str, str]],
    runtime_fields: dict[str, Any],
    limitations: list[str],
) -> Path | None:
    out = Path(args.runtime_evidence_out).expanduser() if args.runtime_evidence_out else None
    if out is None:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    experiment = args.experiment or "experiment"
    payload = {
        "schema": "autosci_runtime_evidence.v1",
        "task_id": f"remote-launch-{experiment}",
        "sprint_id": "remote-launch",
        "node_id": f"node-remote-launch-{experiment}",
        "status": status,
        "inputs": {"approval_ref": args.approval_ref, "experiment": experiment},
        "outputs": {
            "runtime": {
                "action": "run_experiment",
                "status": status,
                "approval_ref": args.approval_ref,
                "command_run": command_run,
                "exit_code": exit_code,
                "evidence_ids": [f"remote-runtime:{experiment}"],
                "checks": checks,
                **runtime_fields,
            }
        },
        "artifacts": artifacts,
        "provenance": {
            "operator_id": "autosci-remote-cli",
            "implementation_package": "tools.remote",
            "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        },
        "limitations": limitations,
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def cmd_launch(args: argparse.Namespace) -> int:
    if not args.approval_ref:
        return emit("launch", "approval_required", {"limitations": ["Remote/local launch requires --approval-ref and external runtime configuration."]})
    if not args.execute_approved:
        return emit("launch", "inconclusive", {"approval_ref": args.approval_ref, "limitations": ["Launch executor requires --execute-approved before running an allowlisted command."]})
    if not args.command_run:
        return emit("launch", "inconclusive", {"approval_ref": args.approval_ref, "limitations": ["Launch executor requires --command."]})

    command = shlex.split(args.command_run)
    allowlists = load_allowlists(args.allowlist_evidence or [])
    allowed, allow_reason = command_allowlisted(command, allowlists)
    run_dir = Path(args.run_dir or ".").expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    if not allowed:
        runtime_path = write_runtime_evidence(
            args=args,
            command_run=" ".join(command),
            exit_code=1,
            status="inconclusive",
            checks=[{"check": "command_allowlisted", "status": "error", "detail": allow_reason}],
            artifacts=[],
            runtime_fields={"result_collected": False, "run_dir": str(run_dir)},
            limitations=["Remote/local launch did not run because command allowlist validation failed."],
        )
        return emit(
            "launch",
            "inconclusive",
            {
                "approval_ref": args.approval_ref,
                "runtime_evidence_path": str(runtime_path) if runtime_path else "",
                "limitations": ["Remote/local launch did not run because command allowlist validation failed."],
            },
        )

    proc = subprocess.run(
        command,
        cwd=run_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=int(args.timeout_seconds),
    )
    stdout_path = run_dir / "remote_stdout.txt"
    stderr_path = run_dir / "remote_stderr.txt"
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    paths = result_paths(run_dir)
    summary = load_result_summary(paths)
    result_collected = bool(paths)
    metrics = summary["metrics"]
    outcome = summary["outcome"] or ("supports" if proc.returncode == 0 and result_collected else "inconclusive")
    runtime_status = "completed" if proc.returncode == 0 and result_collected else ("failed" if proc.returncode else "inconclusive")
    artifacts = [
        {"type": "remote_stdout", "path": str(stdout_path)},
        {"type": "remote_stderr", "path": str(stderr_path)},
        *[{"type": "remote_result", "path": str(path)} for path in paths],
    ]
    runtime_path = write_runtime_evidence(
        args=args,
        command_run=" ".join(command),
        exit_code=int(proc.returncode),
        status=runtime_status,
        checks=[
            {"check": "command_allowlisted", "status": "ok", "detail": allow_reason},
            {"check": "exit_code", "status": "ok" if proc.returncode == 0 else "error", "detail": f"exit_code={proc.returncode}"},
            {"check": "result_collected", "status": "ok" if result_collected else "error", "detail": ", ".join(str(path) for path in paths) if paths else "No result artifact found."},
        ],
        artifacts=artifacts,
        runtime_fields={
            "outcome": outcome,
            "result_collected": result_collected,
            "metrics": metrics,
            "logs": summary["logs"],
            "run_dir": str(run_dir),
            "result_paths": [str(path) for path in paths],
        },
        limitations=["Remote/local launch ran an explicitly approved and allowlisted command."],
    )
    return emit(
        "launch",
        runtime_status,
        {
            "approval_ref": args.approval_ref,
            "run_dir": str(run_dir),
            "exit_code": int(proc.returncode),
            "result_collected": result_collected,
            "runtime_evidence_path": str(runtime_path) if runtime_path else "",
            "artifacts": artifacts,
        },
        ok=runtime_status == "completed",
    )


def cmd_pull_results(args: argparse.Namespace) -> int:
    result_dir = Path(args.result_dir).expanduser() if args.result_dir else None
    if args.pull_command:
        payload: dict[str, Any] = {
            "result_dir": str(result_dir) if result_dir else "",
            "approval_ref": args.approval_ref,
            "transport": args.transport,
            "session_id": args.session_id,
            "collection_scope": "live",
            "live_remote_collection": True,
            "files": [],
            "count": 0,
        }
        if not args.approval_ref or not args.execute_approved:
            payload["limitations"] = ["Live/provider pull-results command requires --approval-ref and --execute-approved."]
            return emit("pull-results", "inconclusive", payload)
        command = shlex.split(args.pull_command)
        allowlists = load_allowlists(args.allowlist_evidence or [])
        allowed, allow_reason = command_allowlisted(command, allowlists)
        payload["allowlist_status"] = allow_reason
        if not allowed:
            payload["limitations"] = ["Live/provider pull-results command was not allowlisted."]
            return emit("pull-results", "inconclusive", payload)
        cwd = result_dir if result_dir else REPO_ROOT
        if result_dir:
            result_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=int(args.timeout_seconds),
        )
        stdout_path = result_dir / "pull_results_stdout.txt" if result_dir else None
        stderr_path = result_dir / "pull_results_stderr.txt" if result_dir else None
        if stdout_path:
            stdout_path.write_text(proc.stdout, encoding="utf-8")
        if stderr_path:
            stderr_path.write_text(proc.stderr, encoding="utf-8")
        ignored = {path for path in (stdout_path, stderr_path) if path is not None}
        files = [
            str(path)
            for path in sorted((result_dir or REPO_ROOT).rglob("*"))
            if path.is_file() and path not in ignored
        ] if result_dir else []
        payload["files"] = files
        payload["count"] = len(files)
        payload["pull_command_exit_code"] = int(proc.returncode)
        if proc.returncode != 0:
            payload["limitations"] = ["Live/provider pull-results command exited non-zero."]
            return emit("pull-results", "failed", payload)
        if files:
            return emit("pull-results", "completed", payload, ok=True)
        payload["limitations"] = ["Live/provider pull-results command did not produce result files."]
        return emit("pull-results", "inconclusive", payload)

    if result_dir and result_dir.exists():
        files = [str(path) for path in sorted(result_dir.rglob("*")) if path.is_file()]
        return emit("pull-results", "completed", {"result_dir": str(result_dir.resolve()), "files": files, "count": len(files)}, ok=True)
    return emit("pull-results", "inconclusive", {"result_dir": str(result_dir) if result_dir else "", "limitations": ["No local result directory was available to collect."]})


def cmd_check(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser() if args.run_dir else None
    if args.status_command:
        payload: dict[str, Any] = {
            "experiment": args.experiment,
            "approval_ref": args.approval_ref,
            "transport": args.transport,
            "session_id": args.session_id,
            "poll_scope": "live",
            "live_remote_poll": True,
            "checked_paths": [],
            "evidence_paths": [],
        }
        if not args.approval_ref or not args.execute_approved:
            payload["limitations"] = ["Live/provider status command requires --approval-ref and --execute-approved."]
            return emit("check", "inconclusive", payload)
        command = shlex.split(args.status_command)
        allowlists = load_allowlists(args.allowlist_evidence or [])
        allowed, allow_reason = command_allowlisted(command, allowlists)
        payload["allowlist_status"] = allow_reason
        if not allowed:
            payload["limitations"] = ["Live/provider status command was not allowlisted."]
            return emit("check", "inconclusive", payload)
        cwd = run_dir if run_dir else REPO_ROOT
        if run_dir:
            run_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=int(args.timeout_seconds),
        )
        stdout_path = run_dir / "status_command_stdout.txt" if run_dir else None
        stderr_path = run_dir / "status_command_stderr.txt" if run_dir else None
        if stdout_path:
            stdout_path.write_text(proc.stdout, encoding="utf-8")
        if stderr_path:
            stderr_path.write_text(proc.stderr, encoding="utf-8")
        checked_paths = [path for path in (stdout_path, stderr_path) if path is not None]
        payload["checked_paths"] = [str(path) for path in checked_paths]
        payload["evidence_paths"] = [str(path.resolve()) for path in checked_paths if path.exists()]
        payload["status_command_exit_code"] = int(proc.returncode)
        payload["remote_state"] = parse_status_value(proc.stdout)
        if proc.returncode != 0:
            payload["limitations"] = ["Live/provider status command exited non-zero."]
            return emit("check", "failed", payload)
        if payload["remote_state"]:
            return emit("check", "completed", payload, ok=True)
        payload["limitations"] = ["Live/provider status command did not report a remote state."]
        return emit("check", "inconclusive", payload)

    candidates = []
    if run_dir:
        candidates.extend([run_dir / "status.json", run_dir / "run_log.json", run_dir / "results.json"])
    existing = [path for path in candidates if path.exists()]
    payload: dict[str, Any] = {"experiment": args.experiment, "checked_paths": [str(path) for path in candidates]}
    if existing:
        payload["evidence_paths"] = [str(path.resolve()) for path in existing]
        return emit("check", "completed", payload, ok=True)
    payload["limitations"] = ["No runtime status artifact was found; remote status remains inconclusive."]
    return emit("check", "inconclusive", payload)


def cmd_remote_approval_required(args: argparse.Namespace) -> int:
    command = str(args.command)
    side_effects = {
        "status": ["ssh_connectivity_probe", "remote_gpu_probe"],
        "gpu-status": ["ssh_gpu_monitor_probe"],
        "sync-code": ["rsync_project_code", "remote_directory_mutation"],
        "setup-env": ["ssh_environment_install", "remote_dependency_mutation"],
        "tail-log": ["ssh_session_log_read"],
    }.get(command, ["remote_side_effect"])
    payload: dict[str, Any] = {
        "experiment": getattr(args, "experiment", "") or getattr(args, "name", ""),
        "approval_ref": getattr(args, "approval_ref", ""),
        "transport": getattr(args, "transport", ""),
        "session_id": getattr(args, "session_id", "") or getattr(args, "name", ""),
        "side_effects": side_effects,
        "limitations": [
            f"`{command}` is part of the native AutoSci remote CLI ABI, but OpenSolar requires an approved allowlisted executor before running SSH/rsync/screen operations.",
        ],
    }
    if getattr(args, "execute_approved", False):
        payload["limitations"].append(
            "No generic native executor is wired for this command; use `launch --command`, `check --status-command`, or `pull-results --pull-command` with approval evidence for executable remote proof."
        )
        return emit(command, "inconclusive", payload)
    return emit(command, "approval_required", payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("launch")
    command.add_argument("--approval-ref", default="")
    command.add_argument("--experiment", default="")
    command.add_argument("--allowlist-evidence", action="append", default=[])
    command.add_argument("--command", dest="command_run", default="")
    command.add_argument("--run-dir", default="")
    command.add_argument("--runtime-evidence-out", default="")
    command.add_argument("--timeout-seconds", type=int, default=120)
    command.add_argument("--execute-approved", action="store_true")
    command.set_defaults(func=cmd_launch)

    command = sub.add_parser("pull-results")
    command.add_argument("--result-dir", default="")
    command.add_argument("--approval-ref", default="")
    command.add_argument("--allowlist-evidence", action="append", default=[])
    command.add_argument("--pull-command", default="")
    command.add_argument("--transport", default="")
    command.add_argument("--session-id", default="")
    command.add_argument("--timeout-seconds", type=int, default=120)
    command.add_argument("--execute-approved", action="store_true")
    command.set_defaults(func=cmd_pull_results)

    command = sub.add_parser("check")
    command.add_argument("--experiment", default="")
    command.add_argument("--run-dir", default=os.environ.get("AUTOSCI_RUN_DIR", ""))
    command.add_argument("--approval-ref", default="")
    command.add_argument("--allowlist-evidence", action="append", default=[])
    command.add_argument("--status-command", default="")
    command.add_argument("--transport", default="")
    command.add_argument("--session-id", default="")
    command.add_argument("--timeout-seconds", type=int, default=120)
    command.add_argument("--execute-approved", action="store_true")
    command.set_defaults(func=cmd_check)

    command = sub.add_parser("status")
    command.add_argument("--experiment", default="")
    command.add_argument("--approval-ref", default="")
    command.add_argument("--transport", default="")
    command.add_argument("--session-id", default="")
    command.add_argument("--execute-approved", action="store_true")
    command.set_defaults(func=cmd_remote_approval_required)

    command = sub.add_parser("gpu-status")
    command.add_argument("--experiment", default="")
    command.add_argument("--approval-ref", default="")
    command.add_argument("--transport", default="")
    command.add_argument("--session-id", default="")
    command.add_argument("--execute-approved", action="store_true")
    command.set_defaults(func=cmd_remote_approval_required)

    command = sub.add_parser("sync-code")
    command.add_argument("--experiment", default="")
    command.add_argument("--approval-ref", default="")
    command.add_argument("--transport", default="")
    command.add_argument("--session-id", default="")
    command.add_argument("--local-path", default=".")
    command.add_argument("--dry-run", action="store_true")
    command.add_argument("--execute-approved", action="store_true")
    command.set_defaults(func=cmd_remote_approval_required)

    command = sub.add_parser("setup-env")
    command.add_argument("--experiment", default="")
    command.add_argument("--approval-ref", default="")
    command.add_argument("--transport", default="")
    command.add_argument("--session-id", default="")
    command.add_argument("--requirements", default="")
    command.add_argument("--execute-approved", action="store_true")
    command.set_defaults(func=cmd_remote_approval_required)

    command = sub.add_parser("tail-log")
    command.add_argument("--name", default="")
    command.add_argument("--experiment", default="")
    command.add_argument("--approval-ref", default="")
    command.add_argument("--transport", default="")
    command.add_argument("--session-id", default="")
    command.add_argument("--lines", type=int, default=80)
    command.add_argument("--execute-approved", action="store_true")
    command.set_defaults(func=cmd_remote_approval_required)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
