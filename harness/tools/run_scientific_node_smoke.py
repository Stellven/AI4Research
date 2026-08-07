#!/usr/bin/env python3
"""Run one scientific node through the Solar operator runtime.

This is intentionally narrow: it proves one bounded ScientificPaperIngestor
node dispatches through operator_runtime.submit -> operatord -> AutoSci bridge
-> deterministic gate. It is not a full research lifecycle runner.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_HARNESS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OPERATOR_ID = "autosci-paper-ingest-worker"
DEFAULT_NODE_ID = "paper_ingest"
DEFAULT_LOGICAL_OPERATOR = "ScientificPaperIngestor"
DEFAULT_ACTION = "ingest_paper"
DEFAULT_EXPECTED_SCHEMA = "research_paper.v1"
DEFAULT_PAPER = "tests/plugins/autosci/fixtures/sample_paper.md"
ACTION_BY_OPERATOR = {
    "autosci-literature-discover-worker": "discover_literature",
    "autosci-paper-ingest-worker": "ingest_paper",
    "autosci-paper-analyze-worker": "analyze_paper",
    "autosci-memory-update-worker": "update_memory",
    "autosci-graph-update-worker": "update_graph",
    "autosci-claim-extract-worker": "extract_claims",
    "autosci-method-extract-worker": "extract_methods",
    "autosci-code-evidence-map-worker": "map_code_evidence",
    "autosci-idea-worker": "generate_ideas",
    "autosci-idea-evaluate-worker": "evaluate_ideas",
    "autosci-experiment-design-worker": "design_experiment",
    "autosci-experiment-run-worker": "run_experiment",
    "autosci-experiment-monitor-worker": "monitor_experiment",
    "autosci-claim-verify-worker": "verify_claim",
    "autosci-artifact-review-worker": "review_artifact",
    "autosci-report-plan-worker": "plan_report",
    "autosci-report-worker": "write_report",
    "autosci-publication-compile-worker": "compile_paper",
    "autosci-workflow-evolve-worker": "evolve_workflow",
}
LOGICAL_BY_OPERATOR = {
    "autosci-literature-discover-worker": "ScientificLiteratureDiscoverer",
    "autosci-paper-ingest-worker": "ScientificPaperIngestor",
    "autosci-paper-analyze-worker": "ScientificPaperAnalyzer",
    "autosci-memory-update-worker": "ScientificMemoryUpdater",
    "autosci-graph-update-worker": "ScientificGraphUpdater",
    "autosci-claim-extract-worker": "ScientificClaimExtractor",
    "autosci-method-extract-worker": "ScientificMethodExtractor",
    "autosci-code-evidence-map-worker": "ScientificCodeEvidenceMapper",
    "autosci-idea-worker": "ScientificIdeaGenerator",
    "autosci-idea-evaluate-worker": "ScientificIdeaEvaluator",
    "autosci-experiment-design-worker": "ScientificExperimentDesigner",
    "autosci-experiment-run-worker": "ScientificExperimentRunner",
    "autosci-experiment-monitor-worker": "ScientificExperimentMonitor",
    "autosci-claim-verify-worker": "ScientificClaimVerifier",
    "autosci-artifact-review-worker": "ScientificArtifactReviewer",
    "autosci-report-plan-worker": "ScientificReportPlanner",
    "autosci-report-worker": "ScientificReportDrafter",
    "autosci-publication-compile-worker": "ScientificPublicationProducer",
    "autosci-workflow-evolve-worker": "ScientificWorkflowEvolver",
}
NODE_BY_OPERATOR = {
    "autosci-literature-discover-worker": "literature_discover",
    "autosci-paper-ingest-worker": "paper_ingest",
    "autosci-paper-analyze-worker": "paper_analyze",
    "autosci-memory-update-worker": "memory_update_initial",
    "autosci-graph-update-worker": "graph_update",
    "autosci-claim-extract-worker": "claim_extract",
    "autosci-method-extract-worker": "method_extract",
    "autosci-code-evidence-map-worker": "code_evidence_map",
    "autosci-idea-worker": "idea_generate",
    "autosci-idea-evaluate-worker": "idea_evaluate",
    "autosci-experiment-design-worker": "experiment_design",
    "autosci-experiment-run-worker": "experiment_run",
    "autosci-experiment-monitor-worker": "experiment_monitor",
    "autosci-claim-verify-worker": "claim_verify",
    "autosci-artifact-review-worker": "artifact_review",
    "autosci-report-plan-worker": "report_plan",
    "autosci-report-worker": "report_draft",
    "autosci-publication-compile-worker": "publication_produce",
    "autosci-workflow-evolve-worker": "workflow_evolve",
}
TASK_TYPE_BY_ACTION = {
    "discover_literature": "scientific-literature-discover",
    "ingest_paper": "scientific-paper-ingest",
    "analyze_paper": "scientific-paper-analyze",
    "update_memory": "scientific-memory-update",
    "update_graph": "scientific-graph-update",
    "extract_claims": "scientific-claim-extract",
    "extract_methods": "scientific-method-extract",
    "map_code_evidence": "scientific-code-evidence-map",
    "generate_ideas": "scientific-idea-generate",
    "evaluate_ideas": "scientific-idea-evaluate",
    "design_experiment": "scientific-experiment-design",
    "run_experiment": "scientific-experiment-run",
    "monitor_experiment": "scientific-experiment-monitor",
    "verify_claim": "scientific-claim-verify",
    "review_artifact": "scientific-artifact-review",
    "plan_report": "scientific-report-plan",
    "write_report": "scientific-report-draft",
    "compile_paper": "scientific-publication-produce",
    "evolve_workflow": "scientific-workflow-evolve",
}
EXPECTED_SCHEMA_BY_ACTION = {
    "discover_literature": "literature_discovery.v1",
    "ingest_paper": "research_paper.v1",
    "analyze_paper": "research_paper.v1",
    "update_memory": "research_memory_update.v1",
    "update_graph": "research_graph_update.v1",
    "extract_claims": "research_claims.v1",
    "extract_methods": "research_method.v1",
    "map_code_evidence": "code_evidence_map.v1",
    "generate_ideas": "idea_candidate.v1",
    "evaluate_ideas": "idea_evaluation.v1",
    "design_experiment": "experiment_plan.v1",
    "run_experiment": "experiment_result.v1",
    "monitor_experiment": "experiment_status.v1",
    "verify_claim": "claim_verdict.v1",
    "review_artifact": "artifact_review.v1",
    "plan_report": "scientific_report.v1",
    "write_report": "scientific_report.v1",
    "compile_paper": "publication_bundle.v1",
    "evolve_workflow": "workflow_evolution.v1",
}
EVIDENCE_NAME_BY_ACTION = {
    "discover_literature": "literature_discovery.json",
    "ingest_paper": "research_paper.json",
    "analyze_paper": "research_paper_analysis.json",
    "update_memory": "research_memory_update.json",
    "update_graph": "research_graph_update.json",
    "extract_claims": "research_claims.json",
    "extract_methods": "research_method.json",
    "map_code_evidence": "code_evidence_map.json",
    "generate_ideas": "idea_candidate.json",
    "evaluate_ideas": "idea_evaluation.json",
    "design_experiment": "experiment_plan.json",
    "run_experiment": "experiment_result.json",
    "monitor_experiment": "experiment_status.json",
    "verify_claim": "claim_verdict.json",
    "review_artifact": "artifact_review.json",
    "plan_report": "scientific_report_plan.json",
    "write_report": "scientific_report.json",
    "compile_paper": "publication_bundle.json",
    "evolve_workflow": "workflow_evolution.json",
}
GATE_FILE_BY_SCHEMA = {
    "literature_discovery.v1": "literature_discovery_gate.py",
    "research_paper.v1": "paper_gate.py",
    "research_memory_update.v1": "memory_update_gate.py",
    "research_graph_update.v1": "graph_update_gate.py",
    "research_claims.v1": "claims_gate.py",
    "research_method.v1": "method_gate.py",
    "code_evidence_map.v1": "code_evidence_gate.py",
    "idea_candidate.v1": "idea_gate.py",
    "idea_evaluation.v1": "idea_gate.py",
    "experiment_plan.v1": "experiment_plan_gate.py",
    "experiment_result.v1": "experiment_result_gate.py",
    "experiment_status.v1": "experiment_status_gate.py",
    "claim_verdict.v1": "claim_verdict_gate.py",
    "artifact_review.v1": "artifact_review_gate.py",
    "scientific_report.v1": "report_gate.py",
    "publication_bundle.v1": "publication_gate.py",
    "workflow_evolution.v1": "workflow_evolution_gate.py",
}


def _utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _resolve_harness_path(root: Path, raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else root / path


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON object expected at {path}")
    return data


def _check(checks: list[dict[str, str]], name: str, ok: bool, detail: str = "") -> None:
    checks.append({
        "check": name,
        "status": "ok" if ok else "error",
        "detail": detail,
    })


def _gate_evidence(evidence_path: Path, harness_dir: Path, expected_schema: str) -> dict[str, Any]:
    gate_file = GATE_FILE_BY_SCHEMA.get(expected_schema)
    if not gate_file:
        return {
            "ok": False,
            "status": "failed",
            "reasons": [f"no smoke gate is configured for {expected_schema}"],
        }
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(harness_dir)
    proc = subprocess.run(
        [sys.executable, str(REPO_HARNESS_DIR / "evaluators/scientific" / gate_file), str(evidence_path)],
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
            "reasons": [f"paper_gate emitted non-json output: {proc.stdout.strip()}"],
            "warnings": [proc.stderr.strip()] if proc.stderr.strip() else [],
        }
    payload["exit_code"] = proc.returncode
    if proc.stderr.strip():
        payload.setdefault("warnings", []).append(proc.stderr.strip())
    return payload


def _wait_for_result(result_path: Path, daemon_pid: int | None, timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    daemon_exit: int | None = None
    while time.monotonic() - started < timeout_seconds:
        if result_path.exists():
            return {
                "found": True,
                "wait_seconds": round(time.monotonic() - started, 3),
                "daemon_exit": daemon_exit,
            }
        if daemon_pid and daemon_exit is None:
            try:
                waited_pid, status = os.waitpid(daemon_pid, os.WNOHANG)
            except ChildProcessError:
                daemon_exit = 0
            except OSError:
                daemon_exit = -1
            else:
                if waited_pid:
                    daemon_exit = os.waitstatus_to_exitcode(status)
        if daemon_exit is not None and not result_path.exists():
            break
        time.sleep(0.2)
    return {
        "found": result_path.exists(),
        "wait_seconds": round(time.monotonic() - started, 3),
        "daemon_exit": daemon_exit,
    }


def _import_operator_runtime(harness_dir: Path):
    os.environ["HARNESS_DIR"] = str(harness_dir)
    os.environ.setdefault("SOLAR_OPERATORD_AUTO_KICK", "1")
    os.environ.setdefault("SOLAR_OPERATORD_ONCE_POLL_INTERVAL", "0.1")
    os.environ.setdefault("SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS", "20")
    lib_dir = REPO_HARNESS_DIR / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import operator_runtime  # type: ignore

    return operator_runtime


def _action_for(args: argparse.Namespace) -> str:
    if args.action:
        return str(args.action)
    return ACTION_BY_OPERATOR.get(str(args.operator_id), DEFAULT_ACTION)


def _logical_operator_for(args: argparse.Namespace) -> str:
    if args.logical_operator:
        return str(args.logical_operator)
    return LOGICAL_BY_OPERATOR.get(str(args.operator_id), DEFAULT_LOGICAL_OPERATOR)


def _node_id_for(args: argparse.Namespace) -> str:
    if args.node_id:
        return str(args.node_id)
    return NODE_BY_OPERATOR.get(str(args.operator_id), DEFAULT_NODE_ID)


def _build_envelope(args: argparse.Namespace, harness_dir: Path) -> tuple[dict[str, Any], dict[str, Path], str, str]:
    task_id = args.task_id or f"task-scientific-node-smoke-{_utc_stamp()}"
    sprint_id = args.sprint_id or f"sprint-scientific-node-smoke-{_utc_stamp()}"
    action = _action_for(args)
    logical_operator = _logical_operator_for(args)
    node_id = _node_id_for(args)
    runtime_mode = str(getattr(args, "runtime_mode", "") or "bounded_runtime_smoke")
    runner_contract = str(getattr(args, "runner_contract", "") or "bounded_node_smoke")
    objective = str(
        getattr(args, "objective", "") or f"Scheduler-dispatched bounded smoke for {logical_operator}."
    )
    expected_schema = str(args.expected_schema or EXPECTED_SCHEMA_BY_ACTION.get(action) or DEFAULT_EXPECTED_SCHEMA)
    evidence_name = str(args.evidence_name or EVIDENCE_NAME_BY_ACTION.get(action, f"{action}.evidence.json"))
    output_rel = Path(args.output_dir or "artifacts/scientific/scheduler-node-smoke") / task_id
    paths = {
        "bridge_result": output_rel / f"{action}.result.json",
        "evidence": output_rel / evidence_name,
        "evidence_jsonl": output_rel / "evidence.jsonl",
        "memory_update": output_rel / "research_memory_update.json",
        "graph_update": output_rel / "research_graph_update.json",
    }
    inputs = {
        "paper_path": args.paper,
        "paper_id": args.paper_id,
        "allow_network_fetch": False,
    }
    input_json = getattr(args, "input_json", None)
    extra_inputs = getattr(args, "extra_inputs", None)
    if input_json:
        loaded = json.loads(str(input_json))
        if not isinstance(loaded, dict):
            raise ValueError("--input-json must decode to an object")
        inputs.update(loaded)
    if isinstance(extra_inputs, dict):
        inputs.update(extra_inputs)

    envelope: dict[str, Any] = {
        "task_id": task_id,
        "sprint_id": sprint_id,
        "node_id": node_id,
        "operator_id": args.operator_id,
        "task_type": TASK_TYPE_BY_ACTION.get(action, "scientific-node-smoke"),
        "objective": objective,
        "mode": runtime_mode,
        "runner_contract": runner_contract,
        "output_dir": str(output_rel),
        "inputs": inputs,
        "outputs": {
            "result_path": str(paths["bridge_result"]),
            "evidence_payload_path": str(paths["evidence"]),
            "evidence_jsonl": str(paths["evidence_jsonl"]),
            "memory_update_path": str(paths["memory_update"]),
            "graph_update_path": str(paths["graph_update"]),
        },
        "expected_schema": expected_schema,
        "expected_action": action,
        "logical_operator": logical_operator,
        "lease_ttl_seconds": int(args.lease_ttl_seconds),
    }
    return envelope, {key: _resolve_harness_path(harness_dir, path) for key, path in paths.items()}, action, logical_operator


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    harness_dir = Path(args.harness_dir).expanduser().resolve()
    operator_runtime = _import_operator_runtime(harness_dir)
    envelope, paths, action, logical_operator = _build_envelope(args, harness_dir)
    checks: list[dict[str, str]] = []

    operator_result_path = (
        harness_dir
        / "run/operator-results"
        / envelope["operator_id"]
        / envelope["task_id"]
        / "result.json"
    )
    materialized_envelope_path = operator_result_path.parent / "envelope.json"
    output_log_path = operator_result_path.parent / "output.log"

    if operator_result_path.exists() and not args.allow_existing_result:
        summary = {
            "schema": "scientific_node_runtime_smoke.v1",
            "status": "failed",
            "task_id": envelope["task_id"],
            "operator_id": envelope["operator_id"],
            "reasons": [f"operator result already exists: {operator_result_path}"],
            "checks": [{"check": "fresh_operator_result", "status": "error", "detail": str(operator_result_path)}],
        }
        return 2, summary

    try:
        submission = operator_runtime.submit(envelope)
    except Exception as exc:  # noqa: BLE001 - CLI must emit structured failure.
        summary = {
            "schema": "scientific_node_runtime_smoke.v1",
            "status": "failed",
            "task_id": envelope["task_id"],
            "operator_id": envelope["operator_id"],
            "reasons": [f"{type(exc).__name__}: {exc}"],
            "checks": [{"check": "operator_runtime_submit", "status": "error", "detail": str(exc)}],
        }
        return 2, summary

    wait = _wait_for_result(
        operator_result_path,
        int(submission["daemon_pid"]) if submission.get("daemon_pid") else None,
        float(args.timeout_seconds),
    )
    _check(checks, "operator_runtime_submit", submission.get("status") == "submitted", str(submission))
    _check(checks, "operatord_result_written", bool(wait.get("found")), str(wait))
    _check(checks, "materialized_envelope_written", materialized_envelope_path.exists(), _rel(materialized_envelope_path, harness_dir))

    operator_result: dict[str, Any] = {}
    bridge_result: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    gate_result: dict[str, Any] = {"ok": False, "status": "failed", "reasons": ["gate not run"]}

    if operator_result_path.exists():
        operator_result = _load_json(operator_result_path)
        _check(checks, "operator_result_completed", operator_result.get("status") == "completed", str(operator_result.get("status")))
        _check(checks, "operator_result_exit_zero", operator_result.get("exit_code") == 0, str(operator_result.get("exit_code")))
    else:
        _check(checks, "operator_result_completed", False, "missing result.json")
        _check(checks, "operator_result_exit_zero", False, "missing result.json")

    if paths["bridge_result"].exists():
        bridge_result = _load_json(paths["bridge_result"])
        _check(checks, "bridge_result_completed", bridge_result.get("status") == "completed", str(bridge_result.get("status")))
        _check(checks, f"bridge_action_{action}", bridge_result.get("action") == action, str(bridge_result.get("action")))
    else:
        _check(checks, "bridge_result_completed", False, _rel(paths["bridge_result"], harness_dir))
        _check(checks, f"bridge_action_{action}", False, "missing bridge result")

    if paths["evidence"].exists():
        evidence = _load_json(paths["evidence"])
        _check(checks, f"evidence_schema_{envelope['expected_schema']}", evidence.get("schema") == envelope["expected_schema"], str(evidence.get("schema")))
        _check(checks, "evidence_task_matches_submission", evidence.get("task_id") == envelope["task_id"], str(evidence.get("task_id")))
        _check(checks, "evidence_node_matches_submission", evidence.get("node_id") == envelope["node_id"], str(evidence.get("node_id")))
        gate_result = _gate_evidence(paths["evidence"], harness_dir, str(envelope["expected_schema"]))
        _check(checks, "evidence_gate_passed", bool(gate_result.get("ok")), str(gate_result.get("status")))
    else:
        _check(checks, f"evidence_schema_{envelope['expected_schema']}", False, _rel(paths["evidence"], harness_dir))
        _check(checks, "evidence_task_matches_submission", False, "missing evidence")
        _check(checks, "evidence_node_matches_submission", False, "missing evidence")
        _check(checks, "evidence_gate_passed", False, "missing evidence")

    if output_log_path.exists():
        log_text = output_log_path.read_text(encoding="utf-8", errors="replace")
        _check(checks, "operator_log_contains_bridge_action", f'"action": "{action}"' in log_text, _rel(output_log_path, harness_dir))
    else:
        _check(checks, "operator_log_contains_bridge_action", False, "missing output.log")

    ok = all(item["status"] == "ok" for item in checks)
    summary = {
        "schema": "scientific_node_runtime_smoke.v1",
        "status": "passed" if ok else "failed",
        "task_id": envelope["task_id"],
        "sprint_id": envelope["sprint_id"],
        "node_id": envelope["node_id"],
        "logical_operator": logical_operator,
        "operator_id": envelope["operator_id"],
        "action": action,
        "runtime_mode": envelope["mode"],
        "runner_contract": envelope["runner_contract"],
        "harness_dir": str(harness_dir),
        "submission": submission,
        "operator_result_path": _rel(operator_result_path, harness_dir),
        "bridge_result_path": _rel(paths["bridge_result"], harness_dir),
        "evidence_path": _rel(paths["evidence"], harness_dir),
        "materialized_envelope_path": _rel(materialized_envelope_path, harness_dir),
        "output_log_path": _rel(output_log_path, harness_dir),
        "operator_result": operator_result,
        "bridge_result": {
            key: bridge_result.get(key)
            for key in ("ok", "action", "status", "schema", "result_path", "evidence_path", "evidence_jsonl")
        },
        "gate_result": gate_result,
        "checks": checks,
        "wait": wait,
    }
    if args.out:
        out_path = _resolve_harness_path(harness_dir, args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary["summary_path"] = _rel(out_path, harness_dir)
    return (0 if ok else 1), summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness-dir", default=str(Path(os.environ.get("HARNESS_DIR", REPO_HARNESS_DIR))))
    parser.add_argument("--operator-id", default=DEFAULT_OPERATOR_ID)
    parser.add_argument("--node-id")
    parser.add_argument("--action")
    parser.add_argument("--logical-operator")
    parser.add_argument("--expected-schema")
    parser.add_argument("--evidence-name")
    parser.add_argument("--task-id")
    parser.add_argument("--sprint-id")
    parser.add_argument("--paper", default=DEFAULT_PAPER)
    parser.add_argument("--paper-id", default="paper-scheduler-node-smoke")
    parser.add_argument("--input-json", help="Additional envelope inputs as a JSON object.")
    parser.add_argument("--output-dir")
    parser.add_argument("--out", help="Optional summary JSON path, relative to --harness-dir.")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--lease-ttl-seconds", type=int, default=120)
    parser.add_argument("--allow-existing-result", action="store_true")
    parser.add_argument("--runtime-mode", default="bounded_runtime_smoke")
    parser.add_argument("--runner-contract", default="bounded_node_smoke")
    parser.add_argument("--objective")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    code, summary = run(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
