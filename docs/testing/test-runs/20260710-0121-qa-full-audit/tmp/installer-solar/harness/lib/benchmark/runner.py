"""CLI entrypoint for the Terminal-Bench 2.0 benchmark runner.

S03 N5: argparse with subparsers (doctor|list|plan|run|report).
Emits events to ~/.solar/harness/state/events.jsonl with compat fallback.
Exit codes: 0=ok, 1=error, 2=warn/pending, 3=usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from . import terminal_bench  # noqa: F401 — trigger registry seeding
from .registry import get_adapter, list_adapters
from .reports import write_run_artifacts
from .schemas import (
    DEFAULT_DATASET,
    asdict_run_result,
)

_EVENTS_LEDGER = Path.home() / ".solar" / "harness" / "state" / "events.jsonl"

_EXIT_OK = 0
_EXIT_ERROR = 1
_EXIT_PENDING = 2
_EXIT_USAGE = 3


def _emit_event(
    event_name: str,
    payload: dict[str, Any],
    run_dir: Path | None = None,
) -> None:
    """Append a benchmark event to the main ledger.

    Falls back to <run-dir>/events.compat.jsonl if the main ledger is
    unwritable (CBD4).
    """
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actor": "benchmark",
        "event": event_name,
        **payload,
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"

    try:
        _EVENTS_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with _EVENTS_LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except (OSError, PermissionError):
        if run_dir is not None:
            compat = run_dir / "events.compat.jsonl"
            compat.parent.mkdir(parents=True, exist_ok=True)
            with compat.open("a", encoding="utf-8") as fh:
                fh.write(line)


def _verdict_exit_code(verdict: str) -> int:
    """Map verdict string to exit code."""
    if verdict == "ok":
        return _EXIT_OK
    if verdict in ("pending", "warn"):
        return _EXIT_PENDING
    return _EXIT_ERROR


def _add_json_flag(p: argparse.ArgumentParser) -> None:
    """Add --json flag to a subparser."""
    p.add_argument("--json", action="store_true", help="Output JSON to stdout")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark",
        description="Terminal-Bench 2.0 benchmark runner",
    )

    sub = parser.add_subparsers(dest="command")

    # doctor
    p_doctor = sub.add_parser("doctor", help="Check prerequisites")
    p_doctor.add_argument("adapter", nargs="?", default=DEFAULT_DATASET)
    _add_json_flag(p_doctor)

    # list
    p_list = sub.add_parser("list", help="List available tasks")
    p_list.add_argument("--adapter", default=DEFAULT_DATASET)
    _add_json_flag(p_list)

    # plan
    p_plan = sub.add_parser("plan", help="Build Harbor command without executing")
    p_plan.add_argument("adapter", nargs="?", default=DEFAULT_DATASET)
    p_plan.add_argument("--agent", required=True)
    p_plan.add_argument("--model", required=True)
    p_plan.add_argument("--env", default="docker")
    p_plan.add_argument("--tasks", default="", help="Comma-separated task ids")
    p_plan.add_argument("--n-concurrent", type=int, default=1)
    _add_json_flag(p_plan)

    # run
    p_run = sub.add_parser("run", help="Execute benchmark run")
    p_run.add_argument("adapter", nargs="?", default=DEFAULT_DATASET)
    p_run.add_argument("--agent", required=True)
    p_run.add_argument("--model", required=True)
    p_run.add_argument("--env", default="docker")
    p_run.add_argument("--tasks", default="", help="Comma-separated task ids")
    p_run.add_argument("--n-concurrent", type=int, default=1)
    p_run.add_argument("--full", action="store_true")
    p_run.add_argument("--confirm-budget", action="store_true")
    p_run.add_argument("--dry-run", action="store_true", default=True)
    p_run.add_argument("--no-dry-run", action="store_false", dest="dry_run")
    _add_json_flag(p_run)

    # report
    p_report = sub.add_parser("report", help="Read a previous run report")
    p_report.add_argument("run_id", help="Run ID to look up")
    _add_json_flag(p_report)

    # Internal host-side entrypoint used by Harbor custom agents.
    p_solve = sub.add_parser("solve-terminal-task", help=argparse.SUPPRESS)
    p_solve.add_argument("--workspace", required=True)
    p_solve.add_argument("--instruction-file", required=True)
    p_solve.add_argument("--backend", default="auto")
    p_solve.add_argument("--model", default="gpt-5.4")
    p_solve.add_argument("--logs-dir", required=True)
    p_solve.add_argument(
        "--timeout-sec",
        type=int,
        default=int(os.environ.get("SOLAR_HARNESS_AGENT_TIMEOUT_SEC", "900")),
    )
    _add_json_flag(p_solve)

    return parser


def _cmd_doctor(args: argparse.Namespace) -> int:
    adapter_id = getattr(args, "adapter", DEFAULT_DATASET)
    try:
        adapter = get_adapter(adapter_id)
    except KeyError:
        print(f"Error: unknown adapter {adapter_id!r}", file=sys.stderr)
        return _EXIT_ERROR

    doc = adapter.doctor()

    _emit_event("benchmark.doctor", {
        "adapter_id": adapter_id,
        "verdict": "ok" if not doc.missing_prereqs else "pending",
        "missing_prereqs": list(doc.missing_prereqs),
    })

    if args.json:
        print(json.dumps(asdict(doc), indent=2, ensure_ascii=False, default=str))
    else:
        print(f"Adapter: {doc.adapter_id}")
        print(f"Harbor: {'ok' if doc.harbor_available else 'MISSING'} ({doc.harbor_kind})")
        print(f"Docker: {'ok' if doc.docker_available else 'MISSING'}")
        print(f"Dataset: {'ok' if doc.dataset_known else 'unknown'}")
        print(f"Agents: {', '.join(doc.agents_known) or 'none'}")
        if doc.missing_prereqs:
            print(f"Missing: {', '.join(doc.missing_prereqs)}")

    return _EXIT_OK


def _cmd_list(args: argparse.Namespace) -> int:
    try:
        adapter = get_adapter(args.adapter)
    except KeyError:
        print(f"Error: unknown adapter {args.adapter!r}", file=sys.stderr)
        return _EXIT_ERROR

    tasks = adapter.list_tasks()
    if args.json:
        print(json.dumps([asdict(t) for t in tasks], indent=2, ensure_ascii=False))
    else:
        for t in tasks:
            tags = ", ".join(t.tags)
            print(f"  {t.id:30s} {t.title:30s} [{tags}]")
    return _EXIT_OK


def _cmd_plan(args: argparse.Namespace) -> int:
    from .schemas import BenchmarkRunRequest

    try:
        adapter = get_adapter(args.adapter)
    except KeyError:
        print(f"Error: unknown adapter {args.adapter!r}", file=sys.stderr)
        return _EXIT_ERROR

    tasks = tuple(t for t in args.tasks.split(",") if t) if args.tasks else ()
    req = BenchmarkRunRequest(
        adapter_id=adapter.id,
        agent=args.agent,
        model=args.model,
        env=args.env,
        tasks=tasks,
        n_concurrent=args.n_concurrent,
    )

    plan = adapter.plan(req)

    _emit_event("benchmark.plan", {
        "adapter_id": adapter.id,
        "command_argv": list(plan.command),
        "dry_run": True,
    })

    if args.json:
        data = {
            "command": list(plan.command),
            "env_overrides": plan.env_overrides,
            "notes": plan.notes,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Command: {' '.join(plan.command)}")
        if plan.env_overrides:
            print(f"Env overrides: {plan.env_overrides}")
        if plan.notes:
            print(f"Notes: {plan.notes}")

    return _EXIT_OK


def _cmd_run(args: argparse.Namespace) -> int:
    from .schemas import BenchmarkRunRequest
    from .reports import _reports_base

    try:
        adapter = get_adapter(args.adapter)
    except KeyError:
        print(f"Error: unknown adapter {args.adapter!r}", file=sys.stderr)
        return _EXIT_ERROR

    tasks = tuple(t for t in args.tasks.split(",") if t) if args.tasks else ()
    req = BenchmarkRunRequest(
        adapter_id=adapter.id,
        agent=args.agent,
        model=args.model,
        env=args.env,
        tasks=tasks,
        n_concurrent=args.n_concurrent,
        full=args.full,
        confirm_budget=args.confirm_budget,
        dry_run=args.dry_run,
    )

    _emit_event("benchmark.run.started", {
        "adapter_id": adapter.id,
        "agent": args.agent,
        "model": args.model,
        "env": args.env,
        "tasks": list(tasks),
        "dry_run": args.dry_run,
    })

    result = adapter.run(req)

    reports_base = _reports_base()
    run_dir = reports_base / result.run_id
    write_run_artifacts(run_dir, result)

    event_name = "benchmark.run.completed" if result.verdict == "ok" else "benchmark.run.pending"
    _emit_event(event_name, {
        "run_id": result.run_id,
        "verdict": result.verdict,
        "score": result.score,
        "pass_count": result.pass_count,
        "fail_count": result.fail_count,
        "duration_sec": result.duration_sec,
    }, run_dir=run_dir)

    if args.json:
        print(json.dumps(asdict_run_result(result), indent=2, ensure_ascii=False))
    else:
        print(f"Run ID: {result.run_id}")
        print(f"Verdict: {result.verdict}")
        if result.failure_modes:
            print(f"Failure modes: {', '.join(result.failure_modes)}")
        if result.limitations:
            for lim in result.limitations:
                print(f"  Note: {lim}")
        print(f"Report: {run_dir}/report.md")

    return _verdict_exit_code(result.verdict)


def _cmd_report(args: argparse.Namespace) -> int:
    from .reports import _reports_base

    reports_base = _reports_base()
    run_json = reports_base / args.run_id / "run.json"

    if not run_json.is_file():
        print(f"Error: no run.json found for run {args.run_id!r}", file=sys.stderr)
        return _EXIT_ERROR

    with run_json.open(encoding="utf-8") as fh:
        data = json.load(fh)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        report_md = run_json.parent / "report.md"
        if report_md.is_file():
            print(report_md.read_text(encoding="utf-8"))
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))

    return _EXIT_OK


def _cmd_solve_terminal_task(args: argparse.Namespace) -> int:
    from .solar_solver import solve_terminal_task

    try:
        result = solve_terminal_task(
            workspace=Path(args.workspace),
            instruction_file=Path(args.instruction_file),
            backend=args.backend,
            model=args.model,
            logs_dir=Path(args.logs_dir),
            timeout_sec=args.timeout_sec,
        )
    except Exception as exc:
        result = {
            "return_code": 1,
            "error": str(exc),
            "workspace": args.workspace,
            "logs_dir": args.logs_dir,
        }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps(result, ensure_ascii=False, default=str))
    return _EXIT_OK if result.get("return_code") == 0 else _EXIT_ERROR


def main(argv: Sequence[str] | None = None) -> int:
    """Parse args and dispatch to subcommand handler."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return _EXIT_USAGE

    handlers = {
        "doctor": _cmd_doctor,
        "list": _cmd_list,
        "plan": _cmd_plan,
        "run": _cmd_run,
        "report": _cmd_report,
        "solve-terminal-task": _cmd_solve_terminal_task,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return _EXIT_USAGE

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
