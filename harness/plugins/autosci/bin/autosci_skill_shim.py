#!/usr/bin/env python3
"""Deterministic AutoSci skill compatibility shim for Solar Harness.

This is the bash-facing replacement for native AutoSci slash skills.  It does
not send free-form natural language through the intent compiler; it maps a
skill name to the Phase 19 route/binding config, builds canonical envelopes,
runs bounded Solar AutoSci bridge actions, and writes typed evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from autosci_operator_smoke import (  # noqa: E402
    BINDING_CONFIG,
    CORE_ACTIONS,
    DEFAULT_PAPER,
    ROUTE_CONFIG,
    as_artifact_path,
    build_envelope,
    load_json,
    make_sample_repo,
    run_bridge_action,
    write_json,
)
from autosci_workspace_projector import project_run_to_workspace  # noqa: E402

REPO_HARNESS = Path(__file__).resolve().parents[3]
OUTPUT_HARNESS = Path(
    os.environ.get("SOLAR_AUTOSCI_OUTPUT_HARNESS")
    or os.environ.get("HARNESS_DIR", REPO_HARNESS)
).resolve()
AUTOSCI_ARTIFACT_ROOT = Path(
    os.environ.get("AUTOSCI_ARTIFACT_ROOT", OUTPUT_HARNESS / "artifacts" / "autosci")
).expanduser()
if not AUTOSCI_ARTIFACT_ROOT.is_absolute():
    AUTOSCI_ARTIFACT_ROOT = OUTPUT_HARNESS / AUTOSCI_ARTIFACT_ROOT
AUTOSCI_ARTIFACT_ROOT = AUTOSCI_ARTIFACT_ROOT.resolve()
SCIENTIFIC_ARTIFACT_ROOT = Path(
    os.environ.get("SCIENTIFIC_ARTIFACT_ROOT", OUTPUT_HARNESS / "artifacts" / "scientific")
).expanduser()
if not SCIENTIFIC_ARTIFACT_ROOT.is_absolute():
    SCIENTIFIC_ARTIFACT_ROOT = OUTPUT_HARNESS / SCIENTIFIC_ARTIFACT_ROOT
SCIENTIFIC_ARTIFACT_ROOT = SCIENTIFIC_ARTIFACT_ROOT.resolve()
SCHEMA = "autosci_skill_run.v1"

ACTION_DEPS: dict[str, list[str]] = {
    "ingest_paper": [],
    "analyze_paper": ["ingest_paper"],
    "update_memory": ["ingest_paper"],
    "update_graph": ["ingest_paper"],
    "discover_literature": [],
    "extract_claims": ["ingest_paper"],
    "extract_methods": ["ingest_paper"],
    "map_code_evidence": ["ingest_paper", "extract_claims"],
    "generate_ideas": ["ingest_paper", "update_memory", "extract_claims", "extract_methods"],
    "evaluate_ideas": ["generate_ideas", "extract_claims", "extract_methods", "update_memory"],
    "design_experiment": ["evaluate_ideas"],
    "run_experiment": ["design_experiment"],
    "monitor_experiment": ["run_experiment"],
    "verify_claim": ["extract_claims", "map_code_evidence", "run_experiment"],
    "write_report": ["verify_claim", "run_experiment", "map_code_evidence"],
    "compile_paper": [],
    "evolve_workflow": [],
}

SOURCE_REQUIRED_ACTIONS = {
    "ingest_paper",
    "analyze_paper",
    "update_memory",
    "update_graph",
    "extract_claims",
    "extract_methods",
    "map_code_evidence",
    "generate_ideas",
    "evaluate_ideas",
    "design_experiment",
    "run_experiment",
    "monitor_experiment",
    "verify_claim",
    "write_report",
}
SCHEDULER_DEMO_NODE_IDS = [
    "paper_ingest",
    "paper_analyze",
    "claim_extract",
    "method_extract",
]


def stable_run_id(skill: str, args: argparse.Namespace) -> str:
    seed = json.dumps(
        {
            "skill": skill,
            "paper": str(args.paper or ""),
            "topic": str(args.topic or ""),
            "target": target_ref(args),
            "anchors": list(args.anchor or []),
            "negative_ids": list(args.negative or []),
            "from_wiki": bool(args.from_wiki),
            "venue": str(args.venue or ""),
            "year": str(args.year or ""),
            "limit": str(args.limit or ""),
            "smoke": bool(args.smoke),
            "native_options": native_options(args),
            "skill_args": list(args.skill_args or []),
        },
        sort_keys=True,
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    safe_skill = skill.replace("_", "-").strip("-") or "skill"
    return f"{safe_skill}-{digest}"


def route_maps(route_config: Path, binding_config: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    routes_payload = load_json(route_config)
    bindings_payload = load_json(binding_config)
    routes = {
        str(item.get("native_skill") or ""): item
        for item in routes_payload.get("routes") or []
        if isinstance(item, dict) and item.get("native_skill")
    }
    bindings = {
        str(item.get("native_skill") or ""): item
        for item in bindings_payload.get("bindings") or []
        if isinstance(item, dict) and item.get("native_skill")
    }
    return routes, bindings


def ordered_actions(targets: list[str]) -> list[str]:
    needed: set[str] = set()

    def visit(action: str) -> None:
        if action in needed:
            return
        for dep in ACTION_DEPS.get(action, []):
            visit(dep)
        needed.add(action)

    for target in targets:
        if target in CORE_ACTIONS:
            visit(target)
    return [action for action in CORE_ACTIONS if action in needed]


def selected_actions(skill: str, route: dict[str, Any], binding: dict[str, Any] | None) -> list[str]:
    if skill == "research":
        return list(CORE_ACTIONS)
    steps = [str(step) for step in (binding or {}).get("smoke_steps") or []]
    if steps:
        return ordered_actions(steps)
    backend_action = str(route.get("solar_backend_action") or "")
    if backend_action in CORE_ACTIONS:
        return ordered_actions([backend_action])
    return []


def target_ref(args: argparse.Namespace) -> str:
    if args.target:
        return str(args.target)
    if getattr(args, "add", None):
        return str(args.add)
    positional = [str(item) for item in list(args.skill_args or []) if not str(item).startswith("-")]
    if str(getattr(args, "skill_name", "")).strip().lstrip("/$") == "edit" and len(positional) > 1 and positional[0].lower() in {"delete", "remove", "rm"}:
        return " ".join(positional)
    for item in positional:
        return str(item)
    return ""


def source_paper_ref(skill: str, args: argparse.Namespace) -> str:
    if args.paper:
        return str(args.paper)
    if skill == "ingest":
        return target_ref(args)
    return str(DEFAULT_PAPER) if args.smoke else ""


def normalize_source_path(raw: str) -> str:
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw
    return str(Path(raw).expanduser())


def native_options(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "env": str(args.env or ""),
        "collect": bool(args.collect),
        "full": bool(args.full),
        "review": bool(args.review),
        "discover": bool(args.discover),
        "visualize": bool(args.visualize),
        "render": bool(args.render),
        "serve": bool(args.serve),
        "obsidian": bool(args.obsidian),
        "canvas": bool(args.canvas),
        "no_introduction": bool(args.no_introduction),
        "title": str(args.title or ""),
        "checklist": bool(args.checklist),
        "fix": bool(args.fix),
        "anonymous": bool(args.anonymous),
        "double_blind": bool(args.double_blind),
        "submission_mode": str(args.submission_mode or ""),
        "submission_profile": str(args.submission_profile or ""),
        "pdf_inspection": str(args.pdf_inspection or ""),
        "submission_audit": str(args.submission_audit or ""),
        "page_limit": args.page_limit,
        "page_count": args.page_count,
        "verified_page_count": args.verified_page_count,
        "min_font_size": args.min_font_size,
        "verified_min_font_size": args.verified_min_font_size,
        "quick": bool(args.quick),
        "verbose": bool(args.verbose),
        "write": bool(args.write),
        "crystallize": bool(args.crystallize),
        "add": str(getattr(args, "add", "") or ""),
        "online": bool(args.online),
        "start_from": str(args.start_from or ""),
        "skip_paper": bool(args.skip_paper),
        "collect_ready": bool(args.collect_ready),
        "all": bool(args.all),
        "pipeline": str(args.pipeline or ""),
        "max_rounds": int(args.max_rounds or 0),
        "target_score": float(args.target_score or 0),
        "format": str(args.format or ""),
        "paper_slug": str(args.paper_slug or ""),
        "authors": str(args.authors or ""),
        "no_figures": bool(args.no_figures),
        "no_logos": bool(args.no_logos),
        "auto_figures": bool(args.auto_figures),
        "no_refine": bool(args.no_refine),
        "refine_iterations": int(args.refine_iterations or 0),
        "affiliation_logo": str(args.affiliation_logo or ""),
        "conference_logo": str(args.conference_logo or ""),
        "layout": str(args.layout or ""),
        "reviewer_thread_evidence": list(args.reviewer_thread_evidence or []),
        "stress_test": args.stress_test,
        "scope": str(args.scope or ""),
        "approval_ref": str(args.approval_ref or ""),
        "allowlist_evidence": list(args.allowlist_evidence or []),
        "runtime_evidence": list(args.runtime_evidence or []),
        "remote_check_command": str(args.remote_check_command or ""),
        "remote_run_dir": str(args.remote_run_dir or ""),
        "lifecycle_summary": list(args.lifecycle_summary or []),
        "scheduler_run": bool(args.scheduler_run),
        "scheduler_demo": bool(args.scheduler_demo),
        "scheduler_include_blocked_external": bool(args.scheduler_include_blocked_external),
        "scheduler_include_human_gates": bool(args.scheduler_include_human_gates),
        "scheduler_dispatch_external_evidence": bool(args.scheduler_dispatch_external_evidence),
        "scheduler_legacy_smoke_runner": bool(args.scheduler_legacy_smoke_runner),
        "scheduler_node_id": list(args.scheduler_node_id or []),
        "scheduler_require_workflow_config_alignment": bool(args.scheduler_require_workflow_config_alignment),
        "scheduler_timeout": float(args.scheduler_timeout or 0),
        "idea_approval_ref": str(args.idea_approval_ref or ""),
        "results_approval_ref": str(args.results_approval_ref or ""),
        "experiment_approval_ref": str(args.experiment_approval_ref or ""),
        "experiment_runtime_evidence": list(args.experiment_runtime_evidence or []),
        "experiment_allowlist_evidence": list(args.experiment_allowlist_evidence or []),
        "experiment_before_artifacts": list(args.experiment_before_artifact or []),
        "experiment_after_artifacts": list(args.experiment_after_artifact or []),
        "experiment_execute_approved": bool(args.experiment_execute_approved),
        "experiment_executor_timeout_seconds": int(args.experiment_executor_timeout_seconds or 0),
        "compile_target": str(args.compile_target or ""),
        "compile_approval_ref": str(args.compile_approval_ref or ""),
        "compile_runtime_evidence": list(args.compile_runtime_evidence or []),
        "compile_allowlist_evidence": list(args.compile_allowlist_evidence or []),
        "compile_before_artifacts": list(args.compile_before_artifact or []),
        "compile_after_artifacts": list(args.compile_after_artifact or []),
        "compile_execute_approved": bool(args.compile_execute_approved),
        "compile_executor_timeout_seconds": int(args.compile_executor_timeout_seconds or 0),
        "before_artifacts": list(args.before_artifact or []),
        "after_artifacts": list(args.after_artifact or []),
        "execute_approved": bool(args.execute_approved),
        "review_llm_evidence": list(args.review_llm_evidence or []),
        "review_llm_command": str(args.review_llm_command or ""),
        "review_llm_provider": str(args.review_llm_provider or ""),
        "review_llm_model": str(args.review_llm_model or ""),
        "review_llm_endpoint": str(args.review_llm_endpoint or ""),
        "require_review_llm": bool(args.require_review_llm),
        "model_evidence": list(args.model_evidence or []),
        "model_command": str(args.model_command or ""),
        "experiment_result_evidence": list(args.experiment_result_evidence or []),
        "claims_evidence": list(args.claims_evidence or []),
        "code_evidence": list(args.code_evidence or []),
        "source_evidence": list(args.source_evidence or []),
        "novelty_evidence": list(args.novelty_evidence or []),
        "difficulty": str(args.difficulty or ""),
        "focus": str(args.focus or ""),
        "depth": int(args.depth or 0),
        "types": str(args.types or ""),
        "edge_types": str(args.edge_types or ""),
        "max_ideas": int(args.max_ideas or 0),
        "skip_validation": bool(args.skip_validation),
        "skip_pilot": bool(args.skip_pilot),
        "auto": bool(args.auto),
        "daily_mode": str(args.daily_mode or ""),
        "daily_hours": int(args.daily_hours or 0),
        "daily_categories": list(args.daily_categories or []),
        "daily_max_recommendations": int(args.daily_max_recommendations or 0),
        "daily_max_auto_ingest": int(args.daily_max_auto_ingest or 0),
        "daily_send_email": str(args.daily_send_email or ""),
    }


def prepare_scheduler_harness(harness_dir: Path) -> None:
    """Expose read-only harness resources when HARNESS_DIR is an isolated run root."""
    for name in ("config", "personas", "tools", "plugins", "evaluators", "schemas", "lib", "templates"):
        source = REPO_HARNESS / name
        target = harness_dir / name
        if target.exists() or not source.exists():
            continue
        target.symlink_to(source, target_is_directory=source.is_dir())
    (harness_dir / "run").mkdir(parents=True, exist_ok=True)
    (harness_dir / "artifacts").mkdir(parents=True, exist_ok=True)


def run_research_scheduler_lifecycle(args: argparse.Namespace, *, run_id: str, work_dir: str) -> dict[str, Any]:
    """Run scheduler-dispatched lifecycle proof for explicit `$research` requests."""
    prepare_scheduler_harness(OUTPUT_HARNESS)
    scheduler_rel = Path(work_dir) / "scheduler_lifecycle"
    scheduler_dir = OUTPUT_HARNESS / scheduler_rel
    scheduler_dir.mkdir(parents=True, exist_ok=True)
    summary_rel = scheduler_rel / "scientific_lifecycle_runtime.json"
    stdout_path = scheduler_dir / "scheduler_run_stdout.json"
    stderr_path = scheduler_dir / "scheduler_run_stderr.txt"
    job_id = f"{run_id}-scheduler"
    runner_kind = "bounded_smoke" if args.scheduler_legacy_smoke_runner else "generic_workflow"
    if args.scheduler_legacy_smoke_runner:
        command = [
            sys.executable,
            str(REPO_HARNESS / "tools" / "run_scientific_lifecycle_smoke.py"),
            "--harness-dir",
            str(OUTPUT_HARNESS),
            "--job-id",
            job_id,
            "--timeout-seconds",
            str(float(args.scheduler_timeout or 30.0)),
            "--output-dir",
            str(scheduler_rel),
            "--out",
            str(summary_rel),
        ]
        if args.scheduler_include_blocked_external:
            command.append("--include-blocked-external")
        if args.scheduler_include_human_gates:
            command.append("--include-human-gates")
        if args.scheduler_dispatch_external_evidence:
            command.append("--dispatch-external-evidence")
        if args.scheduler_require_workflow_config_alignment:
            command.append("--require-workflow-config-alignment")
        if args.scheduler_require_production_dispatch:
            command.append("--require-production-dispatch")
        if args.idea_approval_ref:
            command.extend(["--idea-approval-ref", str(args.idea_approval_ref)])
        if args.results_approval_ref:
            command.extend(["--results-approval-ref", str(args.results_approval_ref)])
        if args.experiment_execute_approved:
            command.append("--experiment-execute-approved")
        for path in args.experiment_allowlist_evidence or []:
            command.extend(["--experiment-allowlist-evidence", str(path)])
        for path in args.experiment_before_artifact or []:
            command.extend(["--experiment-before-artifact", str(path)])
        for path in args.experiment_after_artifact or []:
            command.extend(["--experiment-after-artifact", str(path)])
        if args.compile_execute_approved:
            command.append("--compile-execute-approved")
        for path in args.compile_allowlist_evidence or []:
            command.extend(["--compile-allowlist-evidence", str(path)])
        for path in args.compile_before_artifact or []:
            command.extend(["--compile-before-artifact", str(path)])
        for path in args.compile_after_artifact or []:
            command.extend(["--compile-after-artifact", str(path)])
        if args.online:
            command.extend(["--allow-network-fetch", "--require-online-source-evidence", "--disable-fixture-fallback"])
            if args.approval_ref:
                command.extend(["--source-approval-ref", str(args.approval_ref)])
            for path in args.allowlist_evidence or []:
                command.extend(["--source-allowlist-evidence", str(path)])
            for path in args.before_artifact or []:
                command.extend(["--source-before-artifact", str(path)])
            for path in args.after_artifact or []:
                command.extend(["--source-after-artifact", str(path)])
    else:
        scientific_run_dir = SCIENTIFIC_ARTIFACT_ROOT / "workflow-runs" / job_id
        scientific_run_rel = output_rel(scientific_run_dir)
        summary_rel = Path(scientific_run_rel) / "scientific_lifecycle_runtime.json"
        command = [
            sys.executable,
            str(REPO_HARNESS / "tools" / "run_scientific_workflow.py"),
            "--harness-dir",
            str(OUTPUT_HARNESS),
            "--job-id",
            job_id,
            "--timeout-seconds",
            str(float(args.scheduler_timeout or 30.0)),
            "--output-dir",
            str(scheduler_rel),
            "--out",
            str(summary_rel),
        ]
        scheduler_nodes = list(args.scheduler_node_id or [])
        if args.scheduler_demo:
            scheduler_nodes = list(dict.fromkeys([*scheduler_nodes, *SCHEDULER_DEMO_NODE_IDS]))
        scheduler_nodes = scheduler_nodes or ["paper_ingest"]
        for node_id in scheduler_nodes:
            command.extend(["--node-id", str(node_id)])
        if args.scheduler_include_blocked_external:
            command.append("--require-external-evidence")
        if args.paper:
            command.extend(["--paper", str(args.paper)])
        if args.online:
            command.extend(["--allow-network-fetch", "--require-online-source-evidence"])
            if args.approval_ref:
                command.extend(["--source-approval-ref", str(args.approval_ref)])
    if args.experiment_approval_ref:
        command.extend(["--experiment-approval-ref", str(args.experiment_approval_ref)])
    for path in args.experiment_runtime_evidence or []:
        command.extend(["--experiment-runtime-evidence", str(path)])
    if args.experiment_executor_timeout_seconds and args.scheduler_legacy_smoke_runner:
        command.extend(["--experiment-executor-timeout-seconds", str(int(args.experiment_executor_timeout_seconds))])
    if args.review_llm_evidence:
        for path in args.review_llm_evidence:
            command.extend(["--review-llm-evidence", str(path)])
    if args.compile_target:
        command.extend(["--compile-target", str(args.compile_target)])
    if args.compile_approval_ref:
        command.extend(["--compile-approval-ref", str(args.compile_approval_ref)])
    for path in args.compile_runtime_evidence or []:
        command.extend(["--compile-runtime-evidence", str(path)])
    if args.compile_executor_timeout_seconds and args.scheduler_legacy_smoke_runner:
        command.extend(["--compile-executor-timeout-seconds", str(int(args.compile_executor_timeout_seconds))])
    if args.online:
        for path in args.runtime_evidence or []:
            command.extend(["--source-runtime-evidence", str(path)])
    if args.topic:
        command.extend(["--discovery-query", str(args.topic)])
    if args.limit:
        command.extend(["--discovery-limit", str(int(args.limit))])

    env = dict(os.environ)
    env["HARNESS_DIR"] = str(OUTPUT_HARNESS)
    env["SOLAR_AUTOSCI_OUTPUT_HARNESS"] = str(OUTPUT_HARNESS)
    env.setdefault("SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS", str(max(1, int(float(args.scheduler_timeout or 30.0)))))
    proc = subprocess.run(
        command,
        cwd=REPO_HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    summary_path = OUTPUT_HARNESS / summary_rel
    summary_payload: dict[str, Any] = {}
    if summary_path.exists():
        try:
            summary_payload = load_json(summary_path)
        except Exception:
            summary_payload = {}
    if not summary_payload and proc.stdout.strip():
        try:
            loaded = json.loads(proc.stdout)
            if isinstance(loaded, dict):
                summary_payload = loaded
        except json.JSONDecodeError:
            summary_payload = {}

    status = str(summary_payload.get("lifecycle_status") or "").lower()
    result_status = "passed" if proc.returncode == 0 and status == "passed" else "blocked" if proc.returncode == 3 or status == "blocked" else "failed"
    workflow_alignment = (
        summary_payload.get("workflow_config_alignment")
        if isinstance(summary_payload.get("workflow_config_alignment"), dict)
        else {}
    )
    dispatch_boundary = (
        summary_payload.get("dispatch_boundary")
        if isinstance(summary_payload.get("dispatch_boundary"), dict)
        else {}
    )
    if args.scheduler_require_production_dispatch and dispatch_boundary.get("production_ready") is not True:
        result_status = "failed"
    return {
        "schema": "autosci_scheduler_lifecycle_run.v1",
        "status": result_status,
        "runner_kind": runner_kind,
        "exit_code": proc.returncode,
        "job_id": job_id,
        "summary_path": as_artifact_path(summary_path) if summary_path.exists() else "",
        "stdout_path": as_artifact_path(stdout_path),
        "stderr_path": as_artifact_path(stderr_path),
        "command": command,
        "lifecycle_status": status or "N/A",
        "node_count": len(summary_payload.get("node_results") or {}) if isinstance(summary_payload.get("node_results"), dict) else 0,
        "blocked_node_count": len(summary_payload.get("blocked_nodes") or {}) if isinstance(summary_payload.get("blocked_nodes"), dict) else 0,
        "workflow_config_alignment": workflow_alignment,
        "workflow_config_alignment_status": workflow_alignment.get("status", "N/A"),
        "workflow_config_alignment_ok": workflow_alignment.get("ok"),
        "workflow_config_alignment_issues": list(workflow_alignment.get("issues") or []),
        "dispatch_boundary": dispatch_boundary,
        "dispatch_boundary_status": dispatch_boundary.get("status", "N/A"),
        "dispatch_boundary_production_ready": dispatch_boundary.get("production_ready"),
        "dispatch_boundary_blocking_reasons": list(dispatch_boundary.get("blocking_reasons") or []),
    }


def should_run_actions(actions: list[str], args: argparse.Namespace) -> tuple[bool, str]:
    if not any(action in SOURCE_REQUIRED_ACTIONS for action in actions):
        return True, ""
    skill_name = str(getattr(args, "skill_name", "") or "").strip().lstrip("/$")
    if skill_name in {"ideate", "novelty"} and (
        args.topic
        or target_ref(args)
        or args.from_wiki
        or args.wiki_root
        or args.discovery_evidence
        or args.novelty_evidence
        or args.online
    ):
        return True, ""
    if skill_name in {"exp-run", "exp-status"} and (target_ref(args) or args.collect or args.env or args.pipeline):
        return True, ""
    if skill_name == "exp-design" and (
        target_ref(args)
        or args.topic
        or args.from_wiki
        or args.wiki_root
        or args.review_llm_evidence
    ):
        return True, ""
    if skill_name == "exp-eval" and (
        target_ref(args)
        or args.experiment_result_evidence
        or args.runtime_evidence
        or args.review_llm_evidence
        or args.claims_evidence
        or args.code_evidence
    ):
        return True, ""
    if skill_name == "paper-draft" and (target_ref(args) or args.topic or args.title or args.paper):
        return True, ""
    if skill_name == "rebuttal" and (
        target_ref(args)
        or args.topic
        or args.title
        or args.paper
        or args.reviewer_thread_evidence
        or args.review_llm_evidence
        or args.submission_audit
    ):
        return True, ""
    if args.smoke:
        return True, ""
    if args.paper:
        return True, ""
    if skill_name == "ingest" and target_ref(args):
        return True, ""
    return (
        False,
        "No source paper/artifact resolver is available for this native route yet; "
        "fixture bridge actions require explicit --smoke.",
    )


def maybe_customize_envelope(envelope: dict[str, Any], action: str, args: argparse.Namespace) -> dict[str, Any]:
    envelope["mode"] = "smoke" if args.smoke else "solar_native"
    inputs = envelope.setdefault("inputs", {})
    inputs["smoke_mode"] = bool(args.smoke)
    native = native_options(args)
    inputs["native_options"] = native
    if args.approval_ref:
        inputs["approval_ref"] = str(args.approval_ref)
    if args.allowlist_evidence:
        inputs["allowlist_evidence"] = list(args.allowlist_evidence)
    if args.runtime_evidence:
        inputs["runtime_evidence"] = list(args.runtime_evidence)
    if args.lifecycle_summary:
        inputs["lifecycle_summary"] = list(args.lifecycle_summary)
    if args.discovery_evidence:
        inputs["discovery_evidence"] = list(args.discovery_evidence)
    if args.novelty_evidence:
        inputs["novelty_evidence"] = list(args.novelty_evidence)
    if args.review_llm_evidence:
        inputs["review_llm_evidence"] = list(args.review_llm_evidence)
    if args.review_llm_command:
        inputs["review_llm_command"] = str(args.review_llm_command)
    if args.review_llm_provider:
        inputs["review_llm_provider"] = str(args.review_llm_provider)
    if args.review_llm_model:
        inputs["review_llm_model"] = str(args.review_llm_model)
    if args.review_llm_endpoint:
        inputs["review_llm_endpoint"] = str(args.review_llm_endpoint)
    if args.model_evidence:
        inputs["model_evidence"] = list(args.model_evidence)
    if args.model_command:
        inputs["model_command"] = str(args.model_command)
    if args.experiment_result_evidence:
        inputs["experiment_result_evidence"] = list(args.experiment_result_evidence)
    if args.claims_evidence:
        inputs["claims_evidence"] = list(args.claims_evidence)
    if args.code_evidence:
        inputs["code_evidence"] = list(args.code_evidence)
    if args.source_evidence:
        inputs["source_evidence"] = list(args.source_evidence)
    if args.before_artifact:
        inputs["before_artifacts"] = list(args.before_artifact)
    if args.after_artifact:
        inputs["after_artifacts"] = list(args.after_artifact)
    if args.execute_approved:
        inputs["execute_approved_side_effect"] = True
    target = target_ref(args)
    skill_name = str(getattr(args, "skill_name", "") or "").strip().lstrip("/$")
    if action == "discover_literature":
        if args.topic:
            inputs["query"] = str(args.topic)
        if skill_name == "discover":
            inputs["fixture_fallback"] = False
            if args.from_wiki:
                inputs["discover_mode"] = "wiki"
                inputs["from_wiki"] = True
            elif args.anchor:
                inputs["discover_mode"] = "anchors"
            elif args.venue:
                inputs["discover_mode"] = "venue"
            elif args.topic:
                inputs["discover_mode"] = "topic"
            if args.anchor:
                inputs["anchors"] = list(args.anchor)
            if args.negative:
                inputs["negative_ids"] = list(args.negative)
            if args.venue:
                inputs["venue"] = str(args.venue)
            if args.year:
                inputs["year"] = int(args.year)
            if args.limit:
                inputs["limit"] = int(args.limit)
            if args.wiki_root:
                inputs["wiki_root"] = str(args.wiki_root)
            if args.no_citation_expand:
                inputs["no_citation_expand"] = True
    if args.topic and action in {"generate_ideas", "evaluate_ideas", "design_experiment"}:
        inputs["topic"] = str(args.topic)
    if action in {"generate_ideas", "evaluate_ideas"}:
        if not inputs.get("topic") and target:
            inputs["topic"] = target
        if args.from_wiki:
            inputs["from_wiki"] = True
        if args.wiki_root:
            inputs["wiki_root"] = str(args.wiki_root)
        if args.discovery_evidence:
            inputs["discovery_evidence"] = list(args.discovery_evidence)
        if args.novelty_evidence:
            inputs["novelty_evidence"] = list(args.novelty_evidence)
        if args.online:
            inputs["online_novelty"] = True
        elif not args.quick and not args.skip_validation:
            inputs["online_novelty"] = True
        if (
            args.review
            or args.review_llm_evidence
            or args.review_llm_command
            or args.review_llm_provider
            or args.review_llm_endpoint
        ) and not args.skip_validation:
            inputs["review_llm_requested"] = True
        if args.skip_validation:
            inputs["skip_validation"] = True
        if args.review_llm_evidence:
            inputs["review_llm_evidence"] = list(args.review_llm_evidence)
        if args.review_llm_command:
            inputs["review_llm_command"] = str(args.review_llm_command)
        if args.review_llm_provider:
            inputs["review_llm_provider"] = str(args.review_llm_provider)
        if args.review_llm_model:
            inputs["review_llm_model"] = str(args.review_llm_model)
        if args.review_llm_endpoint:
            inputs["review_llm_endpoint"] = str(args.review_llm_endpoint)
        if args.max_ideas:
            inputs["max_ideas"] = int(args.max_ideas)
        if args.skip_validation:
            inputs["skip_validation"] = True
        if args.skip_pilot:
            inputs["skip_pilot"] = True
    if target and action in {
        "design_experiment",
        "run_experiment",
        "monitor_experiment",
        "verify_claim",
        "review_artifact",
        "plan_report",
        "write_survey",
        "draft_rebuttal",
        "build_poster",
        "prefill_foundations",
        "edit_wiki_plan",
        "setup_status",
        "reset_plan",
        "ask_wiki",
        "check_wiki_health",
        "init_sources",
        "daily_arxiv_prepare_finalize",
        "evaluate_pilot_result",
        "run_pilot_experiment",
        "refine_artifact",
        "run_research_lifecycle",
        "visualize_graph",
    }:
        inputs["target"] = target
    if action == "reset_plan":
        if args.scope:
            inputs["reset_scope"] = str(args.scope)
        if args.wiki_root:
            inputs["wiki_root"] = str(args.wiki_root)
    if action == "verify_claim":
        if target:
            inputs["claim_id"] = target
        if args.claims_evidence:
            inputs["claims_evidence"] = list(args.claims_evidence)
        if args.experiment_result_evidence:
            inputs["experiment_result_evidence"] = list(args.experiment_result_evidence)
        if args.code_evidence:
            inputs["code_evidence"] = list(args.code_evidence)
        if args.review_llm_evidence:
            inputs["review_llm_evidence"] = list(args.review_llm_evidence)
        if args.wiki_root:
            inputs["wiki_root"] = str(args.wiki_root)
    if action == "review_artifact":
        if args.paper:
            inputs["artifact_path"] = str(args.paper)
            inputs["paper_path"] = str(args.paper)
        if args.difficulty:
            inputs["difficulty"] = str(args.difficulty)
        if args.focus:
            inputs["focus"] = str(args.focus)
        if args.wiki_root:
            inputs["wiki_root"] = str(args.wiki_root)
        if args.review:
            inputs["review_llm_requested"] = True
        if args.require_review_llm:
            inputs["require_review_llm"] = True
            inputs["review_llm_requested"] = True
        if args.review_llm_evidence:
            inputs["review_llm_evidence"] = list(args.review_llm_evidence)
        if args.review_llm_command:
            inputs["review_llm_command"] = str(args.review_llm_command)
        if args.review_llm_provider:
            inputs["review_llm_provider"] = str(args.review_llm_provider)
        if args.review_llm_model:
            inputs["review_llm_model"] = str(args.review_llm_model)
        if args.review_llm_endpoint:
            inputs["review_llm_endpoint"] = str(args.review_llm_endpoint)
    if action in {"ingest_paper", "analyze_paper"} and args.wiki_root:
        inputs["wiki_root"] = str(args.wiki_root)
    if action in {"design_experiment", "run_experiment", "monitor_experiment"} and not args.smoke and (
        skill_name in {"exp-run", "exp-pilot-run"} or args.env or args.full or args.review
    ):
        inputs["execution_mode"] = "human_approved"
    if action in {"run_experiment", "monitor_experiment"}:
        if args.env:
            inputs["env"] = str(args.env)
        if args.collect:
            inputs["collect"] = True
        if args.collect_ready:
            inputs["collect_ready"] = True
        if args.remote_check_command:
            inputs["remote_check_command"] = str(args.remote_check_command)
        if args.remote_run_dir:
            inputs["remote_run_dir"] = str(args.remote_run_dir)
        if args.pipeline:
            inputs["pipeline"] = str(args.pipeline)
            inputs.setdefault("target", str(args.pipeline))
        if args.full:
            inputs["full"] = True
        if args.review:
            inputs["review"] = True
    if action == "write_report":
        outputs = envelope.setdefault("outputs", {})
        if args.title:
            inputs["report_title"] = str(args.title)
        elif args.topic:
            inputs["report_title"] = f"{args.topic} Evidence-Linked Solar AutoSci Report"
        if target:
            inputs["target"] = target
        if skill_name == "paper-draft":
            inputs["paper_draft"] = True
            if args.venue:
                inputs["venue"] = str(args.venue)
            if args.review:
                inputs["review_llm_requested"] = True
            outputs.setdefault("paper_dir_path", f"{envelope.get('output_dir')}/paper")
            outputs.setdefault("paper_main_tex_path", f"{envelope.get('output_dir')}/paper/main.tex")
            outputs.setdefault("paper_sections_dir_path", f"{envelope.get('output_dir')}/paper/sections")
        outputs.setdefault("shim_summary_path", f"{envelope.get('output_dir')}/autosci_skill_run.json")
    if action == "compile_paper":
        outputs = envelope.setdefault("outputs", {})
        if target:
            inputs["target"] = target
        if args.paper:
            inputs["paper_path"] = str(args.paper)
        if args.checklist:
            inputs["checklist"] = True
        if args.fix:
            inputs["fix"] = True
        if args.title:
            inputs["title"] = str(args.title)
        if args.anonymous:
            inputs["anonymous"] = True
        if args.double_blind:
            inputs["double_blind"] = True
        if args.submission_mode:
            inputs["submission_mode"] = str(args.submission_mode)
        if args.submission_profile:
            inputs["submission_profile"] = str(args.submission_profile)
        if args.pdf_inspection:
            inputs["pdf_inspection"] = str(args.pdf_inspection)
        if args.submission_audit:
            inputs["submission_audit"] = str(args.submission_audit)
        if args.page_limit is not None:
            inputs["page_limit"] = float(args.page_limit)
        if args.page_count is not None:
            inputs["page_count"] = float(args.page_count)
        if args.verified_page_count is not None:
            inputs["verified_page_count"] = float(args.verified_page_count)
        if args.min_font_size is not None:
            inputs["min_font_size"] = float(args.min_font_size)
        if args.verified_min_font_size is not None:
            inputs["verified_min_font_size"] = float(args.verified_min_font_size)
        outputs.setdefault("compile_checklist_path", f"{envelope.get('output_dir')}/paper_compile_checklist.json")
        outputs.setdefault("compile_diagnostics_path", f"{envelope.get('output_dir')}/paper_compile_diagnostics.md")
        outputs.setdefault("publication_submission_boundary_path", f"{envelope.get('output_dir')}/publication_submission_boundary.json")
    if action in {"plan_report", "write_survey", "draft_rebuttal", "build_poster"}:
        outputs = envelope.setdefault("outputs", {})
        if args.title:
            inputs["title"] = str(args.title)
            inputs["report_title"] = str(args.title)
        elif args.topic:
            inputs["title"] = str(args.topic)
        if args.topic:
            inputs["topic"] = str(args.topic)
        if args.paper:
            inputs["paper_path"] = str(args.paper)
        if args.format:
            inputs["format"] = str(args.format)
        if action in {"plan_report", "write_survey"}:
            if args.max_papers:
                inputs["max_papers"] = int(args.max_papers)
            if args.wiki_root:
                inputs["wiki_root"] = str(args.wiki_root)
        if action == "draft_rebuttal":
            if args.paper_slug:
                inputs["paper_slug"] = str(args.paper_slug)
            if args.venue:
                inputs["venue"] = str(args.venue)
            if args.wiki_root:
                inputs["wiki_root"] = str(args.wiki_root)
            if args.reviewer_thread_evidence:
                inputs["reviewer_thread_evidence"] = list(args.reviewer_thread_evidence)
            if args.review_llm_evidence:
                inputs["review_llm_evidence"] = list(args.review_llm_evidence)
            if args.submission_audit:
                inputs["submission_audit"] = str(args.submission_audit)
            if args.submission_profile:
                inputs["submission_profile"] = str(args.submission_profile)
            if args.stress_test is not None:
                inputs["stress_test"] = bool(args.stress_test)
        if action in {"plan_report", "write_survey"}:
            outputs.setdefault("plan_json_path", f"{envelope.get('output_dir')}/{action}_plan.json")
            outputs.setdefault("markdown_path", f"{envelope.get('output_dir')}/{action}.md")
        elif action == "draft_rebuttal":
            outputs.setdefault("markdown_path", f"{envelope.get('output_dir')}/rebuttal.md")
            outputs.setdefault("formal_text_path", f"{envelope.get('output_dir')}/rebuttal.txt")
            outputs.setdefault("map_json_path", f"{envelope.get('output_dir')}/rebuttal_response_map.json")
        elif action == "build_poster":
            if args.venue:
                inputs["venue"] = str(args.venue)
            if args.anonymous:
                inputs["anonymous"] = True
            if args.review:
                inputs["review"] = True
                inputs["review_llm_requested"] = True
            if args.require_review_llm:
                inputs["require_review_llm"] = True
                inputs["review_llm_requested"] = True
            if args.review_llm_evidence:
                inputs["review_llm_evidence"] = list(args.review_llm_evidence)
            if args.review_llm_command:
                inputs["review_llm_command"] = str(args.review_llm_command)
                inputs["review_llm_requested"] = True
            if args.review_llm_provider:
                inputs["review_llm_provider"] = str(args.review_llm_provider)
                inputs["review_llm_requested"] = True
            if args.review_llm_model:
                inputs["review_llm_model"] = str(args.review_llm_model)
            if args.review_llm_endpoint:
                inputs["review_llm_endpoint"] = str(args.review_llm_endpoint)
                inputs["review_llm_requested"] = True
            if args.authors:
                inputs["authors"] = str(args.authors)
            if args.no_figures:
                inputs["no_figures"] = True
            if args.no_logos:
                inputs["no_logos"] = True
            if args.auto_figures:
                inputs["auto_figures"] = True
            if args.no_refine:
                inputs["no_refine"] = True
            if args.refine_iterations is not None:
                inputs["refine_iterations"] = int(args.refine_iterations)
            if args.affiliation_logo:
                inputs["affiliation_logo"] = str(args.affiliation_logo)
            if args.conference_logo:
                inputs["conference_logo"] = str(args.conference_logo)
            if args.layout:
                inputs["layout"] = str(args.layout)
            outputs.setdefault("html_path", f"{envelope.get('output_dir')}/poster.html")
            outputs.setdefault("map_json_path", f"{envelope.get('output_dir')}/poster_validation.json")
            if args.render:
                inputs["render_requested"] = True
    if action in {
        "prefill_foundations",
        "edit_wiki_plan",
        "setup_status",
        "reset_plan",
        "refine_artifact",
        "run_research_lifecycle",
    }:
        outputs = envelope.setdefault("outputs", {})
        if args.title:
            inputs["title"] = str(args.title)
        if args.topic:
            inputs["topic"] = str(args.topic)
        if args.paper:
            inputs["paper_path"] = str(args.paper)
        if action == "prefill_foundations":
            if getattr(args, "add", None):
                inputs["add"] = str(args.add)
                inputs["prefill_mode"] = "add"
                inputs["target"] = str(args.add)
            elif target.startswith("foundation:"):
                inputs["prefill_mode"] = "add"
            elif target:
                inputs["domain"] = target
                inputs["prefill_mode"] = "catalog"
            if args.topic:
                inputs["domain"] = str(args.topic)
            if args.online:
                inputs["online"] = True
        if action == "edit_wiki_plan" and getattr(args, "delete", False):
            inputs["delete"] = True
        if action in {"setup_status", "reset_plan", "refine_artifact", "run_research_lifecycle"}:
            if args.venue:
                inputs["venue"] = str(args.venue)
            if args.year:
                inputs["year"] = str(args.year)
            if args.pipeline:
                inputs["pipeline"] = str(args.pipeline)
                inputs.setdefault("target", str(args.pipeline))
            if args.auto:
                inputs["auto"] = True
            if args.format:
                inputs["format"] = str(args.format)
            if args.start_from:
                inputs["start_from"] = str(args.start_from)
            if args.skip_paper:
                inputs["skip_paper"] = True
            if args.max_rounds:
                inputs["max_rounds"] = int(args.max_rounds)
            if args.target_score:
                inputs["target_score"] = float(args.target_score)
            if action == "refine_artifact":
                if args.difficulty:
                    inputs["difficulty"] = str(args.difficulty)
                if args.focus:
                    inputs["focus"] = str(args.focus)
                if args.review:
                    inputs["review_llm_requested"] = True
                if args.review_llm_evidence:
                    inputs["review_llm_evidence"] = list(args.review_llm_evidence)
                if args.review_llm_command:
                    inputs["review_llm_command"] = str(args.review_llm_command)
                if args.review_llm_provider:
                    inputs["review_llm_provider"] = str(args.review_llm_provider)
                if args.review_llm_model:
                    inputs["review_llm_model"] = str(args.review_llm_model)
                if args.review_llm_endpoint:
                    inputs["review_llm_endpoint"] = str(args.review_llm_endpoint)
            prefix = {
                "setup_status": "setup",
                "reset_plan": "reset",
                "refine_artifact": "refine",
                "run_research_lifecycle": "research_lifecycle",
            }[action]
            outputs.setdefault("recommended_changes_path", f"{envelope.get('output_dir')}/{prefix}_recommended_changes.md")
            outputs.setdefault("patch_candidates_path", f"{envelope.get('output_dir')}/patch_candidates")
            if action == "run_research_lifecycle":
                outputs.setdefault("pipeline_progress_path", "artifacts/autosci/workspace/wiki/outputs/pipeline-progress.md")
                outputs.setdefault("pipeline_report_path", "artifacts/autosci/workspace/wiki/outputs/PIPELINE_REPORT.md")
                outputs.setdefault("pipeline_state_path", "artifacts/autosci/workspace/wiki/outputs/pipeline-state.json")
    if action in {"ask_wiki", "check_wiki_health", "init_sources", "daily_arxiv_prepare_finalize"}:
        outputs = envelope.setdefault("outputs", {})
        positional_query = next((str(item) for item in list(args.skill_args or []) if not str(item).startswith("-")), "")
        if action == "ask_wiki" and args.topic:
            inputs["topic"] = str(args.topic)
            inputs["query"] = str(args.topic)
        elif action == "ask_wiki" and positional_query:
            inputs["query"] = positional_query
        elif args.topic:
            inputs["topic"] = str(args.topic)
            inputs.setdefault("query", str(args.topic))
        elif target:
            inputs.setdefault("query", target)
        if args.wiki_root:
            inputs["wiki_root"] = str(args.wiki_root)
        if args.limit:
            inputs["limit"] = int(args.limit)
        if action == "daily_arxiv_prepare_finalize":
            daily_command = target if target in {"setup", "status", "disable"} else "run"
            inputs["daily_command"] = daily_command
            if args.daily_mode:
                inputs["mode"] = str(args.daily_mode)
            if args.daily_hours:
                inputs["hours"] = int(args.daily_hours)
            if args.daily_categories:
                inputs["categories"] = list(args.daily_categories)
            if args.daily_max_recommendations:
                inputs["max_recommendations"] = int(args.daily_max_recommendations)
                inputs["limit"] = int(args.daily_max_recommendations)
            if args.daily_max_auto_ingest:
                inputs["max_auto_ingest"] = int(args.daily_max_auto_ingest)
            if args.daily_send_email:
                inputs["send_email"] = str(args.daily_send_email)
            if args.review or args.require_review_llm:
                inputs["review_llm_requested"] = True
            if args.require_review_llm:
                inputs["require_review_llm"] = True
            if args.review_llm_evidence:
                inputs["review_llm_evidence"] = list(args.review_llm_evidence)
            if args.review_llm_command:
                inputs["review_llm_command"] = str(args.review_llm_command)
            if args.review_llm_provider:
                inputs["review_llm_provider"] = str(args.review_llm_provider)
            if args.review_llm_model:
                inputs["review_llm_model"] = str(args.review_llm_model)
            if args.review_llm_endpoint:
                inputs["review_llm_endpoint"] = str(args.review_llm_endpoint)
        if action == "ask_wiki":
            if args.target and positional_query and (args.crystallize or args.write):
                inputs["crystallize_target"] = str(args.target)
            if args.format:
                inputs["format"] = str(args.format)
            if args.crystallize or args.write:
                inputs["crystallize"] = True
            outputs.setdefault("answer_markdown_path", f"{envelope.get('output_dir')}/ask_wiki_answer.md")
        elif action == "check_wiki_health":
            outputs.setdefault("recommended_changes_path", f"{envelope.get('output_dir')}/check_recommended_changes.md")
            outputs.setdefault("patch_candidates_path", f"{envelope.get('output_dir')}/patch_candidates")
    if action in {"evaluate_pilot_result", "run_pilot_experiment", "visualize_graph"}:
        if args.topic:
            inputs["topic"] = str(args.topic)
        if args.wiki_root:
            inputs["wiki_root"] = str(args.wiki_root)
        if args.all:
            inputs["all"] = True
        if action == "visualize_graph" and args.serve:
            inputs["serve_requested"] = True
        if action == "visualize_graph":
            if args.obsidian:
                inputs["obsidian"] = True
            if args.canvas:
                inputs["canvas"] = True
            if args.focus:
                inputs["focus"] = str(args.focus)
            if args.depth:
                inputs["depth"] = int(args.depth)
            if args.types:
                inputs["types"] = str(args.types)
            if args.edge_types:
                inputs["edge_types"] = str(args.edge_types)
    return envelope


def count_results(results: list[dict[str, Any]], status: str) -> int:
    return sum(1 for item in results if item.get("status") == status)


def normalize_dollar_argv(argv: list[str]) -> list[str]:
    """Map AutoSci-style `$...` commands onto the deterministic shim parser."""
    if not argv:
        return argv
    args = list(argv)
    if args[0] == "text":
        raw = " ".join(args[1:]).strip()
        if not raw:
            return args
        try:
            args = shlex.split(raw)
        except ValueError as exc:
            raise SystemExit(f"invalid AutoSci $ command text: {exc}") from exc
        if not args:
            return ["skills", "list"]

    first = str(args[0]).strip()
    if first in {"$skills", "$skill-list", "$autosci-skills"}:
        rest = args[1:]
        if rest and rest[0] in {"list", "ls", "routes"}:
            rest = rest[1:]
        return ["skills", "list", *rest]

    if first == "$skill":
        rest = args[1:]
        if not rest or rest[0] in {"list", "ls", "routes", "skills"}:
            if rest and rest[0] in {"list", "ls", "routes", "skills"}:
                rest = rest[1:]
            return ["skills", "list", *rest]
        return ["skill", *rest]

    if first.startswith("$") and len(first) > 1:
        if any(ch in first for ch in (" ", "\t", "\n", "\"", "'")):
            try:
                expanded = shlex.split(first)
            except ValueError as exc:
                raise SystemExit(f"invalid AutoSci $ command text: {exc}") from exc
            if not expanded:
                return args
            first = expanded[0]
            args = expanded + args[1:]
        skill = first[1:].strip()
        if skill in {"skills", "skill-list", "autosci-skills"}:
            rest = args[1:]
            if rest and rest[0] in {"list", "ls", "routes"}:
                rest = rest[1:]
            return ["skills", "list", *rest]
        return ["skill", skill, *args[1:]]

    return args


def build_payload(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    route_config = Path(args.route_config)
    binding_config = Path(args.binding_config)
    routes, bindings = route_maps(route_config, binding_config)
    skill = args.skill_name.strip().lstrip("/$")
    route = routes.get(skill)
    binding = bindings.get(skill)
    run_id = args.run_id or stable_run_id(skill, args)
    if args.work_dir:
        work_dir = args.work_dir.strip("/")
        out_path = OUTPUT_HARNESS / work_dir / "autosci_skill_run.json"
    else:
        run_dir = AUTOSCI_ARTIFACT_ROOT / "runs" / run_id
        work_dir = output_rel(run_dir)
        out_path = run_dir / "autosci_skill_run.json"

    if not route:
        payload = {
            "schema": SCHEMA,
            "task_id": f"autosci-skill-{skill}",
            "sprint_id": run_id,
            "node_id": f"autosci-skill-{skill}",
            "status": "failed",
            "inputs": {
                "skill": skill,
                "skill_args": list(args.skill_args or []),
                "paper_path": str(args.paper or ""),
                "topic": str(args.topic or ""),
                "target": str(args.target or ""),
                "run_id": run_id,
                "work_dir": work_dir,
                "route_config": str(route_config.resolve()),
                "binding_config": str(binding_config.resolve()),
            },
            "outputs": {
                "skill_run": {
                    "selected_skill": skill,
                    "autosci_command": f"/{skill}",
                    "execution_status": "failed",
                    "side_effect_policy": "unavailable",
                    "action_count": 0,
                    "passed_count": 0,
                    "schema_only_count": 0,
                    "failed_count": 0,
                    "actions": [],
                    "route": {},
                }
            },
            "artifacts": [
                {"type": "route_config", "path": str(route_config.resolve())},
                {"type": "binding_config", "path": str(binding_config.resolve())},
            ],
            "provenance": {
                "operator_id": "AutoSciSkillShim",
                "implementation_package": "harness.plugins.autosci",
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
            "limitations": [f"No Solar AutoSci route is configured for skill: {skill}"],
        }
        return payload, out_path

    paper_path = normalize_source_path(source_paper_ref(skill, args))
    sample_repo = make_sample_repo(work_dir)
    envelope_dir = OUTPUT_HARNESS / work_dir / "envelopes"
    actions = selected_actions(skill, route, binding)
    if skill == "ideate" and not args.paper and not args.smoke:
        actions = ["generate_ideas"] if args.skip_validation else ["generate_ideas", "evaluate_ideas"]
    if skill == "novelty" and not args.paper and not args.smoke:
        actions = ["evaluate_ideas"]
    if skill == "review" and not args.smoke:
        actions = ["review_artifact"]
    if skill == "paper-compile" and (args.checklist or args.fix or target_ref(args) or args.paper) and not args.smoke:
        actions = ["compile_paper"]
    if skill == "exp-run" and args.full and not args.smoke:
        actions = ["design_experiment", "run_experiment", "monitor_experiment"]
    elif skill == "exp-run" and args.collect and not args.smoke:
        actions = ["monitor_experiment"]
    if skill == "exp-status" and not args.smoke:
        actions = ["monitor_experiment"]
    if skill == "exp-eval" and not args.smoke:
        actions = ["verify_claim"]
    if skill == "exp-design" and not args.smoke:
        actions = ["design_experiment"]
    if skill == "paper-plan" and not args.smoke:
        actions = ["plan_report"]
    if skill == "paper-draft" and not args.smoke:
        actions = ["write_report"]
    if skill == "survey" and not args.smoke:
        actions = ["write_survey"]
    if skill == "rebuttal" and not args.smoke:
        actions = ["draft_rebuttal"]
    if skill == "poster" and not args.smoke:
        actions = ["build_poster"]
    if skill == "prefill" and not args.smoke:
        actions = ["prefill_foundations"]
    if skill == "edit" and not args.smoke:
        actions = ["edit_wiki_plan"]
    if skill == "setup" and not args.smoke:
        actions = ["setup_status"]
    if skill == "reset" and not args.smoke:
        actions = ["reset_plan"]
    if skill == "ask" and not args.smoke:
        actions = ["ask_wiki"]
    if skill == "check" and not args.smoke:
        actions = ["check_wiki_health"]
    if skill == "init" and not args.smoke:
        actions = ["init_sources"]
    if skill == "daily-arxiv" and not args.smoke:
        actions = ["daily_arxiv_prepare_finalize"]
    if skill == "exp-pilot-eval" and not args.smoke:
        actions = ["evaluate_pilot_result"]
    if skill == "exp-pilot-run" and not args.smoke:
        actions = ["run_pilot_experiment"]
    if skill == "refine" and not args.smoke:
        actions = ["refine_artifact"]
    if skill == "research" and not args.smoke:
        actions = ["run_research_lifecycle"]
    if skill == "visualize" and not args.smoke:
        actions = ["visualize_graph"]
    scheduler_lifecycle: dict[str, Any] = {}
    if skill == "research" and args.scheduler_run and not args.smoke:
        scheduler_lifecycle = run_research_scheduler_lifecycle(args, run_id=run_id, work_dir=work_dir)
        if scheduler_lifecycle.get("summary_path"):
            args.lifecycle_summary = [
                *list(args.lifecycle_summary or []),
                str(scheduler_lifecycle["summary_path"]),
            ]
    can_run_actions, skip_reason = should_run_actions(actions, args)
    action_results: list[dict[str, Any]] = []
    for action in (actions if can_run_actions else []):
        envelope = build_envelope(action, paper_path=paper_path, base_rel=work_dir, sample_repo=sample_repo)
        envelope = maybe_customize_envelope(envelope, action, args)
        envelope_path = envelope_dir / f"{action}.json"
        action_results.append(run_bridge_action(action, envelope, envelope_path))

    failed_count = count_results(action_results, "failed")
    scheduler_failed = bool(scheduler_lifecycle and scheduler_lifecycle.get("status") == "failed")
    failed_total = failed_count + (1 if scheduler_failed else 0)
    operator_status = str((binding or {}).get("operator_status") or route.get("coverage_status") or "partial")
    side_effect_policy = str(route.get("side_effect_policy") or "unavailable")
    if failed_total:
        execution_status = "failed"
    elif operator_status == "gated" or side_effect_policy == "approval_required":
        execution_status = "gated"
    elif operator_status == "partial" or route.get("coverage_status") == "partial":
        execution_status = "partial"
    else:
        execution_status = "completed"
    payload_status = (
        "failed"
        if failed_total
        else ("completed" if execution_status == "completed" else "inconclusive")
    )

    limitations = [
        *[str(item) for item in route.get("limitations") or []],
        *[str(item) for item in (binding or {}).get("limitations") or []],
    ]
    if side_effect_policy == "approval_required":
        limitations.append("Approval-gated external effects were not executed by the shim.")
    if not actions:
        limitations.append("This skill route has no bounded local bridge action; shim emitted route evidence only.")
    if skip_reason:
        limitations.append(skip_reason)
    if not args.smoke:
        limitations.append("Fixture bridge fallback is disabled unless --smoke is passed explicitly.")

    payload = {
        "schema": SCHEMA,
        "task_id": f"autosci-skill-{skill}",
        "sprint_id": run_id,
        "node_id": f"autosci-skill-{skill}",
        "status": payload_status,
        "inputs": {
            "skill": skill,
            "skill_args": list(args.skill_args or []),
            "paper_path": paper_path,
            "topic": str(args.topic or ""),
            "target": target_ref(args),
            "anchors": list(args.anchor or []),
            "negative_ids": list(args.negative or []),
            "from_wiki": bool(args.from_wiki),
            "venue": str(args.venue or ""),
            "year": str(args.year or ""),
            "limit": int(args.limit or 0),
            "discovery_evidence": list(args.discovery_evidence or []),
            "smoke": bool(args.smoke),
            "native_options": native_options(args),
            "run_id": run_id,
            "work_dir": work_dir,
            "route_config": str(route_config.resolve()),
            "binding_config": str(binding_config.resolve()),
        },
        "outputs": {
            "skill_run": {
                "selected_skill": skill,
                "autosci_command": str(route.get("autosci_command") or f"/{skill}"),
                "execution_status": execution_status,
                "side_effect_policy": side_effect_policy,
                "action_count": len(action_results),
                "passed_count": count_results(action_results, "passed"),
                "schema_only_count": count_results(action_results, "schema_only"),
            "failed_count": failed_count,
            "scheduler_failed": scheduler_failed,
            "actions": action_results,
            "scheduler_lifecycle": scheduler_lifecycle,
            "route": {
                    "solar_capability": str(route.get("solar_capability") or ""),
                    "solar_logical_operator": str(route.get("solar_logical_operator") or ""),
                    "solar_backend_action": str(route.get("solar_backend_action") or ""),
                    "coverage_status": str(route.get("coverage_status") or ""),
                    "backend_mode": str(route.get("backend_mode") or ""),
                    "evidence_schema": str(route.get("evidence_schema") or ""),
                    "physical_operator": str((binding or {}).get("physical_operator") or "N/A"),
                },
            }
        },
        "artifacts": [
            {"type": "route_config", "path": str(route_config.resolve())},
            {"type": "binding_config", "path": str(binding_config.resolve())},
            *[
                {"type": "action_evidence", "path": str(result.get("evidence_path"))}
                for result in action_results
                if result.get("evidence_path") and result.get("status") != "failed"
            ],
            *(
                [
                    {"type": "scientific_lifecycle_summary", "path": str(scheduler_lifecycle.get("summary_path"))},
                    {"type": "scheduler_lifecycle_stdout", "path": str(scheduler_lifecycle.get("stdout_path"))},
                    {"type": "scheduler_lifecycle_stderr", "path": str(scheduler_lifecycle.get("stderr_path"))},
                ]
                if scheduler_lifecycle
                else []
            ),
        ],
        "provenance": {
            "operator_id": "AutoSciSkillShim",
            "implementation_package": "harness.plugins.autosci",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        "limitations": limitations or ["No additional route limitations were declared."],
    }
    if scheduler_lifecycle:
        payload["inputs"]["lifecycle_summary"] = list(args.lifecycle_summary or [])
    if scheduler_failed:
        payload["status"] = "failed"
        payload["limitations"].append("Explicit scheduler lifecycle run failed; research bridge output is not treated as a successful lifecycle.")
    if scheduler_lifecycle and scheduler_lifecycle.get("workflow_config_alignment_status") == "drift":
        payload["limitations"].append("Scheduler workflow-config drift was detected; smoke lifecycle evidence must not be treated as full scheduler parity.")
    return payload, out_path


def cmd_list(args: argparse.Namespace) -> int:
    routes, bindings = route_maps(Path(args.route_config), Path(args.binding_config))
    rows = []
    for skill in sorted(routes):
        route = routes[skill]
        binding = bindings.get(skill, {})
        rows.append(
            {
                "skill": skill,
                "autosci_command": route.get("autosci_command"),
                "coverage_status": route.get("coverage_status"),
                "side_effect_policy": route.get("side_effect_policy"),
                "solar_backend_action": route.get("solar_backend_action"),
                "physical_operator": binding.get("physical_operator", "N/A"),
            }
        )
    print(json.dumps({"ok": True, "count": len(rows), "skills": rows}, indent=2, sort_keys=True))
    return 0


def output_rel(path: Path | str) -> str:
    candidate = Path(str(path))
    if not candidate.is_absolute():
        candidate = OUTPUT_HARNESS / candidate
    try:
        return candidate.resolve().relative_to(OUTPUT_HARNESS.resolve()).as_posix()
    except ValueError:
        return str(candidate.resolve())


def write_paper_draft_workspace_projection_proof(
    payload: dict[str, Any],
    out_path: Path,
    workspace_summary: dict[str, Any],
) -> dict[str, str] | None:
    skill_run = payload.get("outputs", {}).get("skill_run", {})
    if not isinstance(skill_run, dict) or skill_run.get("selected_skill") != "paper-draft":
        return None
    updated_paths = [
        str(path)
        for path in workspace_summary.get("updated_paths", [])
        if str(path).strip()
    ]
    wiki_refs = [
        output_rel(path)
        for path in updated_paths
        if "/wiki/outputs/" in str(path) or str(path).endswith("/wiki/index.md")
    ]
    if not wiki_refs:
        return None
    work_dir = str(payload.get("inputs", {}).get("work_dir") or "").strip()
    run_dir = OUTPUT_HARNESS / work_dir
    action_refs = [
        output_rel(action.get("evidence_path"))
        for action in skill_run.get("actions", [])
        if isinstance(action, dict) and str(action.get("evidence_path") or "").strip()
    ]
    refs = [
        output_rel(out_path),
        *action_refs,
        output_rel(run_dir / "scientific_report.json"),
        output_rel(run_dir / "report.md"),
        *wiki_refs,
    ]
    deduped_refs = []
    for ref in refs:
        if not ref:
            continue
        path = Path(ref)
        candidate = path if path.is_absolute() else OUTPUT_HARNESS / path
        if candidate.exists():
            deduped_refs.append(ref)
    deduped_refs = list(dict.fromkeys(deduped_refs))
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stamp = timestamp.replace(":", "").replace("-", "")
    manifest = {
        "schema": "autosci_runtime_proof_manifest.v1",
        "generated_at": timestamp,
        "proofs": [
            {
                "native_skill": "paper-draft",
                "proof_id": f"runtime:paper-draft:workspace-projection:{stamp}",
                "categories": ["wiki_mutation_evidence"],
                "collection_mode": "manual_review",
                "production_ready": True,
                "provenance": {
                    "source": "solar_autosci_workspace_projector",
                    "captured_at": timestamp,
                    "artifact_kind": "paper_draft_workspace_projection",
                    "command": "autosci_skill_shim:project_run_to_workspace",
                },
                "evidence_refs": deduped_refs,
                "description": "Completed paper-draft workspace wiki projection evidence for AutoSci parity.",
            }
        ],
    }
    proof_path = run_dir / "paper_draft_workspace_wiki_mutation_runtime_proof.json"
    write_json(proof_path, manifest)
    return {"type": "wiki_mutation_runtime_proof_manifest_json", "path": output_rel(proof_path)}


def cmd_run_skill(args: argparse.Namespace) -> int:
    payload, out_path = build_payload(args)
    write_json(out_path, payload)
    skill_run = payload["outputs"]["skill_run"]
    workspace_summary: dict[str, Any] | None = None
    if payload["status"] != "failed" and skill_run["action_count"] > 0:
        workspace_summary = project_run_to_workspace(
            out_path,
            output_harness=OUTPUT_HARNESS,
            workspace_rel=output_rel(AUTOSCI_ARTIFACT_ROOT / "workspace"),
        )
        skill_run["workspace"] = workspace_summary
        for path in workspace_summary.get("updated_paths", []):
            payload["artifacts"].append({"type": "human_workspace", "path": str(path)})
        payload["artifacts"].append({"type": "human_workspace_index", "path": str(workspace_summary["index_path"])})
        projection_proof = write_paper_draft_workspace_projection_proof(payload, out_path, workspace_summary)
        if projection_proof is not None:
            payload["artifacts"].append(projection_proof)
            skill_run["workspace"]["runtime_proof_artifact"] = projection_proof
        write_json(out_path, payload)

    summary = {
        "ok": payload["status"] != "failed",
        "schema": SCHEMA,
        "status": payload["status"],
        "evidence_path": as_artifact_path(out_path),
        "skill": skill_run["selected_skill"],
        "autosci_command": skill_run["autosci_command"],
        "execution_status": skill_run["execution_status"],
        "side_effect_policy": skill_run["side_effect_policy"],
        "action_count": skill_run["action_count"],
        "passed_count": skill_run["passed_count"],
        "schema_only_count": skill_run["schema_only_count"],
        "failed_count": skill_run["failed_count"],
        "work_dir": payload["inputs"]["work_dir"],
    }
    scheduler_lifecycle = skill_run.get("scheduler_lifecycle") if isinstance(skill_run.get("scheduler_lifecycle"), dict) else {}
    if scheduler_lifecycle:
        summary["scheduler_lifecycle_status"] = scheduler_lifecycle.get("status")
        summary["scheduler_lifecycle_summary_path"] = scheduler_lifecycle.get("summary_path")
        summary["scheduler_lifecycle_node_count"] = scheduler_lifecycle.get("node_count")
        summary["scheduler_lifecycle_blocked_node_count"] = scheduler_lifecycle.get("blocked_node_count")
        summary["scheduler_workflow_config_alignment_status"] = scheduler_lifecycle.get("workflow_config_alignment_status")
        summary["scheduler_workflow_config_alignment_ok"] = scheduler_lifecycle.get("workflow_config_alignment_ok")
        summary["scheduler_workflow_config_alignment_issues"] = scheduler_lifecycle.get("workflow_config_alignment_issues")
        summary["scheduler_dispatch_boundary_status"] = scheduler_lifecycle.get("dispatch_boundary_status")
        summary["scheduler_dispatch_boundary_production_ready"] = scheduler_lifecycle.get("dispatch_boundary_production_ready")
        summary["scheduler_dispatch_boundary_blocking_reasons"] = scheduler_lifecycle.get("dispatch_boundary_blocking_reasons")
    if workspace_summary:
        summary["workspace_path"] = workspace_summary["workspace_root"]
        summary["wiki_path"] = workspace_summary["wiki_root"]
        summary["workspace_updated_count"] = workspace_summary["updated_count"]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if payload["status"] != "failed" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    skills = subparsers.add_parser("skills", help="List deterministic AutoSci skill routes", allow_abbrev=False)
    skills_sub = skills.add_subparsers(dest="skills_command", required=True)
    skills_list = skills_sub.add_parser("list", help="List configured AutoSci skill routes", allow_abbrev=False)
    skills_list.add_argument("--route-config", default=str(ROUTE_CONFIG))
    skills_list.add_argument("--binding-config", default=str(BINDING_CONFIG))
    skills_list.set_defaults(func=cmd_list)

    skill = subparsers.add_parser("skill", help="Run a deterministic AutoSci skill route", allow_abbrev=False)
    skill.add_argument("skill_name", help="AutoSci skill name, for example ingest, ideate, research")
    skill.add_argument("skill_args", nargs="*", help="Optional positional skill arguments")
    skill.add_argument("--paper", help="Paper/source path. Markdown/text is supported by the current bridge.")
    skill.add_argument("--topic", help="Research topic or discovery query hint")
    skill.add_argument("--anchor", action="append", help="Discover from one or more anchor paper IDs")
    skill.add_argument("--negative", action="append", help="Paper ID to push recommendations away from")
    skill.add_argument("--discover", action="store_true", help="Native ingest/init discovery follow-up hint")
    skill.add_argument("--visualize", action="store_true", help="Native ingest/init visualization follow-up hint")
    skill.add_argument("--render", action="store_true", help="Native poster render/export request; execution remains approval-gated")
    skill.add_argument("--serve", action="store_true", help="Native visualize web serving request; execution remains approval-gated")
    skill.add_argument("--obsidian", action="store_true", help="Native visualize Obsidian graph config mode")
    skill.add_argument("--canvas", action="store_true", help="Native visualize Canvas generation mode")
    skill.add_argument("--from-wiki", action="store_true", help="Derive discovery anchors from current wiki papers")
    skill.add_argument("--venue", help="Venue slug for venue/year discovery")
    skill.add_argument("--year", type=int, help="Venue year for venue discovery")
    skill.add_argument("--limit", type=int, help="Maximum discovery shortlist size")
    skill.add_argument("--wiki-root", help="Wiki root for discovery dedup and from-wiki mode")
    skill.add_argument("--discovery-evidence", action="append", help="Existing literature_discovery.v1 evidence for ideation")
    skill.add_argument("--novelty-evidence", action="append", help="Existing Web/Semantic Scholar/DeepXiv novelty evidence JSON")
    skill.add_argument("--no-citation-expand", action="store_true", help="Skip citation/reference expansion for anchor discovery")
    skill.add_argument("--target", help="Idea, experiment, artifact, or route target")
    skill.add_argument("--smoke", action="store_true", help="Run bounded fixture bridge actions explicitly")
    skill.add_argument("--env", choices=["local", "remote"], help="Native experiment environment hint")
    skill.add_argument("--collect", action="store_true", help="Native experiment collect mode")
    skill.add_argument("--check", dest="collect", action="store_true", help="Alias for --collect")
    skill.add_argument("--collect-ready", action="store_true", help="Native experiment pipeline collect-ready hint")
    skill.add_argument("--pipeline", help="Native research pipeline slug or status target")
    skill.add_argument("--full", action="store_true", help="Native full experiment run mode")
    skill.add_argument("--review", action="store_true", help="Request native Review LLM review where supported")
    skill.add_argument("--require-review-llm", action="store_true", help="Require Review LLM evidence for final review acceptance")
    skill.add_argument("--review-llm-evidence", action="append", help="Existing Review LLM evidence JSON for /review")
    skill.add_argument("--review-llm-command", help="Command bridge that returns artifact_review.v1 Review LLM JSON on stdout")
    skill.add_argument("--review-llm-provider", choices=["openai", "openrouter", "openai_compatible"], help="OpenAI-compatible Review LLM provider")
    skill.add_argument("--review-llm-model", help="Review LLM model name, defaulting to gpt-5.5 when provider mode is used")
    skill.add_argument("--review-llm-endpoint", help="OpenAI-compatible chat completions endpoint for Review LLM provider mode")
    skill.add_argument("--model-evidence", action="append", help="Existing autosci_model_response.v1 JSON for ask/check synthesis")
    skill.add_argument("--model-command", help="Command bridge that returns autosci_model_response.v1 JSON on stdout")
    skill.add_argument("--experiment-result-evidence", action="append", help="Existing experiment_result.v1 JSON for exp-eval/status/collect")
    skill.add_argument("--claims-evidence", action="append", help="Existing research_claims.v1 JSON for exp-eval claim text")
    skill.add_argument("--code-evidence", action="append", help="Existing code_evidence_map.v1 JSON for exp-eval static/code support")
    skill.add_argument("--source-evidence", action="append", help="Existing source/Wikipedia evidence JSON for source-backed route rendering")
    skill.add_argument("--title", help="Native report/paper working title")
    skill.add_argument("--no-introduction", action="store_true", help="Native init mode without introduction source generation")
    skill.add_argument("--checklist", action="store_true", help="Native paper compile checklist mode")
    skill.add_argument("--fix", action="store_true", help="Native paper compile auto-fix mode")
    skill.add_argument("--anonymous", action="store_true", help="Paper compile evidence: anonymous submission mode requested")
    skill.add_argument("--double-blind", action="store_true", help="Paper compile evidence: double-blind submission mode requested")
    skill.add_argument("--submission-mode", help="Paper compile evidence: submission mode, for example anonymous or double_blind")
    skill.add_argument("--submission-profile", help="Paper compile evidence: JSON venue submission profile with source-backed requirements")
    skill.add_argument("--pdf-inspection", help="Paper compile evidence: JSON PDF inspection with verified page/font measurements")
    skill.add_argument("--submission-audit", help="Paper compile evidence: JSON publication submission audit/checklist evidence")
    skill.add_argument("--page-limit", type=float, help="Paper compile evidence: venue page limit")
    skill.add_argument("--page-count", type=float, help="Paper compile evidence: observed page count")
    skill.add_argument("--verified-page-count", type=float, help="Paper compile evidence: verified PDF page count")
    skill.add_argument("--min-font-size", type=float, help="Paper compile evidence: required minimum font size")
    skill.add_argument("--verified-min-font-size", type=float, help="Paper compile evidence: verified minimum PDF font size")
    skill.add_argument("--quick", action="store_true", help="Native quick novelty/review mode")
    skill.add_argument("--online", action="store_true", help="Attempt live online evidence fetching for supported skills")
    skill.add_argument("--approval-ref", help="Human approval reference for gated side-effect execution")
    skill.add_argument("--allowlist-evidence", action="append", help="JSON/text artifact proving approved command/source allowlist")
    skill.add_argument("--runtime-evidence", action="append", help="Runtime log/result artifact from an approved side-effect execution")
    skill.add_argument("--remote-check-command", help="Approved allowlisted command that returns autosci_remote_cli.v1 check status JSON")
    skill.add_argument("--remote-run-dir", help="Remote/local run directory to pass through approved status-check commands")
    skill.add_argument("--lifecycle-summary", action="append", help="Existing scientific_lifecycle.v1 scheduler runtime summary evidence")
    skill.add_argument("--scheduler-run", action="store_true", help="For $research only: explicitly run the scheduler-dispatched scientific lifecycle proof and attach its summary")
    skill.add_argument("--scheduler-demo", action="store_true", help="For $research --scheduler-run only: dispatch the demo-safe multi-node lifecycle preset")
    skill.add_argument("--scheduler-legacy-smoke-runner", action="store_true", help="Use the legacy bounded lifecycle smoke runner instead of the generic workflow runner")
    skill.add_argument("--scheduler-node-id", action="append", help="For the generic workflow runner, dispatch a specific workflow node; may be repeated")
    skill.add_argument("--scheduler-timeout", type=float, default=30.0, help="Timeout in seconds for each scheduler-dispatched lifecycle node")
    skill.add_argument("--scheduler-include-blocked-external", action="store_true", help="Record report/compile external nodes as blocked scheduler state")
    skill.add_argument("--scheduler-include-human-gates", action="store_true", help="Record idea/results human approval gates as scheduler-visible lifecycle state")
    skill.add_argument("--scheduler-dispatch-external-evidence", action="store_true", help="Dispatch report/compile external nodes when Review LLM and compile evidence are supplied")
    skill.add_argument("--scheduler-require-workflow-config-alignment", action="store_true", help="Fail scheduler lifecycle smoke when it diverges from the declared workflow config")
    skill.add_argument("--scheduler-require-production-dispatch", action="store_true", help="Fail scheduler lifecycle smoke when it is not a production-ready non-fixture dispatch")
    skill.add_argument("--idea-approval-ref", help="Durable approval reference for the scheduler idea acceptance gate")
    skill.add_argument("--results-approval-ref", help="Durable approval reference for the scheduler results acceptance gate")
    skill.add_argument("--experiment-approval-ref", help="Durable approval reference for scheduler experiment runtime evidence")
    skill.add_argument("--experiment-runtime-evidence", action="append", help="Approved runtime evidence for scheduler experiment_run/experiment_monitor")
    skill.add_argument("--experiment-allowlist-evidence", action="append", help="Allowlist evidence for scheduler experiment runtime")
    skill.add_argument("--experiment-before-artifact", action="append", help="Before-state artifact for scheduler experiment runtime")
    skill.add_argument("--experiment-after-artifact", action="append", help="After-state artifact for scheduler experiment runtime")
    skill.add_argument("--experiment-execute-approved", action="store_true", help="Execute an approved allowlisted scheduler experiment command")
    skill.add_argument("--experiment-executor-timeout-seconds", type=int, default=120, help="Timeout for an approved scheduler experiment command")
    skill.add_argument("--compile-target", help="LaTeX/PDF target directory for scheduler publication_produce dispatch")
    skill.add_argument("--compile-approval-ref", help="Durable approval reference for scheduler publication compile evidence")
    skill.add_argument("--compile-runtime-evidence", action="append", help="Approved runtime evidence for scheduler publication_produce")
    skill.add_argument("--compile-allowlist-evidence", action="append", help="Allowlist evidence for scheduler publication compile")
    skill.add_argument("--compile-before-artifact", action="append", help="Before-state artifact for scheduler publication compile")
    skill.add_argument("--compile-after-artifact", action="append", help="After-state artifact for scheduler publication compile")
    skill.add_argument("--compile-execute-approved", action="store_true", help="Execute an approved allowlisted scheduler publication compile command")
    skill.add_argument("--compile-executor-timeout-seconds", type=int, default=120, help="Timeout for an approved scheduler publication compile command")
    skill.add_argument("--before-artifact", action="append", help="Before-state artifact for approved mutation/execution")
    skill.add_argument("--after-artifact", action="append", help="After-state artifact for approved mutation/execution")
    skill.add_argument("--execute-approved", action="store_true", help="Execute an implemented side-effect path only when approval and allowlist evidence are present")
    skill.add_argument("--verbose", action="store_true", help="Native verbose output mode")
    skill.add_argument("--write", action="store_true", help="Native write-back mode for supported skills")
    skill.add_argument("--crystallize", action="store_true", help="Native ask mode: approved crystallized wiki output write-back")
    skill.add_argument("--add", help="Native prefill add mode: seed exactly one foundation concept")
    skill.add_argument("--delete", action="store_true", help="Native edit mode: delete an approved raw source target")
    skill.add_argument("--difficulty", choices=["standard", "hard", "adversarial"], help="Native review difficulty")
    skill.add_argument("--focus", help="Native review focus or visualize focus node id")
    skill.add_argument("--depth", type=int, help="Native visualize focused canvas BFS depth")
    skill.add_argument("--types", help="Native visualize comma-separated node/page types")
    skill.add_argument("--edge-types", dest="edge_types", help="Native visualize comma-separated graph edge types")
    skill.add_argument("--max-ideas", type=int, help="Native ideate maximum ideas")
    skill.add_argument("--max-papers", type=int, help="Native survey maximum cited paper count")
    skill.add_argument("--skip-validation", action="store_true", help="Native ideate fast path without deep validation")
    skill.add_argument("--skip-pilot", action="store_true", help="Native ideate fast path without pilot execution")
    skill.add_argument("--auto", action="store_true", help="Native automatic mode for research pipelines")
    skill.add_argument("--start-from", help="Native research pipeline resume stage")
    skill.add_argument("--skip-paper", action="store_true", help="Native research pipeline mode that skips paper generation")
    skill.add_argument("--all", action="store_true", help="Native visualize/check all mode")
    skill.add_argument("--max-rounds", type=int, help="Native refine maximum rounds")
    skill.add_argument("--target-score", type=float, help="Native refine target score")
    skill.add_argument("--format", help="Native output format hint, for example latex or markdown")
    skill.add_argument("--paper-slug", help="Native rebuttal paper slug used to locate paper-plan/wiki context")
    skill.add_argument("--authors", help="Native poster author display override")
    skill.add_argument("--no-figures", action="store_true", help="Native poster text-only mode")
    skill.add_argument("--no-logos", action="store_true", help="Native poster skip logo injection mode")
    skill.add_argument("--auto-figures", action="store_true", help="Native poster automatic figure selection mode")
    skill.add_argument("--no-refine", action="store_true", help="Native poster skip critique/refine mode")
    skill.add_argument("--refine-iterations", type=int, help="Native poster critique/refine iteration cap")
    skill.add_argument("--affiliation-logo", help="Native poster affiliation logo path")
    skill.add_argument("--conference-logo", help="Native poster conference logo path")
    skill.add_argument("--layout", choices=["corners", "stacked"], help="Native poster header layout")
    skill.add_argument("--reviewer-thread-evidence", action="append", help="Native rebuttal reviewer-thread JSON/text evidence path")
    skill.add_argument("--stress-test", dest="stress_test", action="store_true", default=None, help="Enable native rebuttal Review LLM stress-test boundary")
    skill.add_argument("--no-stress-test", dest="stress_test", action="store_false", help="Disable native rebuttal Review LLM stress-test boundary")
    skill.add_argument("--scope", help="Native reset scope: wiki, raw, log, checkpoints, all, or comma-separated values")
    skill.add_argument("--mode", dest="daily_mode", choices=["inform", "auto-ingest"], help="Native daily-arxiv mode")
    skill.add_argument("--hours", dest="daily_hours", type=int, help="Native daily-arxiv lookback window")
    skill.add_argument("--categories", dest="daily_categories", nargs="*", help="Native daily-arxiv arXiv categories")
    skill.add_argument("--max-recommendations", dest="daily_max_recommendations", type=int, help="Native daily-arxiv recommendation cap")
    skill.add_argument("--max-auto-ingest", dest="daily_max_auto_ingest", type=int, help="Native daily-arxiv auto-ingest cap")
    skill.add_argument("--send-email", dest="daily_send_email", choices=["true", "false"], help="Native daily-arxiv SMTP delivery preference")
    skill.add_argument("--run-id", help="Stable run/artifact namespace")
    skill.add_argument("--work-dir", help="Output work dir relative to HARNESS_DIR")
    skill.add_argument("--route-config", default=str(ROUTE_CONFIG))
    skill.add_argument("--binding-config", default=str(BINDING_CONFIG))
    skill.set_defaults(func=cmd_run_skill)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    normalized = normalize_dollar_argv(list(sys.argv[1:] if argv is None else argv))
    args = parser.parse_args(normalized)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
