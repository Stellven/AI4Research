"""GitHub Intelligence scheduling strategy.

Connects GitHub Intelligence pipeline tasks with the solar-harness
graph-scheduler interface contract. Provides:
  - Dependency resolution via graph_scheduler.ready_nodes()
  - Concurrent batching via graph_scheduler.make_batches() with write_scope
    conflict detection
  - Model capability matching: maps node required_capabilities/skills to
    available operators from the model registry

Design principle: thin adapter over graph_scheduler.py — zero duplication of
scheduling logic. All state machine and DAG semantics live in the core module.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", Path.home() / ".solar" / "harness"))

# Core graph scheduler — loaded by absolute path to avoid shadowing by this
# package's own __init__.py when both 'lib/' and 'tools/' are on sys.path.
_CORE_MODULE: Any = None


def _import_core() -> Any:
    global _CORE_MODULE
    if _CORE_MODULE is not None:
        return _CORE_MODULE
    import importlib.util

    core_path = HARNESS_DIR / "lib" / "graph_scheduler.py"
    # Ensure sibling lib modules (prerequisite_resolver etc.) are importable.
    lib_dir = str(HARNESS_DIR / "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)

    spec = importlib.util.spec_from_file_location(
        "_harness_graph_scheduler_core", core_path
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["_harness_graph_scheduler_core"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    _CORE_MODULE = mod
    return mod


# ---------------------------------------------------------------------------
# Model capability matching table
# ---------------------------------------------------------------------------

# Maps graph_scheduler capability/skill labels → preferred model identifiers.
# Extend this table as new capabilities are certified.
_CAPABILITY_MODEL_MAP: dict[str, list[str]] = {
    "workflow.planning":    ["sonnet", "opus"],
    "observability":        ["sonnet", "glm-5"],
    "frontend":             ["sonnet", "glm-5"],
    "python":               ["sonnet", "glm-5", "deepseek"],
    "distributed-systems":  ["sonnet", "opus"],
    "javascript":           ["sonnet", "glm-5"],
    "css":                  ["sonnet", "glm-5"],
    "html":                 ["sonnet", "glm-5"],
    "testing":              ["sonnet", "glm-5"],
    # GitHub Intelligence–specific
    "github.dispatch":      ["sonnet"],
    "browser.browse":       ["sonnet"],
}

_DEFAULT_MODELS = ["sonnet", "glm-5"]


class GitHubIntelligenceStrategy:
    """Scheduling strategy for GitHub Intelligence DAG sprints.

    Acts as an adapter between the GitHub Intelligence pipeline and the
    solar-harness graph-scheduler interface contract.
    """

    def resolve_dependencies(self, graph: dict[str, Any]) -> list[dict[str, Any]]:
        """Return nodes whose dependencies are all passed (ready to dispatch).

        Delegates directly to graph_scheduler.ready_nodes() so dependency
        resolution logic stays canonical.

        Args:
            graph: Loaded task_graph.json dict.

        Returns:
            List of node dicts that are ready for dispatch.
        """
        gs = _import_core()
        return gs.ready_nodes(graph)

    def make_concurrent_batches(
        self,
        graph: dict[str, Any],
        max_parallel: int | None = None,
    ) -> dict[str, Any]:
        """Return write-scope-safe concurrent batches for ready nodes.

        Delegates to graph_scheduler.make_batches() which enforces:
          - write_scope conflict detection (no two nodes in a batch may write
            to overlapping paths)
          - effect_union exclusive-writer rules (secrets, destructive ops)
          - nodes without declared write_scope serialized as exclusive writers

        Args:
            graph: Loaded task_graph.json dict.
            max_parallel: Optional cap on nodes per batch.

        Returns:
            make_batches() result dict with keys:
              ok, sprint_id, blocked_prerequisites, batch_count, batches
        """
        gs = _import_core()
        return gs.make_batches(graph, max_parallel=max_parallel)

    def match_model_for_node(self, node: dict[str, Any]) -> list[str]:
        """Return ordered list of preferred model identifiers for a node.

        Inspects required_capabilities and required_skills, looks them up in
        _CAPABILITY_MODEL_MAP, deduplicates while preserving priority order.

        Args:
            node: Node dict from task_graph.json.

        Returns:
            Ordered list of model identifier strings, e.g. ["sonnet", "glm-5"].
        """
        preferred_model = str(node.get("preferred_model") or "").strip()
        caps = list(node.get("required_capabilities") or [])
        skills = list(node.get("required_skills") or [])

        candidates: list[str] = []
        if preferred_model:
            candidates.append(preferred_model)

        for label in caps + skills:
            for model in _CAPABILITY_MODEL_MAP.get(str(label).lower(), []):
                if model not in candidates:
                    candidates.append(model)

        for model in _DEFAULT_MODELS:
            if model not in candidates:
                candidates.append(model)

        return candidates

    def dispatch_plan(
        self,
        graph: dict[str, Any],
        max_parallel: int | None = None,
    ) -> dict[str, Any]:
        """Produce a full dispatch plan: batches + model assignments.

        Combines make_concurrent_batches() and match_model_for_node() into a
        single output suitable for consumption by autopilot or graph_node_dispatcher.

        Args:
            graph: Loaded task_graph.json dict.
            max_parallel: Optional cap on nodes per batch.

        Returns:
            Dict with keys:
              ok, sprint_id, batch_count, batches (each augmented with
              node_model_assignments), blocked_prerequisites
        """
        gs = _import_core()
        batches_result = self.make_concurrent_batches(graph, max_parallel=max_parallel)
        node_map = {n["id"]: n for n in graph.get("nodes", []) if n.get("id")}

        augmented_batches = []
        for batch in batches_result.get("batches", []):
            node_ids = batch.get("nodes", [])
            assignments = {
                nid: self.match_model_for_node(node_map[nid])
                for nid in node_ids
                if nid in node_map
            }
            augmented_batches.append({
                **batch,
                "node_model_assignments": assignments,
            })

        return {
            **batches_result,
            "batches": augmented_batches,
        }

    def validate(self, graph: dict[str, Any]) -> dict[str, Any]:
        """Run graph-scheduler validation on the DAG.

        Returns the validation dict from graph_scheduler.validate_graph().
        Acceptance criterion: ok=true (no errors; warnings are allowed).
        """
        gs = _import_core()
        return gs.validate_graph(graph)


# ---------------------------------------------------------------------------
# CLI entry point for smoke-testing
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse
    import sys

    ap = argparse.ArgumentParser(prog="github_strategy")
    ap.add_argument("--graph", required=True, help="Path to task_graph.json")
    ap.add_argument(
        "--action",
        choices=["validate", "ready", "batches", "dispatch-plan"],
        default="dispatch-plan",
    )
    ap.add_argument("--max-parallel", type=int, default=None)
    args = ap.parse_args()

    graph_path = Path(args.graph).expanduser()
    graph = json.loads(graph_path.read_text(encoding="utf-8"))

    strategy = GitHubIntelligenceStrategy()

    if args.action == "validate":
        result = strategy.validate(graph)
    elif args.action == "ready":
        nodes = strategy.resolve_dependencies(graph)
        result = {"ok": True, "ready_count": len(nodes), "nodes": [n.get("id") for n in nodes]}
    elif args.action == "batches":
        result = strategy.make_concurrent_batches(graph, max_parallel=args.max_parallel)
    else:
        result = strategy.dispatch_plan(graph, max_parallel=args.max_parallel)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()
