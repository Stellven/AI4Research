#!/usr/bin/env python3
"""Solar-Harness adapter for smallnest/autoresearch.

Solar uses autoresearch as a pane-level execution optimizer/advisor and explicit
issue implementation loop. It is not a replacement builder; `run-local` is
dry-run unless `--execute` is provided.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
SOURCE_DIR = Path(os.environ.get("AUTORESEARCH_SOURCE_DIR", HARNESS / "vendor" / "autoresearch"))
REPO = "https://github.com/smallnest/autoresearch.git"
REPORTS = HARNESS / "reports" / "autoresearch"


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 30, env: dict[str, str] | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, text=True, capture_output=True, timeout=timeout, check=False)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except Exception as exc:
        return 99, f"{type(exc).__name__}: {exc}"


def git(args: list[str]) -> str:
    if not SOURCE_DIR.exists():
        return ""
    code, out = run(["git", *args], cwd=SOURCE_DIR, timeout=8)
    return out.splitlines()[0].strip() if code == 0 and out else ""


def text(path: Path, limit: int = 30000) -> str:
    return path.read_text(encoding="utf-8", errors="replace")[:limit] if path.exists() else ""


def vendor_meta() -> dict[str, str]:
    path = SOURCE_DIR / "SOLAR_VENDOR.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(k, str)}


def interface() -> dict[str, Any]:
    run_sh = SOURCE_DIR / "run.sh"
    payload = text(run_sh)
    return {
        "run_sh": str(run_sh),
        "run_sh_exists": run_sh.exists(),
        "run_sh_executable": run_sh.exists() and os.access(run_sh, os.X_OK),
        "local_issue_mode": "--issues-dir" in payload,
        "project_flag": "-p" in payload,
        "agents_flag": "-a" in payload,
        "max_iterations_positional": "max_iterations" in payload,
        "passing_score_env": "PASSING_SCORE" in payload,
    }


def inventory() -> dict[str, int]:
    if not SOURCE_DIR.exists():
        return {"shell_scripts": 0, "python_files": 0, "docs": 0, "agents": 0}
    return {
        "shell_scripts": len(list(SOURCE_DIR.rglob("*.sh"))),
        "python_files": len(list(SOURCE_DIR.rglob("*.py"))),
        "docs": len(list(SOURCE_DIR.rglob("*.md"))),
        "agents": len(list((SOURCE_DIR / "agents").glob("*"))) if (SOURCE_DIR / "agents").exists() else 0,
    }


def status() -> dict[str, Any]:
    iface = interface()
    exists = SOURCE_DIR.exists()
    meta = vendor_meta()
    return {
        "ok": exists and iface["run_sh_exists"],
        "integration_level": "basic_usable" if exists and iface["run_sh_exists"] else "pending",
        "mode": "pane_optimizer_advisor_and_explicit_local_issue_runner",
        "source": {
            "path": str(SOURCE_DIR),
            "repo": meta.get("upstream") or git(["remote", "get-url", "origin"]) or REPO,
            "commit": meta.get("commit") or git(["rev-parse", "--short", "HEAD"]),
            "exists": exists,
            "vendor_manifest": str(SOURCE_DIR / "SOLAR_VENDOR.json"),
        },
        "interface": iface,
        "inventory": inventory(),
        "safety": {
            "default_execution": "dry_run",
            "execute_requires_flag": "--execute",
            "issue_mode": "local_issue_file",
            "not_default_builder": True,
            "replaces_builder": False,
            "pane_optimizer_advisor": True,
        },
        "commands": {
            "vendor": "solar-harness integrations autoresearch-vendor --json",
            "doctor": "solar-harness integrations autoresearch-doctor --json",
            "dry_run": "solar-harness integrations autoresearch-run-local --project <repo> --issue-title <title> --issue-body <body> --json",
            "execute": "solar-harness integrations autoresearch-run-local --project <repo> --issue-file <md> --execute --json",
        },
    }


def doctor() -> dict[str, Any]:
    st = status()
    checks = {
        "vendor_source": {"status": "ok" if st["source"]["exists"] else "pending", "ok": bool(st["source"]["exists"]), "path": st["source"]["path"]},
        "run_sh": {"status": "ok" if st["interface"]["run_sh_exists"] else "pending", "ok": bool(st["interface"]["run_sh_exists"]), "path": st["interface"]["run_sh"]},
        "git": {"status": "ok" if shutil.which("git") else "error", "ok": bool(shutil.which("git"))},
        "gh": {"status": "ok" if shutil.which("gh") else "warn", "ok": True, "optional": True},
        "claude": {"status": "ok" if shutil.which("claude") else "warn", "ok": True, "optional": True},
        "codex": {"status": "ok" if shutil.which("codex") else "warn", "ok": True, "optional": True},
    }
    errors = [k for k, v in checks.items() if v["status"] == "error"]
    pending = [k for k, v in checks.items() if v["status"] == "pending"]
    warnings = [k for k, v in checks.items() if v["status"] == "warn"]
    return {"ok": not errors and not pending, "status": "error" if errors else ("pending" if pending else ("warn" if warnings else "ok")), "checks": checks, "errors": errors, "warnings": warnings, "pending": pending}


def vendor(update: bool = False) -> dict[str, Any]:
    SOURCE_DIR.parent.mkdir(parents=True, exist_ok=True)
    if SOURCE_DIR.exists():
        if update:
            code, out = run(["git", "-C", str(SOURCE_DIR), "pull", "--ff-only"], timeout=180)
            return {"ok": code == 0, "action": "update", "exit_code": code, "output_tail": out[-4000:], "status": status()}
        return {"ok": True, "action": "noop", "status": status()}
    code, out = run(["git", "clone", "--depth", "1", REPO, str(SOURCE_DIR)], timeout=300)
    return {"ok": code == 0, "action": "clone", "exit_code": code, "output_tail": out[-4000:], "status": status()}


def slug(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip().lower()).strip("-")[:80] or "solar-task"


def next_issue_number(issues_dir: Path) -> int:
    numbers = [int(m.group(1)) for p in issues_dir.glob("issue-*.md") if (m := re.match(r"issue-(\d+)-", p.name))]
    return max(numbers, default=0) + 1


def write_issue(project: Path, issues_dir: Path, title: str, body: str) -> Path:
    issues_dir.mkdir(parents=True, exist_ok=True)
    number = next_issue_number(issues_dir)
    path = issues_dir / f"issue-{number:03d}-{slug(title)}.md"
    path.write_text(f"# {title.strip() or 'Solar Autoresearch Task'}\n\n{body.strip() or 'No issue body provided.'}\n\n---\nCreated by Solar-Harness at {now()}\nProject: {project}\n", encoding="utf-8")
    return path


def command(project: Path, issue_number: int, issues_dir: Path, max_iterations: int, agents: str, no_archive: bool, continue_existing: bool) -> list[str]:
    cmd = ["bash", str(SOURCE_DIR / "run.sh"), "-p", str(project), f"--issues-dir={issues_dir}"]
    if agents.strip():
        cmd.extend(["-a", agents.strip()])
    if no_archive:
        cmd.append("--no-archive")
    if continue_existing:
        cmd.append("-c")
    cmd.extend([str(issue_number), str(max_iterations)])
    return cmd


def run_local(args: argparse.Namespace) -> dict[str, Any]:
    project = Path(args.project).expanduser().resolve()
    if not project.exists():
        return {"ok": False, "reason": "project_path_missing", "project": str(project)}
    if not (SOURCE_DIR / "run.sh").exists():
        return {"ok": False, "reason": "autoresearch_run_sh_missing", "autoresearch_dir": str(SOURCE_DIR)}
    issues_dir = Path(args.issues_dir).expanduser() if args.issues_dir else project / ".autoresearch" / "issues"
    if not issues_dir.is_absolute():
        issues_dir = project / issues_dir
    selected = int(args.issue_number or 0)
    created = ""
    if args.issue_file:
        src = Path(args.issue_file).expanduser().resolve()
        if not src.exists():
            return {"ok": False, "reason": "issue_file_missing", "issue_file": str(src)}
        issues_dir.mkdir(parents=True, exist_ok=True)
        target = issues_dir / src.name
        if src != target:
            target.write_text(src.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        match = re.match(r"issue-(\d+)-", target.name)
        if not match:
            return {"ok": False, "reason": "issue_file_name_must_match_issue_NNN_slug_md", "issue_file": str(target)}
        selected = int(match.group(1))
    elif args.issue_title or args.issue_body:
        target = write_issue(project, issues_dir, args.issue_title, args.issue_body)
        created = str(target)
        selected = int(re.match(r"issue-(\d+)-", target.name).group(1))  # type: ignore[union-attr]
    if not selected:
        return {"ok": False, "reason": "issue_number_or_issue_content_required"}
    cmd = command(project, selected, issues_dir, args.max_iterations, args.agents, args.no_archive, args.continue_existing)
    payload: dict[str, Any] = {"ok": True, "executed": False, "mode": "execute" if args.execute else "dry_run", "project": str(project), "issue_number": selected, "issues_dir": str(issues_dir), "created_issue": created, "command": cmd, "environment": {"PASSING_SCORE": str(args.passing_score)}}
    if not args.execute:
        return payload
    env = os.environ.copy()
    env["PASSING_SCORE"] = str(args.passing_score)
    code, out = run(cmd, cwd=SOURCE_DIR, timeout=args.timeout, env=env)
    payload.update({"executed": True, "ok": code == 0, "exit_code": code, "output_tail": out[-8000:]})
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "run-local-latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    for name in ("status", "doctor"):
        sub.add_parser(name).add_argument("--json", action="store_true")
    p = sub.add_parser("vendor")
    p.add_argument("--json", action="store_true")
    p.add_argument("--update", action="store_true")
    p = sub.add_parser("run-local")
    p.add_argument("--json", action="store_true")
    p.add_argument("--project", required=True)
    p.add_argument("--issue-file", default="")
    p.add_argument("--issue-title", default="")
    p.add_argument("--issue-body", default="")
    p.add_argument("--issue-number", type=int, default=0)
    p.add_argument("--issues-dir", default="")
    p.add_argument("--max-iterations", type=int, default=5)
    p.add_argument("--agents", default="")
    p.add_argument("--passing-score", type=int, default=80)
    p.add_argument("--no-archive", action="store_true")
    p.add_argument("--continue-existing", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    if args.cmd == "doctor":
        data = doctor()
    elif args.cmd == "vendor":
        data = vendor(update=args.update)
    elif args.cmd == "run-local":
        data = run_local(args)
    else:
        data = status()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if args.cmd in {"status", "doctor"} or data.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
