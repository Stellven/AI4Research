#!/usr/bin/env python3
"""Workflow router — thin CLI over workflow_contract (Lane 1).

The Lane 0 intake stub in solar-harness.sh calls:

    python3 "$HARNESS_DIR/lib/workflow_router.py" match --request "$req"

Exit codes: 0 = a registered contract matched (workflow_id on stdout),
1 = no match (generic path), 2 = usage/load error. The stub treats any
non-zero status as "no match", so every failure mode here falls back to the
legacy path (fail-safe, bit-identical flag-off behavior).

No runtime imports — this module only consumes workflow_contract.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_contract as wc  # noqa: E402

EXIT_MATCH = 0
EXIT_NO_MATCH = 1
EXIT_ERROR = 2
EXIT_COMPILE_FAILED = 3
FIXED_RESEARCH_WORKFLOW_ID = "research.evidence_to_poc.v1"


# --- research request classification ---------------------------------------
#
# research.evidence_to_poc.v1 declares no explicit trigger markers ("selection":
# "typed RESEARCH intake"), so match_trigger can never select it from prompt
# text and the caller has to name the workflow id outright. The dashboard
# profile did exactly that -- it pinned SOLAR_INTAKE_WORKFLOW_ID for EVERY
# prompt, so "fix a bug in my parser" would still compile the 15-node
# research topology.
#
# These tiers let the router decide instead:
#   simple          -> no match; the generic Planner/Epic path handles it
#   research_report -> the fixed contract, Part A only (A1-A8)
#   research_poc    -> the fixed contract, Part A plus Part B (all 15)
#
# Deliberately lexical and inspectable rather than model-judged: routing decides
# which governance applies, so it must be reproducible and reviewable.

# Every marker here must be vocabulary that an ordinary engineering request
# would not use. Widening this list is not free: a false positive sends a
# debugging task through the fifteen-node research contract, while a false
# negative only costs the user a rephrase. That asymmetry is why bare words
# like "investigate", "compare" and "evidence" are deliberately absent -- "add
# evidence logging" and "investigate this crash" are not research requests.
_RESEARCH_MARKERS = re.compile(
    r"\b(?:research|literature|scholarly|survey|systematic\s+review|prior\s+work|"
    r"related\s+work|meta[-\s]analys[ei]s|preprints?|arxiv|bibliograph\w*|"
    r"state[-\s]of[-\s]the[-\s]art|papers?|publications?|citations?|cite|"
    r"empirical\s+(?:study|studies|evidence|comparison)|"
    r"evidence[-\s]backed|evidence[-\s]linked|source[-\s]linked|peer[-\s]reviewed)\b",
    re.IGNORECASE,
)

# Asking to BUILD or RUN something, not merely to discuss benchmarks. "benchmark"
# alone is a topic word -- "compare reliability benchmarks" is a report request --
# so Part B needs an explicit build/execute intent.
_POC_MARKERS = re.compile(
    r"\b(?:proof[-\s]of[-\s]concept|poc|prototype|implement(?:ation)?|"
    r"build\s+(?:a|an|the)?|run\s+(?:a|an|the)?\s*(?:experiment|benchmark)|"
    r"execute\s+(?:a|an|the)?\s*(?:experiment|benchmark)|"
    r"design\s+and\s+run|empirical(?:ly)?|reproduce|measure\s+)\b",
    re.IGNORECASE,
)


def classify_research_request(request: str) -> dict:
    """Route a free-text request to a workflow and execution profile."""
    text = str(request or "")
    research = sorted({m.group(0).lower() for m in _RESEARCH_MARKERS.finditer(text)})
    if not research:
        return {
            "tier": "simple",
            "workflow_id": None,
            "execution_profile": None,
            "research_markers": [],
            "poc_markers": [],
            "reason": "no research markers; the generic planner path applies",
        }
    poc = sorted({m.group(0).lower().strip() for m in _POC_MARKERS.finditer(text)})
    if poc:
        return {
            "tier": "research_poc",
            "workflow_id": FIXED_RESEARCH_WORKFLOW_ID,
            "execution_profile": "part_a_plus_poc",
            "research_markers": research,
            "poc_markers": poc,
            "reason": "research request that also asks to build or run something",
        }
    return {
        "tier": "research_report",
        "workflow_id": FIXED_RESEARCH_WORKFLOW_ID,
        "execution_profile": "part_a_only",
        "research_markers": research,
        "poc_markers": [],
        "reason": "research request with no build or execute intent",
    }


def cmd_classify(args: argparse.Namespace) -> int:
    result = classify_research_request(args.request)
    print(json.dumps(result, indent=2, sort_keys=True))
    return EXIT_MATCH if result["workflow_id"] else EXIT_NO_MATCH


def _workflows_dir(args: argparse.Namespace) -> Path:
    if getattr(args, "workflows_dir", None):
        return Path(args.workflows_dir)
    return wc.default_workflows_dir()


def cmd_match(args: argparse.Namespace) -> int:
    # F12: a single malformed contract must not break routing for every request.
    contracts = wc.load_all_contracts(_workflows_dir(args), skip_invalid=True)
    workflow_id = wc.match_trigger(
        args.request,
        env=os.environ,
        requirement_type=args.requirement_type,
        contracts=contracts,
    )
    if workflow_id:
        print(workflow_id)
        return EXIT_MATCH
    return EXIT_NO_MATCH


def cmd_list(args: argparse.Namespace) -> int:
    for contract in wc.load_all_contracts(_workflows_dir(args), skip_invalid=True):
        print(
            f"{contract.get('workflow_id')}\t{contract.get('version')}\t"
            f"{contract.get('stages_mode', 'fixed')}\t{contract.get('title', '')}"
        )
    return EXIT_MATCH


def _load_target_contract(args: argparse.Namespace) -> dict:
    if getattr(args, "contract_file", None):
        return wc.load_contract(args.contract_file)
    contract = wc.find_contract(args.workflow_id, _workflows_dir(args))
    if contract is None:
        raise wc.ContractSchemaError(
            args.workflow_id, [f"workflow {args.workflow_id!r} is not registered"]
        )
    return contract


def cmd_compile(args: argparse.Namespace) -> int:
    contract = _load_target_contract(args)
    config_dir = Path(args.config_dir) if args.config_dir else wc.default_config_dir()
    capsules = wc.load_capsule_registry(config_dir)
    operators = wc.load_operator_registry(config_dir / "physical-operators.json")
    errors = wc.compile_checks(contract, capsules, operators)
    if errors:
        json.dump({"workflow_id": contract.get("workflow_id"), "errors": errors}, sys.stdout, indent=2)
        print()
        return EXIT_COMPILE_FAILED
    print(f"{contract.get('workflow_id')}: compile clean")
    return EXIT_MATCH


def cmd_instantiate(args: argparse.Namespace) -> int:
    contract = _load_target_contract(args)
    if str(contract.get("workflow_id") or "") == FIXED_RESEARCH_WORKFLOW_ID:
        raise wc.ContractInstantiationError(
            "research.evidence_to_poc.v1 requires the typed workflow_intake boundary; "
            "raw instantiation cannot authorize a source pack or specialize conditional Part B"
        )
    inputs = {}
    for pair in args.input or []:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise ValueError(f"--input expects key=value, got {pair!r}")
        inputs[key] = value
    graph = wc.instantiate(contract, inputs)
    sys.stdout.write(wc.canonical_graph_json(graph))
    return EXIT_MATCH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workflow_router", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_match = sub.add_parser("match", help="match intake text against registered contract triggers")
    p_match.add_argument("--request", required=True)
    p_match.add_argument("--requirement-type", default=None)
    p_match.add_argument("--workflows-dir", default=None)
    p_match.set_defaults(func=cmd_match)

    p_list = sub.add_parser("list", help="list registered contracts")
    p_list.add_argument("--workflows-dir", default=None)
    p_list.set_defaults(func=cmd_list)

    p_compile = sub.add_parser("compile", help="run R2 compile checks against the shipped registries")
    group = p_compile.add_mutually_exclusive_group(required=True)
    group.add_argument("--workflow-id")
    group.add_argument("--contract-file")
    p_compile.add_argument("--workflows-dir", default=None)
    p_compile.add_argument("--config-dir", default=None)
    p_compile.set_defaults(func=cmd_compile)

    p_inst = sub.add_parser("instantiate", help="emit the task graph for a fixed contract")
    group = p_inst.add_mutually_exclusive_group(required=True)
    group.add_argument("--workflow-id")
    group.add_argument("--contract-file")
    p_inst.add_argument("--workflows-dir", default=None)
    p_inst.add_argument("--input", action="append", metavar="KEY=VALUE")
    p_inst.set_defaults(func=cmd_instantiate)

    return parser


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except SystemExit:
        raise
    except wc.ContractSchemaError as exc:
        print(f"workflow_router: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # fail-safe: the intake stub falls back to legacy
        print(f"workflow_router: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
