#!/usr/bin/env python3
"""ruflo_adapter.py — safe read-only Ruflo integration status.

The adapter vendors ruvnet/ruflo and exposes inventory/status to Solar-Harness
without running `ruflo init`, registering MCP, or writing Claude Code hooks.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import shutil
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hands_runtime import SandboxHand  # noqa: E402
from runtime_interfaces import ResultStatus  # noqa: E402


HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
RUFLO_DIR = Path(os.environ.get("RUFLO_SOURCE_DIR", HARNESS / "vendor" / "ruflo"))
RUFLO_REPO = "https://github.com/ruvnet/ruflo.git"
RUFLO_STATE = HARNESS / "state" / "ruflo"
RUFLO_RUNTIME = Path(os.environ.get("RUFLO_RUNTIME_DIR", RUFLO_STATE / "claude-flow-runtime"))
RUFLO_REPORTS = HARNESS / "reports" / "ruflo"
RUFLO_RUNTIME_PACKAGE = os.environ.get("RUFLO_RUNTIME_PACKAGE", "@claude-flow/cli@latest")


def _run(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int = 10,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except Exception as exc:
        return 99, f"{type(exc).__name__}: {exc}"


def _run_sandboxed(
    cmd: list[str],
    cwd: Path,
    timeout: int,
    env: dict[str, str],
    *,
    guard_root: Path,
    command_name: str,
) -> tuple[int, str, dict[str, Any]]:
    """Run a Ruflo runtime command through Solar's local SandboxHand.

    Ruflo runtime commands are allowed to touch only the managed Ruflo runtime
    directory. The disposable hand still provides evidence, argv-mode execution,
    redaction, activity events, and write-guard telemetry.
    """
    hand = SandboxHand()
    ref = hand.provision(capabilities=["ruflo-runtime", command_name])
    script = "cd {cwd} && env {env} {cmd}".format(
        cwd=shlex.quote(str(cwd)),
        env=" ".join(f"{key}={shlex.quote(str(value))}" for key, value in sorted(env.items())),
        cmd=" ".join(shlex.quote(str(part)) for part in cmd),
    )
    try:
        result = hand.execute(
            ref,
            f"ruflo-{command_name}",
            {
                "argv": ["/bin/sh", "-lc", script],
                "write_guard_roots": [str(guard_root)],
                "write_allowed_roots": [str(guard_root)],
                "session_id": f"ruflo-runtime-{os.getpid()}",
                "sprint_id": f"ruflo-runtime-{os.getpid()}",
                "activity_id": f"ruflo-{command_name}",
            },
            idempotency_key=f"ruflo-runtime:{command_name}:{os.getpid()}:{hashlib.sha1(script.encode()).hexdigest()[:12]}",
            timeout_seconds=timeout,
        )
        output_parts = [str(result.output or "")]
        stderr = str((result.metadata or {}).get("stderr", "") or "")
        if stderr:
            output_parts.append(stderr)
        code = 0 if result.status == ResultStatus.OK else 1
        if result.status == ResultStatus.TIMEOUT:
            code = 124
        meta = {
            "executor": "sandbox",
            "execution_mode": (result.metadata or {}).get("execution_mode", ""),
            "write_guard": (result.metadata or {}).get("write_guard", {}),
            "evidence_file": (result.metadata or {}).get("evidence_file", ""),
            "sandbox_status": result.status.value if hasattr(result.status, "value") else str(result.status),
        }
        return code, "\n".join(part for part in output_parts if part).strip(), meta
    finally:
        hand.dispose(ref)


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(args: list[str]) -> str:
    if not RUFLO_DIR.exists():
        return ""
    code, out = _run(["git", *args], cwd=RUFLO_DIR, timeout=5)
    return out.splitlines()[0].strip() if code == 0 and out else ""


def _read_package() -> dict[str, Any]:
    path = RUFLO_DIR / "package.json"
    if not path.exists():
        return {"ok": False, "reason": "package.json missing"}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {"ok": False, "reason": f"package.json invalid: {exc}"}
    return {
        "ok": True,
        "name": data.get("name"),
        "version": data.get("version"),
        "description": data.get("description"),
        "bin": data.get("bin", {}),
        "node_engine": (data.get("engines") or {}).get("node"),
    }


def _count_paths() -> dict[str, Any]:
    if RUFLO_DIR.exists():
        by_lower = {str(p).lower(): p for p in RUFLO_DIR.rglob("SKILL.md")}
        by_lower.update({str(p).lower(): p for p in RUFLO_DIR.rglob("skill.md")})
        skill_files = sorted(str(p) for p in by_lower.values())
    else:
        skill_files = []
    plugin_dirs = [p for p in (RUFLO_DIR / "plugins").iterdir() if p.is_dir()] if (RUFLO_DIR / "plugins").exists() else []
    agent_files = list((RUFLO_DIR / ".agents").rglob("*.md")) if (RUFLO_DIR / ".agents").exists() else []
    return {
        "skill_files": len(skill_files),
        "plugins": len(plugin_dirs),
        "agent_markdown_files": len(agent_files),
        "sample_skills": [str(Path(p).relative_to(RUFLO_DIR)) for p in skill_files[:20]],
        "sample_plugins": [p.name for p in plugin_dirs[:40]],
    }


def _case_collision_warnings() -> list[str]:
    warnings: list[str] = []
    code, out = _run(["git", "ls-files"], cwd=RUFLO_DIR, timeout=10)
    if code == 0:
        by_lower: dict[str, list[str]] = {}
        for line in out.splitlines():
            by_lower.setdefault(line.lower(), []).append(line)
        collisions = [paths for paths in by_lower.values() if len(paths) > 1]
        for paths in collisions[:20]:
            hashes: set[str] = set()
            for item in paths:
                try:
                    payload = (RUFLO_DIR / item).read_bytes()
                    hashes.add(hashlib.sha256(payload).hexdigest())
                except Exception:
                    hashes.add("unreadable")
            if len(hashes) > 1:
                warnings.append("case-collision-content-differs: " + " | ".join(paths))
    return warnings


def status() -> dict[str, Any]:
    exists = RUFLO_DIR.exists()
    pkg = _read_package() if exists else {"ok": False, "reason": "source missing"}
    counts = _count_paths() if exists else {"skill_files": 0, "plugins": 0, "agent_markdown_files": 0}
    warnings = _case_collision_warnings() if exists else []
    runtime = runtime_status()
    return {
        "ok": exists and bool(pkg.get("ok")),
        "integration_level": "full_runtime_usable" if runtime.get("ok") else "basic_usable",
        "mode": "read_only_safe_vendor",
        "source": {
            "path": str(RUFLO_DIR),
            "repo": _git(["remote", "get-url", "origin"]),
            "commit": _git(["rev-parse", "--short", "HEAD"]),
            "exists": exists,
        },
        "package": pkg,
        "inventory": counts,
        "warnings": warnings,
        "runtime": runtime,
        "blocked_actions": [
            "Host-level ruflo init is still blocked because it writes .claude, hooks, MCP config and workspace files.",
            "Full runtime is allowed only inside the Solar-managed sandbox runtime directory.",
        ],
    }


def _runtime_env(runtime_dir: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "LANG", "LC_ALL", "TERM", "SHELL"):
        if key in os.environ:
            env[key] = os.environ[key]
    env["HOME"] = str(runtime_dir / "home")
    env["npm_config_cache"] = str(runtime_dir / "npm-cache")
    env["CLAUDE_CONFIG_DIR"] = str(runtime_dir / "home" / ".claude")
    env["RUFLO_SANDBOX"] = "1"
    return env


def runtime_paths(runtime_dir: Path = RUFLO_RUNTIME) -> dict[str, str]:
    source = runtime_dir / "source"
    work = runtime_dir / "work"
    return {
        "runtime_dir": str(runtime_dir),
        "source": str(source),
        "home": str(runtime_dir / "home"),
        "npm_cache": str(runtime_dir / "npm-cache"),
        "work": str(work),
        "published_cli": str(work / "node_modules" / ".bin" / "claude-flow"),
        "published_mcp_cli": str(work / "node_modules" / ".bin" / "claude-flow-mcp"),
        "published_package": str(work / "node_modules" / "@claude-flow" / "cli" / "package.json"),
        "source_cli": str(source / "bin" / "cli.js"),
        "source_cli_dist": str(source / "v3" / "@claude-flow" / "cli" / "dist" / "src" / "index.js"),
    }


def runtime_status(runtime_dir: Path = RUFLO_RUNTIME) -> dict[str, Any]:
    paths = runtime_paths(runtime_dir)
    source = Path(paths["source"])
    work = Path(paths["work"])
    published_cli = Path(paths["published_cli"])
    published_package = Path(paths["published_package"])
    source_cli = Path(paths["source_cli"])
    source_dist = Path(paths["source_cli_dist"])
    evidence = runtime_dir / "runtime-smoke.json"
    package_data: dict[str, Any] = {}
    if published_package.exists():
        try:
            package_data = json.loads(published_package.read_text(encoding="utf-8"))
        except Exception as exc:
            package_data = {"error": str(exc)}
    backend = "none"
    if published_cli.exists():
        backend = "official_claude_flow_cli"
    elif source_cli.exists():
        backend = "vendored_ruflo_source"
    data: dict[str, Any] = {
        "ok": False,
        "integration_level": "pending",
        "mode": "sandboxed_full_runtime",
        "backend": backend,
        "runtime_package": RUFLO_RUNTIME_PACKAGE,
        "paths": paths,
        "work_exists": work.exists(),
        "source_exists": source.exists(),
        "node_modules_exists": (work / "node_modules").exists() or (source / "node_modules").exists(),
        "cli_exists": published_cli.exists() or source_cli.exists(),
        "published_cli_exists": published_cli.exists(),
        "published_package": package_data,
        "source_cli_exists": source_cli.exists(),
        "source_cli_dist_exists": source_dist.exists(),
        "evidence": str(evidence),
    }
    if evidence.exists():
        try:
            smoke = json.loads(evidence.read_text(encoding="utf-8"))
            data["last_smoke"] = smoke
            if smoke.get("ok"):
                data["ok"] = True
                data["integration_level"] = "full_runtime_usable"
        except Exception as exc:
            data["last_smoke_error"] = str(exc)
    return data


def bootstrap_runtime(runtime_dir: Path = RUFLO_RUNTIME, force: bool = False, build: bool = False) -> dict[str, Any]:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    work = runtime_dir / "work"
    if force and work.exists():
        shutil.rmtree(work)
    for key in ("home", "npm-cache", "work"):
        (runtime_dir / key).mkdir(parents=True, exist_ok=True)

    steps: list[dict[str, Any]] = []
    env = _runtime_env(runtime_dir)
    if not (work / "package.json").exists():
        code, out = _run(["npm", "init", "-y"], cwd=work, timeout=30, env=env)
        steps.append({"step": "npm_init", "ok": code == 0, "exit_code": code, "output_tail": out[-2000:]})
        if code != 0:
            return {"ok": False, "stage": "npm_init", "runtime": runtime_status(runtime_dir), "steps": steps}

    timeout = int(os.environ.get("RUFLO_RUNTIME_BOOTSTRAP_TIMEOUT", "900"))
    code, out = _run(
        [
            "npm",
            "install",
            "--ignore-scripts",
            "--omit=optional",
            "--no-audit",
            "--no-fund",
            RUFLO_RUNTIME_PACKAGE,
        ],
        cwd=work,
        timeout=timeout,
        env=env,
    )
    steps.append({"step": "npm_install_official_cli", "ok": code == 0, "exit_code": code, "output_tail": out[-4000:]})
    if code != 0:
        return {"ok": False, "stage": "npm_install_official_cli", "runtime": runtime_status(runtime_dir), "steps": steps}

    if build:
        source = runtime_dir / "source"
        if not source.exists():
            ignore = shutil.ignore_patterns(".git", "node_modules", ".turbo", "dist")
            shutil.copytree(RUFLO_DIR, source, ignore=ignore)
        code, out = _run(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=source, timeout=300, env=env)
        steps.append({"step": "source_npm_ci", "ok": code == 0, "exit_code": code, "output_tail": out[-4000:]})
        if code == 0:
            code, out = _run(["npm", "run", "build"], cwd=source, timeout=180, env=env)
            steps.append({"step": "source_npm_run_build", "ok": code == 0, "exit_code": code, "output_tail": out[-4000:]})
        if code != 0:
            return {"ok": False, "stage": "source_build", "runtime": runtime_status(runtime_dir), "steps": steps}

    return {"ok": True, "stage": "bootstrap", "runtime": runtime_status(runtime_dir), "steps": steps}


def runtime_smoke(runtime_dir: Path = RUFLO_RUNTIME, bootstrap: bool = False) -> dict[str, Any]:
    if bootstrap:
        boot = bootstrap_runtime(runtime_dir=runtime_dir)
        if not boot.get("ok"):
            return boot
    paths = runtime_paths(runtime_dir)
    work = Path(paths["work"])
    source = Path(paths["source"])
    published_cli = Path(paths["published_cli"])
    source_cli = Path(paths["source_cli"])
    env = _runtime_env(runtime_dir)
    if published_cli.exists():
        cwd = work
        backend = "official_claude_flow_cli"
        commands = [
            {"name": "help", "cmd": [str(published_cli), "--help"], "timeout": 30},
            {"name": "version", "cmd": [str(published_cli), "--version"], "timeout": 30},
            {"name": "mcp_help", "cmd": [str(published_cli), "mcp", "--help"], "timeout": 30},
        ]
    elif source_cli.exists():
        cwd = source
        backend = "vendored_ruflo_source"
        commands = [
            {"name": "help", "cmd": ["node", "bin/cli.js", "--help"], "timeout": 30},
            {"name": "version", "cmd": ["node", "bin/cli.js", "--version"], "timeout": 30},
        ]
    else:
        payload = {
            "ok": False,
            "checked_at": _utc_now(),
            "runtime_dir": str(runtime_dir),
            "backend": "none",
            "error": "no executable Ruflo/Claude-Flow CLI found in sandbox; run ruflo-runtime-bootstrap first",
            "commands": [],
        }
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "runtime-smoke.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        RUFLO_REPORTS.mkdir(parents=True, exist_ok=True)
        (RUFLO_REPORTS / "runtime-smoke-latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload
    results = []
    ok = True
    for item in commands:
        code, out, sandbox_meta = _run_sandboxed(
            item["cmd"],
            cwd=cwd,
            timeout=item["timeout"],
            env=env,
            guard_root=runtime_dir,
            command_name=item["name"],
        )
        passed = code == 0 and bool(out.strip())
        ok = ok and passed
        results.append({
            "name": item["name"],
            "ok": passed,
            "exit_code": code,
            "output_tail": out[-4000:],
            **sandbox_meta,
        })
    payload = {
        "ok": ok,
        "checked_at": _utc_now(),
        "runtime_dir": str(runtime_dir),
        "backend": backend,
        "runtime_package": RUFLO_RUNTIME_PACKAGE,
        "commands": results,
        "host_pollution_check": {
            "sandbox_home": str(runtime_dir / "home"),
            "host_claude_dir_unchanged_by_policy": True,
        },
    }
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "runtime-smoke.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    RUFLO_REPORTS.mkdir(parents=True, exist_ok=True)
    (RUFLO_REPORTS / "runtime-smoke-latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def vendor(update: bool = False) -> dict[str, Any]:
    RUFLO_DIR.parent.mkdir(parents=True, exist_ok=True)
    if RUFLO_DIR.exists():
        if update:
            code, out = _run(["git", "-C", str(RUFLO_DIR), "pull", "--ff-only"], timeout=120)
            return {"ok": code == 0, "action": "update", "output": out, "status": status()}
        return {"ok": True, "action": "noop", "status": status()}
    code, out = _run(["git", "clone", "--depth", "1", RUFLO_REPO, str(RUFLO_DIR)], timeout=300)
    return {"ok": code == 0, "action": "clone", "output": out, "status": status()}


def main() -> int:
    ap = argparse.ArgumentParser(prog="ruflo_adapter.py")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("vendor")
    p.add_argument("--json", action="store_true")
    p.add_argument("--update", action="store_true")
    p = sub.add_parser("runtime-status")
    p.add_argument("--json", action="store_true")
    p.add_argument("--runtime-dir", default="")
    p = sub.add_parser("runtime-bootstrap")
    p.add_argument("--json", action="store_true")
    p.add_argument("--runtime-dir", default="")
    p.add_argument("--force", action="store_true")
    p.add_argument("--no-build", action="store_true")
    p = sub.add_parser("runtime-smoke")
    p.add_argument("--json", action="store_true")
    p.add_argument("--runtime-dir", default="")
    p.add_argument("--bootstrap", action="store_true")
    args = ap.parse_args()

    if args.cmd == "vendor":
        data = vendor(update=args.update)
    elif args.cmd == "runtime-status":
        data = runtime_status(Path(args.runtime_dir) if args.runtime_dir else RUFLO_RUNTIME)
    elif args.cmd == "runtime-bootstrap":
        data = bootstrap_runtime(
            runtime_dir=Path(args.runtime_dir) if args.runtime_dir else RUFLO_RUNTIME,
            force=args.force,
            build=not args.no_build,
        )
    elif args.cmd == "runtime-smoke":
        data = runtime_smoke(
            runtime_dir=Path(args.runtime_dir) if args.runtime_dir else RUFLO_RUNTIME,
            bootstrap=args.bootstrap,
        )
    else:
        data = status()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if data.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
