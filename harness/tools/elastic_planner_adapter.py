#!/usr/bin/env python3
"""Typed production adapter from RequirementIR v2 to scheduler authority.

The adapter owns no lifecycle state.  It writes an isolated, content-addressed
planning bundle plus a small result record that Coordinator can poll.  Runtime
dispatch remains impossible until the frozen SchedulerInput has been verified
and materialized as a scheduler projection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


HARNESS_DIR = Path(os.environ.get("SOLAR_HARNESS_DIR", Path(__file__).resolve().parents[1]))
LIB_DIR = HARNESS_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from elastic_planner import run_elastic_planning_request  # noqa: E402
from structured_model import StructuredJsonModel, stage_model  # noqa: E402
from scheduler_input import prepare_runtime_graph, verify_runtime_projection  # noqa: E402


def _trusted_test_policy() -> dict[str, Any]:
    mode = os.environ.get("SOLAR_TEST_MODE", "").strip().lower()
    if not mode:
        return {}
    if mode != "rapid_smoke":
        raise ValueError(f"unsupported SOLAR_TEST_MODE: {mode!r}")
    return {
        "mode": "rapid_smoke",
        "semantic_evaluation_budget": 0,
        "deterministic_gates_required": True,
    }


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _model(role: str) -> StructuredJsonModel:
    timeout = int(os.environ.get("SOLAR_PLANNER_MODEL_TIMEOUT_SEC", "240") or "240")
    return stage_model("planner", role, timeout_seconds=timeout)


def run_adapter(
    *,
    requirement_ir_path: Path,
    output_root: Path,
    sprint_id: str,
    workspace_root: str,
    workspace_authority_path: Path | None = None,
    planner_model: Any | None = None,
    reviewer_model: Any | None = None,
) -> dict[str, Any]:
    requirement_ir = _read_object(requirement_ir_path)
    if requirement_ir.get("schema_version") != "solar.requirement_ir.v2":
        raise ValueError("typed Planner adapter requires solar.requirement_ir.v2")
    test_policy = _trusted_test_policy()

    upstream_artifacts: dict[str, dict[str, Any]] = {}
    if workspace_authority_path is not None:
        authority_path = workspace_authority_path.expanduser().resolve()
        authority = _read_object(authority_path)
        if str(authority.get("path") or "") != str(authority_path):
            raise ValueError("workspace authority path does not bind its own canonical file")
        if str(authority.get("sprint_id") or "") != sprint_id:
            raise ValueError("workspace authority belongs to another sprint")
        upstream_artifacts["workspace_authority"] = authority

    result = run_elastic_planning_request(
        requirement_ir,
        output_root,
        planner_model or _model("compiler"),
        reviewer_model or _model("reviewer"),
        sprint_id=sprint_id,
        workspace_root=workspace_root,
        test_policy=test_policy,
        upstream_artifacts=upstream_artifacts,
    )
    status = str(result.get("status") or "failed")
    verification_errors = list(result.get("verification_errors") or [])
    summary: dict[str, Any] = {
        "schema_version": "solar.elastic_planner_adapter_result.v1",
        "sprint_id": sprint_id,
        "status": status,
        "verification_errors": verification_errors,
        "output_root": str(output_root),
        "runtime_handoff_allowed": False,
        "test_policy": test_policy,
    }

    if status == "accepted" and not verification_errors:
        execution_dir = output_root / "execution"
        scheduler_input_path = execution_dir / "scheduler_input.json"
        run_contract_path = execution_dir / "run_contract.frozen.json"
        runtime_dir = output_root / "runtime"
        projection_path = prepare_runtime_graph(
            scheduler_input_path,
            runtime_dir,
            run_contract_path=run_contract_path,
            # PlanIR and capability contracts use ``requirement_ir.v1`` as the
            # stable artifact identity.  Preserve the controller-owned source
            # document as an exact, hash-bound runtime input even though the
            # current document schema is solar.requirement_ir.v2.
            artifact_bindings={
                "requirement_ir.v1": str(requirement_ir_path.expanduser().resolve())
            },
        )
        projection_verdict = verify_runtime_projection(
            _read_object(projection_path),
            graph_path=projection_path,
        )
        if not projection_verdict.get("ok"):
            raise RuntimeError(
                "scheduler projection verification failed: "
                + ",".join(str(item) for item in projection_verdict.get("errors") or [])
            )
        summary.update(
            {
                "runtime_handoff_allowed": True,
                "scheduler_input": str(scheduler_input_path),
                "run_contract": str(run_contract_path),
                "scheduler_runtime_dir": str(runtime_dir),
                "runtime_projection": str(projection_path),
                "plan_acceptance": str(execution_dir / "plan_acceptance.json"),
            }
        )
    elif status == "direct_response" and not verification_errors:
        semantic_dir = output_root / "semantic"
        summary.update(
            {
                "direct_response": str(semantic_dir / "direct_response.json"),
                "plan_acceptance": str(semantic_dir / "plan_acceptance.json"),
            }
        )

    _write_json(output_root / "adapter_result.json", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirement-ir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sprint-id", required=True)
    parser.add_argument("--workspace-root", default="workspace")
    parser.add_argument("--workspace-authority", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_adapter(
            requirement_ir_path=args.requirement_ir,
            output_root=args.output_root,
            sprint_id=args.sprint_id,
            workspace_root=args.workspace_root,
            workspace_authority_path=args.workspace_authority,
        )
    except Exception as exc:
        summary = {
            "schema_version": "solar.elastic_planner_adapter_result.v1",
            "sprint_id": args.sprint_id,
            "status": "failed",
            "verification_errors": [f"{type(exc).__name__}: {exc}"],
            "output_root": str(args.output_root),
            "runtime_handoff_allowed": False,
        }
        _write_json(args.output_root / "adapter_result.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] in {"accepted", "direct_response"} and not summary["verification_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
