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


def _paths_alias(left: Path, right: Path) -> bool:
    left_resolved = left.resolve()
    right_resolved = right.resolve()
    if left_resolved == right_resolved:
        return True
    try:
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except OSError:
        return False


def _evidence_paths(request: object, source_root: Path) -> list[Path]:
    if not isinstance(request, dict):
        raise DecisionArtifactError("decision request must be an object")
    entries = request.get("evidence")
    if not isinstance(entries, list):
        return []
    paths: list[Path] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("source_path"), str):
            continue
        path = Path(entry["source_path"])
        paths.append((path if path.is_absolute() else source_root / path).resolve())
    return paths


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = args.input.resolve()
    source_root = (args.source_root or input_path.parent).resolve()
    output_path = args.output.resolve()
    temp_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    alias_audit_passed = False
    try:
        request = json.loads(input_path.read_text(encoding="utf-8"))
        protected_paths = [input_path, *_evidence_paths(request, source_root)]
        for candidate_name, candidate in (("output", output_path), ("temporary output", temp_path)):
            aliases = [path for path in protected_paths if _paths_alias(candidate, path)]
            if aliases:
                raise DecisionArtifactError(
                    f"{candidate_name} aliases protected input/evidence path: {aliases[0]}"
                )
        alias_audit_passed = True
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.unlink(missing_ok=True)
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
        cleanup_errors: list[str] = []
        if alias_audit_passed:
            for path in (temp_path, output_path):
                try:
                    path.unlink(missing_ok=True)
                except OSError as cleanup_exc:
                    cleanup_errors.append(f"{path}: {cleanup_exc}")
        error = str(exc)
        if cleanup_errors:
            error += "; cleanup failed: " + "; ".join(cleanup_errors)
        print(json.dumps({"status": "rejected", "error": error}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "completed", "artifact": str(output_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
