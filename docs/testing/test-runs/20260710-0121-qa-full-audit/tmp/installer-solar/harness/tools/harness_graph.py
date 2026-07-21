#!/usr/bin/env python3
"""
harness_graph.py — Solar Harness dependency graph.

Generates a dependency map of core harness components (shell scripts, Python
libs, config files) and their relationships, in both JSON and Mermaid formats.

Usage:
  python3 harness_graph.py [--json] [--mermaid] [--output FILE]
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parent.parent

# ── static node catalogue ──────────────────────────────────────────────────
# Each entry: id, path (relative to HARNESS_DIR), type, description
NODES: list[dict[str, str]] = [
    {"id": "solar-harness", "path": "solar-harness.sh", "type": "entrypoint",
     "description": "Main CLI entrypoint — routes all subcommands"},
    {"id": "coordinator", "path": "coordinator.sh", "type": "orchestrator",
     "description": "Sprint dispatch loop — manages pane lifecycle and sprint state"},
    {"id": "pane-launcher", "path": "pane-launcher.sh", "type": "launcher",
     "description": "Launches Claude Code panes with persona config and MCP flags"},
    {"id": "persona-config", "path": "lib/persona-config.sh", "type": "config",
     "description": "Per-persona model/MCP/auth config provider"},
    {"id": "solar_skills", "path": "lib/solar_skills.py", "type": "library",
     "description": "Skills inventory, doctor, inject — capability plane"},
    {"id": "harness_graph", "path": "lib/harness_graph.py", "type": "library",
     "description": "Dependency graph generator (this file)"},
    {"id": "solar_mirage", "path": "lib/solar_mirage.py", "type": "library",
     "description": "Mirage VFS — logical mount abstraction for cross-source reads"},
    {"id": "solar_db", "path": "lib/solar_db.py", "type": "library",
     "description": "SQLite connection factory — WAL mode + busy_timeout"},
    {"id": "data_plane_audit", "path": "lib/data_plane_audit.py", "type": "library",
     "description": "Data infrastructure audit and repair"},
    {"id": "solar-unified-context", "path": "lib/solar-unified-context.py", "type": "library",
     "description": "Knowledge base context builder for dispatch injection"},
    {"id": "status-server", "path": "lib/symphony/status-server.py", "type": "service",
     "description": "HTTP status dashboard — pane capability cards and sprint overview"},
    {"id": "solar-config-server", "path": "integrations/solar-config-server.py", "type": "service",
     "description": "Config UI backend at :8789 — manages model/MCP/drive settings"},
    {"id": "phase-state-machine", "path": "lib/phase-state-machine.sh", "type": "library",
     "description": "Sprint phase transitions (spec → planning → building → reviewing → passed)"},
    {"id": "events", "path": "lib/events.sh", "type": "library",
     "description": "Append-only events.jsonl API — session-scoped event stream"},
    {"id": "run-state", "path": "lib/run-state.sh", "type": "library",
     "description": "Runtime state variables sourced by solar-harness.sh"},
    {"id": "dispatch-ledger", "path": "lib/dispatch-ledger.sh", "type": "library",
     "description": "Dispatch attempt/nack/delivered ledger for audit"},
    {"id": "queue", "path": "lib/queue.sh", "type": "library",
     "description": "Sprint queue management — pending/dequeued operations"},
    {"id": "empty-mcp-config", "path": "config/empty-mcp.json", "type": "config",
     "description": "Empty MCP config used by STRICT mode panes"},
]

# ── static edge catalogue ──────────────────────────────────────────────────
# Each entry: from_id, to_id, label
EDGES: list[dict[str, str]] = [
    {"from": "solar-harness", "to": "coordinator", "label": "starts"},
    {"from": "solar-harness", "to": "solar_mirage", "label": "delegates mirage subcommand"},
    {"from": "solar-harness", "to": "solar_skills", "label": "delegates skills subcommand"},
    {"from": "solar-harness", "to": "data_plane_audit", "label": "delegates data-plane subcommand"},
    {"from": "solar-harness", "to": "harness_graph", "label": "delegates graph subcommand"},
    {"from": "solar-harness", "to": "run-state", "label": "sources"},
    {"from": "coordinator", "to": "pane-launcher", "label": "launches panes via"},
    {"from": "coordinator", "to": "solar_skills", "label": "inject_dispatch_context"},
    {"from": "coordinator", "to": "events", "label": "emit_event"},
    {"from": "coordinator", "to": "dispatch-ledger", "label": "ledger_append"},
    {"from": "coordinator", "to": "phase-state-machine", "label": "phase transitions"},
    {"from": "coordinator", "to": "queue", "label": "dequeue sprint"},
    {"from": "pane-launcher", "to": "persona-config", "label": "reads config via"},
    {"from": "pane-launcher", "to": "empty-mcp-config", "label": "STRICT mode uses"},
    {"from": "solar_skills", "to": "solar-unified-context", "label": "KB block inject"},
    {"from": "data_plane_audit", "to": "solar_db", "label": "uses connection factory"},
    {"from": "status-server", "to": "solar_mirage", "label": "mirage health probe"},
    {"from": "solar-config-server", "to": "solar_mirage", "label": "mirage reprobe"},
]


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _node_exists(node: dict[str, str]) -> bool:
    return (HARNESS_DIR / node["path"]).exists()


def build_graph() -> dict[str, Any]:
    nodes_out = []
    for n in NODES:
        nodes_out.append({
            **n,
            "exists": _node_exists(n),
            "absolute_path": str(HARNESS_DIR / n["path"]),
        })

    # Validate edges reference known node ids
    node_ids = {n["id"] for n in NODES}
    edges_out = []
    for e in EDGES:
        valid = e["from"] in node_ids and e["to"] in node_ids
        edges_out.append({**e, "valid": valid})

    return {
        "nodes": nodes_out,
        "edges": edges_out,
        "stats": {
            "total_nodes": len(nodes_out),
            "existing_nodes": sum(1 for n in nodes_out if n["exists"]),
            "missing_nodes": sum(1 for n in nodes_out if not n["exists"]),
            "total_edges": len(edges_out),
            "invalid_edges": sum(1 for e in edges_out if not e["valid"]),
        },
        "harness_dir": str(HARNESS_DIR),
        "generated_at": _now_iso(),
    }


def to_mermaid(graph: dict[str, Any]) -> str:
    lines = ["graph LR"]
    # Subgraphs by type
    types: dict[str, list[str]] = {}
    for n in graph["nodes"]:
        t = n["type"]
        types.setdefault(t, []).append(n["id"])

    for t, ids in sorted(types.items()):
        lines.append(f"  subgraph {t}")
        for nid in ids:
            node = next(x for x in graph["nodes"] if x["id"] == nid)
            label = node["description"][:40].replace('"', "'")
            style = "" if node["exists"] else ":::missing"
            lines.append(f'    {nid}["{nid}\\n{label}"]{style}')
        lines.append("  end")

    lines.append("")
    for e in graph["edges"]:
        if e["valid"]:
            label = e["label"].replace('"', "'")
            lines.append(f'  {e["from"]} -- "{label}" --> {e["to"]}')

    lines.append("")
    lines.append("  classDef missing fill:#faa,stroke:#c00")
    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]
    as_json = "--json" in args
    as_mermaid = "--mermaid" in args
    output_file = None
    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output_file = args[idx + 1]

    # Default: both JSON + Mermaid
    if not as_json and not as_mermaid:
        as_json = True
        as_mermaid = True

    graph = build_graph()

    output_parts = []
    if as_json:
        output_parts.append(json.dumps(graph, indent=2, ensure_ascii=False))
    if as_mermaid:
        output_parts.append(to_mermaid(graph))

    out = "\n\n".join(output_parts)

    if output_file:
        Path(output_file).write_text(out, encoding="utf-8")
        print(f"graph written to {output_file}")
    else:
        print(out)


if __name__ == "__main__":
    main()
