#!/usr/bin/env python3
"""Build a canonical, evidence-bound decision artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import jsonschema

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
    output_path = args.output.resolve()
    temp_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.unlink(missing_ok=True)
        temp_path.unlink(missing_ok=True)
        request = json.loads(input_path.read_text(encoding="utf-8"))
        artifact = construct_decision_artifact(
            request,
            request_path=input_path,
            source_root=source_root,
        )
        schema_path = HARNESS_DIR / "schemas" / "evidence" / "decision_artifact.v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(artifact)
        temp_path.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(output_path)
    except (
        OSError,
        json.JSONDecodeError,
        jsonschema.SchemaError,
        jsonschema.ValidationError,
        DecisionArtifactError,
    ) as exc:
        temp_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        print(json.dumps({"status": "rejected", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "completed", "artifact": str(output_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
