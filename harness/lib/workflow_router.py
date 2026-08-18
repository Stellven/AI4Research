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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_contract as wc  # noqa: E402

EXIT_MATCH = 0
EXIT_NO_MATCH = 1
EXIT_ERROR = 2
EXIT_COMPILE_FAILED = 3
FIXED_RESEARCH_WORKFLOW_ID = "research.evidence_to_poc.v1"


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
