#!/usr/bin/env python3
"""Run skillgen-backed smoke checks through real AutoSci bridge operators."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_HARNESS = Path(__file__).resolve().parents[3]
OUTPUT_HARNESS = Path(
    os.environ.get("SOLAR_AUTOSCI_OUTPUT_HARNESS")
    or os.environ.get("HARNESS_DIR", REPO_HARNESS)
).resolve()
BRIDGE = REPO_HARNESS / "plugins" / "autosci" / "bin" / "autosci_bridge.py"
ROUTE_CONFIG = REPO_HARNESS / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"
BINDING_CONFIG = REPO_HARNESS / "plugins" / "autosci" / "config" / "feature_operator_bindings.v1.json"
DEFAULT_PAPER = REPO_HARNESS / "plugins" / "autosci" / "tests" / "fixtures" / "skillgen_operator_smoke_paper.md"
SCHEMA = "autosci_operator_smoke.v1"

GATES = {
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

CORE_ACTIONS = [
    "ingest_paper",
    "analyze_paper",
    "update_memory",
    "update_graph",
    "discover_literature",
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
    "evolve_workflow",
]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def resolve_output(raw: str | None, default_rel: str) -> Path:
    path = Path(raw) if raw else Path(default_rel)
    if path.is_absolute():
        return path
    return OUTPUT_HARNESS / path


def as_artifact_path(path: Path) -> str:
    return str(path.resolve())


def rel_to_output(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(OUTPUT_HARNESS))
    except ValueError:
        return str(path.resolve())


def collect_ids(value: Any) -> list[str]:
    ids: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                if key == "evidence_ids" and isinstance(nested, list):
                    ids.extend(str(entry) for entry in nested if str(entry).strip())
                elif key.endswith("_id") and isinstance(nested, str) and nested.strip():
                    ids.append(nested)
                else:
                    walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)
        elif isinstance(item, str) and item.strip():
            ids.append(item)

    walk(value)
    seen: set[str] = set()
    unique: list[str] = []
    for item in ids:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique or ["operator-smoke-evidence"]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_sample_repo(base_rel: str) -> str:
    repo_path = OUTPUT_HARNESS / base_rel / "sample_repo"
    repo_path.mkdir(parents=True, exist_ok=True)
    repo_path.joinpath("bridge_fixture.py").write_text(
        "\n".join(
            [
                "def run_fixture_bridge():",
                "    skillgen_framework = 'SKILLGEN verifies reusable agent skills'",
                "    empirical_net_effect = 'candidate verification checks regressions before deployment'",
                "    return skillgen_framework, empirical_net_effect",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rel_to_output(repo_path)


def base_outputs(base_rel: str, action: str, evidence_name: str) -> dict[str, str]:
    return {
        "result_path": f"{base_rel}/{action}.result.json",
        "evidence_payload_path": f"{base_rel}/{evidence_name}",
        "evidence_jsonl": f"{base_rel}/evidence.jsonl",
    }


def build_envelope(action: str, *, paper_path: str, base_rel: str, sample_repo: str) -> dict[str, Any]:
    common = {
        "task_id": f"task-autosci-skillgen-{action}",
        "sprint_id": "phase19-skillgen-operator-smoke",
        "node_id": f"node-{action.replace('_', '-')}",
        "mode": "fixture",
        "output_dir": base_rel,
    }
    if action == "ingest_paper":
        return {
            **common,
            "inputs": {"paper_path": paper_path},
            "outputs": {
                **base_outputs(base_rel, action, "research_paper.json"),
                "memory_update_path": f"{base_rel}/research_memory_update.json",
                "graph_update_path": f"{base_rel}/research_graph_update.json",
            },
        }
    if action == "analyze_paper":
        return {
            **common,
            "inputs": {"paper_path": paper_path},
            "outputs": base_outputs(base_rel, action, "research_paper.analyzed.json"),
        }
    if action == "update_memory":
        return {
            **common,
            "inputs": {"paper_path": paper_path},
            "outputs": base_outputs(base_rel, action, "research_memory_update.direct.json"),
        }
    if action == "update_graph":
        return {
            **common,
            "inputs": {"paper_path": paper_path},
            "outputs": base_outputs(base_rel, action, "research_graph_update.direct.json"),
        }
    if action == "ask_wiki":
        outputs = base_outputs(base_rel, action, "research_memory_update.ask.json")
        outputs.update({"answer_markdown_path": f"{base_rel}/ask_wiki_answer.md"})
        return {
            **common,
            "inputs": {"query": "What evidence supports SkillGen?"},
            "outputs": outputs,
        }
    if action == "init_sources":
        return {
            **common,
            "inputs": {"topic": "SkillGen verified inference-time agent skill synthesis", "limit": 10},
            "outputs": base_outputs(base_rel, action, "literature_discovery.init.json"),
        }
    if action == "prefill_foundations":
        return {
            **common,
            "inputs": {"target": "SkillGen foundation scaffold"},
            "outputs": base_outputs(base_rel, action, "research_memory_update.prefill.json"),
        }
    if action == "edit_wiki_plan":
        return {
            **common,
            "inputs": {"target": "wiki/ideas/skillgen.md"},
            "outputs": base_outputs(base_rel, action, "research_memory_update.edit_plan.json"),
        }
    if action == "discover_literature":
        return {
            **common,
            "inputs": {"query": "SkillGen verified inference-time agent skill synthesis"},
            "outputs": base_outputs(base_rel, action, "literature_discovery.json"),
        }
    if action == "daily_arxiv_prepare_finalize":
        return {
            **common,
            "inputs": {"query": "SkillGen verified inference-time agent skill synthesis", "limit": 10},
            "outputs": base_outputs(base_rel, action, "literature_discovery.daily_arxiv.json"),
        }
    if action == "extract_claims":
        return {
            **common,
            "inputs": {"paper_path": paper_path},
            "outputs": base_outputs(base_rel, action, "research_claims.json"),
        }
    if action == "extract_methods":
        return {
            **common,
            "inputs": {"paper_path": paper_path, "source_evidence": f"{base_rel}/research_paper.json"},
            "outputs": base_outputs(base_rel, action, "research_method.json"),
        }
    if action == "map_code_evidence":
        return {
            **common,
            "inputs": {
                "claim_id": "claim-001",
                "claims_evidence": f"{base_rel}/research_claims.json",
                "repo_path": sample_repo,
            },
            "outputs": {
                **base_outputs(base_rel, action, "code_evidence_map.json"),
                "handoff_path": f"{base_rel}/code_evidence_handoff.md",
            },
        }
    if action == "generate_ideas":
        return {
            **common,
            "inputs": {
                "paper_evidence": f"{base_rel}/research_paper.json",
                "claims_evidence": f"{base_rel}/research_claims.json",
                "method_evidence": f"{base_rel}/research_method.json",
                "memory_evidence": f"{base_rel}/research_memory_update.json",
            },
            "outputs": base_outputs(base_rel, action, "idea_candidate.json"),
        }
    if action == "evaluate_ideas":
        return {
            **common,
            "inputs": {
                "ideas_evidence": f"{base_rel}/idea_candidate.json",
                "claims_evidence": f"{base_rel}/research_claims.json",
                "method_evidence": f"{base_rel}/research_method.json",
                "memory_evidence": f"{base_rel}/research_memory_update.json",
            },
            "outputs": {
                **base_outputs(base_rel, action, "idea_evaluation.json"),
                "memory_update_path": f"{base_rel}/research_memory_update.ideas.json",
            },
        }
    if action == "design_experiment":
        return {
            **common,
            "inputs": {"claim_id": "claim-001", "idea_id": "idea-001", "execution_mode": "fixture"},
            "outputs": base_outputs(base_rel, action, "experiment_plan.json"),
        }
    if action == "run_experiment":
        return {
            **common,
            "inputs": {
                "experiment_plan_evidence": f"{base_rel}/experiment_plan.json",
                "experiment_result": "plugins/autosci/tests/fixtures/sample_autosci_raw_experiment_result.json",
                "execution_mode": "fixture",
            },
            "outputs": base_outputs(base_rel, action, "experiment_result.json"),
        }
    if action == "run_pilot_experiment":
        return {
            **common,
            "inputs": {"target": "pilot-skillgen-001"},
            "outputs": base_outputs(base_rel, action, "experiment_result.pilot.json"),
        }
    if action == "monitor_experiment":
        return {
            **common,
            "inputs": {
                "experiment_plan_evidence": f"{base_rel}/experiment_plan.json",
                "experiment_result_evidence": f"{base_rel}/experiment_result.json",
                "execution_mode": "fixture",
            },
            "outputs": base_outputs(base_rel, action, "experiment_status.json"),
        }
    if action == "verify_claim":
        return {
            **common,
            "inputs": {
                "claim_id": "claim-001",
                "claims_evidence": f"{base_rel}/research_claims.json",
                "experiment_result_evidence": f"{base_rel}/experiment_result.json",
                "code_evidence": f"{base_rel}/code_evidence_map.json",
            },
            "outputs": base_outputs(base_rel, action, "claim_verdict.json"),
        }
    if action == "evaluate_pilot_result":
        return {
            **common,
            "inputs": {"target": "pilot-claim-001"},
            "outputs": base_outputs(base_rel, action, "claim_verdict.pilot.json"),
        }
    if action == "write_report":
        outputs = base_outputs(base_rel, action, "scientific_report.json")
        outputs.update(
            {
                "report_plan_path": f"{base_rel}/report_plan.json",
                "publication_bundle_path": f"{base_rel}/publication_bundle.json",
                "report_markdown_path": f"{base_rel}/report.md",
                "report_evidence_index_path": f"{base_rel}/report_evidence_index.json",
                "poster_html_path": f"{base_rel}/optional_poster.html",
                "rebuttal_markdown_path": f"{base_rel}/optional_rebuttal.md",
            }
        )
        return {
            **common,
            "inputs": {
                "claim_id": "claim-001",
                "experiment_id": "exp-supported-001",
                "claims_evidence": f"{base_rel}/research_claims.json",
                "claim_verdict_evidence": f"{base_rel}/claim_verdict.json",
                "experiment_result": f"{base_rel}/experiment_result.json",
                "code_evidence": f"{base_rel}/code_evidence_map.json",
                "report_id": "report-skillgen-operator-smoke",
                "report_title": "SkillGen Evidence-Linked Operator Smoke Report",
            },
            "outputs": outputs,
        }
    if action == "plan_report":
        outputs = base_outputs(base_rel, action, "scientific_report.plan.json")
        outputs.update(
            {
                "plan_json_path": f"{base_rel}/paper_plan.json",
                "markdown_path": f"{base_rel}/paper_plan.md",
            }
        )
        return {
            **common,
            "inputs": {
                "target": "idea-001",
                "title": "SkillGen Evidence-Linked Paper Plan",
                "claims_evidence": f"{base_rel}/research_claims.json",
                "method_evidence": f"{base_rel}/research_method.json",
            },
            "outputs": outputs,
        }
    if action == "write_survey":
        outputs = base_outputs(base_rel, action, "scientific_report.survey.json")
        outputs.update(
            {
                "plan_json_path": f"{base_rel}/survey_plan.json",
                "markdown_path": f"{base_rel}/survey.md",
            }
        )
        return {
            **common,
            "inputs": {
                "topic": "SkillGen verified inference-time agent skill synthesis",
                "paper_evidence": f"{base_rel}/research_paper.json",
                "method_evidence": f"{base_rel}/research_method.json",
            },
            "outputs": outputs,
        }
    if action == "draft_rebuttal":
        outputs = base_outputs(base_rel, action, "publication_bundle.rebuttal.json")
        outputs.update(
            {
                "markdown_path": f"{base_rel}/rebuttal.md",
                "map_json_path": f"{base_rel}/rebuttal_response_map.json",
            }
        )
        return {
            **common,
            "inputs": {
                "target": "report-skillgen-operator-smoke",
                "claim_verdict_evidence": f"{base_rel}/claim_verdict.json",
            },
            "outputs": outputs,
        }
    if action == "build_poster":
        outputs = base_outputs(base_rel, action, "publication_bundle.poster.json")
        outputs.update(
            {
                "html_path": f"{base_rel}/poster.html",
                "map_json_path": f"{base_rel}/poster_validation.json",
            }
        )
        return {
            **common,
            "inputs": {
                "target": "report-skillgen-operator-smoke",
                "report_evidence": f"{base_rel}/scientific_report.json",
            },
            "outputs": outputs,
        }
    if action == "compile_paper":
        outputs = base_outputs(base_rel, action, "publication_bundle.compile.json")
        outputs.update(
            {
                "compile_checklist_path": f"{base_rel}/paper_compile_checklist.json",
                "compile_diagnostics_path": f"{base_rel}/paper_compile_diagnostics.md",
            }
        )
        return {
            **common,
            "inputs": {"target": "paper/", "checklist": True},
            "outputs": outputs,
        }
    if action == "evolve_workflow":
        return {
            **common,
            "inputs": {
                "failed_run": {
                    "workflow_id": "skillgen-operator-smoke",
                    "failed_nodes": [
                        {
                            "node_id": "node-review-llm",
                            "logical_operator": "ScientificClaimVerifier",
                            "status": "inconclusive",
                            "gate": "claim_verdict_gate",
                        }
                    ],
                    "gate_rejection_reasons": [
                        {
                            "gate_id": "claim_verdict_gate",
                            "status": "inconclusive",
                            "reasons": ["Review LLM is not available in fixture smoke."],
                        }
                    ],
                    "ambiguous_manuals_or_prompts": [
                        {
                            "id": "manual-review-llm-availability",
                            "description": "The review path must state how to report unavailable Review LLM evidence.",
                        }
                    ],
                    "poor_operator_bindings": [
                        {
                            "id": "daily-arxiv-live",
                            "description": "Live feed, email, and auto-ingest require explicit approval.",
                        }
                    ],
                }
            },
            "outputs": {
                **base_outputs(base_rel, action, "workflow_evolution.json"),
                "recommended_changes_path": f"{base_rel}/recommended_changes.md",
                "patch_candidates_path": f"{base_rel}/patch_candidates",
            },
        }
    if action == "setup_status":
        outputs = base_outputs(base_rel, action, "workflow_evolution.setup.json")
        outputs.update(
            {
                "recommended_changes_path": f"{base_rel}/setup_recommended_changes.md",
                "patch_candidates_path": f"{base_rel}/patch_candidates",
            }
        )
        return {
            **common,
            "inputs": {"target": "autosci setup"},
            "outputs": outputs,
        }
    if action == "reset_plan":
        outputs = base_outputs(base_rel, action, "workflow_evolution.reset.json")
        outputs.update(
            {
                "recommended_changes_path": f"{base_rel}/reset_recommended_changes.md",
                "patch_candidates_path": f"{base_rel}/patch_candidates",
            }
        )
        return {
            **common,
            "inputs": {"target": "autosci reset"},
            "outputs": outputs,
        }
    if action == "refine_artifact":
        outputs = base_outputs(base_rel, action, "workflow_evolution.refine.json")
        outputs.update(
            {
                "recommended_changes_path": f"{base_rel}/refine_recommended_changes.md",
                "patch_candidates_path": f"{base_rel}/patch_candidates",
            }
        )
        return {
            **common,
            "inputs": {"target": "report-skillgen-operator-smoke"},
            "outputs": outputs,
        }
    if action == "run_research_lifecycle":
        outputs = base_outputs(base_rel, action, "workflow_evolution.research.json")
        outputs.update(
            {
                "recommended_changes_path": f"{base_rel}/research_lifecycle_recommended_changes.md",
                "patch_candidates_path": f"{base_rel}/patch_candidates",
            }
        )
        return {
            **common,
            "inputs": {"target": "skillgen research lifecycle"},
            "outputs": outputs,
        }
    if action == "check_wiki_health":
        outputs = base_outputs(base_rel, action, "workflow_evolution.check.json")
        outputs.update(
            {
                "recommended_changes_path": f"{base_rel}/check_recommended_changes.md",
                "patch_candidates_path": f"{base_rel}/patch_candidates",
            }
        )
        return {
            **common,
            "inputs": {"target": "autosci wiki"},
            "outputs": outputs,
        }
    if action == "visualize_graph":
        return {
            **common,
            "inputs": {"target": "autosci graph"},
            "outputs": base_outputs(base_rel, action, "research_graph_update.visualize.json"),
        }
    if action == "review_artifact":
        return {
            **common,
            "inputs": {"paper_path": paper_path, "target": paper_path},
            "outputs": base_outputs(base_rel, action, "artifact_review.json"),
        }
    raise ValueError(f"unsupported smoke action: {action}")


def run_gate(schema: str, evidence_path: Path) -> dict[str, Any]:
    gate_name = GATES.get(schema)
    if not gate_name:
        return {"gate_status": "not_available", "reasons": [], "warnings": ["no deterministic gate registered"]}
    gate_path = REPO_HARNESS / "evaluators" / "scientific" / gate_name
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(OUTPUT_HARNESS)
    env["SOLAR_AUTOSCI_OUTPUT_HARNESS"] = str(OUTPUT_HARNESS)
    proc = subprocess.run(
        [sys.executable, str(gate_path), str(evidence_path)],
        cwd=REPO_HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "gate_status": "failed",
            "reasons": [f"gate output was not JSON: {proc.stdout.strip()} {proc.stderr.strip()}"],
            "warnings": [],
        }
    return {
        "gate_status": str(result.get("status") or "failed"),
        "reasons": [str(item) for item in result.get("reasons") or []],
        "warnings": [str(item) for item in result.get("warnings") or []],
    }


def run_bridge_action(action: str, envelope: dict[str, Any], envelope_path: Path) -> dict[str, Any]:
    if len(str(envelope_path.resolve())) >= 240:
        envelope_path = envelope_path.parent.parent / "_e.json"
    write_json(envelope_path, envelope)
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(OUTPUT_HARNESS)
    env["SOLAR_AUTOSCI_OUTPUT_HARNESS"] = str(OUTPUT_HARNESS)
    proc = subprocess.run(
        [sys.executable, str(BRIDGE), "run", "--action", action, "--envelope", str(envelope_path)],
        cwd=REPO_HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "action": action,
            "status": "failed",
            "schema": "N/A",
            "evidence_path": str(envelope_path),
            "gate_status": "failed",
            "evidence_ids": [f"failed:{action}"],
            "reasons": [proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"],
            "warnings": [],
        }
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "action": action,
            "status": "failed",
            "schema": "N/A",
            "evidence_path": str(envelope_path),
            "gate_status": "failed",
            "evidence_ids": [f"failed:{action}"],
            "reasons": [f"bridge output was not JSON: {proc.stdout[:500]}"],
            "warnings": [],
        }
    schema = str(result.get("schema") or "N/A")
    evidence_raw = str(result.get("evidence_path") or "")
    evidence_path = Path(evidence_raw)
    if not evidence_path.is_absolute():
        evidence_path = OUTPUT_HARNESS / evidence_path
    evidence = load_json(evidence_path)
    gate_result = run_gate(schema, evidence_path)
    gate_status = gate_result["gate_status"]
    if gate_status == "passed":
        status = "passed"
    elif gate_status in {"not_available", "inconclusive"}:
        status = "schema_only"
    else:
        status = "failed"
    action_gate_status = "schema_only" if gate_status == "inconclusive" else gate_status
    return {
        "action": action,
        "status": status,
        "schema": schema,
        "evidence_path": as_artifact_path(evidence_path),
        "result_path": str(result.get("result_path") or ""),
        "evidence_jsonl": str(result.get("evidence_jsonl") or ""),
        "handoff_path": str(result.get("handoff_path") or ""),
        "gate_status": action_gate_status,
        "evidence_ids": collect_ids(evidence),
        "reasons": gate_result["reasons"],
        "warnings": gate_result["warnings"],
    }


def operator_items(
    *,
    routes: list[dict[str, Any]],
    bindings: dict[str, dict[str, Any]],
    core_results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for route in sorted(routes, key=lambda item: str(item.get("native_skill") or "")):
        skill = str(route.get("native_skill") or "")
        binding = bindings.get(skill)
        if not binding:
            items.append(
                {
                    "native_skill": skill,
                    "autosci_feature": str(route.get("autosci_command") or f"/{skill}"),
                    "solar_backend_action": str(route.get("solar_backend_action") or "N/A"),
                    "physical_operator": "N/A",
                    "side_effect_policy": str(route.get("side_effect_policy") or "unavailable"),
                    "execution_status": "unbound",
                    "smoke_steps": [],
                    "evidence_paths": [],
                    "gate_statuses": [],
                    "evidence_ids": [f"unbound:{skill}"],
                    "limitations": ["No physical operator binding was configured."],
                }
            )
            continue
        smoke_steps = [str(step) for step in binding.get("smoke_steps") or []]
        step_results = [core_results.get(step) for step in smoke_steps]
        missing_steps = [step for step, result in zip(smoke_steps, step_results, strict=False) if result is None]
        failed_steps = [
            str(result.get("action") or step)
            for step, result in zip(smoke_steps, step_results, strict=False)
            if isinstance(result, dict) and result.get("status") == "failed"
        ]
        operator_status = str(binding.get("operator_status") or "partial")
        if missing_steps or failed_steps:
            execution_status = "failed"
        elif operator_status == "gated":
            execution_status = "gated"
        elif operator_status == "partial":
            execution_status = "partial"
        else:
            execution_status = "completed"
        evidence_paths = [
            str(result.get("evidence_path"))
            for result in step_results
            if isinstance(result, dict) and result.get("evidence_path")
        ]
        gate_statuses = [
            str(result.get("gate_status"))
            for result in step_results
            if isinstance(result, dict) and result.get("gate_status")
        ]
        evidence_ids = [f"route:{skill}", f"operator:{binding.get('physical_operator')}"]
        for result in step_results:
            if isinstance(result, dict):
                evidence_ids.extend(str(item) for item in result.get("evidence_ids") or [])
        limitations = [
            *[str(item) for item in route.get("limitations") or []],
            *[str(item) for item in binding.get("limitations") or []],
        ]
        if missing_steps:
            limitations.append(f"Missing smoke steps: {', '.join(missing_steps)}")
        if failed_steps:
            limitations.append(f"Failed smoke steps: {', '.join(failed_steps)}")
        items.append(
            {
                "native_skill": skill,
                "autosci_feature": str(route.get("autosci_command") or f"/{skill}"),
                "solar_backend_action": str(route.get("solar_backend_action") or "N/A"),
                "physical_operator": str(binding.get("physical_operator") or "N/A"),
                "side_effect_policy": str(route.get("side_effect_policy") or "unavailable"),
                "execution_status": execution_status,
                "smoke_steps": smoke_steps,
                "evidence_paths": evidence_paths,
                "gate_statuses": gate_statuses,
                "evidence_ids": collect_ids(evidence_ids),
                "limitations": limitations or ["N/A"],
            }
        )
    return items


def count(items: list[dict[str, Any]], status: str) -> int:
    return sum(1 for item in items if item.get("execution_status") == status)


def build_payload(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    paper_path = str(Path(args.paper).expanduser())
    route_config = load_json(Path(args.route_config))
    binding_config = load_json(Path(args.binding_config))
    routes = [item for item in route_config.get("routes") or [] if isinstance(item, dict)]
    bindings = {
        str(item.get("native_skill") or ""): item
        for item in binding_config.get("bindings") or []
        if isinstance(item, dict)
    }
    base_rel = args.work_dir.strip("/") if args.work_dir else "artifacts/autosci/operator-smoke/skillgen"
    sample_repo = make_sample_repo(base_rel)
    envelope_dir = OUTPUT_HARNESS / base_rel / "envelopes"
    core_results: dict[str, dict[str, Any]] = {}
    for action in CORE_ACTIONS:
        envelope = build_envelope(action, paper_path=paper_path, base_rel=base_rel, sample_repo=sample_repo)
        envelope_path = envelope_dir / f"{action}.json"
        core_results[action] = run_bridge_action(action, envelope, envelope_path)
    items = operator_items(routes=routes, bindings=bindings, core_results=core_results)
    failed_count = count(items, "failed")
    unbound_count = count(items, "unbound")
    payload = {
        "schema": SCHEMA,
        "task_id": "phase19-autosci-skillgen-operator-smoke",
        "sprint_id": "phase19",
        "node_id": "autosci-skillgen-operator-smoke",
        "status": "failed" if failed_count or unbound_count else "completed",
        "inputs": {
            "paper_path": paper_path,
            "route_config": str(Path(args.route_config).resolve()),
            "binding_config": str(Path(args.binding_config).resolve()),
            "work_dir": base_rel,
        },
        "outputs": {
            "smoke": {
                "paper_path": paper_path,
                "route_count": len(routes),
                "bound_count": len(items) - unbound_count,
                "completed_count": count(items, "completed"),
                "partial_count": count(items, "partial"),
                "gated_count": count(items, "gated"),
                "failed_count": failed_count,
                "unbound_count": unbound_count,
                "core_action_count": len(core_results),
                "core_actions": [core_results[action] for action in CORE_ACTIONS],
                "items": items,
            }
        },
        "artifacts": [
            {"type": "route_config", "path": str(Path(args.route_config).resolve())},
            {"type": "binding_config", "path": str(Path(args.binding_config).resolve())},
            *[
                {"type": "core_action_evidence", "path": str(result.get("evidence_path"))}
                for result in core_results.values()
                if result.get("evidence_path") and result.get("status") != "failed"
            ],
        ],
        "provenance": {
            "operator_id": "AutoSciSkillgenOperatorSmoke",
            "implementation_package": "harness.plugins.autosci",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        "limitations": [
            "Skillgen operator smoke verifies local bridge operator wiring and deterministic gates.",
            "Approval-gated external effects are bound but not executed in this smoke.",
            "Fixture outputs do not replace live literature, Review LLM, remote execution, browser rendering, email, or LaTeX toolchain evidence.",
        ],
    }
    out_path = resolve_output(args.out, f"{base_rel}/autosci_operator_smoke.json")
    return payload, out_path


def run_skillgen(args: argparse.Namespace) -> int:
    payload, out_path = build_payload(args)
    write_json(out_path, payload)
    smoke = payload["outputs"]["smoke"]
    print(
        json.dumps(
            {
                "ok": payload["status"] == "completed",
                "schema": SCHEMA,
                "evidence_path": str(out_path),
                "route_count": smoke["route_count"],
                "bound_count": smoke["bound_count"],
                "completed_count": smoke["completed_count"],
                "partial_count": smoke["partial_count"],
                "gated_count": smoke["gated_count"],
                "failed_count": smoke["failed_count"],
                "unbound_count": smoke["unbound_count"],
                "core_action_count": smoke["core_action_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "completed" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    skillgen = subparsers.add_parser("skillgen", help="Run the skillgen paper operator smoke")
    skillgen.add_argument("--paper", default=str(DEFAULT_PAPER), help="Skillgen paper markdown path")
    skillgen.add_argument("--route-config", default=str(ROUTE_CONFIG), help="Feature parity route config")
    skillgen.add_argument("--binding-config", default=str(BINDING_CONFIG), help="Feature operator binding config")
    skillgen.add_argument("--work-dir", default="artifacts/autosci/operator-smoke/skillgen", help="Output work dir relative to HARNESS_DIR")
    skillgen.add_argument("--out", help="Output smoke evidence JSON path")
    skillgen.set_defaults(func=run_skillgen)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
