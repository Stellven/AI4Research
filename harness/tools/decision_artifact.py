#!/usr/bin/env python3
"""Build a canonical, evidence-bound decision artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1]
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

from lib.research.decision_artifact import DecisionArtifactError, construct_decision_artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="decision_request.v1 JSON")
    parser.add_argument("--output", required=True, type=Path, help="destination decision_artifact.v1 JSON")
    parser.add_argument(
        "--source-root",
        type=Path,
        help="root containing all referenced evidence (defaults to input directory)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = args.input.resolve()
    source_root = (args.source_root or input_path.parent).resolve()
    try:
        request = json.loads(input_path.read_text(encoding="utf-8"))
        artifact = construct_decision_artifact(
            request,
            request_path=input_path,
            source_root=source_root,
        )
    except (OSError, json.JSONDecodeError, DecisionArtifactError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "artifact": str(args.output.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
