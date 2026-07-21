#!/usr/bin/env python3
"""architecture_guard.py — package-first architecture policy for Solar-Harness.

This guard turns the "do not mutate the main harness for new capabilities"
principle into machine-checkable graph policy. It is intentionally lightweight:
planner task_graph nodes declare an optional `architecture_policy`; dispatcher
injects the policy into pane prompts; evaluator checks it before PASS.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))

PROTECTED_CORE = {
    "solar-harness.sh",
    "coordinator.sh",
    "pane-launcher.sh",
    "coordinator-watchdog.sh",
    "tools/solar-autopilot-monitor.py",
    "lib/graph_node_dispatcher.py",
    "lib/graph_scheduler.py",
    "lib/workflow_guard.py",
}

PACKAGE_PREFIXES = (
    "plugins/",
    "skills/",
    "integrations/",
    "lib/packages/",
    "lib/research/",
    "lib/capabilities/",
    "packages/",
)

FEATURE_RE = re.compile(
    r"新增|集成|开发|feature|integration|plugin|package|skill|connector|source|research|能力",
    re.I,
)
EXPLORATION_RE = re.compile(r"exploration|探索|尝试|候选|方案|淘汰", re.I)


def _rel(path: str) -> str:
    p = Path(str(path)).expanduser()
    try:
        resolved = p.resolve()
        return str(resolved.relative_to(HARNESS_DIR))
    except Exception:
        raw = str(path)
        marker = "/.solar/harness/"
        return raw.split(marker, 1)[1] if marker in raw else raw.lstrip("./")


def _write_scope(node: dict[str, Any]) -> list[str]:
    scope = node.get("write_scope") or []
    return [str(x) for x in scope if str(x).strip()]


def _touches_core(node: dict[str, Any]) -> list[str]:
    touched: list[str] = []
    for raw in _write_scope(node):
        rel = _rel(raw)
        for protected in PROTECTED_CORE:
            if rel == protected or rel.startswith(protected.rstrip("/") + "/"):
                touched.append(rel)
    return sorted(set(touched))


def _has_package_boundary(node: dict[str, Any]) -> bool:
    policy = node.get("architecture_policy") or {}
    if policy.get("package_boundary") or policy.get("plugin_id") or policy.get("package_id"):
        return True
    for raw in _write_scope(node):
        rel = _rel(raw)
        if rel.startswith(PACKAGE_PREFIXES):
            return True
    return False


def _is_feature_node(node: dict[str, Any]) -> bool:
    text = " ".join([
        str(node.get("goal") or ""),
        " ".join(str(x) for x in (node.get("required_capabilities") or [])),
        " ".join(str(x) for x in (node.get("required_skills") or [])),
    ])
    return bool(FEATURE_RE.search(text))


def _is_exploration_node(node: dict[str, Any]) -> bool:
    text = " ".join([
        str(node.get("goal") or ""),
        json.dumps(node.get("architecture_policy") or {}, ensure_ascii=False),
    ])
    return bool(EXPLORATION_RE.search(text))


def assess_graph(graph: dict[str, Any], *, strict: bool | None = None) -> dict[str, Any]:
    if strict is None:
        guard = graph.get("architecture_guard") or {}
        strict = (
            os.environ.get("SOLAR_ARCH_GUARD_STRICT") == "1"
            or guard.get("mode") in {"strict", "package_required"}
            or guard.get("package_first") is True
        )

    errors: list[str] = []
    warnings: list[str] = []
    node_reports: list[dict[str, Any]] = []

    for node in graph.get("nodes", []):
        node_id = str(node.get("id") or "?")
        policy = node.get("architecture_policy") or {}
        core_hits = _touches_core(node)
        has_package = _has_package_boundary(node)
        feature_node = _is_feature_node(node)
        exploration_node = _is_exploration_node(node)
        report = {
            "node": node_id,
            "core_hits": core_hits,
            "has_package_boundary": has_package,
            "feature_node": feature_node,
            "exploration_node": exploration_node,
        }
        node_reports.append(report)

        if core_hits and not policy.get("core_patch_allowed"):
            msg = f"{node_id} touches protected core without architecture_policy.core_patch_allowed=true: {','.join(core_hits)}"
            (errors if strict else warnings).append(msg)
        if feature_node and not has_package and not policy.get("core_patch_allowed"):
            msg = f"{node_id} feature/integration node missing package_boundary/plugin boundary"
            (errors if strict else warnings).append(msg)
        if exploration_node:
            alternatives = policy.get("exploration_alternatives") or []
            kill = policy.get("kill_criteria") or policy.get("淘汰标准")
            if not isinstance(alternatives, list) or len(alternatives) < 2:
                msg = f"{node_id} exploration node requires >=2 exploration_alternatives"
                (errors if strict else warnings).append(msg)
            if not kill:
                msg = f"{node_id} exploration node requires kill_criteria"
                (errors if strict else warnings).append(msg)

    return {
        "ok": not errors,
        "strict": strict,
        "errors": errors,
        "warnings": warnings,
        "nodes": node_reports,
    }


def dispatch_policy_block(node: dict[str, Any], graph: dict[str, Any] | None = None) -> str:
    graph = graph or {"nodes": [node]}
    assessed = assess_graph({"nodes": [node], "architecture_guard": (graph or {}).get("architecture_guard", {})})
    policy = node.get("architecture_policy") or {}
    return "\n".join([
        "## Architecture Guard",
        "",
        "- 默认原则: 新能力必须做成可插拔 package / plugin / skill / connector，不改主架构和主循环。",
        "- 允许例外: 仅限 P0 bugfix，并且 node.architecture_policy.core_patch_allowed=true 且写明 rollback。",
        "- Online Exploration: 涉及探索/尝试时必须列出 >=2 个候选方向和 kill_criteria，快速淘汰弱方案。",
        f"- package_boundary: `{policy.get('package_boundary') or policy.get('plugin_id') or policy.get('package_id') or 'N/A'}`",
        f"- core_hits: `{','.join(assessed['nodes'][0]['core_hits']) if assessed['nodes'] else 'N/A'}`",
        f"- guard_warnings: `{'; '.join(assessed.get('warnings') or []) or 'none'}`",
        f"- guard_errors: `{'; '.join(assessed.get('errors') or []) or 'none'}`",
    ])


def main() -> int:
    ap = argparse.ArgumentParser(prog="architecture_guard.py")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("validate")
    p.add_argument("--graph", required=True)
    p.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    if args.cmd == "validate":
        graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
        result = assess_graph(graph, strict=args.strict)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 2
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
