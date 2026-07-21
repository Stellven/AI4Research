#!/usr/bin/env python3
"""Solar-Harness adapter for the existing Meta-Harness outer-loop optimizer.

The Meta-Harness implementation lives outside this repo under
``~/.claude/core/solar-farm/meta-harness.ts``. This adapter makes it visible to
Solar-Harness without silently applying self-modifying patches.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
META_DIR = Path(os.environ.get("SOLAR_META_HARNESS_DIR", HOME / ".solar" / "meta-harness"))
TOOL = Path(os.environ.get("SOLAR_META_HARNESS_TOOL", HOME / ".claude" / "core" / "solar-farm" / "meta-harness.ts"))
SKILL = Path(os.environ.get("SOLAR_META_HARNESS_SKILL", HOME / ".claude" / "skills" / "meta-harness" / "SKILL.md"))
REPORTS = HARNESS / "reports" / "meta-harness"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def count_eval_items() -> int:
    data = load_json(META_DIR / "evaluation_set.json", [])
    return len(data) if isinstance(data, list) else 0


def pareto_summary() -> dict[str, Any]:
    data = load_json(META_DIR / "pareto.json", {})
    if not isinstance(data, dict):
        data = {}
    pareto = data.get("pareto") if isinstance(data.get("pareto"), list) else []
    all_runs = data.get("all_runs") if isinstance(data.get("all_runs"), list) else []
    return {
        "path": str(META_DIR / "pareto.json"),
        "exists": (META_DIR / "pareto.json").exists(),
        "pareto_count": len(pareto),
        "all_runs_count": len(all_runs),
        "best_run_id": str((pareto[0] or {}).get("run_id") or (pareto[0] or {}).get("id") or "") if pareto else "",
    }


def run_inventory() -> dict[str, Any]:
    runs_dir = META_DIR / "runs"
    run_dirs = sorted([p for p in runs_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True) if runs_dir.exists() else []
    return {
        "runs_dir": str(runs_dir),
        "exists": runs_dir.exists(),
        "count": len(run_dirs),
        "latest": run_dirs[0].name if run_dirs else "",
    }


def status() -> dict[str, Any]:
    bun = shutil.which("bun")
    config = load_json(META_DIR / "config.json", {})
    if not isinstance(config, dict):
        config = {}
    ok = TOOL.exists() and SKILL.exists() and META_DIR.exists()
    return {
        "ok": ok,
        "status": "ok" if ok else "pending",
        "integration_level": "solar_harness_cli_adapter" if ok else "external_tool_detected" if TOOL.exists() else "missing",
        "mode": "controlled_meta_harness_wrapper",
        "tool": {
            "path": str(TOOL),
            "exists": TOOL.exists(),
            "bun": bun or "",
            "bun_available": bool(bun),
        },
        "skill": {"path": str(SKILL), "exists": SKILL.exists()},
        "store": {
            "path": str(META_DIR),
            "exists": META_DIR.exists(),
            "config": str(META_DIR / "config.json"),
            "evaluation_set": str(META_DIR / "evaluation_set.json"),
            "evaluation_count": count_eval_items(),
            "proposer_model": str(config.get("proposer_model", "")),
            "evaluator_model": str(config.get("evaluator_model", "")),
            "max_iterations": config.get("max_iterations", ""),
        },
        "pareto": pareto_summary(),
        "runs": run_inventory(),
        "safety": {
            "default_execution": "dry_run",
            "run_requires_execute": True,
            "apply_defaults_to_dry_run": True,
            "real_apply_requires_execute": True,
            "coordinator_autorun": False,
        },
        "commands": {
            "status": "solar-harness meta-harness status --json",
            "run_dry": "solar-harness meta-harness run 3 hooks --json",
            "run_execute": "solar-harness meta-harness run 3 hooks --execute --json",
            "apply_dry": "solar-harness meta-harness apply <run_id> --json",
            "apply_execute": "solar-harness meta-harness apply <run_id> --execute --json",
        },
    }


def doctor() -> dict[str, Any]:
    st = status()
    checks = {
        "tool": {"ok": st["tool"]["exists"], "status": "ok" if st["tool"]["exists"] else "error", "path": st["tool"]["path"]},
        "bun": {"ok": st["tool"]["bun_available"], "status": "ok" if st["tool"]["bun_available"] else "warn", "path": st["tool"]["bun"], "optional_for_status": True},
        "skill": {"ok": st["skill"]["exists"], "status": "ok" if st["skill"]["exists"] else "warn", "path": st["skill"]["path"]},
        "store": {"ok": st["store"]["exists"], "status": "ok" if st["store"]["exists"] else "pending", "path": st["store"]["path"]},
        "evaluation_set": {"ok": st["store"]["evaluation_count"] > 0, "status": "ok" if st["store"]["evaluation_count"] > 0 else "pending", "count": st["store"]["evaluation_count"]},
    }
    errors = [k for k, v in checks.items() if v["status"] == "error"]
    pending = [k for k, v in checks.items() if v["status"] == "pending"]
    warnings = [k for k, v in checks.items() if v["status"] == "warn"]
    return {
        "ok": not errors and not pending,
        "status": "error" if errors else "pending" if pending else "warn" if warnings else "ok",
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "pending": pending,
    }


def build_command(subcmd: str, args: argparse.Namespace) -> list[str]:
    cmd = ["bun", str(TOOL), subcmd]
    if subcmd == "run":
        cmd.append(str(args.iterations))
        if args.domain:
            cmd.append(args.domain)
    elif subcmd == "init":
        pass
    elif subcmd == "apply":
        cmd.append(args.run_id)
        if args.force:
            cmd.append("--force")
        if not args.execute:
            cmd.append("--dry-run")
    elif subcmd == "evaluate":
        cmd.append(args.run_id)
    elif subcmd == "propose":
        if args.domain:
            cmd.append(args.domain)
    return cmd


def execute_or_preview(subcmd: str, args: argparse.Namespace) -> dict[str, Any]:
    if not TOOL.exists():
        return {"ok": False, "reason": "meta_harness_tool_missing", "tool": str(TOOL)}
    cmd = build_command(subcmd, args)
    payload: dict[str, Any] = {
        "ok": True,
        "subcommand": subcmd,
        "executed": bool(args.execute),
        "mode": "execute" if args.execute else "dry_run",
        "command": cmd,
        "generated_at": now(),
    }
    if not args.execute:
        return payload
    if not shutil.which("bun"):
        payload.update({"ok": False, "reason": "bun_not_found"})
        return payload
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=args.timeout, check=False)
    except Exception as exc:
        payload.update({"ok": False, "reason": f"{type(exc).__name__}: {exc}"})
        return payload
    payload.update(
        {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout_tail": proc.stdout[-6000:],
            "stderr_tail": proc.stderr[-6000:],
        }
    )
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "latest-command.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def history(args: argparse.Namespace) -> dict[str, Any]:
    data = status()
    if args.execute:
        return execute_or_preview("history", args)
    return {
        "ok": True,
        "mode": "dry_run",
        "pareto": data["pareto"],
        "runs": data["runs"],
        "command": ["bun", str(TOOL), "history"],
    }


def emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Solar-Harness Meta-Harness adapter")
    sub = parser.add_subparsers(dest="cmd")
    for name in ("status", "doctor"):
        p = sub.add_parser(name)
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("init")
    p.add_argument("--json", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--timeout", type=int, default=600)
    p = sub.add_parser("run")
    p.add_argument("iterations", nargs="?", type=int, default=3)
    p.add_argument("domain", nargs="?", default="")
    p.add_argument("--json", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--timeout", type=int, default=3600)
    p = sub.add_parser("propose")
    p.add_argument("domain", nargs="?", default="")
    p.add_argument("--json", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--timeout", type=int, default=1800)
    p = sub.add_parser("evaluate")
    p.add_argument("run_id")
    p.add_argument("--json", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--timeout", type=int, default=1800)
    p = sub.add_parser("apply")
    p.add_argument("run_id")
    p.add_argument("--json", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--timeout", type=int, default=600)
    p = sub.add_parser("history")
    p.add_argument("--json", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    if args.cmd == "doctor":
        data = doctor()
    elif args.cmd in {"init", "run", "propose", "evaluate", "apply"}:
        data = execute_or_preview(args.cmd, args)
    elif args.cmd == "history":
        data = history(args)
    else:
        data = status()
        args.json = getattr(args, "json", False)
    emit(data, bool(getattr(args, "json", False)))
    return 0 if data.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
