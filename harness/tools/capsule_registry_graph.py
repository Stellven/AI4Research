#!/usr/bin/env python3
"""Emit deterministic capsule-registry audit or composition-candidate artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


HARNESS_DIR = Path(__file__).resolve().parents[1]
LIB_DIR = HARNESS_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from capsule_composition import (  # noqa: E402
    build_registry_graph_audit,
    search_composition_candidates,
    write_json,
)
from elastic_planner import build_planning_catalog_snapshot  # noqa: E402


def _types(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _trust_requirement(value: str) -> tuple[str, list[str]]:
    artifact_type, separator, raw_classes = value.partition("=")
    classes = _types(raw_classes)
    if not separator or not artifact_type.strip() or not classes:
        raise argparse.ArgumentTypeError(
            "trust requirement must use ARTIFACT_TYPE=TRUST_CLASS[,TRUST_CLASS]"
        )
    return artifact_type.strip(), classes


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--output", type=Path, required=True)
    compose = subparsers.add_parser("compose")
    compose.add_argument("--available", type=_types, required=True)
    compose.add_argument("--targets", type=_types, required=True)
    compose.add_argument("--max-depth", type=int, default=12)
    compose.add_argument("--max-states", type=int, default=500)
    compose.add_argument("--max-candidates", type=int, default=20)
    compose.add_argument(
        "--allowed-effects",
        type=_types,
        default=["read", "write", "execute", "network"],
    )
    compose.add_argument(
        "--required-trust",
        type=_trust_requirement,
        action="append",
        default=[],
        metavar="ARTIFACT_TYPE=TRUST_CLASS[,TRUST_CLASS]",
    )
    compose.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    catalog = build_planning_catalog_snapshot()
    if args.command == "audit":
        artifact = build_registry_graph_audit(catalog)
        exit_code = 0 if artifact["verdict"] == "pass" else 1
    else:
        artifact = search_composition_candidates(
            catalog,
            available_inputs=args.available,
            target_outputs=args.targets,
            max_depth=args.max_depth,
            max_states=args.max_states,
            max_candidates=args.max_candidates,
            allowed_effects=args.allowed_effects,
            required_trust_by_output=dict(args.required_trust),
        )
        exit_code = 0 if artifact["verdict"] == "candidates_found" else 2
    write_json(args.output, artifact)
    print(args.output)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
