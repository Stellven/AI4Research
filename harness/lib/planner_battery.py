#!/usr/bin/env python3
"""Deterministic planner-quality battery scorer for P5 G2 prep.

Given a directory of planner-emitted ``<case>.task_graph.json`` files, validate
each graph with the shipped ``plan_validator`` against the real capsule and
operator registries plus the ``pm.generic.v1`` workflow contract. The output is
a stable JSON scorecard for the live planner runbook to compare across models
without spending quota inside this deterministic step.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import plan_validator as pv
import workflow_contract as wc

SCORECARD_SCHEMA = "solar.planner_battery.scorecard.v3"
TASK_GRAPH_SUFFIX = ".task_graph.json"
DEFAULT_OUTPUT_NAME = "battery-scorecard.json"

# Legacy top-level keys the requirement compiler stamps on its pre-planner
# template graph. A live capture that closes its window while the planner is
# still in flight snapshots that template, and scoring it as planner output
# misreads the battery both ways (G2b run 20260709T144445Z: E5's gateless
# template produced a false PLAN_REPAIR_BUDGET_MISSING reject; E4's gated
# template validated offline into a false compile).
PRE_PLANNER_TEMPLATE_MARKERS = ("dag_variant", "required_gates")
GRAPH_KIND_PLANNER = "planner"
GRAPH_KIND_PRE_PLANNER_TEMPLATE = "pre_planner_template"
GRAPH_KIND_UNSTAMPED = "unstamped"


def graph_kind(graph: Dict[str, Any]) -> str:
    """Classify a captured graph.

    Raw planner output may legitimately lack workflow_contract_id (the
    compile seam stamps it) — and G3 run 4 (p5-g3-live-rung-20260709T201817Z)
    showed the planner may keep the compiler template's legacy marker keys by
    editing the graph file in place, so the markers alone over-classify. The
    compiler template's own signature is that EVERY node is gateless; a
    marker-carrying graph with evaluator gates is planner-shaped but
    unstamped — authorship cannot be proven, so it is validated and reported
    separately instead of joining compile_rate in either direction."""
    if str(graph.get("workflow_contract_id") or "").strip():
        return GRAPH_KIND_PLANNER
    if any(marker in graph for marker in PRE_PLANNER_TEMPLATE_MARKERS):
        nodes = [n for n in graph.get("nodes") or [] if isinstance(n, dict)]
        if nodes and all(not (n.get("evaluator_gate") or {}) for n in nodes):
            return GRAPH_KIND_PRE_PLANNER_TEMPLATE
        return GRAPH_KIND_UNSTAMPED
    return GRAPH_KIND_PLANNER


def _case_id(path: Path) -> str:
    name = path.name
    if name.endswith(TASK_GRAPH_SUFFIX):
        return name[: -len(TASK_GRAPH_SUFFIX)]
    return path.stem


def discover_graphs(graphs_dir: os.PathLike) -> List[Path]:
    """Return planner-output graph files in deterministic case order."""
    directory = Path(graphs_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"graphs_dir is not a directory: {directory}")
    return sorted(directory.glob(f"*{TASK_GRAPH_SUFFIX}"), key=lambda path: path.name)


def _load_validator_inputs(
    config_dir: Optional[os.PathLike] = None,
    workflows_dir: Optional[os.PathLike] = None,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], Optional[Dict[str, Any]]]:
    config = Path(config_dir) if config_dir else wc.default_config_dir()
    workflows = Path(workflows_dir) if workflows_dir else config / "workflows"
    capsule_registry = wc.load_capsule_registry(config)
    operator_registry = wc.load_operator_registry(config / "physical-operators.json")
    contract = wc.find_contract(pv.GENERIC_CONTRACT_ID, workflows)
    return capsule_registry, operator_registry, contract


def _code_counts(errors: Iterable[Dict[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for error in errors:
        counts[str(error.get("code") or "UNKNOWN")] += 1
    return counts


def score_directory(
    graphs_dir: os.PathLike,
    config_dir: Optional[os.PathLike] = None,
    workflows_dir: Optional[os.PathLike] = None,
) -> Dict[str, Any]:
    """Validate every graph in ``graphs_dir`` and return a deterministic scorecard."""
    capsule_registry, operator_registry, contract = _load_validator_inputs(
        config_dir=config_dir,
        workflows_dir=workflows_dir,
    )
    cases: Dict[str, Any] = {}
    total_reject_codes: Counter = Counter()

    for graph_path in discover_graphs(graphs_dir):
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        case_id = _case_id(graph_path)
        kind = graph_kind(graph)
        if kind == GRAPH_KIND_PRE_PLANNER_TEMPLATE:
            # Not planner output: the capture window closed before the
            # planner replaced the compiler template. Validation verdicts on
            # the template are meaningless, so the case is recorded but
            # excluded from compiled/rejected/compile_rate.
            cases[case_id] = {
                "graph_file": graph_path.name,
                "graph_kind": kind,
                "compiled": None,
                "error_count": 0,
                "error_codes": [],
                "code_counts": {},
                "note": "snapshot predates planner output (requirement-compiler "
                        "template); excluded from compile_rate",
            }
            continue

        errors = pv.validate_plan(
            graph,
            capsule_registry,
            operator_registry,
            contract=contract,
        )
        counts = _code_counts(errors)
        if kind == GRAPH_KIND_PLANNER:
            total_reject_codes.update(counts)
        row: Dict[str, Any] = {
            "graph_file": graph_path.name,
            "graph_kind": kind,
            "compiled": (not errors) if kind == GRAPH_KIND_PLANNER else None,
            "error_count": len(errors),
            "error_codes": sorted(counts),
            "code_counts": dict(sorted(counts.items())),
        }
        if kind == GRAPH_KIND_UNSTAMPED:
            row["note"] = (
                "graph carries legacy markers and no workflow_contract_id but "
                "has evaluator gates — planner-shaped yet never stamped; "
                "validated for information, excluded from compile_rate"
            )
        cases[case_id] = row

    case_count = len(cases)
    scored_rows = [row for row in cases.values() if row["graph_kind"] == GRAPH_KIND_PLANNER]
    scored_count = len(scored_rows)
    template_count = sum(
        1 for row in cases.values() if row["graph_kind"] == GRAPH_KIND_PRE_PLANNER_TEMPLATE
    )
    unstamped_count = sum(
        1 for row in cases.values() if row["graph_kind"] == GRAPH_KIND_UNSTAMPED
    )
    compiled = sum(1 for row in scored_rows if row["compiled"])
    rejected = scored_count - compiled
    compile_rate = compiled / scored_count if scored_count else 0.0
    top_reject_codes = [
        {"code": code, "count": count}
        for code, count in sorted(total_reject_codes.items(), key=lambda item: (-item[1], item[0]))
    ]

    return {
        "schema": SCORECARD_SCHEMA,
        "validator": "plan_validator",
        "workflow_contract_id": pv.GENERIC_CONTRACT_ID,
        "cases": cases,
        "totals": {
            "case_count": case_count,
            "scored_count": scored_count,
            "pre_planner_templates": template_count,
            "unstamped": unstamped_count,
            "compiled": compiled,
            "rejected": rejected,
            "compile_rate": compile_rate,
            "top_reject_codes": top_reject_codes,
        },
    }


def write_scorecard(scorecard: Dict[str, Any], out_path: os.PathLike) -> Path:
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps(scorecard, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, target)
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="planner_battery", description=__doc__)
    parser.add_argument("graphs_dir", help="directory containing <case>.task_graph.json files")
    parser.add_argument("--out", default=None, help="scorecard output path")
    parser.add_argument("--config-dir", default=None, help="harness config directory")
    parser.add_argument("--workflows-dir", default=None, help="workflow contract directory")
    args = parser.parse_args(argv)

    try:
        scorecard = score_directory(
            args.graphs_dir,
            config_dir=args.config_dir,
            workflows_dir=args.workflows_dir,
        )
        out_path = Path(args.out) if args.out else Path(args.graphs_dir) / DEFAULT_OUTPUT_NAME
        write_scorecard(scorecard, out_path)
    except Exception as exc:
        print(f"planner_battery: {exc}", file=sys.stderr)
        return 2

    print(f"battery scorecard: {out_path}")
    # 3 = planner rejects; 4 = capture incomplete (pre-planner template or
    # unstamped snapshots present, so the battery under-measures the planner).
    if scorecard["totals"]["rejected"]:
        return 3
    if scorecard["totals"]["pre_planner_templates"] or scorecard["totals"]["unstamped"]:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
