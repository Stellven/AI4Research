#!/usr/bin/env python3
"""Audit scientific workflow runtime binding integrity.

This is a static guard for the chain:

workflow node -> logical operator -> binding -> physical operator -> host
-> bridge action -> evidence schema -> deterministic gate.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dependency is available in repo env.
    yaml = None  # type: ignore[assignment]


HARNESS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOWS = [
    HARNESS_DIR / "workflows" / "scientific_research_lifecycle_full_v1.json",
    HARNESS_DIR / "workflows" / "scientific_research_resume_v1.json",
]

SCHEMA_GATE_MAP = {
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
    "scientific_report.v1": "report_gate.py",
    "artifact_review.v1": "artifact_review_gate.py",
    "publication_bundle.v1": "publication_gate.py",
    "workflow_evolution.v1": "workflow_evolution_gate.py",
}

NODE_ACTION_MAP = {
    "literature_discover": "discover_literature",
    "paper_ingest": "ingest_paper",
    "paper_analyze": "analyze_paper",
    "memory_update_initial": "update_memory",
    "graph_update": "update_graph",
    "claim_extract": "extract_claims",
    "method_extract": "extract_methods",
    "code_evidence_map": "map_code_evidence",
    "idea_generate": "generate_ideas",
    "idea_evaluate": "evaluate_ideas",
    "experiment_design": "design_experiment",
    "experiment_run": "run_experiment",
    "experiment_monitor": "monitor_experiment",
    "claim_verify": "verify_claim",
    "report_plan": "plan_report",
    "report_draft": "write_report",
    "artifact_review": "review_artifact",
    "publication_produce": "compile_paper",
    "memory_update_final": "update_memory",
    "workflow_evolve": "evolve_workflow",
}

SUPPORTED_HOST_TYPES = {
    "local_command_worker",
    "tmux_pane",
    "codex_worktree",
    "codex_cloud",
    "claude_code_session",
    "antigravity_managed_env",
    "local_mlx_process",
    "ssh_devbox",
    "docker_sandbox",
}


@dataclass
class AuditPaths:
    logical_operators: Path = HARNESS_DIR / "config" / "logical-operators.json"
    physical_operators: Path = HARNESS_DIR / "config" / "physical-operators.json"
    actor_hosts: Path = HARNESS_DIR / "config" / "actor-hosts.json"
    plugin_manifest: Path = HARNESS_DIR / "plugins" / "autosci" / "manifest.yaml"
    bridge: Path = HARNESS_DIR / "plugins" / "autosci" / "bin" / "autosci_bridge.py"
    schemas_dir: Path = HARNESS_DIR / "schemas" / "evidence"
    gates_dir: Path = HARNESS_DIR / "evaluators" / "scientific"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to read plugin manifest")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML object")
    return payload


def bridge_actions(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^ACTIONS:\s*dict\[.*?\]\s*=\s*\{(?P<body>.*?)^\}", text, flags=re.M | re.S)
    if not match:
        return set()
    return set(re.findall(r'^\s*"([^"]+)":', match.group("body"), flags=re.M))


def action_from_command(command: str) -> str:
    match = re.search(r"--action\s+([A-Za-z0-9_:-]+)", command)
    return match.group(1) if match else ""


def expected_schema(node: dict[str, Any]) -> str:
    policy = node.get("evidence_policy")
    if isinstance(policy, dict):
        return str(policy.get("expected_schema") or "")
    return str(node.get("expected_schema") or "")


def candidate_host_type(operator: dict[str, Any], host: dict[str, Any] | None) -> str:
    compat = operator.get("compat_maps_to") if isinstance(operator.get("compat_maps_to"), dict) else {}
    if compat.get("host_type"):
        return str(compat.get("host_type"))
    if host:
        return str(host.get("host_type") or "")
    return ""


def run_audit(workflows: list[Path], paths: AuditPaths = AuditPaths()) -> dict[str, Any]:
    logical_payload = load_json(paths.logical_operators)
    physical_payload = load_json(paths.physical_operators)
    hosts_payload = load_json(paths.actor_hosts)
    manifest = load_yaml(paths.plugin_manifest)
    actions = bridge_actions(paths.bridge)

    logical_ops = logical_payload.get("logical_operators") if isinstance(logical_payload.get("logical_operators"), dict) else {}
    bindings = logical_payload.get("bindings") if isinstance(logical_payload.get("bindings"), dict) else {}
    physical_ops = physical_payload.get("operators") if isinstance(physical_payload.get("operators"), dict) else {}
    hosts = hosts_payload.get("hosts") if isinstance(hosts_payload.get("hosts"), dict) else {}
    manifest_caps = set(str(item) for item in manifest.get("capabilities") or [])

    issues: list[dict[str, str]] = []
    checked_nodes = 0

    for workflow_path in workflows:
        workflow = load_json(workflow_path)
        workflow_id = str(workflow.get("workflow_id") or workflow_path.stem)
        for node in workflow.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            checked_nodes += 1
            node_id = str(node.get("id") or "N/A")
            logical = str(node.get("logical_operator") or "")
            _check_node(
                issues,
                workflow_id=workflow_id,
                node_id=node_id,
                node=node,
                logical=logical,
                logical_ops=logical_ops,
                bindings=bindings,
                physical_ops=physical_ops,
                hosts=hosts,
                manifest_caps=manifest_caps,
                actions=actions,
                paths=paths,
            )

    return {
        "ok": not issues,
        "checked_workflow_count": len(workflows),
        "checked_node_count": checked_nodes,
        "issue_count": len(issues),
        "issues": issues,
    }


def _issue(issues: list[dict[str, str]], workflow_id: str, node_id: str, code: str, message: str) -> None:
    issues.append({"workflow_id": workflow_id, "node_id": node_id, "code": code, "message": message})


def _check_node(
    issues: list[dict[str, str]],
    *,
    workflow_id: str,
    node_id: str,
    node: dict[str, Any],
    logical: str,
    logical_ops: dict[str, Any],
    bindings: dict[str, Any],
    physical_ops: dict[str, Any],
    hosts: dict[str, Any],
    manifest_caps: set[str],
    actions: set[str],
    paths: AuditPaths,
) -> None:
    if not logical or logical not in logical_ops:
        _issue(issues, workflow_id, node_id, "missing_logical_operator", f"logical operator missing: {logical or 'N/A'}")
    binding = bindings.get(logical)
    if not isinstance(binding, dict):
        _issue(issues, workflow_id, node_id, "missing_logical_binding", f"logical binding missing for {logical or 'N/A'}")
        candidates: list[Any] = []
    else:
        candidates = binding.get("candidates") if isinstance(binding.get("candidates"), list) else []
        if not candidates:
            _issue(issues, workflow_id, node_id, "missing_binding_candidate", f"no binding candidates for {logical}")

    capabilities = [str(item) for item in node.get("required_capabilities") or [] if str(item).startswith("cap.research-")]
    if not capabilities:
        _issue(issues, workflow_id, node_id, "missing_research_capability", "node must require at least one cap.research-* capability")
    for capability in capabilities:
        if capability not in manifest_caps:
            _issue(issues, workflow_id, node_id, "manifest_missing_capability", f"plugin manifest does not declare {capability}")

    schema = expected_schema(node)
    if not schema:
        _issue(issues, workflow_id, node_id, "missing_expected_schema", "node has no expected evidence schema")
    elif not (paths.schemas_dir / f"{schema}.schema.json").exists():
        _issue(issues, workflow_id, node_id, "missing_schema_file", f"missing schema file for {schema}")
    gate_file = SCHEMA_GATE_MAP.get(schema)
    if not gate_file:
        _issue(issues, workflow_id, node_id, "missing_gate_mapping", f"no audit gate mapping for schema {schema or 'N/A'}")
    elif not (paths.gates_dir / gate_file).exists():
        _issue(issues, workflow_id, node_id, "missing_gate_file", f"missing gate file {gate_file}")

    for candidate in candidates:
        if not isinstance(candidate, dict):
            _issue(issues, workflow_id, node_id, "invalid_binding_candidate", "binding candidate must be an object")
            continue
        condition = str(candidate.get("condition") or "")
        if condition == "backend_action_pending":
            _issue(issues, workflow_id, node_id, "stale_binding_condition", "binding condition is backend_action_pending")
        actor_id = str(candidate.get("actor_id") or "")
        if not actor_id:
            _issue(issues, workflow_id, node_id, "missing_actor_id", "binding candidate actor_id is required")
            continue
        operator = physical_ops.get(actor_id)
        if not isinstance(operator, dict):
            _issue(issues, workflow_id, node_id, "missing_physical_operator", f"physical operator missing: {actor_id}")
            continue
        owner_host = str(operator.get("owner_host") or "")
        host = hosts.get(owner_host)
        if not isinstance(host, dict):
            _issue(issues, workflow_id, node_id, "missing_host", f"owner_host is not registered: {owner_host or 'N/A'}")
        host_type = candidate_host_type(operator, host if isinstance(host, dict) else None)
        if host_type and host_type not in SUPPORTED_HOST_TYPES:
            _issue(issues, workflow_id, node_id, "unsupported_host_type", f"unsupported host_type {host_type}")
        if not host_type:
            _issue(issues, workflow_id, node_id, "missing_host_type", f"host type missing for {actor_id}")
        command = str(operator.get("command") or "")
        if not command:
            _issue(issues, workflow_id, node_id, "missing_command", f"physical operator {actor_id} has no command")
        action = action_from_command(command)
        if not action:
            _issue(issues, workflow_id, node_id, "missing_bridge_action", f"physical operator {actor_id} command has no --action")
        elif action not in actions:
            _issue(issues, workflow_id, node_id, "unknown_bridge_action", f"bridge action not registered: {action}")
        expected_action = NODE_ACTION_MAP.get(node_id)
        if expected_action and action != expected_action:
            _issue(
                issues,
                workflow_id,
                node_id,
                "unexpected_bridge_action",
                f"node {node_id} expects bridge action {expected_action}, got {action} from {actor_id}",
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", action="append", type=Path, help="Workflow JSON to audit; defaults to full and resume scientific workflows.")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero when issues are found.")
    parser.add_argument("--json", action="store_true", help="Emit only JSON.")
    args = parser.parse_args()

    workflows = args.workflow or list(DEFAULT_WORKFLOWS)
    report = run_audit([path if path.is_absolute() else Path.cwd() / path for path in workflows])
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["issues"]:
            print("scientific runtime binding audit failed")
    return 1 if args.strict and report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
