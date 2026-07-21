#!/usr/bin/env python3
"""Infer Solar capability requirements for task_graph nodes.

Planner output is still authoritative, but planners often describe goals in
natural language and forget `required_capabilities`. This module bridges that
gap by reusing Solar's dispatch capability rules and writing deterministic
node-level capability hints before graph scheduling.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_rules() -> list[dict[str, Any]]:
    try:
        import solar_skills  # type: ignore

        return list(getattr(solar_skills, "CAPABILITY_RULES", []))
    except Exception:
        return []


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_as_text(v) for v in value)
    if isinstance(value, dict):
        return "\n".join(f"{k}: {_as_text(v)}" for k, v in sorted(value.items()))
    return str(value)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = str(value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


PROVIDER_ALIASES: dict[str, list[str]] = {
    "ruflo": ["ruflo", "ruvflo", "claude-flow", "claude flow"],
    "autoresearch": [
        "autoresearch",
        "auto research",
        "issue-loop",
        "issue loop",
        "local issue",
        "pane optimizer",
        "execution optimizer",
        "dispatch advisor",
        "implementation loop",
        "score-gated",
        "score gate",
        "passing score",
        "自动实现 issue",
        "多代理迭代",
        "评分门禁",
        "执行优化器",
        "质量优化",
    ],
    "everything claude code": ["everything-claude-code", "everything claude code"],
    "browser-use mcp": ["browser-use", "browser use", "browser mcp"],
    "gstack": ["gstack"],
    "superpowers": ["superpowers"],
    "atlas": ["atlas"],
    "owl": ["owl", "camel-ai", "camel ai"],
    "markitdown": ["markitdown", "mark it down"],
    "agency-agents": ["agency-agents", "agency agents"],
    "empirical research": ["empirical research"],
    "addyosmani/agent-skills": ["addyosmani", "agent-skills"],
    "openai-agents-python": ["openai-agents-python", "openai agents"],
    "codex bridge": ["codex bridge"],
}


def _explicit_providers(text: str) -> set[str]:
    lowered = text.lower()
    explicit: set[str] = set()
    for provider, aliases in PROVIDER_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            explicit.add(provider)
    return explicit


def infer_capabilities(text: str) -> list[dict[str, Any]]:
    """Return matched providers and capabilities for free-form task text."""
    matches: list[dict[str, Any]] = []
    rules = _load_rules()
    explicit = _explicit_providers(text)
    for rule in rules:
        provider = str(rule.get("provider", ""))
        provider_key = provider.lower()
        if explicit and provider_key not in explicit:
            continue
        patterns = rule.get("patterns") or []
        matched_pattern = ""
        for pattern in patterns:
            if re.search(str(pattern), text, re.IGNORECASE | re.MULTILINE):
                matched_pattern = str(pattern)
                break
        if not matched_pattern:
            continue
        matches.append({
            "provider": provider,
            "capabilities": _dedupe([str(c) for c in rule.get("capabilities", [])]),
            "matched_pattern": matched_pattern,
        })
    return matches


def _node_text(node: dict[str, Any], source_text: str = "") -> str:
    fields = [
        node.get("id", ""),
        node.get("goal", ""),
        node.get("acceptance", []),
        node.get("read_scope", []),
        node.get("write_scope", []),
        node.get("required_skills", []),
        node.get("notes", ""),
        node.get("handoff", ""),
    ]
    if source_text:
        fields.append(source_text)
    return "\n".join(_as_text(field) for field in fields if field is not None)


def infer_node_capabilities(node: dict[str, Any], source_text: str = "") -> dict[str, Any]:
    matches = infer_capabilities(_node_text(node, source_text))
    caps = _dedupe([cap for match in matches for cap in match.get("capabilities", [])])
    providers = _dedupe([str(match.get("provider", "")) for match in matches])
    return {
        "capabilities": caps,
        "providers": providers,
        "matches": matches,
    }


def enrich_graph(graph: dict[str, Any], source_text: str = "",
                 overwrite: bool = False) -> dict[str, Any]:
    """Add missing `required_capabilities` to graph nodes.

    Existing planner-declared capabilities are preserved by default and unioned
    with inferred capabilities. Set `overwrite=True` only for controlled tests.
    """
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("task_graph.nodes must be a list")

    changed_nodes: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        inferred = infer_node_capabilities(node, source_text=source_text)
        inferred_caps = inferred["capabilities"]
        existing = node.get("required_capabilities", [])
        had_required_capabilities = "required_capabilities" in node
        if isinstance(existing, str):
            existing_caps = [existing]
        elif isinstance(existing, list):
            existing_caps = [str(item) for item in existing if str(item)]
        else:
            existing_caps = []

        final_caps = inferred_caps if overwrite else _dedupe(existing_caps + inferred_caps)
        if final_caps != existing_caps or not had_required_capabilities:
            node["required_capabilities"] = final_caps
            changed_nodes.append(str(node.get("id", "")))
        if inferred_caps:
            node["capability_inference"] = {
                "source": "solar-capability-rules",
                "generated_at": _now(),
                "providers": inferred["providers"],
                "capabilities": inferred_caps,
            }

    graph.setdefault("capability_inference", {})
    graph["capability_inference"].update({
        "ok": True,
        "generated_at": _now(),
        "changed_nodes": [node_id for node_id in changed_nodes if node_id],
        "rule_source": "solar_skills.CAPABILITY_RULES",
    })
    return graph


def _load_source(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(prog="capability_inference.py")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("infer")
    p.add_argument("--text", required=True)

    p = sub.add_parser("enrich-graph")
    p.add_argument("--graph", required=True)
    p.add_argument("--source")
    p.add_argument("--out")
    p.add_argument("--in-place", action="store_true")
    p.add_argument("--overwrite", action="store_true")

    args = ap.parse_args()
    try:
        if args.cmd == "infer":
            print(json.dumps({"ok": True, "matches": infer_capabilities(args.text)}, ensure_ascii=False))
            return 0
        if args.cmd == "enrich-graph":
            graph_path = Path(args.graph)
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            enriched = enrich_graph(graph, source_text=_load_source(args.source), overwrite=args.overwrite)
            if args.in_place:
                out_path = graph_path
            elif args.out:
                out_path = Path(args.out)
            else:
                out_path = None
            if out_path:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = out_path.with_suffix(out_path.suffix + ".tmp")
                tmp.write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                tmp.replace(out_path)
            print(json.dumps(enriched.get("capability_inference", {"ok": True}), ensure_ascii=False))
            return 0
        ap.print_help()
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
