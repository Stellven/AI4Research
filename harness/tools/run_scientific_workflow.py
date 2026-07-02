#!/usr/bin/env python3
"""Run a declared scientific workflow through Solar node runtime dispatch.

This runner is intentionally config-driven: it reads workflow nodes from a
Solar workflow JSON file and dispatches each node through the existing
operator_runtime -> AutoSci bridge single-node path. It is not an AutoSci
black-box lifecycle wrapper.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_HARNESS_DIR = Path(__file__).resolve().parents[1]
if str(REPO_HARNESS_DIR / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_HARNESS_DIR / "tools"))

import run_scientific_lifecycle_smoke as lifecycle_smoke  # noqa: E402
import run_scientific_node_smoke as node_runtime  # noqa: E402


DEFAULT_WORKFLOW_ID = "scientific_research_lifecycle_full_v1"
DEFAULT_WORKFLOW_CONFIG = REPO_HARNESS_DIR / "workflows" / f"{DEFAULT_WORKFLOW_ID}.json"
DEFAULT_PAPER = "plugins/autosci/tests/fixtures/sample_paper.md"
NODE_SPEC_BY_ID = {
    spec["node_id"]: spec
    for spec in [*lifecycle_smoke.NODE_SPECS, *lifecycle_smoke.EXTERNAL_NODE_SPECS]
}
SIDE_EFFECT_OR_PROVIDER_NODES = {
    "literature_discover",
    "experiment_run",
    "experiment_monitor",
    "report_plan",
    "publication_produce",
}
CAPABILITY_NATIVE_SKILL_BY_NODE = {
    "literature_discover": "daily-arxiv",
    "paper_ingest": "ingest",
    "paper_analyze": "survey",
    "memory_update_initial": "edit",
    "memory_update_final": "edit",
    "graph_update": "research",
    "claim_extract": "check",
    "method_extract": "check",
    "code_evidence_map": "check",
    "idea_generate": "ideate",
    "idea_evaluate": "novelty",
    "experiment_design": "exp-design",
    "experiment_run": "exp-run",
    "experiment_monitor": "exp-status",
    "claim_verify": "exp-eval",
    "report_plan": "paper-plan",
    "report_draft": "paper-draft",
    "artifact_review": "review",
    "publication_produce": "paper-compile",
    "workflow_evolve": "refine",
}


def _utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def _resolve_harness_path(root: Path, raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else root / path


def _artifact_root_from_env(harness_dir: Path, env_name: str, default_rel: str) -> Path:
    raw = os.environ.get(env_name)
    path = Path(raw).expanduser() if raw else harness_dir / default_rel
    if not path.is_absolute():
        path = harness_dir / path
    return path.resolve()


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON object expected at {path}")
    return data


def _workflow_nodes(workflow_config: Path, selected: set[str] | None = None) -> tuple[str, list[dict[str, Any]]]:
    payload = _load_json(workflow_config)
    workflow_id = str(payload.get("workflow_id") or workflow_config.stem)
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError(f"Workflow config must contain a non-empty nodes array: {workflow_config}")
    nodes: list[dict[str, Any]] = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        node_id = str(raw.get("id") or "").strip()
        if not node_id or (selected and node_id not in selected):
            continue
        spec = NODE_SPEC_BY_ID.get(node_id)
        if not spec:
            raise ValueError(f"No scientific node runtime binding for workflow node {node_id}")
        merged = dict(spec)
        depends_on = [str(item) for item in raw.get("depends_on") or [] if str(item).strip()]
        if selected:
            depends_on = [item for item in depends_on if item in selected]
        merged["depends_on"] = depends_on
        merged["workflow_logical_operator"] = str(raw.get("logical_operator") or spec["logical_operator"])
        merged["workflow_gate"] = str(raw.get("gate") or spec["gate"])
        nodes.append(merged)
    if not nodes:
        raise ValueError("No selected workflow nodes were found in the workflow config")
    return workflow_id, nodes


def _has_external_evidence(args: argparse.Namespace, node_id: str) -> bool:
    if node_id == "literature_discover":
        return bool(args.allow_network_fetch or args.source_runtime_evidence)
    if node_id in {"experiment_run", "experiment_monitor"}:
        return bool(args.experiment_runtime_evidence or args.experiment_approval_ref)
    if node_id == "report_plan":
        return bool(args.review_llm_evidence)
    if node_id == "publication_produce":
        return bool(args.compile_target or args.compile_runtime_evidence or args.compile_approval_ref)
    return True


def _should_block_before_dispatch(args: argparse.Namespace, spec: dict[str, Any], node_results: dict[str, Any]) -> str:
    node_id = spec["node_id"]
    missing_dependencies = [
        dep for dep in spec.get("depends_on", []) if dep and dep not in node_results
    ]
    if missing_dependencies:
        return f"Waiting for dependency node results: {', '.join(missing_dependencies)}"
    if args.require_external_evidence and node_id in SIDE_EFFECT_OR_PROVIDER_NODES and not _has_external_evidence(args, node_id):
        return "Waiting for supplied provider/runtime evidence or explicit approval."
    return ""


def _blocked_node(job_id: str, spec: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "node_id": spec["node_id"],
        "logical_operator": spec["logical_operator"],
        "operator_id": spec["operator_id"],
        "action": spec["action"],
        "gate": spec["gate"],
        "status": "blocked",
        "reason": reason,
        "required_evidence": ["provider/runtime evidence or upstream node artifact"],
        "unblock_condition": "Resume the workflow after supplying the missing evidence.",
    }


def _artifact_path(node_results: dict[str, Any], node_id: str) -> str:
    result = node_results.get(node_id)
    return str(result.get("artifact_path") or "") if isinstance(result, dict) else ""


def _extra_inputs_for(spec: dict[str, Any], node_results: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    node_id = spec["node_id"]
    inputs: dict[str, Any] = {
        "workflow_id": args.workflow_id,
        "workflow_runner": "generic_workflow_runner",
    }
    paper_path = _artifact_path(node_results, "paper_ingest")
    claims_path = _artifact_path(node_results, "claim_extract")
    method_path = _artifact_path(node_results, "method_extract")
    code_path = _artifact_path(node_results, "code_evidence_map")
    idea_path = _artifact_path(node_results, "idea_generate")
    idea_eval_path = _artifact_path(node_results, "idea_evaluate")
    experiment_plan_path = _artifact_path(node_results, "experiment_design")
    experiment_result_path = _artifact_path(node_results, "experiment_run")
    claim_verdict_path = _artifact_path(node_results, "claim_verify")
    report_path = _artifact_path(node_results, "report_draft")
    report_plan_path = _artifact_path(node_results, "report_plan")

    if node_id == "literature_discover":
        inputs.update({
            "query": args.discovery_query or "scientific workflow run",
            "topic": args.discovery_query or "scientific workflow run",
            "limit": int(args.discovery_limit),
            "allow_network_fetch": bool(args.allow_network_fetch),
            "fixture_fallback": False,
            "require_online_source_evidence": bool(args.require_online_source_evidence),
            "min_online_source_channels": int(args.min_online_source_channels),
        })
        if args.source_runtime_evidence:
            inputs["runtime_evidence"] = list(args.source_runtime_evidence)
        if args.source_approval_ref:
            inputs["approval_ref"] = args.source_approval_ref
    if node_id in {"paper_analyze", "memory_update_initial", "graph_update", "claim_extract", "method_extract"} and paper_path:
        inputs["paper_evidence"] = paper_path
        inputs["source_evidence"] = paper_path
    if node_id in {"code_evidence_map", "idea_generate", "idea_evaluate"}:
        if paper_path:
            inputs["paper_evidence"] = paper_path
        if claims_path:
            inputs["claims_evidence"] = claims_path
        if method_path:
            inputs["method_evidence"] = method_path
    if node_id == "code_evidence_map" and args.repo_path:
        inputs["repo_path"] = args.repo_path
    if node_id == "idea_evaluate" and idea_path:
        inputs["ideas_evidence"] = idea_path
    if node_id == "experiment_design" and idea_eval_path:
        inputs["idea_evaluation_evidence"] = idea_eval_path
    if node_id in {"experiment_run", "experiment_monitor"}:
        inputs["execution_mode"] = "human_approved"
        if experiment_plan_path:
            inputs["experiment_plan_evidence"] = experiment_plan_path
        if experiment_result_path:
            inputs["experiment_result_evidence"] = experiment_result_path
        if args.experiment_approval_ref:
            inputs["approval_ref"] = args.experiment_approval_ref
        if args.experiment_runtime_evidence:
            inputs["runtime_evidence"] = list(args.experiment_runtime_evidence)
    if node_id in {"claim_verify", "report_plan", "report_draft"}:
        if claims_path:
            inputs["claims_evidence"] = claims_path
        if code_path:
            inputs["code_evidence"] = code_path
        if method_path:
            inputs["method_evidence"] = method_path
        if experiment_result_path:
            inputs["experiment_result"] = experiment_result_path
        if claim_verdict_path:
            inputs["claim_verdict_evidence"] = claim_verdict_path
        if idea_eval_path:
            inputs["idea_evaluation_evidence"] = idea_eval_path
        if paper_path:
            inputs["paper_evidence"] = paper_path
        if args.review_llm_evidence:
            inputs["review_llm_evidence"] = list(args.review_llm_evidence)
            inputs["artifact_review_evidence"] = list(args.review_llm_evidence)
    if node_id == "claim_verify":
        inputs["claim_id"] = "claim-001"
    if node_id == "report_plan":
        inputs.update({
            "claim_id": "claim-001",
            "experiment_id": "exp-001",
            "report_id": f"report-{args.job_id}",
            "report_title": args.report_title or "Scientific Workflow Report Plan",
        })
    if node_id == "report_draft":
        inputs.update({
            "claim_id": "claim-001",
            "experiment_id": "exp-001",
            "report_id": f"report-{args.job_id}",
            "report_title": args.report_title or "Scientific Workflow Report",
            "paper_draft": True,
        })
        if report_plan_path:
            inputs["report_plan_evidence"] = report_plan_path
    if node_id == "artifact_review" and report_path:
        inputs["target"] = report_path
        inputs["artifact_path"] = report_path
    if node_id == "publication_produce":
        inputs["checklist"] = True
        inputs["title"] = args.report_title or "Scientific Workflow Publication"
        if args.compile_target:
            inputs["target"] = args.compile_target
            inputs["paper_path"] = args.compile_target
        if args.compile_runtime_evidence:
            inputs["runtime_evidence"] = list(args.compile_runtime_evidence)
        if args.compile_approval_ref:
            inputs["approval_ref"] = args.compile_approval_ref
    if node_id == "memory_update_final" and report_path:
        inputs["source_evidence"] = report_path
    if node_id == "workflow_evolve":
        inputs["failed_run"] = {
            "workflow_id": args.workflow_id,
            "sprint_id": args.job_id,
            "nodes": [],
            "gate_results": {},
            "ambiguous_manuals_or_prompts": [],
            "insufficient_schemas": [],
            "poor_operator_bindings": [],
            "human_intervention_points": [],
            "runtime_errors": [],
        }
    return inputs


def _contains_fixture_reference(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        return "fixtures/" in normalized or "/fixtures/" in normalized
    if isinstance(value, list):
        return any(_contains_fixture_reference(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_fixture_reference(item) for item in value.values())
    return False


def _dispatch_input_profile(spec: dict[str, Any], node_args: argparse.Namespace) -> dict[str, Any]:
    fixture_markers: list[str] = []
    if _contains_fixture_reference(getattr(node_args, "paper", "")):
        fixture_markers.append("fixture_reference_in_paper")
    if _contains_fixture_reference(getattr(node_args, "extra_inputs", {})):
        fixture_markers.append("fixture_reference_in_inputs")
    return {
        "node_id": spec["node_id"],
        "logical_operator": spec["logical_operator"],
        "operator_id": spec["operator_id"],
        "action": spec["action"],
        "runner_mode": str(getattr(node_args, "runtime_mode", "")),
        "runner_contract": str(getattr(node_args, "runner_contract", "")),
        "smoke_mode": False,
        "fixture_markers": fixture_markers,
        "uses_fixture_or_smoke_input": bool(fixture_markers),
    }


def _node_args(
    args: argparse.Namespace,
    harness_dir: Path,
    workflow_output_dir: Path,
    spec: dict[str, Any],
    node_results: dict[str, Any],
) -> argparse.Namespace:
    node_id = spec["node_id"]
    return argparse.Namespace(
        harness_dir=str(harness_dir),
        operator_id=spec["operator_id"],
        node_id=node_id,
        action=spec["action"],
        logical_operator=spec["logical_operator"],
        expected_schema=None,
        evidence_name=spec["evidence_name"],
        task_id=f"task-{args.job_id}-{node_id}",
        sprint_id=args.job_id,
        paper=args.paper,
        paper_id=f"paper-{args.job_id}",
        input_json=None,
        extra_inputs=_extra_inputs_for(spec, node_results, args),
        output_dir=_rel(workflow_output_dir / node_id, harness_dir),
        out=None,
        timeout_seconds=float(args.timeout_seconds),
        lease_ttl_seconds=int(args.lease_ttl_seconds),
        allow_existing_result=bool(args.allow_existing_result),
        runtime_mode="solar_scientific_workflow",
        runner_contract="generic_workflow_runner",
        objective=f"Run {node_id} from scientific workflow {args.workflow_id}.",
    )


def _gate_lifecycle(summary_path: Path, harness_dir: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(harness_dir)
    proc = subprocess.run(
        [sys.executable, str(REPO_HARNESS_DIR / "evaluators/scientific/lifecycle_runtime_gate.py"), str(summary_path)],
        cwd=str(REPO_HARNESS_DIR),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "status": "failed",
            "reasons": [f"lifecycle_runtime_gate emitted non-json output: {proc.stdout.strip()}"],
            "warnings": [proc.stderr.strip()] if proc.stderr.strip() else [],
        }
    payload["exit_code"] = proc.returncode
    if proc.stderr.strip():
        payload.setdefault("warnings", []).append(proc.stderr.strip())
    return payload


def _runtime_manifest(
    *,
    workflow_id: str,
    job_id: str,
    node_results: dict[str, Any],
    harness_dir: Path,
    out_path: Path,
) -> dict[str, Any]:
    proofs: list[dict[str, Any]] = []
    for node_id, result in sorted(node_results.items()):
        if not isinstance(result, dict):
            continue
        native_skill = CAPABILITY_NATIVE_SKILL_BY_NODE.get(node_id, node_id)
        refs = [
            str(result.get("artifact_path") or ""),
            str(result.get("operator_result_path") or ""),
            str(result.get("bridge_result_path") or ""),
        ]
        proofs.append({
            "proof_id": f"workflow-runtime:{workflow_id}:{job_id}:{node_id}",
            "native_skill": native_skill,
            "categories": ["workflow_node_runtime_evidence"],
            "evidence_refs": [ref for ref in refs if ref],
            "description": "Generic scientific workflow runner dispatched this node through operator_runtime and the AutoSci bridge.",
        })
    manifest = {
        "schema": "scientific_workflow_runtime_manifest.v1",
        "workflow_id": workflow_id,
        "job_id": job_id,
        "generated_by": "harness.tools.run_scientific_workflow",
        "proofs": proofs,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["path"] = _rel(out_path, harness_dir)
    return manifest


def _dispatch_boundary(
    *,
    workflow_id: str,
    workflow_config: Path,
    summary_path: Path,
    required_nodes: list[str],
    dispatch_input_profiles: dict[str, Any],
    blocked_nodes: dict[str, Any],
) -> dict[str, Any]:
    fixture_nodes = [
        node_id
        for node_id, profile in sorted(dispatch_input_profiles.items())
        if isinstance(profile, dict) and profile.get("uses_fixture_or_smoke_input")
    ]
    blocking_reasons: list[str] = []
    if fixture_nodes:
        blocking_reasons.append("node_inputs_include_fixture_or_fixture_fallback")
    if blocked_nodes:
        blocking_reasons.append("workflow_has_blocked_nodes")
    production_ready = not fixture_nodes and not blocked_nodes
    return {
        "schema": "autosci_scheduler_dispatch_boundary.v1",
        "status": "generic_workflow_runner",
        "production_ready": production_ready,
        "runner": _rel(Path(__file__).resolve(), REPO_HARNESS_DIR),
        "runner_contract": "generic_workflow_runner",
        "workflow_id": workflow_id,
        "workflow_config_path": _rel(workflow_config, REPO_HARNESS_DIR),
        "workflow_config_sha256": _sha256(workflow_config),
        "summary_path": _rel(summary_path, Path(os.environ.get("HARNESS_DIR", REPO_HARNESS_DIR)).resolve()),
        "required_nodes": list(required_nodes),
        "profiled_nodes": sorted(dispatch_input_profiles),
        "smoke_nodes": [],
        "fixture_nodes": fixture_nodes,
        "blocking_reasons": blocking_reasons,
        "limitations": [] if production_ready else [
            "Generic workflow dispatch is present, but some nodes still need non-fixture inputs or supplied external runtime evidence."
        ],
    }


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    harness_dir = Path(args.harness_dir).expanduser().resolve()
    workflow_config = _resolve_harness_path(harness_dir, args.workflow_config)
    selected = set(args.node_id or []) or None
    workflow_id, specs = _workflow_nodes(workflow_config, selected)
    args.workflow_id = workflow_id
    args.job_id = args.job_id or f"job-scientific-workflow-{_utc_stamp()}"

    scientific_artifact_root = _artifact_root_from_env(
        harness_dir,
        "SCIENTIFIC_ARTIFACT_ROOT",
        "artifacts/scientific",
    )
    output_dir = _resolve_harness_path(
        harness_dir,
        args.output_dir or scientific_artifact_root / "workflow-runs" / args.job_id,
    )
    summary_path = _resolve_harness_path(
        harness_dir,
        args.out or output_dir / "scientific_workflow_runtime.json",
    )
    runtime_manifest_path = output_dir / "scientific_workflow_runtime_manifest.json"

    node_summaries: dict[str, Any] = {}
    node_results: dict[str, Any] = {}
    gate_results: dict[str, Any] = {}
    blocked_nodes: dict[str, Any] = {}
    dispatch_input_profiles: dict[str, Any] = {}
    checks: list[dict[str, str]] = []
    required_nodes = [spec["node_id"] for spec in specs]
    nodes = [
        {
            "id": spec["node_id"],
            "logical_operator": spec["logical_operator"],
            "operator_id": spec["operator_id"],
            "action": spec["action"],
            "gate": spec["gate"],
            "depends_on": list(spec.get("depends_on") or []),
        }
        for spec in specs
    ]

    for spec in specs:
        node_id = spec["node_id"]
        block_reason = _should_block_before_dispatch(args, spec, node_results)
        if block_reason:
            blocked_nodes[node_id] = _blocked_node(args.job_id, spec, block_reason)
            checks.append({
                "check": f"{node_id}_blocked",
                "status": "ok",
                "detail": block_reason,
            })
            if args.stop_on_blocked:
                break
            continue
        node_args = _node_args(args, harness_dir, output_dir, spec, node_results)
        dispatch_input_profiles[node_id] = _dispatch_input_profile(spec, node_args)
        code, node_summary = node_runtime.run(node_args)
        node_summaries[node_id] = node_summary
        node_ok = code == 0 and node_summary.get("status") == "passed"
        checks.append({
            "check": f"{node_id}_dispatched",
            "status": "ok" if node_ok else "error",
            "detail": str(node_summary.get("status")),
        })
        if not node_ok:
            if args.stop_on_failure:
                break
            continue
        node_result, gate_result = lifecycle_smoke._node_result_from_summary(
            node_summary=node_summary,
            harness_dir=harness_dir,
            job_id=args.job_id,
            gate_name=spec["gate"],
        )
        node_results[node_id] = node_result
        gate_results[node_id] = gate_result

    runtime_manifest = _runtime_manifest(
        workflow_id=workflow_id,
        job_id=args.job_id,
        node_results=node_results,
        harness_dir=harness_dir,
        out_path=runtime_manifest_path,
    )
    checks.append({
        "check": "generic_workflow_runtime_manifest_written",
        "status": "ok" if Path(runtime_manifest_path).exists() else "error",
        "detail": _rel(runtime_manifest_path, harness_dir),
    })
    lifecycle_status = "passed"
    if any(item["status"] == "error" for item in checks):
        lifecycle_status = "failed"
    elif blocked_nodes:
        lifecycle_status = "blocked"

    lifecycle = {
        "schema": "scientific_lifecycle.v1",
        "workflow_id": workflow_id,
        "job_id": args.job_id,
        "sprint_id": args.job_id,
        "lifecycle_status": lifecycle_status,
        "execution_owner": "solar.operator_runtime.generic_scientific_workflow_runner",
        "required_nodes": required_nodes,
        "nodes": nodes,
        "node_results": node_results,
        "gate_results": gate_results,
        "blocked_nodes": blocked_nodes,
        "node_summaries": node_summaries,
        "dispatch_input_profiles": dispatch_input_profiles,
        "runtime_manifest_path": runtime_manifest["path"],
        "runtime_manifest": runtime_manifest,
        "checks": checks,
    }
    lifecycle["dispatch_boundary"] = _dispatch_boundary(
        workflow_id=workflow_id,
        workflow_config=workflow_config,
        summary_path=summary_path,
        required_nodes=required_nodes,
        dispatch_input_profiles=dispatch_input_profiles,
        blocked_nodes=blocked_nodes,
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    lifecycle["summary_path"] = _rel(summary_path, harness_dir)
    summary_path.write_text(json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lifecycle_gate = _gate_lifecycle(summary_path, harness_dir)
    lifecycle["lifecycle_gate_result"] = lifecycle_gate
    lifecycle_gate_ok = lifecycle_gate.get("ok") is True or (
        bool(blocked_nodes) and str(lifecycle_gate.get("status") or "") == "inconclusive"
    )
    checks.append({
        "check": "lifecycle_runtime_gate_passed",
        "status": "ok" if lifecycle_gate_ok else "error",
        "detail": str(lifecycle_gate.get("status")),
    })
    if any(item["status"] == "error" for item in checks):
        lifecycle["lifecycle_status"] = "failed"
    elif blocked_nodes:
        lifecycle["lifecycle_status"] = "blocked"
    else:
        lifecycle["lifecycle_status"] = "passed"
    summary_path.write_text(json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if lifecycle["lifecycle_status"] == "passed":
        return 0, lifecycle
    if lifecycle["lifecycle_status"] == "blocked":
        return 3, lifecycle
    return 1, lifecycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness-dir", default=str(Path(os.environ.get("HARNESS_DIR", REPO_HARNESS_DIR))))
    parser.add_argument("--workflow-config", default=str(DEFAULT_WORKFLOW_CONFIG))
    parser.add_argument("--job-id")
    parser.add_argument("--node-id", action="append", help="Optional workflow node id to run; may be repeated.")
    parser.add_argument("--paper", default=DEFAULT_PAPER)
    parser.add_argument("--repo-path", default="")
    parser.add_argument("--output-dir")
    parser.add_argument("--out", help="Optional lifecycle summary JSON path, relative to --harness-dir.")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--lease-ttl-seconds", type=int, default=120)
    parser.add_argument("--allow-existing-result", action="store_true")
    parser.add_argument("--stop-on-blocked", action="store_true", default=True)
    parser.add_argument("--stop-on-failure", action="store_true", default=True)
    parser.add_argument("--require-external-evidence", action="store_true")
    parser.add_argument("--allow-network-fetch", action="store_true")
    parser.add_argument("--require-online-source-evidence", action="store_true")
    parser.add_argument("--min-online-source-channels", type=int, default=1)
    parser.add_argument("--discovery-query")
    parser.add_argument("--discovery-limit", type=int, default=3)
    parser.add_argument("--source-approval-ref", default="")
    parser.add_argument("--source-runtime-evidence", action="append")
    parser.add_argument("--experiment-approval-ref", default="")
    parser.add_argument("--experiment-runtime-evidence", action="append")
    parser.add_argument("--review-llm-evidence", action="append")
    parser.add_argument("--compile-target", default="")
    parser.add_argument("--compile-approval-ref", default="")
    parser.add_argument("--compile-runtime-evidence", action="append")
    parser.add_argument("--report-title", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    code, summary = run(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
