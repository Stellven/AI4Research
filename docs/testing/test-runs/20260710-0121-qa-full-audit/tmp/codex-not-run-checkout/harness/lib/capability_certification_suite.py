#!/usr/bin/env python3
"""Solar capability certification suite.

This is the top-level proof runner for the question:

  Are Solar/Solar-Harness capabilities complete, automatic, default-on,
  usable, and effective?

It composes existing E2E tests and benchmarks, adds anti-false-positive checks,
and writes an auditable JSON + Markdown report.  It intentionally separates
``fast`` certification from ``full``/``heavy`` because some real runtime probes
load browsers, local embedding models, or external agent runtimes.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
REPORTS = HARNESS / "reports"
SOLAR_BIN = HARNESS / "solar-harness.sh"


DIMENSIONS = {
    "complete": "能力清单、插件、skill、capability registry 有覆盖。",
    "default": "默认 dispatch/coordinator/DAG 路径会注入能力上下文。",
    "automatic": "无需人工挑 skill，任务文本自动命中 intent/capability。",
    "usable": "CLI、脚本、runtime、pane 配置能实际运行。",
    "effective": "正例命中、负例不乱命中，benchmark 有分数和证据。",
    "evidence": "每个判断都有 JSON/Markdown/命令输出证据。",
}


FAST_CHECKS: list[dict[str, Any]] = [
    {
        "id": "syntax-core",
        "name": "Core syntax gate",
        "dimensions": ["usable"],
        "cmd": [
            sys.executable,
            "-m",
            "py_compile",
            str(HARNESS / "lib" / "intent_engine_adapter.py"),
            str(HARNESS / "lib" / "solar_skills.py"),
            str(HARNESS / "lib" / "capability_fusion_benchmark.py"),
            str(HARNESS / "lib" / "platform_workflow_benchmark.py"),
            str(HARNESS / "lib" / "agent_arena_benchmark.py"),
            str(HARNESS / "lib" / "model_call_runtime.py"),
            str(HARNESS / "lib" / "runtime_context_inject.py"),
        ],
        "timeout": 30,
    },
    {
        "id": "bash-syntax",
        "name": "solar-harness.sh bash syntax",
        "dimensions": ["usable"],
        "cmd": ["bash", "-n", str(SOLAR_BIN)],
        "timeout": 30,
    },
    {
        "id": "intent-adapter",
        "name": "Intent adapter direct/hint/learned DB",
        "dimensions": ["automatic", "effective"],
        "cmd": ["bash", str(HARNESS / "tests" / "test-intent-engine-adapter.sh")],
        "timeout": 60,
    },
    {
        "id": "skills-inject",
        "name": "Skills/context/capability/intent inject idempotency",
        "dimensions": ["default", "automatic", "effective"],
        "cmd": ["bash", str(HARNESS / "tests" / "test-skills-inject-idempotent.sh")],
        "timeout": 90,
    },
    {
        "id": "graph-dispatcher",
        "name": "DAG graph node dispatcher inject path",
        "dimensions": ["default", "automatic"],
        "cmd": ["bash", str(HARNESS / "tests" / "control_plane" / "test-graph-node-dispatcher.sh")],
        "timeout": 120,
    },
    {
        "id": "model-call-runtime",
        "name": "Model-call runtime event bridge",
        "dimensions": ["default", "usable", "evidence"],
        "cmd": ["bash", str(HARNESS / "tests" / "runtime" / "test-model-call-runtime.sh")],
        "timeout": 120,
    },
    {
        "id": "capability-plane-e2e",
        "name": "Capability plane E2E",
        "dimensions": ["complete", "usable"],
        "cmd": ["bash", str(HARNESS / "tests" / "integrations" / "test-capability-plane-e2e.sh")],
        "timeout": 180,
    },
    {
        "id": "expanded-capability-plane",
        "name": "Expanded capability plane E2E",
        "dimensions": ["complete", "usable"],
        "cmd": ["bash", str(HARNESS / "tests" / "integrations" / "test-expanded-capability-plane-e2e.sh")],
        "timeout": 240,
    },
    {
        "id": "ruflo-integration",
        "name": "Ruflo safe vendor capability",
        "dimensions": ["complete", "default", "usable"],
        "cmd": ["bash", str(HARNESS / "tests" / "plugins" / "test-ruflo-integration.sh")],
        "timeout": 120,
    },
]


FULL_CHECKS: list[dict[str, Any]] = [
    {
        "id": "capability-fusion-benchmark",
        "name": "Capability fusion benchmark",
        "dimensions": ["complete", "default", "automatic", "usable", "effective", "evidence"],
        "cmd": ["bash", str(HARNESS / "tests" / "integrations" / "test-capability-fusion-benchmark.sh")],
        "timeout": 360,
    },
    {
        "id": "platform-workflow-benchmark",
        "name": "Platform workflow benchmark",
        "dimensions": ["complete", "usable", "effective", "evidence"],
        "cmd": ["bash", str(HARNESS / "tests" / "integrations" / "test-platform-workflow-benchmark.sh")],
        "timeout": 420,
    },
    {
        "id": "agent-arena-smoke",
        "name": "Agent arena local verifier",
        "dimensions": ["effective", "evidence"],
        "cmd": [
            "bash",
            str(SOLAR_BIN),
            "agent-arena",
            "run",
            "--suite",
            "head-to-head",
            "--agents",
            "solar-harness,claude-code",
            "--json",
        ],
        "timeout": 300,
        "allow_fail": True,
        "allow_fail_reason": "Claude Code naked may require login/OAuth outside Solar-Harness; failure is reported, not hidden.",
    },
]


HEAVY_CHECKS: list[dict[str, Any]] = [
    {
        "id": "heavy-proof-benchmark",
        "name": "Heavy runtime proof benchmark",
        "dimensions": ["usable", "effective", "evidence"],
        "cmd": ["bash", str(SOLAR_BIN), "integrations", "heavy-proof", "--json"],
        "timeout": 900,
        "allow_fail": True,
        "allow_fail_reason": "Heavy proof may load browser/model runtimes; failures identify remaining non-default integrations.",
    },
]


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_check(check: dict[str, Any], evidence_dir: Path) -> dict[str, Any]:
    started = time.time()
    cmd = [str(part) for part in check["cmd"]]
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=int(check.get("timeout", 120)))
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except Exception as exc:
        exit_code = 99
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}"

    raw_ok = exit_code == 0
    allowed_fail = bool(check.get("allow_fail") and not raw_ok)
    status = "ok" if raw_ok else ("warn" if allowed_fail else "error")
    duration = round(time.time() - started, 3)
    stem = safe_id(check["id"])
    write_json(
        evidence_dir / "commands" / f"{stem}.json",
        {
            "id": check["id"],
            "name": check["name"],
            "cmd": cmd,
            "exit_code": exit_code,
            "duration_s": duration,
            "status": status,
            "dimensions": check["dimensions"],
            "allow_fail_reason": check.get("allow_fail_reason", ""),
        },
    )
    write_text(evidence_dir / "commands" / f"{stem}.stdout.txt", stdout[-80000:])
    write_text(evidence_dir / "commands" / f"{stem}.stderr.txt", stderr[-80000:])
    return {
        "id": check["id"],
        "name": check["name"],
        "status": status,
        "ok": raw_ok,
        "blocking": not raw_ok and not allowed_fail,
        "exit_code": exit_code,
        "duration_s": duration,
        "dimensions": check["dimensions"],
        "evidence": {
            "command": str(evidence_dir / "commands" / f"{stem}.json"),
            "stdout": str(evidence_dir / "commands" / f"{stem}.stdout.txt"),
            "stderr": str(evidence_dir / "commands" / f"{stem}.stderr.txt"),
        },
        "allow_fail_reason": check.get("allow_fail_reason", ""),
    }


def run_negative_controls(evidence_dir: Path) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="solar-cert-negative-"))
    try:
        dispatch = tmp / "negative.md"
        dispatch.write_text("# Negative\n\nCompute 2 + 2 only.\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(HARNESS / "lib" / "solar_skills.py"), "inject", str(dispatch)],
            text=True,
            capture_output=True,
            timeout=60,
        )
        text = dispatch.read_text(encoding="utf-8", errors="replace")
        unrelated = ["gstack", "Browser-use MCP", "Ruflo", "MarkItDown", "Empirical Research"]
        no_false_provider = all(word not in text for word in unrelated)
        has_context = "<solar-intent-context>" in text and "<solar-capability-context>" in text
        query = subprocess.run(
            [sys.executable, str(HARNESS / "lib" / "capability_registry.py"), "query", "__solar.fake_missing_capability__", "--json"],
            text=True,
            capture_output=True,
            timeout=30,
        )
        fake_missing_fails = query.returncode != 0
        write_text(evidence_dir / "negative" / "negative.injected.md", text)
        write_text(evidence_dir / "negative" / "fake-query.stdout.txt", query.stdout)
        write_text(evidence_dir / "negative" / "fake-query.stderr.txt", query.stderr)
        ok = proc.returncode == 0 and no_false_provider and has_context and fake_missing_fails
        return {
            "id": "negative-controls",
            "name": "Negative controls",
            "status": "ok" if ok else "error",
            "ok": ok,
            "blocking": not ok,
            "exit_code": 0 if ok else 1,
            "duration_s": 0,
            "dimensions": ["effective", "evidence"],
            "checks": {
                "inject_ok": proc.returncode == 0,
                "has_context": has_context,
                "no_false_provider": no_false_provider,
                "fake_missing_capability_fails": fake_missing_fails,
            },
            "evidence": {
                "injected": str(evidence_dir / "negative" / "negative.injected.md"),
                "fake_query_stdout": str(evidence_dir / "negative" / "fake-query.stdout.txt"),
            },
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_checks(mode: str) -> list[dict[str, Any]]:
    checks = list(FAST_CHECKS)
    if mode in {"full", "heavy"}:
        checks.extend(FULL_CHECKS)
    if mode == "heavy":
        checks.extend(HEAVY_CHECKS)
    return checks


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    dimension_summary: dict[str, dict[str, Any]] = {
        key: {"description": desc, "total": 0, "ok": 0, "warn": 0, "error": 0}
        for key, desc in DIMENSIONS.items()
    }
    for result in results:
        for dim in result.get("dimensions", []):
            if dim not in dimension_summary:
                continue
            dimension_summary[dim]["total"] += 1
            dimension_summary[dim][result["status"]] += 1
    blocking = [r for r in results if r.get("blocking")]
    warn = [r for r in results if r.get("status") == "warn"]
    return {
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "warn": len(warn),
        "error": len(blocking),
        "blocking_ids": [r["id"] for r in blocking],
        "warn_ids": [r["id"] for r in warn],
        "dimensions": dimension_summary,
    }


def render_markdown(data: dict[str, Any]) -> str:
    rows = []
    for item in data["results"]:
        rows.append(
            f"| {item['id']} | {item['status']} | {','.join(item['dimensions'])} | "
            f"{item['exit_code']} | {item['duration_s']}s |"
        )
    dim_rows = []
    for key, item in data["summary"]["dimensions"].items():
        status = "ok" if item["error"] == 0 and item["warn"] == 0 else ("warn" if item["error"] == 0 else "error")
        dim_rows.append(f"| {key} | {status} | {item['ok']}/{item['total']} | {item['description']} |")
    return "\n".join([
        f"# Solar Capability Certification — {data['generated_at']}",
        "",
        f"- Mode: `{data['mode']}`",
        f"- Result: `{'PASS' if data['ok'] else 'FAIL'}`",
        f"- Evidence: `{data['evidence_dir']}`",
        f"- Blocking: `{', '.join(data['summary']['blocking_ids']) or 'N/A'}`",
        f"- Warnings: `{', '.join(data['summary']['warn_ids']) or 'N/A'}`",
        "",
        "## Dimension Verdict",
        "",
        "| Dimension | Status | OK/Total | Meaning |",
        "|---|---:|---:|---|",
        *dim_rows,
        "",
        "## Checks",
        "",
        "| Check | Status | Dimensions | Exit | Duration |",
        "|---|---:|---|---:|---:|",
        *rows,
        "",
        "## Standard",
        "",
        "- `ok`: check passed with local evidence.",
        "- `warn`: non-blocking known external/runtime dependency failed and is explicitly marked allow-fail.",
        "- `error`: blocking failure; capability cannot be claimed as complete/default/effective.",
        "",
    ])


def certify(mode: str, evidence_dir: Path) -> dict[str, Any]:
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    results = [run_check(check, evidence_dir) for check in build_checks(mode)]
    results.append(run_negative_controls(evidence_dir))
    summary = summarize(results)
    data = {
        "ok": summary["error"] == 0,
        "mode": mode,
        "generated_at": now(),
        "harness": str(HARNESS),
        "evidence_dir": str(evidence_dir),
        "dimensions": DIMENSIONS,
        "summary": summary,
        "results": results,
    }
    write_json(evidence_dir / "certification.json", data)
    write_text(evidence_dir / "certification.md", render_markdown(data))
    return data


def main() -> int:
    parser = argparse.ArgumentParser(prog="capability_certification_suite.py")
    parser.add_argument("--mode", choices=["fast", "full", "heavy"], default="fast")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--out-json", default=str(REPORTS / "capability-certification-latest.json"))
    parser.add_argument("--out-md", default=str(REPORTS / "capability-certification-latest.md"))
    parser.add_argument("--evidence-dir", default=str(REPORTS / "capability-certification-evidence" / "latest"))
    args = parser.parse_args()

    data = certify(args.mode, Path(args.evidence_dir))
    write_json(Path(args.out_json), data)
    write_text(Path(args.out_md), render_markdown(data))

    if args.as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"Solar Capability Certification: {'PASS' if data['ok'] else 'FAIL'}")
        print(f"  mode: {args.mode}")
        print(f"  checks: {data['summary']['ok']} ok / {data['summary']['warn']} warn / {data['summary']['error']} error")
        print(f"  report: {args.out_md}")
        print(f"  evidence: {args.evidence_dir}")
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
