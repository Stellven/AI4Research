#!/usr/bin/env python3
"""Benchmark whether external capabilities are fused into Solar-Harness.

This is not a micro-performance benchmark. It measures integration quality:
manifest validity, capability registry exposure, health visibility, dispatch
auto-injection, local runtime smoke, and pane-level availability.
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
PLUGIN_LOADER = HARNESS / "lib" / "plugin_loader.py"
CAPABILITY_REGISTRY = HARNESS / "lib" / "capability_registry.py"
HEALTH_PROBE = HARNESS / "lib" / "external-integrations-health.py"
SKILLS_PY = HARNESS / "lib" / "solar_skills.py"
PERSONA_CONFIG = HARNESS / "lib" / "persona-config.sh"


WEIGHTS = {
    "manifest": 15,
    "registry": 20,
    "health": 15,
    "dispatch": 20,
    "runtime": 20,
    "pane": 10,
}


SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "empirical-research",
        "name": "Empirical Research skills",
        "plugin": "empirical-research",
        "health_name": "Empirical Research skills",
        "capabilities": ["research.empirical_pipeline", "research.literature_review", "analysis.causal_inference"],
        "dispatch_text": "empirical research literature review causal analysis reproducible academic paper 实证 因果 文献综述",
        "expected_provider": "Empirical Research",
        "runtime_paths": [HOME / ".claude" / "skills" / "empirical-pipeline" / "SKILL.md"],
    },
    {
        "id": "addy-agent-skills",
        "name": "addyosmani/agent-skills",
        "plugin": "addy-agent-skills",
        "health_name": "addyosmani/agent-skills",
        "capabilities": ["agent_skills.catalog", "workflow.spec_driven", "workflow.code_review", "workflow.test_driven"],
        "dispatch_text": "addyosmani agent-skills spec-driven source-driven context engineering 规范驱动 上下文工程",
        "expected_provider": "addyosmani/agent-skills",
        "runtime_paths": [
            HOME / ".claude" / "plugins" / "marketplaces" / "addy-agent-skills" / "README.md",
            HOME / ".claude" / "plugins" / "marketplaces" / "addy-agent-skills" / "agents" / "code-reviewer.md",
        ],
    },
    {
        "id": "gstack",
        "name": "Gstack",
        "plugin": "gstack",
        "health_name": "gstack",
        "capabilities": ["browser.browse", "browser.qa", "code.review"],
        "dispatch_text": "browser localhost webpage screenshot frontend visual QA 打开页面 截图 前端",
        "expected_provider": "gstack",
        "runtime_paths": [HOME / ".claude" / "skills" / "gstack" / "SKILL.md"],
    },
    {
        "id": "superpowers",
        "name": "Superpowers",
        "plugin": "superpowers",
        "health_name": "Superpowers",
        "capabilities": ["skill.methodology", "workflow.planning", "debug.systematic", "test.tdd"],
        "dispatch_text": "superpowers TDD systematic debug root cause planning 系统化 调试 根因 测试驱动",
        "expected_provider": "Superpowers",
        "runtime_paths": [HOME / ".codex" / "plugins" / "cache" / "openai-curated" / "superpowers"],
    },
    {
        "id": "browser-use",
        "name": "Browser-use MCP",
        "plugin": "browser-use",
        "health_name": "Browser-use MCP",
        "capabilities": ["browser.mcp", "browser.automation", "browser.screenshot", "browser.localhost_test"],
        "dispatch_text": "browser-use browser mcp localhost screenshot click type 浏览器 MCP 点击 输入 截图",
        "expected_provider": "Browser-use MCP",
        "runtime_paths": [
            HOME / ".claude" / "mcp-servers" / "browser-use" / "server.py",
            HOME / ".codex" / "plugins" / "cache" / "openai-bundled" / "browser-use",
        ],
        "runtime_commands": [[
            str(HOME / ".claude" / "mcp-servers" / "browser-use" / ".venv" / "bin" / "python"),
            "-m",
            "py_compile",
            str(HOME / ".claude" / "mcp-servers" / "browser-use" / "server.py"),
        ]],
    },
    {
        "id": "openai-agents-python",
        "name": "openai-agents-python PoC",
        "plugin": "openai-agents-python",
        "health_name": "openai-agents-python PoC",
        "capabilities": ["agents_sdk.design", "agents_sdk.guardrails", "agents_sdk.tracing", "agents_sdk.handoff_model"],
        "dispatch_text": "openai agents sdk guardrails tracing handoffs sessions OpenAI Agents 智能体 SDK 护栏 追踪",
        "expected_provider": "openai-agents-python",
        "runtime_paths": [HOME / ".solar" / "reports" / "2026-04-20-openai-agents-integration-codex.md"],
        "expected_level": "basic_usable",
        "candidate": True,
    },
    {
        "id": "codex-bridge",
        "name": "Codex Bridge / pane3 bridge",
        "plugin": "codex-bridge",
        "health_name": "Codex Bridge / pane3 bridge",
        "capabilities": ["codex.bridge", "codex.contract_ingest", "codex.review_handoff", "pane3.bridge"],
        "dispatch_text": "codex bridge pane3 from-codex chain-watcher execution-contract 合约导入 三号 pane",
        "expected_provider": "Codex Bridge",
        "runtime_paths": [
            HOME / ".solar" / "codex-bridge" / "CODEX-PROTOCOL.md",
            HOME / ".solar" / "codex-bridge" / "from-codex",
            HARNESS / "chain-watcher.sh",
        ],
        "runtime_commands": [["bash", "-n", str(HARNESS / "chain-watcher.sh")]],
    },
    {
        "id": "ruflo",
        "name": "Ruflo / Claude Flow",
        "plugin": "ruflo",
        "health_name": "ruflo / Claude Flow",
        "capabilities": ["ruflo.swarm", "ruflo.plugins", "ruflo.agent_catalog", "ruflo.memory", "ruflo.mcp", "ruflo.workflow_templates"],
        "dispatch_text": "ruflo claude-flow swarm hive-mind agentdb ruvector sparc MCP 多代理编排 自学习",
        "expected_provider": "Ruflo",
        "runtime_paths": [
            HARNESS / "vendor" / "ruflo",
            HARNESS / "state" / "ruflo" / "claude-flow-runtime" / "work" / "node_modules" / ".bin" / "claude-flow",
            HARNESS / "state" / "ruflo" / "claude-flow-runtime" / "runtime-smoke.json",
        ],
        "runtime_commands": [[
            "bash",
            str(SOLAR_BIN),
            "integrations",
            "ruflo-runtime-smoke",
            "--json",
        ]],
    },
]


def run(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except Exception as exc:
        return 99, f"{type(exc).__name__}: {exc}"


def run_json(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    code, out = run(cmd, timeout=timeout)
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data["_exit_code"] = code
            return data
    except Exception:
        pass
    return {"ok": False, "_exit_code": code, "_raw": out[:2000]}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def by_key(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(item.get(key, "")): item for item in items}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def inject_dispatch(text: str, evidence_dir: Path | None = None, scenario_id: str = "dispatch") -> str:
    with tempfile.TemporaryDirectory(prefix="solar-cap-bench-") as td:
        path = Path(td) / "dispatch.md"
        path.write_text("# Benchmark Dispatch\n\n" + text + "\n", encoding="utf-8")
        if evidence_dir:
            (evidence_dir / "dispatch").mkdir(parents=True, exist_ok=True)
            (evidence_dir / "dispatch" / f"{scenario_id}.input.md").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        run([sys.executable, str(SKILLS_PY), "inject", str(path)], timeout=45)
        injected = path.read_text(encoding="utf-8", errors="replace")
        if evidence_dir:
            (evidence_dir / "dispatch" / f"{scenario_id}.injected.md").write_text(injected, encoding="utf-8")
        return injected


def pane_ready(evidence_dir: Path | None = None) -> tuple[bool, dict[str, Any]]:
    doctor = run_json(["bash", str(SOLAR_BIN), "skills", "doctor", "--json"], timeout=20)
    if evidence_dir:
        write_json(evidence_dir / "pane-doctor.json", doctor)
    panes = doctor.get("panes", [])
    names = {p.get("pane") for p in panes if isinstance(p, dict)}
    ok = "builder" in names and "lab-builder" in names
    evidence = {"builder": "builder" in names, "lab_builder": "lab-builder" in names}
    if PERSONA_CONFIG.exists():
        for pane in ("builder", "lab-builder"):
            code, out = run(["bash", str(PERSONA_CONFIG), "--print-config", pane], timeout=10)
            evidence[f"{pane}_persona_config"] = code == 0 and "MODEL_FLAG" in out
    return ok, evidence


def score_bool(ok: bool, points: int) -> int:
    return points if ok else 0


def benchmark(threshold: int, evidence_dir: Path | None = None) -> dict[str, Any]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    if evidence_dir:
        if evidence_dir.exists():
            shutil.rmtree(evidence_dir)
        evidence_dir.mkdir(parents=True, exist_ok=True)

    plugin_validate = run_json([sys.executable, str(PLUGIN_LOADER), "validate", "--json"], timeout=30)
    run([sys.executable, str(CAPABILITY_REGISTRY), "sync", "--json"], timeout=30)
    caps = run_json([sys.executable, str(CAPABILITY_REGISTRY), "list", "--json"], timeout=30)
    health = run_json([sys.executable, str(HEALTH_PROBE), "--json", "--refresh"], timeout=60)
    pane_ok, pane_evidence = pane_ready(evidence_dir=evidence_dir)
    if evidence_dir:
        write_json(evidence_dir / "plugin-validate.json", plugin_validate)
        write_json(evidence_dir / "capability-registry-list.json", caps)
        write_json(evidence_dir / "external-integrations-health.json", health)

    plugin_results = by_key(plugin_validate.get("results", []), "id")
    caps_list = caps.get("capabilities", [])
    health_items = by_key(health.get("integrations", []), "name")

    scenarios_out: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        checks: dict[str, Any] = {}

        plugin = plugin_results.get(scenario["plugin"], {})
        manifest_ok = bool(plugin.get("valid"))
        checks["manifest"] = {
            "ok": manifest_ok,
            "points": score_bool(manifest_ok, WEIGHTS["manifest"]),
            "evidence": plugin,
        }

        required_caps = scenario["capabilities"]
        found_caps = [
            item for item in caps_list
            if item.get("capability") in required_caps and item.get("provider") == scenario["plugin"] and item.get("status") == "active"
        ]
        found_names = {item.get("capability") for item in found_caps}
        registry_ok = all(cap in found_names for cap in required_caps)
        checks["registry"] = {
            "ok": registry_ok,
            "points": score_bool(registry_ok, WEIGHTS["registry"]),
            "evidence": {"required": required_caps, "found": sorted(found_names)},
        }

        health_item = health_items.get(scenario["health_name"], {})
        expected_level = scenario.get("expected_level")
        health_ok = bool(
            health_item.get("status") in {"ok", "warn"}
            and health_item.get("health", {}).get("basic_available") == "ok"
            and health_item.get("health", {}).get("dead_ends") == "ok"
        )
        if expected_level:
            health_ok = health_ok and health_item.get("status_label") == expected_level
        checks["health"] = {
            "ok": health_ok,
            "points": score_bool(health_ok, WEIGHTS["health"]),
            "evidence": {
                "status": health_item.get("status"),
                "status_label": health_item.get("status_label"),
                "lifecycle": health_item.get("lifecycle"),
                "candidate": health_item.get("candidate"),
            },
        }

        injected = inject_dispatch(scenario["dispatch_text"], evidence_dir=evidence_dir, scenario_id=scenario["id"])
        dispatch_ok = (
            "<solar-capability-context>" in injected
            and scenario["expected_provider"] in injected
            and all(cap in injected for cap in required_caps[:1])
        )
        checks["dispatch"] = {
            "ok": dispatch_ok,
            "points": score_bool(dispatch_ok, WEIGHTS["dispatch"]),
            "evidence": {"expected_provider": scenario["expected_provider"]},
        }

        path_checks = {str(path): path.exists() for path in scenario.get("runtime_paths", [])}
        command_checks = []
        for cmd in scenario.get("runtime_commands", []):
            code, out = run([str(x) for x in cmd], timeout=30)
            command_checks.append({"cmd": cmd, "ok": code == 0, "exit_code": code, "output": out[:400]})
        if evidence_dir:
            write_json(
                evidence_dir / "runtime" / f"{scenario['id']}.json",
                {"paths": {str(path): path.exists() for path in scenario.get("runtime_paths", [])}, "commands": command_checks},
            )
        runtime_ok = all(path_checks.values()) and all(item["ok"] for item in command_checks)
        checks["runtime"] = {
            "ok": runtime_ok,
            "points": score_bool(runtime_ok, WEIGHTS["runtime"]),
            "evidence": {"paths": path_checks, "commands": command_checks},
        }

        checks["pane"] = {
            "ok": pane_ok,
            "points": score_bool(pane_ok, WEIGHTS["pane"]),
            "evidence": pane_evidence,
        }

        score = sum(int(item["points"]) for item in checks.values())
        scenarios_out.append({
            "id": scenario["id"],
            "name": scenario["name"],
            "score": score,
            "max_score": sum(WEIGHTS.values()),
            "passed": score >= threshold,
            "candidate": bool(scenario.get("candidate", False)),
            "checks": checks,
        })

    avg_score = round(sum(s["score"] for s in scenarios_out) / max(len(scenarios_out), 1), 2)
    min_score = min((s["score"] for s in scenarios_out), default=0)
    passed = all(s["passed"] for s in scenarios_out)
    out = {
        "ok": passed,
        "benchmark": "solar_capability_fusion",
        "generated_at": now(),
        "threshold": threshold,
        "score": {
            "average": avg_score,
            "minimum": min_score,
            "max": sum(WEIGHTS.values()),
        },
        "summary": {
            "scenarios": len(scenarios_out),
            "passed": sum(1 for s in scenarios_out if s["passed"]),
            "failed": sum(1 for s in scenarios_out if not s["passed"]),
            "candidate": sum(1 for s in scenarios_out if s.get("candidate")),
        },
        "weights": WEIGHTS,
        "scenarios": scenarios_out,
        "evidence_dir": str(evidence_dir) if evidence_dir else "",
        "global_evidence": {
            "plugins_checked": plugin_validate.get("checked"),
            "capabilities_total": caps.get("total"),
            "health_summary": health.get("summary"),
            "pane": pane_evidence,
        },
    }
    return out


def write_markdown(path: Path, data: dict[str, Any]) -> None:
    rows = []
    for item in data["scenarios"]:
        failed_checks = [name for name, check in item["checks"].items() if not check["ok"]]
        rows.append(
            f"| {item['name']} | {'ok' if item['passed'] else 'error'} | "
            f"{item['score']}/{item['max_score']} | {', '.join(failed_checks) or 'N/A'} |"
        )
    text = "\n".join([
        f"# Solar Capability Fusion Benchmark — {data['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Result: {'PASS' if data['ok'] else 'FAIL'}",
        f"- Threshold: {data['threshold']}",
        f"- Average score: {data['score']['average']}/{data['score']['max']}",
        f"- Minimum score: {data['score']['minimum']}/{data['score']['max']}",
        f"- Scenarios: {data['summary']['passed']}/{data['summary']['scenarios']} passed",
        f"- Evidence dir: `{data.get('evidence_dir') or 'N/A'}`",
        "",
        "## Score Matrix",
        "",
        "| Capability | Status | Score | Failed checks |",
        "|---|---:|---:|---|",
        *rows,
        "",
        "## Dimensions",
        "",
        "| Dimension | Points | Meaning |",
        "|---|---:|---|",
        "| manifest | 15 | Plugin manifest exists and validates. |",
        "| registry | 20 | Capabilities are active in Solar-Harness registry. |",
        "| health | 15 | Status API exposes the integration without dead-end. |",
        "| dispatch | 20 | Task text auto-selects and injects the capability. |",
        "| runtime | 20 | Local runtime/files/smoke checks pass. |",
        "| pane | 10 | Builder and lab-builder panes can receive skill context. |",
        "",
        "## Boundary",
        "",
        "`openai-agents-python PoC` is expected to score as `basic_usable`: it is a design capability, not the production Solar executor.",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(prog="capability_fusion_benchmark.py")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--threshold", type=int, default=90)
    ap.add_argument("--out-json", default=str(REPORTS / "capability-fusion-benchmark-latest.json"))
    ap.add_argument("--out-md", default=str(REPORTS / "capability-fusion-benchmark-latest.md"))
    ap.add_argument("--evidence-dir", default=str(REPORTS / "capability-fusion-evidence" / "latest"))
    args = ap.parse_args()

    data = benchmark(threshold=args.threshold, evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None)
    write_json(Path(args.out_json), data)
    write_markdown(Path(args.out_md), data)

    if args.as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if data["ok"] else "FAIL"
        print(f"Solar Capability Fusion Benchmark: {status}")
        print(f"  average: {data['score']['average']}/{data['score']['max']}")
        print(f"  minimum: {data['score']['minimum']}/{data['score']['max']}")
        print(f"  report:  {args.out_md}")
        for item in data["scenarios"]:
            print(f"  {item['score']:3d}/{item['max_score']}  {'PASS' if item['passed'] else 'FAIL'}  {item['name']}")

    return 0 if data["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
