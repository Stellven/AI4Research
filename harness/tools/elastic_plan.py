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
from intent_compiler import IntentCompilerError, JsonModel  # noqa: E402
from planner_failure import ensure_planner_failure  # noqa: E402
from planner_replay import ReplayJsonModel, replay_fallback_live, replay_root_from_environment  # noqa: E402
from structured_model import StructuredModelError, stage_model  # noqa: E402
from structured_output import OutputContractError  # noqa: E402


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


def _codex_model(role: str, output_root: Path | None = None) -> JsonModel:
    replay_root = replay_root_from_environment()
    timeout = int(os.environ.get("SOLAR_PLANNER_MODEL_TIMEOUT_SEC", "240") or "240")
    if replay_root is not None:
        if output_root is None:
            raise ValueError("replay requires the planner output root")
        fallback = None
        if replay_fallback_live():
            fallback = stage_model("planner", role, timeout_seconds=timeout)
        return ReplayJsonModel(
            replay_root=replay_root,
            output_root=output_root,
            fallback=fallback,
        )
    return stage_model("planner", role, timeout_seconds=timeout)


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
    output_root = Path(args.output_root).expanduser().resolve()
    try:
        result = run_elastic_planning_request(
            _load_object(args.requirement_ir),
            output_root,
            _codex_model("compiler", output_root),
            _codex_model("reviewer", output_root),
            sprint_id=args.sprint_id,
            workspace_root=args.workspace_root,
            upstream_artifacts=_load_context_artifacts(args.context_artifact),
        )
    except (IntentCompilerError, StructuredModelError, OutputContractError) as exc:
        failure = ensure_planner_failure(
            output_root,
            fallback_stage="model_call",
            fallback_code="provider_error",
            fallback_detail=str(exc),
        )
        print(
            json.dumps(
                {
                    "status": "failed",
                    "failure": failure,
                    "output_root": str(output_root),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    admitted = (
        result["status"] in {"accepted", "direct_response"}
        and not result["verification_errors"]
    )
    summary = {
        "status": result["status"],
        "verification_errors": result["verification_errors"],
        "output_root": str(output_root),
    }
    if not admitted:
        summary["failure"] = ensure_planner_failure(
            output_root,
            fallback_stage=(
                "chain_verification" if result["verification_errors"] else "acceptance"
            ),
            fallback_code=(
                str(result["verification_errors"][0])
                if result["verification_errors"]
                else str(result["status"] or "failed")
            ),
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if admitted else 2


if __name__ == "__main__":
    raise SystemExit(main())
