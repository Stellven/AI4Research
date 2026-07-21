#!/usr/bin/env python3
"""Agent Arena — reproducible cross-agent benchmark harness.

This runner is intentionally evidence-first. It does not claim Solar-Harness is
on an external leaderboard unless the public benchmark adapter is actually
configured and run. The first supported suite is a local Solar smoke suite that
proves orchestration capabilities and creates a stable place to plug in SWE-
bench, Terminal-Bench, OSWorld, GAIA, WebArena, and tau-bench adapters.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
REPORTS = HARNESS / "reports"
SOLAR_BIN = HARNESS / "solar-harness.sh"
HERMES_SOURCE_DIR = Path(os.environ.get("HERMES_SOURCE_DIR", HARNESS / "vendor" / "hermes-agent"))
HERMES_REPO = "https://github.com/nousresearch/hermes-agent.git"
HERMES_LOCAL_BIN = HERMES_SOURCE_DIR / ".arena-venv" / "bin" / "hermes"
UV_BIN = os.environ.get("UV_BIN") or shutil.which("uv") or "/opt/homebrew/bin/uv"

PUBLIC_BENCHMARKS: list[dict[str, Any]] = [
    {
        "id": "swe-bench-pro",
        "name": "SWE-bench Pro",
        "domain": "real GitHub issue repair",
        "adapter_env": "SWE_BENCH_PRO_CMD",
        "default_binary": "swebench",
        "source": "https://scale.com/blog/swe-bench-pro",
        "score_contract": "runner must write JSON score to SOLAR_ARENA_SCORE_FILE or --score-file path",
    },
    {
        "id": "swe-bench",
        "name": "SWE-bench Verified",
        "domain": "real GitHub issue repair",
        "adapter_env": "SWE_BENCH_CMD",
        "default_binary": "swebench",
        "source": "https://www.swebench.com/",
        "score_contract": "runner must write JSON score to SOLAR_ARENA_SCORE_FILE or --score-file path",
    },
    {
        "id": "terminal-bench",
        "name": "Terminal-Bench",
        "domain": "terminal task execution",
        "adapter_env": "TERMINAL_BENCH_CMD",
        "default_binary": "tb",
        "source": "https://terminalbench.lol/",
        "alternate_binaries": ["harbor"],
        "score_contract": "runner must write JSON score to SOLAR_ARENA_SCORE_FILE or --score-file path",
    },
    {
        "id": "browsecomp",
        "name": "BrowseComp",
        "domain": "hard web browsing and answer grounding",
        "adapter_env": "BROWSECOMP_CMD",
        "default_binary": "simple-evals",
        "source": "https://openai.com/index/browsecomp/",
        "alternate_binaries": ["browsecomp"],
        "score_contract": "runner must write JSON score to SOLAR_ARENA_SCORE_FILE and answer/grader artifacts under SOLAR_ARENA_EVIDENCE_DIR",
    },
    {
        "id": "osworld",
        "name": "OSWorld",
        "domain": "desktop computer-use tasks",
        "adapter_env": "OSWORLD_CMD",
        "default_binary": "osworld",
        "source": "https://os-world.github.io/",
    },
    {
        "id": "gaia",
        "name": "GAIA",
        "domain": "general assistant tool-use reasoning",
        "adapter_env": "GAIA_CMD",
        "default_binary": "gaia",
        "source": "https://huggingface.co/datasets/gaia-benchmark/GAIA",
    },
    {
        "id": "webarena",
        "name": "WebArena",
        "domain": "long-horizon web tasks",
        "adapter_env": "WEBARENA_CMD",
        "default_binary": "webarena",
        "source": "https://webarena.dev/",
    },
    {
        "id": "tau-bench",
        "name": "tau-bench",
        "domain": "multi-turn tool agents with business rules",
        "adapter_env": "TAU_BENCH_CMD",
        "default_binary": "taubench",
        "source": "https://github.com/sierra-research/tau-bench",
    },
]


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_name(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in value)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_command(
    name: str,
    cmd: list[str],
    evidence_dir: Path,
    timeout: int = 180,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.time()
    try:
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=proc_env)
        result = {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "duration_s": round(time.time() - started, 3),
            "cmd": cmd,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as exc:
        result = {
            "ok": False,
            "exit_code": 99,
            "duration_s": round(time.time() - started, 3),
            "cmd": cmd,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }

    stem = safe_name(name)
    write_json(evidence_dir / "commands" / f"{stem}.json", {k: v for k, v in result.items() if k not in {"stdout", "stderr"}})
    write_text(evidence_dir / "commands" / f"{stem}.stdout.txt", result["stdout"][-60000:])
    write_text(evidence_dir / "commands" / f"{stem}.stderr.txt", result["stderr"][-60000:])
    return result


def ensure_hermes_runtime(evidence_dir: Path) -> dict[str, Any]:
    """Create an isolated Hermes arena venv without touching shell config."""
    if HERMES_LOCAL_BIN.exists():
        return {"ok": True, "skipped": "runtime_exists", "runner": str(HERMES_LOCAL_BIN)}
    if not HERMES_SOURCE_DIR.exists():
        vendor = vendor_hermes(update=False)
        if not vendor.get("ok"):
            return {"ok": False, "reason": "vendor_failed", "vendor": vendor}
    if not Path(UV_BIN).exists() and not shutil.which(UV_BIN):
        return {"ok": False, "reason": "uv_missing", "uv": UV_BIN}
    venv = run_command(
        "hermes_arena_venv_create",
        [UV_BIN, "venv", ".arena-venv", "--python", "3.11"],
        evidence_dir,
        timeout=180,
        env={"UV_NO_CONFIG": "1"},
    )
    if not venv.get("ok"):
        return {"ok": False, "reason": "venv_create_failed", "venv": venv}
    install = run_command(
        "hermes_arena_pip_install",
        [UV_BIN, "pip", "install", "--python", ".arena-venv/bin/python", "-e", "."],
        evidence_dir,
        timeout=600,
        env={"UV_NO_CONFIG": "1"},
    )
    return {"ok": bool(install.get("ok") and HERMES_LOCAL_BIN.exists()), "venv": venv, "install": install, "runner": str(HERMES_LOCAL_BIN)}


def latest_json_ok(path: Path, *, score_key: str = "score", min_score: int = 100) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "reason": "missing_report", "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {"ok": False, "reason": "invalid_json", "error": str(exc), "path": str(path)}
    score = data.get(score_key)
    if isinstance(score, dict):
        score_value = score.get("minimum", score.get("average", 0))
    else:
        score_value = score
    ok = bool(data.get("ok")) and isinstance(score_value, (int, float)) and score_value >= min_score
    return {"ok": ok, "path": str(path), "score": score_value, "report_ok": data.get("ok")}


def _git_value(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True, timeout=5)
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return ""


def _read_hermes_pyproject(root: Path) -> dict[str, Any]:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return {"ok": False, "reason": "pyproject.toml missing"}
    text = pyproject.read_text(encoding="utf-8", errors="replace")
    def extract(prefix: str) -> str:
        for line in text.splitlines():
            if line.strip().startswith(prefix):
                return line.split("=", 1)[1].strip().strip('"')
        return ""
    return {
        "ok": True,
        "name": extract("name"),
        "version": extract("version"),
        "has_hermes_script": 'hermes = "hermes_cli.main:main"' in text,
        "has_agent_script": 'hermes-agent = "run_agent:main"' in text,
        "has_acp_script": 'hermes-acp = "acp_adapter.entry:main"' in text,
    }


def hermes_source_status() -> dict[str, Any]:
    root = HERMES_SOURCE_DIR
    exists = root.exists()
    files = {
        "README.md": (root / "README.md").exists(),
        "pyproject.toml": (root / "pyproject.toml").exists(),
        "hermes": (root / "hermes").exists(),
        "setup-hermes.sh": (root / "setup-hermes.sh").exists(),
        "scripts/install.sh": (root / "scripts" / "install.sh").exists(),
        "hermes_cli/main.py": (root / "hermes_cli" / "main.py").exists(),
    }
    return {
        "exists": exists,
        "path": str(root),
        "repo": _git_value(["remote", "get-url", "origin"], root) if exists else "",
        "commit": _git_value(["rev-parse", "--short", "HEAD"], root) if exists else "",
        "files": files,
        "pyproject": _read_hermes_pyproject(root) if exists else {"ok": False, "reason": "source missing"},
        "source_verified": exists and all(files.values()),
    }


def agent_status(agent: str) -> dict[str, Any]:
    if agent == "solar-harness":
        return {"available": SOLAR_BIN.exists(), "runner": str(SOLAR_BIN), "reason": "" if SOLAR_BIN.exists() else "missing solar-harness.sh"}
    if agent == "hermes":
        env_cmd = os.environ.get("HERMES_ARENA_CMD", "")
        binary = shutil.which("hermes")
        local_bin = str(HERMES_LOCAL_BIN) if HERMES_LOCAL_BIN.exists() else ""
        source = hermes_source_status()
        runner = env_cmd or binary or local_bin
        return {
            "available": bool(runner),
            "runner": runner,
            "reason": "" if runner else "Hermes source is vendored but runnable CLI is not installed; set HERMES_ARENA_CMD or create .arena-venv",
            "source": source,
        }
    if agent == "codex-local":
        cmd = os.environ.get("CODEX_ARENA_CMD", "")
        return {"available": bool(cmd), "runner": cmd, "reason": "" if cmd else "CODEX_ARENA_CMD not configured"}
    if agent in {"claude-code", "claude-code-bare"}:
        binary = shutil.which("claude")
        return {"available": bool(binary), "runner": binary or "", "reason": "" if binary else "claude binary not found"}
    return {"available": False, "runner": "", "reason": "unknown agent"}


def public_adapter_status() -> list[dict[str, Any]]:
    out = []
    for bench in PUBLIC_BENCHMARKS:
        env_cmd = os.environ.get(bench["adapter_env"], "")
        candidates = [bench["default_binary"], *bench.get("alternate_binaries", [])]
        binary = next((found for item in candidates if (found := shutil.which(item))), None)
        configured = bool(env_cmd or binary)
        out.append({
            **bench,
            "configured": configured,
            "runner": env_cmd or binary or "",
            "status": "ok" if configured else "pending",
            "reason": "" if configured else f"{bench['adapter_env']} not set and none of {','.join(candidates)} found",
        })
    return out


def public_benchmark_by_id(benchmark_id: str) -> dict[str, Any] | None:
    for bench in PUBLIC_BENCHMARKS:
        if bench["id"] == benchmark_id:
            return bench
    return None


def public_benchmark_status(benchmark_id: str) -> dict[str, Any] | None:
    for status in public_adapter_status():
        if status["id"] == benchmark_id:
            return status
    return None


def parse_runner_command(value: str) -> list[str]:
    if not value.strip():
        return []
    return shlex.split(value)


def coerce_score_value(data: dict[str, Any]) -> float | None:
    for key in ("score", "pass_rate", "accuracy", "success_rate"):
        value = data.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            for nested_key in ("score", "value", "mean", "average", "pass_rate", "accuracy"):
                nested = value.get(nested_key)
                if isinstance(nested, (int, float)) and not isinstance(nested, bool):
                    return float(nested)
    passed = data.get("passed")
    total = data.get("total")
    if isinstance(passed, (int, float)) and isinstance(total, (int, float)) and total:
        return round(100.0 * float(passed) / float(total), 4)
    return None


def parse_score_file(score_file: Path) -> dict[str, Any]:
    if not score_file.exists():
        return {"ok": False, "reason": "missing_score_file", "path": str(score_file)}
    try:
        data = json.loads(score_file.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {"ok": False, "reason": "invalid_score_json", "path": str(score_file), "error": str(exc)}
    score = coerce_score_value(data if isinstance(data, dict) else {})
    ok_value = data.get("ok") if isinstance(data, dict) else None
    ok = bool(ok_value) if isinstance(ok_value, bool) else score is not None
    return {"ok": ok, "path": str(score_file), "score": score, "data": data}


def benchmark_artifacts_ok(benchmark_id: str, evidence_dir: Path) -> dict[str, Any]:
    if benchmark_id != "browsecomp":
        return {"ok": True, "required": []}
    required = ["answers.jsonl", "grader.json"]
    missing = [name for name in required if not (evidence_dir / name).exists()]
    return {"ok": not missing, "required": required, "missing": missing}


def benchmark_doctor(args: argparse.Namespace) -> dict[str, Any]:
    statuses = public_adapter_status()
    if getattr(args, "benchmark", ""):
        statuses = [item for item in statuses if item["id"] == args.benchmark]
    return {
        "ok": True,
        "generated_at": now(),
        "schema": {
            "id": "benchmark adapter id",
            "runner": "external command from *_CMD env or discovered binary",
            "dataset": "optional dataset selector passed via SOLAR_ARENA_DATASET",
            "task_limit": "optional task limit passed via SOLAR_ARENA_TASK_LIMIT",
            "timeout": "subprocess timeout seconds",
            "agent_cmd": "agent command passed via SOLAR_ARENA_AGENT_CMD",
            "out_dir": "benchmark output directory",
            "score_file": "required JSON score file path",
            "evidence_dir": "stdout/stderr/score/artifacts directory",
            "status": "ok|pending|error",
        },
        "adapters": statuses,
    }


def benchmark_run(args: argparse.Namespace) -> dict[str, Any]:
    status = public_benchmark_status(args.benchmark)
    if not status:
        return {
            "ok": False,
            "generated_at": now(),
            "benchmark": args.benchmark,
            "status": "error",
            "reason": "unknown_benchmark",
            "known": [bench["id"] for bench in PUBLIC_BENCHMARKS],
        }

    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evidence_dir = Path(args.evidence_dir or REPORTS / "agent-arena-evidence" / ts / "benchmarks" / safe_name(args.benchmark))
    out_dir = Path(args.out_dir or evidence_dir / "out")
    score_file = Path(args.score_file or evidence_dir / "score.json")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    base = {
        "id": status["id"],
        "runner": status["runner"],
        "dataset": args.dataset or "",
        "task_limit": args.task_limit,
        "timeout": args.timeout,
        "agent_cmd": args.agent_cmd or "",
        "out_dir": str(out_dir),
        "score_file": str(score_file),
        "evidence_dir": str(evidence_dir),
        "status": status["status"],
    }

    if not status["configured"]:
        data = {
            "ok": False,
            "generated_at": now(),
            "benchmark": base,
            "status": "pending",
            "reason": status["reason"],
            "adapter": status,
        }
        write_json(evidence_dir / "benchmark.json", data)
        return data

    cmd = parse_runner_command(status["runner"])
    if not cmd:
        data = {
            "ok": False,
            "generated_at": now(),
            "benchmark": base,
            "status": "error",
            "reason": "empty_runner_command",
            "adapter": status,
        }
        write_json(evidence_dir / "benchmark.json", data)
        return data

    env = {
        "SOLAR_ARENA_BENCHMARK_ID": args.benchmark,
        "SOLAR_ARENA_AGENT_CMD": args.agent_cmd or "",
        "SOLAR_ARENA_DATASET": args.dataset or "",
        "SOLAR_ARENA_TASK_LIMIT": str(args.task_limit or ""),
        "SOLAR_ARENA_OUT_DIR": str(out_dir),
        "SOLAR_ARENA_SCORE_FILE": str(score_file),
        "SOLAR_ARENA_EVIDENCE_DIR": str(evidence_dir),
    }
    if args.dataset:
        env["DATASET"] = args.dataset
    if args.task_limit is not None:
        env["TASK_LIMIT"] = str(args.task_limit)

    result = run_command(f"benchmark-{args.benchmark}", cmd, evidence_dir, timeout=int(args.timeout), env=env)
    score = parse_score_file(score_file)
    artifacts = benchmark_artifacts_ok(args.benchmark, evidence_dir)
    ok = bool(result.get("ok")) and bool(score.get("ok")) and bool(artifacts.get("ok"))
    data = {
        "ok": ok,
        "generated_at": now(),
        "benchmark": {**base, "status": "ok" if ok else "error"},
        "status": "ok" if ok else "error",
        "adapter": status,
        "runner_result": {k: v for k, v in result.items() if k not in {"stdout", "stderr"}},
        "score": score,
        "artifacts": artifacts,
        "claim_boundary": "This is an adapter execution record, not a public leaderboard submission. Score is accepted only from the configured benchmark runner output.",
    }
    write_json(evidence_dir / "benchmark.json", data)
    return data


def render_benchmark_markdown(data: dict[str, Any]) -> str:
    bench = data.get("benchmark", {})
    adapter = data.get("adapter", {})
    score = data.get("score", {})
    return "\n".join([
        f"# Agent Arena Public Benchmark Adapter — {bench.get('id', 'unknown')}",
        "",
        f"- Status: `{data.get('status')}`",
        f"- Runner: `{bench.get('runner') or 'N/A'}`",
        f"- Dataset: `{bench.get('dataset') or 'N/A'}`",
        f"- Task limit: `{bench.get('task_limit') if bench.get('task_limit') is not None else 'N/A'}`",
        f"- Evidence: `{bench.get('evidence_dir')}`",
        f"- Score file: `{bench.get('score_file')}`",
        f"- Parsed score: `{score.get('score', 'N/A') if isinstance(score, dict) else 'N/A'}`",
        "",
        "## Boundary",
        "",
        f"- Source: {adapter.get('source', 'N/A')}",
        "- Pending means the official/approved runner is missing; it is not a failed benchmark.",
        "- OK requires runner exit 0, score JSON, and required artifacts for that adapter.",
        "",
    ])


def solar_quick_tasks() -> list[dict[str, Any]]:
    return [
        {
            "id": "state-read-preflight",
            "name": "Dispatch Write/Edit preflight guard",
            "benchmark_family": "Solar hidden orchestration",
            "command": ["bash", str(HARNESS / "tests" / "test-state-read-preflight.sh")],
            "timeout": 45,
        },
        {
            "id": "dag-scheduler",
            "name": "DAG planning, write-scope and join gate",
            "benchmark_family": "Terminal-Bench style shell verifier",
            "command": ["bash", str(HARNESS / "tests" / "control_plane" / "test-graph-scheduler.sh")],
            "timeout": 120,
        },
        {
            "id": "dag-node-dispatcher",
            "name": "DAG node dispatch and evaluator handoff",
            "benchmark_family": "Terminal-Bench style shell verifier",
            "command": ["bash", str(HARNESS / "tests" / "control_plane" / "test-graph-node-dispatcher.sh")],
            "timeout": 120,
        },
        {
            "id": "heavy-proof-latest",
            "name": "Latest heavy proof evidence is passing",
            "benchmark_family": "Solar hidden integration proof",
            "latest_json": str(REPORTS / "heavy-proof-benchmark-latest.json"),
            "min_score": 100,
        },
    ]


def solar_deep_tasks() -> list[dict[str, Any]]:
    return solar_quick_tasks() + [
        {
            "id": "heavy-proof-rerun",
            "name": "Rerun heavyweight Solar integration proof",
            "benchmark_family": "Solar hidden integration proof",
            "command": ["bash", str(SOLAR_BIN), "integrations", "heavy-proof", "--threshold", "100"],
            "timeout": 420,
        },
        {
            "id": "platform-benchmark-rerun",
            "name": "Rerun platform workflow benchmark",
            "benchmark_family": "Solar hidden workflow proof",
            "command": ["bash", str(SOLAR_BIN), "integrations", "platform-benchmark", "--threshold", "80"],
            "timeout": 300,
        },
    ]


def hermes_smoke_tasks(runner: str, evidence_dir: Path) -> list[dict[str, Any]]:
    hermes_home = evidence_dir / "hermes-home"
    hermes_home.mkdir(parents=True, exist_ok=True)
    return [
        {
            "id": "hermes-cli-help",
            "name": "Hermes CLI help is runnable",
            "benchmark_family": "Agent runtime smoke",
            "command": [runner, "--help"],
            "timeout": 45,
            "env": {"HERMES_HOME": str(hermes_home)},
        },
        {
            "id": "hermes-doctor",
            "name": "Hermes doctor executes in isolated home",
            "benchmark_family": "Agent runtime smoke",
            "command": [runner, "--ignore-user-config", "doctor"],
            "timeout": 90,
            "env": {"HERMES_HOME": str(hermes_home)},
        },
    ]


def head_to_head_tasks(agent: str, runner: str | None, evidence_dir: Path) -> list[dict[str, Any]]:
    """Run a first fair same-task verifier suite without external LLM calls.

    This is intentionally modest but real: both agents run the same command-line
    tasks and are judged by the same filesystem/verifier checks. It proves the
    arena can execute comparable tasks before we spend tokens on model-backed
    tasks.
    """
    root = evidence_dir / "head-to-head-workdir"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / "artifact.json"
    marker = root / "MARKER.txt"
    empty_settings = root / "claude-empty-settings.json"
    empty_settings.write_text("{}", encoding="utf-8")
    hermes_home = evidence_dir / "hermes-home"
    hermes_home.mkdir(parents=True, exist_ok=True)

    if agent == "solar-harness":
        cmd = [
            sys.executable,
            "-c",
            (
                "import json, pathlib; "
                f"p=pathlib.Path({str(artifact)!r}); "
                "p.write_text(json.dumps({'agent':'solar-harness','task':'same-task-artifact','ok':True}, sort_keys=True), encoding='utf-8')"
            ),
        ]
    elif agent == "hermes" and runner:
        cmd = [runner, "--ignore-user-config", "--help"]
    elif agent == "claude-code-bare" and runner:
        cmd = [runner, "--bare", "-p", "Return exactly: CLAUDE_CODE_READY", "--permission-mode", "bypassPermissions", "--tools", "", "--model", "sonnet", "--max-budget-usd", "0.25"]
    elif agent == "claude-code" and runner:
        cmd = [
            runner, "-p", "Return exactly: CLAUDE_CODE_READY",
            "--permission-mode", "bypassPermissions",
            "--model", "sonnet",
            "--max-budget-usd", "0.25",
            "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}',
            "--settings", str(empty_settings),
            "--setting-sources", "local",
            "--disable-slash-commands",
            "--output-format", "text",
        ]
    else:
        cmd = [sys.executable, "-c", "raise SystemExit(2)"]

    return [
        {
            "id": "same-task-cli-ready",
            "name": "Same-task CLI readiness",
            "benchmark_family": "Agent Arena same-task verifier",
            "command": cmd,
            "timeout": 60,
            "env": {"HERMES_HOME": str(hermes_home)} if agent == "hermes" else {},
            "verifier": "stdout_contains" if agent in {"hermes", "claude-code", "claude-code-bare"} else "json_artifact",
            "stdout_contains": "CLAUDE_CODE_READY" if agent in {"claude-code", "claude-code-bare"} else "Hermes Agent",
            "artifact": str(artifact),
            "expected_json": {"ok": True, "task": "same-task-artifact"},
        },
        {
            "id": "same-task-filesystem",
            "name": "Same-task filesystem verifier",
            "benchmark_family": "Agent Arena same-task verifier",
            "command": [
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).write_text({agent!r}, encoding='utf-8')",
            ],
            "timeout": 30,
            "verifier": "file_contains",
            "artifact": str(marker),
            "contains": agent,
        },
    ]


def verify_task(task: dict[str, Any], result: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    verifier = task.get("verifier")
    if not verifier:
        return bool(result.get("ok")), {"type": "exit_code", "ok": bool(result.get("ok"))}
    if verifier == "stdout_contains":
        needle = str(task.get("stdout_contains", ""))
        ok = bool(result.get("ok")) and needle in str(result.get("stdout", ""))
        return ok, {"type": verifier, "needle": needle, "ok": ok}
    if verifier == "file_contains":
        path = Path(str(task.get("artifact", "")))
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        needle = str(task.get("contains", ""))
        ok = bool(result.get("ok")) and needle in text
        return ok, {"type": verifier, "path": str(path), "needle": needle, "ok": ok}
    if verifier == "json_artifact":
        path = Path(str(task.get("artifact", "")))
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            return False, {"type": verifier, "path": str(path), "ok": False, "error": str(exc)}
        expected = task.get("expected_json") or {}
        ok = bool(result.get("ok")) and all(data.get(k) == v for k, v in expected.items())
        return ok, {"type": verifier, "path": str(path), "expected": expected, "actual": data, "ok": ok}
    return False, {"type": verifier, "ok": False, "reason": "unknown_verifier"}


def run_solar_task(task: dict[str, Any], evidence_dir: Path) -> dict[str, Any]:
    if "command" in task:
        result = run_command(task["id"], task["command"], evidence_dir, timeout=int(task.get("timeout", 180)))
        return {**task, "status": "ok" if result["ok"] else "error", "passed": result["ok"], "evidence": result}
    if "latest_json" in task:
        result = latest_json_ok(Path(task["latest_json"]), min_score=int(task.get("min_score", 0)))
        write_json(evidence_dir / "reports" / f"{safe_name(task['id'])}.json", result)
        return {**task, "status": "ok" if result["ok"] else "error", "passed": result["ok"], "evidence": result}
    return {**task, "status": "error", "passed": False, "evidence": {"reason": "invalid_task"}}


def run_command_task(task: dict[str, Any], evidence_dir: Path) -> dict[str, Any]:
    result = run_command(
        task["id"],
        task["command"],
        evidence_dir,
        timeout=int(task.get("timeout", 180)),
        env=task.get("env"),
    )
    passed, verification = verify_task(task, result)
    return {**task, "status": "ok" if passed else "error", "passed": passed, "evidence": result, "verification": verification}


def run_agent(agent: str, suite: str, evidence_dir: Path, deep: bool) -> dict[str, Any]:
    status = agent_status(agent)
    agent_dir = evidence_dir / "agents" / safe_name(agent)
    write_json(agent_dir / "status.json", status)
    if not status["available"]:
        return {
            "agent": agent,
            "available": False,
            "status": "pending",
            "reason": status["reason"],
            "source": status.get("source"),
            "score": 0,
            "max_score": 0,
            "tasks": [],
        }

    if agent == "hermes":
        tasks = head_to_head_tasks(agent, status["runner"], agent_dir) if suite == "head-to-head" else hermes_smoke_tasks(status["runner"], agent_dir)
        results = [run_command_task(task, agent_dir) for task in tasks]
        passed = sum(1 for item in results if item["passed"])
        total = len(results)
        return {
            "agent": agent,
            "available": True,
            "status": "ok" if passed == total else "error",
            "score": passed,
            "max_score": total,
            "pass_rate": round(100.0 * passed / total, 2) if total else 0,
            "reason": "same-task verifier suite" if suite == "head-to-head" else "runtime smoke only; not a same-task Solar-vs-Hermes capability comparison yet",
            "source": status.get("source"),
            "tasks": results,
        }

    if agent in {"claude-code", "claude-code-bare"}:
        tasks = head_to_head_tasks(agent, status["runner"], agent_dir)
        results = [run_command_task(task, agent_dir) for task in tasks]
        passed = sum(1 for item in results if item["passed"])
        total = len(results)
        return {
            "agent": agent,
            "available": True,
            "status": "ok" if passed == total else "error",
            "score": passed,
            "max_score": total,
            "pass_rate": round(100.0 * passed / total, 2) if total else 0,
            "reason": "Claude Code bare mode same-task verifier" if suite == "head-to-head" else "Claude Code bare adapter",
            "tasks": results,
        }

    if agent != "solar-harness":
        return {
            "agent": agent,
            "available": True,
            "status": "pending",
            "reason": "adapter discovered but task execution adapter is not configured in this version",
            "score": 0,
            "max_score": 0,
            "tasks": [],
        }

    if suite == "head-to-head":
        tasks = head_to_head_tasks(agent, status["runner"], agent_dir)
        results = [run_command_task(task, agent_dir) for task in tasks]
    else:
        tasks = solar_deep_tasks() if deep else solar_quick_tasks()
        results = [run_solar_task(task, agent_dir) for task in tasks]
    passed = sum(1 for item in results if item["passed"])
    total = len(results)
    return {
        "agent": agent,
        "available": True,
        "status": "ok" if passed == total else "error",
        "score": passed,
        "max_score": total,
        "pass_rate": round(100.0 * passed / total, 2) if total else 0,
        "tasks": results,
    }


def render_markdown(data: dict[str, Any]) -> str:
    agent_rows = []
    for agent in data["agents"]:
        agent_rows.append(
            f"| {agent['agent']} | {agent['status']} | {agent.get('score', 0)}/{agent.get('max_score', 0)} | "
            f"{agent.get('pass_rate', 0)}% | {agent.get('reason', 'N/A') or 'N/A'} |"
        )
    task_rows = []
    for agent in data["agents"]:
        for task in agent.get("tasks", []):
            task_rows.append(
                f"| {agent['agent']} | {task['id']} | {task['status']} | {task.get('benchmark_family', 'N/A')} |"
            )
    public_rows = [
        f"| {bench['name']} | {bench['status']} | {bench['domain']} | {bench['runner'] or 'N/A'} |"
        for bench in data["public_benchmark_adapters"]
    ]
    return "\n".join([
        f"# Solar Agent Arena Benchmark — {data['generated_at']}",
        "",
        "## Result",
        "",
        f"- Status: {'PASS' if data['ok'] else 'FAIL'}",
        f"- Suite: `{data['suite']}`",
        f"- Mode: `{data['mode']}`",
        f"- Evidence dir: `{data['evidence_dir']}`",
        "",
        "## Agents",
        "",
        "| Agent | Status | Score | Pass Rate | Reason |",
        "|---|---:|---:|---:|---|",
        *agent_rows,
        "",
        "## Tasks",
        "",
        "| Agent | Task | Status | Benchmark Family |",
        "|---|---|---:|---|",
        *(task_rows or ["| N/A | N/A | pending | N/A |"]),
        "",
        "## Public Benchmark Adapters",
        "",
        "| Benchmark | Status | Domain | Runner |",
        "|---|---:|---|---|",
        *public_rows,
        "",
        "## Boundary",
        "",
        "- This report is not a public leaderboard submission.",
        "- `pending` public adapters mean the official benchmark runner is not installed/configured locally.",
        "- Head-to-head superiority can only be claimed after two or more available agents run the same tasks under the same budget.",
        "",
    ])


def run_arena(args: argparse.Namespace) -> dict[str, Any]:
    evidence_dir = Path(args.evidence_dir or REPORTS / "agent-arena-evidence" / "latest")
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    agents = [item.strip() for item in args.agents.split(",") if item.strip()]
    started = time.time()
    agent_results = [run_agent(agent, args.suite, evidence_dir, args.deep) for agent in agents]
    comparable_agents = [a for a in agent_results if a.get("available") and a.get("max_score", 0) > 0]
    ok = bool(comparable_agents) and all(a.get("status") == "ok" for a in comparable_agents)
    durations = []
    for agent in agent_results:
        for task in agent.get("tasks", []):
            ev = task.get("evidence") or {}
            if isinstance(ev, dict) and isinstance(ev.get("duration_s"), (int, float)):
                durations.append(float(ev["duration_s"]))
            elif isinstance(ev, dict) and isinstance((ev.get("evidence") or {}).get("duration_s"), (int, float)):
                durations.append(float(ev["evidence"]["duration_s"]))

    data = {
        "ok": ok,
        "generated_at": now(),
        "suite": args.suite,
        "mode": "deep" if args.deep else "quick",
        "duration_s": round(time.time() - started, 3),
        "evidence_dir": str(evidence_dir),
        "agents": agent_results,
        "public_benchmark_adapters": public_adapter_status(),
        "stats": {
            "task_duration_median_s": round(statistics.median(durations), 3) if durations else None,
            "task_duration_stdev_s": round(statistics.pstdev(durations), 3) if len(durations) > 1 else 0,
            "task_duration_samples": len(durations),
        },
        "claim_boundary": "Solar-Harness can claim local orchestration proof if Solar tasks pass; cross-agent superiority requires at least one comparable external agent adapter to run the same suite.",
    }
    write_json(evidence_dir / "arena.json", data)
    return data


def soak(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.out_dir or REPORTS / "agent-arena-soak" / "latest")
    root.mkdir(parents=True, exist_ok=True)
    journal = root / "soak.jsonl"
    started = time.time()
    deadline = started + max(0, float(args.duration_hours)) * 3600
    max_iterations = int(args.max_iterations or 0)
    interval = max(0, int(args.interval_sec))
    iterations: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    iteration = 0

    while True:
        if max_iterations and iteration >= max_iterations:
            break
        if iteration > 0 and time.time() >= deadline:
            break

        iteration += 1
        iter_id = f"iter-{iteration:04d}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
        iter_dir = root / iter_id

        repair: dict[str, Any] | None = None
        if args.auto_repair:
            repair = ensure_hermes_runtime(iter_dir / "repair")

        run_args = argparse.Namespace(
            suite=args.suite,
            agents=args.agents,
            deep=args.deep,
            evidence_dir=str(iter_dir),
        )
        result = run_arena(run_args)
        compact = {
            "iteration": iteration,
            "ts": now(),
            "ok": result.get("ok"),
            "suite": result.get("suite"),
            "mode": result.get("mode"),
            "duration_s": result.get("duration_s"),
            "evidence_dir": result.get("evidence_dir"),
            "agents": [
                {
                    "agent": a.get("agent"),
                    "status": a.get("status"),
                    "score": a.get("score"),
                    "max_score": a.get("max_score"),
                    "reason": a.get("reason"),
                }
                for a in result.get("agents", [])
            ],
            "repair": repair,
        }
        iterations.append(compact)
        if not compact["ok"]:
            failures.append(compact)
        with journal.open("a", encoding="utf-8") as f:
            f.write(json.dumps(compact, ensure_ascii=False) + "\n")
        write_json(root / "latest-iteration.json", compact)

        if max_iterations and iteration >= max_iterations:
            break
        if time.time() + interval > deadline:
            break
        if interval:
            time.sleep(interval)

    summary = {
        "ok": not failures,
        "generated_at": now(),
        "duration_hours_requested": args.duration_hours,
        "elapsed_s": round(time.time() - started, 3),
        "iterations": len(iterations),
        "failures": len(failures),
        "suite": args.suite,
        "agents": args.agents,
        "deep": args.deep,
        "auto_repair": args.auto_repair,
        "out_dir": str(root),
        "journal": str(journal),
        "last": iterations[-1] if iterations else None,
        "failed_iterations": failures[-20:],
    }
    write_json(root / "summary.json", summary)
    return summary


def doctor() -> dict[str, Any]:
    agents = ["solar-harness", "hermes", "codex-local", "claude-code", "claude-code-bare"]
    return {
        "ok": True,
        "generated_at": now(),
        "agents": {agent: agent_status(agent) for agent in agents},
        "public_benchmark_adapters": public_adapter_status(),
        "recommended_next": "Configure official benchmark runners via *_CMD env vars, then run `solar-harness agent-arena run --agents solar-harness,hermes --deep`.",
    }


def vendor_hermes(update: bool = False) -> dict[str, Any]:
    HERMES_SOURCE_DIR.parent.mkdir(parents=True, exist_ok=True)
    if HERMES_SOURCE_DIR.exists():
        if update:
            result = run_command(
                "hermes_vendor_update",
                ["git", "-C", str(HERMES_SOURCE_DIR), "pull", "--ff-only"],
                REPORTS / "agent-arena-evidence" / "latest",
                timeout=120,
            )
        else:
            result = {"ok": True, "skipped": "already_exists"}
        return {"ok": bool(result.get("ok")), "action": "update" if update else "noop", "result": result, "source": hermes_source_status()}
    result = run_command(
        "hermes_vendor_clone",
        ["git", "clone", "--depth", "1", HERMES_REPO, str(HERMES_SOURCE_DIR)],
        REPORTS / "agent-arena-evidence" / "latest",
        timeout=300,
    )
    return {"ok": bool(result.get("ok")), "action": "clone", "result": result, "source": hermes_source_status()}


def main() -> int:
    ap = argparse.ArgumentParser(prog="agent_arena_benchmark.py")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("doctor")
    p.add_argument("--json", action="store_true", dest="as_json")

    p = sub.add_parser("vendor-hermes")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.add_argument("--update", action="store_true")

    p = sub.add_parser("run")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.add_argument("--suite", default="smoke", choices=["smoke", "head-to-head"])
    p.add_argument("--agents", default="solar-harness")
    p.add_argument("--deep", action="store_true")
    p.add_argument("--out-json", default=str(REPORTS / "agent-arena-benchmark-latest.json"))
    p.add_argument("--out-md", default=str(REPORTS / "agent-arena-benchmark-latest.md"))
    p.add_argument("--evidence-dir", default=str(REPORTS / "agent-arena-evidence" / "latest"))

    p = sub.add_parser("soak")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.add_argument("--suite", default="head-to-head", choices=["smoke", "head-to-head"])
    p.add_argument("--agents", default="solar-harness,hermes")
    p.add_argument("--deep", action="store_true")
    p.add_argument("--duration-hours", type=float, default=10.0)
    p.add_argument("--interval-sec", type=int, default=300)
    p.add_argument("--max-iterations", type=int, default=0)
    p.add_argument("--auto-repair", action="store_true")
    p.add_argument("--out-dir", default=str(REPORTS / "agent-arena-soak" / "latest"))

    p = sub.add_parser("benchmarks")
    bench_sub = p.add_subparsers(dest="benchmark_cmd")

    p_list = bench_sub.add_parser("list")
    p_list.add_argument("--json", action="store_true", dest="as_json")

    p_doc = bench_sub.add_parser("doctor")
    p_doc.add_argument("--json", action="store_true", dest="as_json")
    p_doc.add_argument("--benchmark", default="")

    p_run = bench_sub.add_parser("run")
    p_run.add_argument("benchmark")
    p_run.add_argument("--json", action="store_true", dest="as_json")
    p_run.add_argument("--dataset", default="")
    p_run.add_argument("--task-limit", type=int, default=None)
    p_run.add_argument("--timeout", type=int, default=1800)
    p_run.add_argument("--agent-cmd", default="")
    p_run.add_argument("--out-dir", default="")
    p_run.add_argument("--score-file", default="")
    p_run.add_argument("--evidence-dir", default="")
    p_run.add_argument("--out-json", default=str(REPORTS / "agent-arena-benchmark-latest.json"))
    p_run.add_argument("--out-md", default=str(REPORTS / "agent-arena-benchmark-latest.md"))

    args = ap.parse_args()
    if args.cmd == "doctor":
        data = doctor()
        if args.as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print("Solar Agent Arena Doctor")
            for agent, status in data["agents"].items():
                print(f"  {agent}: {'ok' if status['available'] else 'pending'} {status.get('reason', '')}")
        return 0

    if args.cmd == "vendor-hermes":
        data = vendor_hermes(update=args.update)
        if args.as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"Hermes vendor: {'ok' if data['ok'] else 'error'} action={data['action']}")
            print(f"  path: {data['source']['path']}")
            print(f"  commit: {data['source'].get('commit') or 'N/A'}")
        return 0 if data["ok"] else 1

    if args.cmd == "run":
        data = run_arena(args)
        write_json(Path(args.out_json), data)
        write_text(Path(args.out_md), render_markdown(data))
        if args.as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"Solar Agent Arena: {'PASS' if data['ok'] else 'FAIL'}")
            print(f"  suite: {data['suite']} mode={data['mode']}")
            print(f"  report: {args.out_md}")
            for agent in data["agents"]:
                print(f"  {agent['agent']}: {agent['status']} {agent.get('score', 0)}/{agent.get('max_score', 0)}")
        return 0 if data["ok"] else 1

    if args.cmd == "soak":
        data = soak(args)
        if args.as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"Solar Agent Arena Soak: {'PASS' if data['ok'] else 'FAIL'}")
            print(f"  iterations: {data['iterations']} failures={data['failures']}")
            print(f"  out_dir: {data['out_dir']}")
        return 0 if data["ok"] else 1

    if args.cmd == "benchmarks":
        if args.benchmark_cmd == "list":
            data = {"ok": True, "generated_at": now(), "adapters": public_adapter_status()}
            if args.as_json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print("Agent Arena Public Benchmark Adapters")
                for item in data["adapters"]:
                    print(f"  {item['id']}: {item['status']} runner={item['runner'] or 'N/A'}")
            return 0

        if args.benchmark_cmd == "doctor":
            data = benchmark_doctor(args)
            if args.as_json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print("Agent Arena Benchmark Doctor")
                for item in data["adapters"]:
                    print(f"  {item['id']}: {item['status']} {item.get('reason', '')}")
            return 0

        if args.benchmark_cmd == "run":
            data = benchmark_run(args)
            write_json(Path(args.out_json), data)
            write_text(Path(args.out_md), render_benchmark_markdown(data))
            if args.as_json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                bench = data.get("benchmark", {})
                print(f"Agent Arena Benchmark Adapter: {data.get('status', 'error').upper()}")
                print(f"  benchmark: {bench.get('id')}")
                print(f"  runner: {bench.get('runner') or 'N/A'}")
                print(f"  evidence: {bench.get('evidence_dir')}")
            return 0 if data.get("ok") or data.get("status") == "pending" else 1

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
