#!/usr/bin/env python3
"""Production CLI for RequirementIR -> accepted direct answer or frozen TaskGraph."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


HARNESS_DIR = Path(__file__).resolve().parents[1]
LIB_DIR = HARNESS_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from elastic_planner import run_elastic_planning_request  # noqa: E402
from intent_compiler import CodexJsonModel  # noqa: E402


def _load_object(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"RequirementIR must be a JSON object: {path}")
    return payload


def _load_context_artifacts(values: list[str]) -> dict[str, dict]:
    artifacts: dict[str, dict] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        name = name.strip()
        if not separator or not name or not raw_path.strip():
            raise ValueError("--context-artifact must use NAME=PATH")
        if name in artifacts:
            raise ValueError(f"duplicate context artifact name: {name}")
        artifacts[name] = _load_object(Path(raw_path).expanduser().resolve())
    return artifacts


def _codex_model(role: str) -> CodexJsonModel:
    provider = os.environ.get(f"SOLAR_PLANNER_{role.upper()}_PROVIDER", "codex").strip().lower()
    if provider != "codex":
        raise ValueError(f"unsupported planner {role} provider: {provider!r}")
    model = os.environ.get(f"SOLAR_PLANNER_{role.upper()}_MODEL", "").strip()
    timeout = int(os.environ.get("SOLAR_PLANNER_MODEL_TIMEOUT_SEC", "240") or "240")
    return CodexJsonModel(model=model, timeout_seconds=timeout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirement-ir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sprint-id", required=True)
    parser.add_argument("--workspace-root", default="workspace")
    parser.add_argument(
        "--context-artifact",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Accepted upstream JSON artifact supplied to the Planner component; repeatable.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_elastic_planning_request(
        _load_object(args.requirement_ir),
        args.output_root,
        _codex_model("compiler"),
        _codex_model("reviewer"),
        sprint_id=args.sprint_id,
        workspace_root=args.workspace_root,
        upstream_artifacts=_load_context_artifacts(args.context_artifact),
    )
    summary = {
        "status": result["status"],
        "verification_errors": result["verification_errors"],
        "output_root": str(args.output_root),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"accepted", "direct_response"} and not result["verification_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
