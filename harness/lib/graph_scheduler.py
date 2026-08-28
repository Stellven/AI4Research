#!/usr/bin/env python3
"""graph_scheduler.py — machine-executable DAG scheduler for Solar Harness.

This module turns planner output (`sprint-<sid>.task_graph.json`) into concrete
dispatch decisions. It intentionally stays in Python so it can plug into the
existing S6 control plane without adding a TypeScript runtime dependency.

Core guarantees:
  - invalid DAGs fail fast (missing deps, cycles, duplicate nodes)
  - ready nodes require all dependencies to be passed
  - nodes with overlapping write_scope never share a batch
  - nodes without declared write_scope are treated as exclusive writers
  - parent sprint cannot pass until every node and required gate has passed
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from executable_node import dispatch_role as executable_dispatch_role
from prerequisite_resolver import evaluate_prerequisite, iter_blocked

try:  # Lane 3 gate ledger (R4); optional so a partial install never breaks scheduling
    import gate_ledger as _gate_ledger
except Exception:  # pragma: no cover
    _gate_ledger = None

HOME = Path.home()
HARNESS_DIR = Path(
    os.environ.get("HARNESS_DIR")
    or os.environ.get("SOLAR_HARNESS_DIR")
    or HOME / ".solar" / "harness"
)
STATE_DB = Path(os.environ.get("HARNESS_STATE_DB", HARNESS_DIR / "run" / "state.db"))

TERMINAL_STATUSES = {"passed", "failed", "skipped", "cancelled", "skipped_parent_passed"}
ACTIVE_STATUSES = {"assigned", "dispatched", "in_progress", "running", "reviewing"}
READY_STATUSES = {"pending", "queued", "blocked", "worker_blocked", "failed_review", ""}
PASS_STATUSES = {"passed"}
CLOSED_NON_PASS_STATUSES = {"skipped", "cancelled", "skipped_parent_passed"}
DEPENDENCY_BLOCK_STATUSES = {"failed", "cancelled", "skipped", "skipped_parent_passed", "needs_human_review"}
HUMAN_REVIEW_STATUS = "needs_human_review"
HUMAN_REVIEW_SCHEMA_VERSION = "solar.human_review.v1"
HUMAN_REVIEW_HISTORY_LIMIT = 20
SPRINTS_DIR = Path(os.environ.get("HARNESS_SPRINTS_DIR", HARNESS_DIR / "sprints"))
RUNTIME_NODE_SPEC_FIELDS = {
    "assigned_to",
    "blocking_reason",
    "closeout_receipt",
    "dispatch_id",
    "eval_json",
    "gate_status",
    "human_review",
    "queued_pane",
    "result",
    "status",
    "updated_at",
    "worker_match_details",
}
SCHEDULER_RUNTIME_MUTABLE_NODE_FIELDS = RUNTIME_NODE_SPEC_FIELDS | {
    "attempt",
    "candidate_observations",
    "evaluation_results",
    "evaluation_state",
    "execution_attempt",
    "execution_attempt_error",
    "failure_policy_exhausted",
    "lease_id",
    "repair_attempts",
    "result_path",
    "selected_operator",
    "scheduler_candidate_observations",
}
SCHEDULER_RUNTIME_STATIC_NODE_FIELDS = {
    "id", "goal", "logical_operator", "dispatch_task_type", "task_type",
    "depends_on", "requirement_ids", "capsule_binding", "capability_capsule_id",
    "required_capabilities", "physical_candidates", "artifact_contract",
    "artifact_routes", "evaluation_binding", "evaluation_plan",
    "evaluator_gate", "evaluation_policy",
    "resource_requirements", "effects", "priority", "failure_policy",
    "max_repair_attempts", "on_failure_exhausted", "read_scope", "write_scope",
    "acceptance",
}
REPAIR_ACTIVE_STATUSES = {
    "failed_review",
    "reviewing",
    "assigned",
    "dispatched",
    "in_progress",
    "running",
    "pending",
    "queued",
    "blocked",
    "worker_blocked",
    "",
}


def _effective_graph_max_parallel(default: int | None = None) -> int | None:
    try:
        lib_dir = HARNESS_DIR / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        import concurrency_policy  # type: ignore

        return int(concurrency_policy.effective_max_parallel(default or 8, scope="graph"))
    except Exception:
        return default

LABEL_ALIAS_GROUPS = [
    {
        "solar-harness-control-plane",
        "control-plane",
        "workflow.planning",
        "governance",
        "autopilot",
        "routing",
        "diagnostics",
        "harness.contracts",
        "harness.dag",
        "harness.status",
    },
    {
        "architecture-writing",
        "technical-writing",
        "architecture",
        "markdown",
        "docs",
        "documentation",
        "spec.write",
    },
    {
        "algorithm_design",
        "algorithm",
        "optimization",
        "runtime_design",
        "scheduler.design",
        "state-machine.design",
        "architecture",
        "data-modeling",
        "api-design",
    },
    {
        "code_impl",
        "ImplementationWorker",
        "backend-development",
        "backend.development",
        "backend",
        "python",
        "typescript",
        "refactor",
        "integration",
        "subprocess",
        "sqlite",
        "sqlite3",
    },
    {
        "test_generation",
        "test_execution",
        "testing",
        "pytest",
        "regression",
        "regression-tests",
        "integration-testing",
        "integration-tests",
        "bash-tests",
        "test.tdd",
    },
    {
        "solar-harness-verification",
        "solar-harness-compat-review",
        "compat-review",
        "compatibility",
        "harness.verification",
        "verification",
        "verifier",
        "review",
        "testing",
        "test_execution",
        "code.review",
    },
    {
        "ai-rag-pipeline",
        "rag",
        "retrieval",
        "knowledge",
        "harness.knowledge",
        "context.inject",
    },
    {
        "reporting",
        "report",
        "report.compile",
        "research.report.compile",
        "harness.reporting",
        "documentation",
        "technical-writing",
    },
    {
        "model.routing",
        "harness.model_routing",
        "model_routing",
        "models.lab_matrix",
        "models.show",
    },
    {
        "api-adapter",
        "api_adapter",
        "api.adapter",
        "api",
        "integration",
        "subprocess",
        "python",
        "provider.contract",
        "api-design",
        "schema",
    },
    {
        "gstack",
        "browser.browse",
        "browser.qa",
        "code.review",
        "browser",
        "browser-automation",
        "browser.automation",
        "browser.agent",
        "web",
        "web.capture",
        "scraping",
        "crawler",
        "collector",
    },
    {
        "ATLAS",
        "atlas",
        "repair.pr-cot",
        "failure.structured_repair",
        "routing.complexity_budget",
        "debug.systematic",
        "regression",
        "regression-tests",
    },
    {
        "social",
        "social.monitor",
        "social_signal",
        "social.signal",
        "social_links",
        "entity.extract",
        "link.extract",
        "url.extract",
        "cross_source.dispatch",
        "github.dispatch",
        "hf.dispatch",
        "youtube.dispatch",
    },
    {
        "policy",
        "policy.verdict",
        "governance",
        "harness.contracts",
        "solar-harness-control-plane",
    },
    {
        "quota",
        "quota-management",
        "quota_fallback",
        "quota.fallback",
        "fallback",
        "observability",
        "metrics",
    },
]


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_graph(path: str | Path) -> dict[str, Any]:
    graph_path = Path(path)
    graph = json.loads(graph_path.read_text())
    state = _load_graph_state_for_path(graph_path, graph)
    _attach_runtime_planes(graph, graph_path=graph_path, state=state)
    return graph


def save_graph(path: str | Path, graph: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    state = _runtime_state_from_graph(graph, graph_path=p)
    _save_graph_state(_state_path_for_graph(graph, p), state)
    _save_closure_projection(_closure_path_for_graph(graph, p), graph, state)
    spec_graph = _graph_spec_payload(graph)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(spec_graph, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


def _state_path_for_graph(graph: dict[str, Any], graph_path: str | Path | None = None) -> Path:
    sid = _sprint_id_for_graph(graph, graph_path)
    if graph_path:
        base_dir = Path(graph_path).expanduser().parent
    else:
        base_dir = SPRINTS_DIR
    configured = str(graph.get("runtime_state_filename") or "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.name != configured or candidate.suffix.lower() != ".json":
            raise ValueError("runtime_state_filename must be a safe JSON basename")
        return base_dir / candidate
    return base_dir / f"{sid}.task_dag.state.json"


def _closure_path_for_graph(graph: dict[str, Any], graph_path: str | Path | None = None) -> Path:
    sid = _sprint_id_for_graph(graph, graph_path)
    if graph_path:
        base_dir = Path(graph_path).expanduser().parent
    else:
        base_dir = SPRINTS_DIR
    return base_dir / f"{sid}.closure.json"


def _load_graph_state_for_path(graph_path: Path, graph: dict[str, Any]) -> dict[str, Any]:
    state_path = _state_path_for_graph(graph, graph_path)
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _attach_runtime_planes(
    graph: dict[str, Any],
    *,
    graph_path: Path | None,
    state: dict[str, Any] | None = None,
) -> None:
    runtime = graph.get("_solar_runtime")
    if not isinstance(runtime, dict):
        runtime = {}
        graph["_solar_runtime"] = runtime
    runtime["graph_path"] = str(graph_path) if graph_path else ""
    if state is None:
        state = {}
    runtime["state_path"] = str(_state_path_for_graph(graph, graph_path)) if graph_path else ""
    runtime["closure_path"] = str(_closure_path_for_graph(graph, graph_path)) if graph_path else ""
    runtime["state"] = deepcopy(state) if state else {}
    node_results = state.get("node_results") if isinstance(state.get("node_results"), dict) else {}
    gate_results = state.get("gate_results") if isinstance(state.get("gate_results"), dict) else {}
    if node_results:
        graph["node_results"] = deepcopy(node_results)
    elif "node_results" not in graph:
        graph["node_results"] = {}
    if gate_results:
        graph["gate_results"] = deepcopy(gate_results)
    elif "gate_results" not in graph:
        graph["gate_results"] = {}
    ids = _node_map(graph)
    for node_id, result in node_results.items():
        if node_id not in ids or not isinstance(result, dict):
            continue
        # The spec plane deliberately strips every runtime field in
        # RUNTIME_NODE_SPEC_FIELDS.  Rehydrate the same complete field set on
        # load; restoring only status/lease metadata silently drops durable
        # closeout authority such as closeout_receipt.  Downstream evaluators
        # then reject a valid published ancestor because its digest chain
        # appears incomplete after the first save/load round trip.
        fields = (
            SCHEDULER_RUNTIME_MUTABLE_NODE_FIELDS
            if graph.get("schema_version") == "solar.scheduler_runtime_projection.v1"
            else RUNTIME_NODE_SPEC_FIELDS
        )
        for field in fields:
            if field in result:
                ids[node_id][field] = deepcopy(result[field])


def _runtime_state_from_graph(graph: dict[str, Any], *, graph_path: Path | None = None) -> dict[str, Any]:
    runtime = graph.get("_solar_runtime") if isinstance(graph.get("_solar_runtime"), dict) else {}
    base_state = deepcopy(runtime.get("state")) if isinstance(runtime.get("state"), dict) else {}
    sid = _sprint_id_for_graph(graph, graph_path)
    base_state["schema_version"] = str(base_state.get("schema_version") or "solar.task_graph_state.v1")
    base_state["sprint_id"] = sid
    base_state["graph_ref"] = f"{sid}.task_graph.json" if sid else str(graph_path or "")
    base_state["node_results"] = deepcopy(_node_results(graph))
    gate_results = graph.get("gate_results") if isinstance(graph.get("gate_results"), dict) else {}
    base_state["gate_results"] = deepcopy(gate_results)
    leases = base_state.get("leases")
    if not isinstance(leases, dict):
        leases = {}
    dispatch_ids = base_state.get("dispatch_ids")
    if not isinstance(dispatch_ids, dict):
        dispatch_ids = {}
    for node_id, result in base_state["node_results"].items():
        if not isinstance(result, dict):
            continue
        dispatch_id = str(result.get("dispatch_id") or "").strip()
        assigned_to = str(result.get("assigned_to") or "").strip()
        if dispatch_id:
            dispatch_ids[node_id] = dispatch_id
        if assigned_to:
            leases[node_id] = {"pane": assigned_to, "dispatch_id": dispatch_id}
    base_state["leases"] = leases
    base_state["dispatch_ids"] = dispatch_ids
    base_state["updated_at"] = _now()
    events = base_state.get("events")
    if not isinstance(events, list):
        base_state["events"] = []
    if graph.get("schema_version") == "solar.scheduler_runtime_projection.v1":
        prior_revision = base_state.get("revision")
        try:
            revision = int(prior_revision) + 1
        except (TypeError, ValueError):
            revision = 1
        ids = _node_map(graph)
        runtime_results: dict[str, dict[str, Any]] = {}
        for node_id, node in ids.items():
            runtime_result = {
                key: deepcopy(value)
                for key, value in node.items()
                if key in SCHEDULER_RUNTIME_MUTABLE_NODE_FIELDS
            }
            prior_result = base_state["node_results"].get(node_id)
            if isinstance(prior_result, dict):
                for key, value in prior_result.items():
                    if key in SCHEDULER_RUNTIME_MUTABLE_NODE_FIELDS:
                        runtime_result.setdefault(key, deepcopy(value))
            status = str(node_status(graph, node_id) or "pending").strip().lower()
            runtime_result["status"] = status

            # Runtime projection merges the prior ledger so attempt history and
            # evaluator evidence survive.  Status-scoped routing fields are not
            # history, though: retaining them after the node advances makes a
            # healthy reviewing/terminal node still look worker-blocked and
            # keeps a dead builder lease visible to the coordinator and GUI.
            if status not in {"queued", "blocked", "worker_blocked"}:
                runtime_result.pop("blocking_reason", None)
                runtime_result.pop("worker_match_details", None)
                runtime_result.pop("queued_pane", None)
            elif status != "worker_blocked":
                runtime_result.pop("worker_match_details", None)

            if status not in {"assigned", "dispatched", "in_progress", "running"}:
                runtime_result.pop("assigned_to", None)
                runtime_result.pop("dispatch_id", None)
            runtime_results[node_id] = runtime_result
        base_state["node_results"] = runtime_results
        # These maps describe live claims, not historical dispatches. Rebuild
        # them from the cleaned current projection instead of carrying entries
        # forward from base_state forever.
        projection_leases: dict[str, Any] = {}
        projection_dispatch_ids: dict[str, str] = {}
        for node_id, result in runtime_results.items():
            status = str(result.get("status") or "").strip().lower()
            if status not in {"assigned", "dispatched", "in_progress", "running"}:
                continue
            dispatch_id = str(result.get("dispatch_id") or "").strip()
            assigned_to = str(result.get("assigned_to") or "").strip()
            if dispatch_id:
                projection_dispatch_ids[node_id] = dispatch_id
            if assigned_to:
                projection_leases[node_id] = {
                    "pane": assigned_to,
                    "dispatch_id": dispatch_id,
                }
        base_state["leases"] = projection_leases
        base_state["dispatch_ids"] = projection_dispatch_ids
        state_nodes: dict[str, Any] = {}
        ready: list[str] = []
        terminal = True
        any_failed = False
        any_active = False
        for node_id, node in ids.items():
            status = node_status(graph, node_id) or "pending"
            terminal = terminal and status in TERMINAL_STATUSES
            any_failed = any_failed or status in DEPENDENCY_BLOCK_STATUSES
            any_active = any_active or status in ACTIVE_STATUSES
            blocked_by = [
                dep for dep in _internal_depends_on(node)
                if dep in ids and not _is_passed(graph, dep)
            ]
            execution_attempt = node.get("execution_attempt") if isinstance(node.get("execution_attempt"), dict) else {}
            try:
                attempt = max(0, int(execution_attempt.get("sequence") or 0))
            except (TypeError, ValueError):
                attempt = 0
            state_nodes[node_id] = {
                "status": status,
                "attempt": attempt,
                "blocked_by": blocked_by,
            }
            if status in READY_STATUSES and not blocked_by:
                ready.append(node_id)
        if terminal:
            run_status = "failed" if any_failed else "completed"
        elif any_active:
            run_status = "running"
        else:
            run_status = "queued"
        base_state.update(
            {
                "artifact_role": "mutable_execution_ledger",
                "run_contract_ref": deepcopy(graph.get("run_contract_ref") or {}),
                "scheduler_input_ref": deepcopy(graph.get("scheduler_input_ref") or {}),
                "revision": revision,
                "run_status": run_status,
                "nodes": state_nodes,
                "ready_nodes": sorted(ready),
                "last_event_id": (
                    base_state["events"][-1].get("id")
                    if base_state.get("events") and isinstance(base_state["events"][-1], dict)
                    else None
                ),
            }
        )
    return base_state


def _graph_spec_payload(graph: dict[str, Any]) -> dict[str, Any]:
    spec = deepcopy(graph)
    spec.pop("_solar_runtime", None)
    spec.pop("node_results", None)
    spec.pop("gate_results", None)
    for node in spec.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        if graph.get("schema_version") == "solar.scheduler_runtime_projection.v1":
            for key in list(node):
                if key not in SCHEDULER_RUNTIME_STATIC_NODE_FIELDS:
                    node.pop(key, None)
            continue
        for key in RUNTIME_NODE_SPEC_FIELDS:
            node.pop(key, None)
    return spec


def _save_graph_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _save_closure_projection(path: Path, graph: dict[str, Any], state: dict[str, Any]) -> None:
    parent = parent_ready_check(graph)
    terminal_status = str(parent.get("terminal_status") or "")
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                existing = payload
        except Exception:
            existing = {}
    record = dict(existing)
    record["schema_version"] = str(record.get("schema_version") or "solar.closure_record.v1")
    record["sprint_id"] = _sprint_id_for_graph(graph)
    record["graph_ref"] = f"{record['sprint_id']}.task_graph.json" if record["sprint_id"] else str(path)
    record["graph_state_ref"] = str(state.get("graph_ref") or f"{record['sprint_id']}.task_dag.state.json")
    if parent.get("ready"):
        record["status"] = "closed"
    elif terminal_status:
        record["status"] = terminal_status
    else:
        record["status"] = "pending"
    record["all_nodes_passed"] = not parent.get("open_nodes") and not parent.get("failed_nodes")
    record["all_required_gates_passed"] = not parent.get("missing_gates")
    # No coverage artifact means unknown, not zero.  requirement_coverage owns
    # the numeric projection and refreshes this field after it writes the
    # canonical coverage report.
    record["acceptance_traceability_coverage"] = record.get("acceptance_traceability_coverage")
    record["open_nodes"] = list(parent.get("open_nodes") or [])
    record["failed_nodes"] = list(parent.get("failed_nodes") or [])
    record["human_review_nodes"] = list(parent.get("human_review_nodes") or [])
    record["terminal_status"] = terminal_status or None
    record["missing_gates"] = list(parent.get("missing_gates") or [])
    record["updated_at"] = _now()
    if parent.get("ready") and not record.get("closed_at"):
        record["closed_at"] = record["updated_at"]
    if terminal_status == "failed" and not record.get("failed_at"):
        record["failed_at"] = record["updated_at"]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _sprint_id_for_graph(graph: dict[str, Any], graph_path: str | Path | None = None) -> str:
    sid = str(graph.get("sprint_id") or "").strip()
    if sid:
        return sid
    legacy_id = str(graph.get("id") or "").strip()
    if legacy_id:
        return legacy_id
    if graph_path:
        return Path(graph_path).name.removesuffix(".task_graph.json")
    return ""


def _status_path_for_graph(graph: dict[str, Any], graph_path: str | Path | None = None) -> Path:
    sid = _sprint_id_for_graph(graph, graph_path)
    if graph_path:
        return Path(graph_path).expanduser().parent / f"{sid}.status.json"
    return SPRINTS_DIR / f"{sid}.status.json"


def _write_route_proof_for_sprint(sid: str) -> dict[str, Any]:
    if not sid:
        return {}
    try:
        import route_proof  # type: ignore

        return route_proof.write_route_proof(HARNESS_DIR, sid, sprints_dir=SPRINTS_DIR)
    except Exception as exc:
        return {
            "ok": False,
            "enforced": False,
            "sprint_id": sid,
            "error": str(exc),
            "reason": "route_proof_write_failed",
        }


def _status_has_terminal_evidence(sid: str, status: dict[str, Any] | None = None, graph_path: str | Path | None = None) -> bool:
    base_dir = Path(graph_path).expanduser().parent if graph_path else SPRINTS_DIR
    if (base_dir / f"{sid}.finalized").exists():
        return True
    try:
        closure = json.loads((base_dir / f"{sid}.closure.json").read_text(encoding="utf-8"))
        if closure.get("all_nodes_passed") and closure.get("all_required_gates_passed"):
            return True
    except Exception:
        pass
    if graph_path:
        return False
    handoff = (base_dir / f"{sid}.handoff.md").exists() or any(base_dir.glob(f"{sid}.*-handoff.md"))
    eval_exists = (
        (base_dir / f"{sid}.eval.md").exists()
        or (base_dir / f"{sid}.eval.json").exists()
        or any(base_dir.glob(f"{sid}.*-eval.md"))
        or any(base_dir.glob(f"{sid}.*-eval.json"))
    )
    return handoff and eval_exists


def _project_status_via_runtime(
    status_path: Path,
    *,
    new_status: str,
    actor: str,
    event: str,
    graph_path: str | Path | None = None,
    allow_reopen: bool = False,
    status_fields: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from runtime_status import transition_status  # noqa: WPS433

    payload = dict(extra or {})
    payload["graph_sync"] = True
    payload["graph_path"] = str(graph_path or "")
    payload["allow_reopen"] = allow_reopen
    payload["status_fields"] = dict(status_fields or {})
    updated, _message = transition_status(
        status_path,
        new_status,
        event,
        actor,
        extra=payload,
    )
    return updated


def _ensure_status_cache_exists_from_graph(
    graph: dict[str, Any],
    graph_path: str | Path | None,
    status_path: Path,
    *,
    actor: str,
    event: str,
) -> dict[str, Any] | None:
    """Create the legacy status cache for an in-flight graph if it is missing."""
    if status_path.exists():
        return None
    sid = _sprint_id_for_graph(graph, graph_path)
    if not sid:
        return None
    now = _now()
    open_nodes = [
        str(node.get("id") or "")
        for node in graph.get("nodes", [])
        if str(node.get("status") or "") not in TERMINAL_STATUSES
    ]
    failed_nodes = [
        str(node.get("id") or "")
        for node in graph.get("nodes", [])
        if str(node.get("status") or "") == "failed"
    ]
    status = {
        "id": sid,
        "sprint_id": sid,
        "title": str(graph.get("title") or sid),
        "status": "active",
        "phase": "graph_in_progress",
        "handoff_to": "builder_main",
        "target_role": "builder_main",
        "created_at": str(graph.get("created_at") or now),
        "updated_at": now,
        "task_graph": str(graph_path or ""),
        "graph_status_cache": True,
        "graph_parent_ready": parent_ready_check(graph),
        "active_node": open_nodes[0] if open_nodes else None,
        "open_nodes": open_nodes,
        "failed_nodes": failed_nodes,
        "history": [],
    }
    # Seed legacy cache once, then immediately bridge through transition_status
    # so session-log v2 and compatibility status.json stay aligned.
    tmp = status_path.with_suffix(status_path.suffix + ".tmp")
    tmp.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, status_path)
    return _project_status_via_runtime(
        status_path,
        new_status="active",
        actor=actor,
        event=event,
        graph_path=graph_path,
        status_fields={
            "phase": "graph_in_progress",
            "handoff_to": "builder_main",
            "target_role": "builder_main",
            "task_graph": str(graph_path or ""),
            "graph_status_cache": True,
            "graph_parent_ready": status.get("graph_parent_ready", {}),
            "active_node": status.get("active_node"),
            "open_nodes": status.get("open_nodes", []),
            "failed_nodes": status.get("failed_nodes", []),
            "stage": "graph_in_progress",
            "task_graph_status": "active",
        },
        extra={"note": "created missing status cache from task_graph"},
    )


def sync_status_cache_from_graph(
    graph: dict[str, Any],
    graph_path: str | Path | None = None,
    *,
    actor: str = "graph_scheduler",
    event: str = "graph_parent_ready_passed",
) -> dict[str, Any]:
    """Project a completed task_graph into the legacy sprint status cache.

    `task_graph.json` is the scheduler source of truth, while
    `status.json` is a compatibility projection used by epic activation,
    status UI, exports, and old monitors. Keeping this projection in the same
    write path as graph closeout prevents a passed DAG from looking active.
    """
    # Once the split runtime plane exists, it is authoritative for node/gate
    # status.  Some callers retain a specification-only graph object across a
    # save, so calculating parent readiness from that stale object falsely
    # projects every node and gate as open.  Rehydrate from disk at this
    # compatibility boundary; callers without a persisted state plane retain
    # the legacy in-memory behavior.
    if graph_path:
        persisted_graph_path = Path(graph_path).expanduser()
        state_path = _state_path_for_graph(graph, persisted_graph_path)
        if persisted_graph_path.exists() and state_path.exists():
            graph = load_graph(persisted_graph_path)
    parent = parent_ready_check(graph)
    sid = _sprint_id_for_graph(graph, graph_path)
    status_path = _status_path_for_graph(graph, graph_path)
    result: dict[str, Any] = {
        "ok": True,
        "updated": False,
        "created": False,
        "sprint_id": sid,
        "status_path": str(status_path),
        "parent": parent,
    }
    if not sid:
        result.update({"ok": False, "reason": "missing_sprint_id"})
        return result
    created_status = _ensure_status_cache_exists_from_graph(
        graph,
        graph_path,
        status_path,
        actor=actor,
        event=event,
    )
    if created_status is not None:
        result.update({"created": True, "updated": True, "status": created_status})
    if not status_path.exists():
        result["reason"] = "status_missing"
        return result
    try:
        current = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as exc:
        result.update({"ok": False, "reason": "status_corrupt", "error": str(exc)})
        return result
    if not parent.get("ready"):
        now = _now()
        open_nodes = parent.get("open_nodes") or []
        failed_nodes = parent.get("failed_nodes") or []
        human_review_nodes = parent.get("human_review_nodes") or []
        terminal_status = str(parent.get("terminal_status") or "")
        desired_active_node = open_nodes[0] if open_nodes else None
        history = current.get("history")
        if not isinstance(history, list):
            history = []
        if str(current.get("status") or "").lower() == "passed":
            if _status_has_terminal_evidence(sid, current, graph_path):
                current = _project_status_via_runtime(
                    status_path,
                    new_status="passed",
                    actor=actor,
                    event="graph_parent_ready_preserved_terminal",
                    graph_path=graph_path,
                    status_fields={
                        "phase": str(current.get("phase") or "completed"),
                        "stage": str(current.get("stage") or "completed"),
                        "graph_parent_ready": parent,
                        "task_graph_status": str(current.get("task_graph_status") or "passed"),
                        "active_node": None,
                    },
                    extra={"note": "terminal closeout evidence preserved while parent projection refreshed"},
                )
                result.update({"updated": True, "status": current, "reason": "terminal_evidence_preserved"})
                return result
            current = _project_status_via_runtime(
                status_path,
                new_status="active",
                actor=actor,
                event="graph_parent_ready_revoked",
                graph_path=graph_path,
                allow_reopen=True,
                status_fields={
                    "phase": "graph_in_progress",
                    "stage": "graph_in_progress",
                    "active_node": desired_active_node,
                    "open_nodes": open_nodes,
                    "failed_nodes": failed_nodes,
                    "graph_parent_ready": parent,
                    "task_graph_status": "active",
                    "completed_at": None,
                },
                extra={"note": "task_graph no longer satisfies parent_ready_check; reopening legacy status cache"},
            )
            result.update({"updated": True, "status": current, "reason": "parent_reopened"})
            return result
        if terminal_status == "failed":
            current = _project_status_via_runtime(
                status_path,
                new_status="failed",
                actor=actor,
                event="graph_parent_failed",
                graph_path=graph_path,
                status_fields={
                    "phase": "failed",
                    "stage": "failed",
                    "active_node": None,
                    "open_nodes": open_nodes,
                    "failed_nodes": failed_nodes,
                    "human_review_nodes": human_review_nodes,
                    "graph_parent_ready": parent,
                    "task_graph_status": "failed",
                },
                extra={"note": "task_graph has terminal failed nodes and no runnable downstream nodes"},
            )
            result.update({"updated": True, "status": current, "reason": "parent_failed"})
            return result
        if terminal_status == HUMAN_REVIEW_STATUS:
            current = _project_status_via_runtime(
                status_path,
                new_status=HUMAN_REVIEW_STATUS,
                actor=actor,
                event="graph_parent_needs_human_review",
                graph_path=graph_path,
                allow_reopen=True,
                status_fields={
                    "phase": "needs_human",
                    "stage": HUMAN_REVIEW_STATUS,
                    "active_node": None,
                    "open_nodes": open_nodes,
                    "failed_nodes": failed_nodes,
                    "human_review_nodes": human_review_nodes,
                    "graph_parent_ready": parent,
                    "task_graph_status": HUMAN_REVIEW_STATUS,
                },
                extra={"note": "task_graph has only human-review blockers and no runnable nodes"},
            )
            result.update({
                "updated": True,
                "status": current,
                "reason": "parent_needs_human_review",
            })
            return result
        if str(current.get("status") or "").lower() == "failed" and open_nodes:
            current = _project_status_via_runtime(
                status_path,
                new_status="active",
                actor=actor,
                event="graph_parent_failed_reopened_for_repair",
                graph_path=graph_path,
                allow_reopen=True,
                status_fields={
                    "phase": "graph_in_progress",
                    "stage": "graph_in_progress",
                    "active_node": desired_active_node,
                    "open_nodes": open_nodes,
                    "failed_nodes": failed_nodes,
                    "graph_parent_ready": parent,
                    "task_graph_status": "active",
                    "completed_at": None,
                },
                extra={"note": "task_graph has active repair/re-eval work; revoking stale failed parent projection"},
            )
            result.update({"updated": True, "status": current, "reason": "parent_reopened_for_repair"})
            return result
        if str(current.get("status") or "").lower() == HUMAN_REVIEW_STATUS and open_nodes:
            current = _project_status_via_runtime(
                status_path,
                new_status="active",
                actor=actor,
                event="graph_parent_reopened_after_human_resume",
                graph_path=graph_path,
                allow_reopen=True,
                status_fields={
                    "phase": "graph_in_progress",
                    "stage": "graph_in_progress",
                    "active_node": desired_active_node,
                    "open_nodes": open_nodes,
                    "failed_nodes": failed_nodes,
                    "human_review_nodes": human_review_nodes,
                    "graph_parent_ready": parent,
                    "task_graph_status": "active",
                    "completed_at": None,
                },
                extra={"note": "human resumed a graph node; reopening the parent projection"},
            )
            result.update({
                "updated": True,
                "status": current,
                "reason": "parent_reopened_after_human_resume",
            })
            return result
        projection_changed = any([
            current.get("active_node") != desired_active_node,
            list(current.get("open_nodes") or []) != list(open_nodes),
            list(current.get("failed_nodes") or []) != list(failed_nodes),
            (current.get("graph_parent_ready") or {}) != parent,
            str(current.get("task_graph_status") or "") != "active",
        ])
        if projection_changed:
            current = _project_status_via_runtime(
                status_path,
                new_status=str(current.get("status") or "active"),
                actor=actor,
                event="graph_parent_projection_refreshed",
                graph_path=graph_path,
                status_fields={
                    "phase": str(current.get("phase") or "graph_in_progress"),
                    "stage": str(current.get("stage") or "graph_in_progress"),
                    "active_node": desired_active_node,
                    "open_nodes": open_nodes,
                    "failed_nodes": failed_nodes,
                    "human_review_nodes": human_review_nodes,
                    "graph_parent_ready": parent,
                    "task_graph_status": "active",
                },
                extra={"note": "task_graph changed while in flight; refreshing legacy status projection"},
            )
            result.update({"updated": True, "status": current, "reason": "parent_projection_refreshed"})
            return result
        result["reason"] = "parent_projection_refreshed" if result.get("created") else "parent_not_ready"
        return result

    route_proof = _write_route_proof_for_sprint(sid)
    if route_proof:
        result["route_proof"] = {
            "ok": route_proof.get("ok"),
            "complete": route_proof.get("complete"),
            "path": route_proof.get("path"),
            "selected_runtime": route_proof.get("selected_runtime"),
            "allowed_providers": route_proof.get("allowed_providers", []),
            "violations": route_proof.get("violations", []),
            "incomplete_stages": route_proof.get("incomplete_stages", []),
        }
        if route_proof.get("enforced") and not route_proof.get("ok"):
            reason = "route_proof_incomplete" if route_proof.get("complete") is False else "route_proof_violation"
            result.update({"ok": False, "reason": reason})
            return result

    already_passed = str(current.get("status") or "").lower() == "passed"
    already_closed = not current.get("active_node") and str(current.get("stage") or "").lower() in {
        "completed",
        "done",
        "",
    }
    already_graph_passed = str(current.get("task_graph_status") or "").lower() == "passed"
    if (
        already_passed
        and already_closed
        and already_graph_passed
        and (current.get("graph_parent_ready") or {}).get("ready") is True
        and not current.get("legacy_pass_blocked")
        and not current.get("legacy_pass_block_reason")
        and not current.get("legacy_pass_block_detail")
    ):
        result["reason"] = "already_synced"
        return result

    try:
        from runtime_status import transition_status  # noqa: WPS433

        updated, message = transition_status(
            status_path,
            "passed",
            event,
            actor,
            extra={
                "graph_sync": True,
                "graph_path": str(graph_path or ""),
                "status_fields": {
                    "phase": "completed",
                    "stage": "completed",
                    "completed_at": str(current.get("completed_at") or _now()),
                    "active_node": None,
                    "graph_parent_ready": parent,
                    "task_graph_status": "passed",
                    "legacy_pass_blocked": False,
                    "legacy_pass_block_reason": None,
                    "legacy_pass_block_detail": None,
                },
            },
        )
        result.update({"updated": True, "message": message, "status": updated})
    except Exception as exc:
        result.update({"ok": False, "reason": "transition_failed", "error": str(exc)})
    return result


def _source_text_for_graph(graph_path: str | Path | None, explicit_source: str | Path | None = None) -> str:
    paths: list[Path] = []
    if explicit_source:
        paths.append(Path(explicit_source))
    if graph_path:
        graph_p = Path(graph_path)
        if graph_p.name.endswith(".task_graph.json"):
            stem = graph_p.name[:-len(".task_graph.json")]
            paths.extend([
                graph_p.with_name(f"{stem}.contract.md"),
                graph_p.with_name(f"{stem}.plan.md"),
            ])
    chunks: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        path = path.expanduser()
        if path in seen or not path.exists() or not path.is_file():
            continue
        seen.add(path)
        chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(chunks)


def auto_enrich_graph(graph: dict[str, Any], graph_path: str | Path | None = None,
                      source: str | Path | None = None) -> dict[str, Any]:
    """Best-effort capability enrichment for default dispatch paths."""
    try:
        from capability_inference import enrich_graph  # noqa: WPS433

        return enrich_graph(graph, source_text=_source_text_for_graph(graph_path, source))
    except Exception:
        return graph


def _changed_nodes(graph: dict[str, Any]) -> list[str]:
    info = graph.get("capability_inference") or {}
    changed = info.get("changed_nodes") or []
    if isinstance(changed, list):
        return [str(item) for item in changed if str(item)]
    return []


def _required_capability_snapshot(graph: dict[str, Any]) -> dict[str, list[str]]:
    snapshot: dict[str, list[str]] = {}
    try:
        nodes = _nodes(graph)
    except Exception:
        return snapshot
    for node in nodes:
        node_id = str(node.get("id", ""))
        if not node_id:
            continue
        if "required_capabilities" not in node:
            snapshot[node_id] = ["__MISSING_REQUIRED_CAPABILITIES__"]
            continue
        snapshot[node_id] = _capability_list(node)
    return snapshot


def _nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("task_graph.nodes must be a list")
    return nodes


def _node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for node in _nodes(graph):
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("every task graph node requires non-empty id")
        if node_id in result:
            raise ValueError(f"duplicate node id: {node_id}")
        result[node_id] = node
    return result


def _node_results(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = graph.get("node_results") or graph.get("results") or {}
    return results if isinstance(results, dict) else {}


def _parse_ts(value: Any) -> datetime.datetime | None:
    if not value:
        return None
    try:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.datetime.fromisoformat(raw)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _human_review_record(node: dict[str, Any], result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the most authoritative durable human-review record available."""
    candidates = [
        node.get("human_review"),
        (result or {}).get("human_review") if isinstance(result, dict) else None,
    ]
    valid = [
        item
        for item in candidates
        if isinstance(item, dict)
        and str(item.get("schema_version") or "") == HUMAN_REVIEW_SCHEMA_VERSION
    ]
    if not valid:
        return {}

    def authority_rank(item: dict[str, Any]) -> tuple[int, int]:
        try:
            generation = max(0, int(item.get("generation") or 0))
        except (TypeError, ValueError):
            generation = 0
        # A later generation supersedes an earlier one.  Within one
        # generation, conflicting mirrors fail closed: an outstanding block
        # is authoritative until both durable records agree it was resumed.
        blocked = int(str(item.get("state") or "").strip().lower() == "blocked")
        return generation, blocked

    return max(valid, key=authority_rank)


def _human_review_is_blocking(node: dict[str, Any], result: dict[str, Any] | None = None) -> bool:
    """Human review is absorbing until the dedicated resume seam clears it.

    The raw-status fallback deliberately protects legacy graphs created before
    ``solar.human_review.v1`` existed.  A newer unrecorded ``pending`` mirror
    must not erase an older inline escalation (the exact rc.9 loop class).
    """
    record = _human_review_record(node, result)
    if str(record.get("state") or "").strip().lower() == "blocked":
        return True
    statuses = {
        str(node.get("status") or "").strip().lower(),
        str((result or {}).get("status") or "").strip().lower(),
    }
    return HUMAN_REVIEW_STATUS in statuses


def human_review_generation(graph: dict[str, Any], node_id: str) -> int:
    """Latest durable review generation (legacy escalations are generation 1).

    A later terminal result can replace the current ``node_results`` mirror
    without erasing ``human_review_history``. The history maximum remains the
    generation floor so a fresh block never reuses an already resumed token.
    """
    ids = _node_map(graph)
    if node_id not in ids:
        raise ValueError(f"unknown node: {node_id}")
    result = _node_results(graph).get(node_id)
    record = _human_review_record(ids[node_id], result)
    generation = 0
    candidates: list[Any] = [record]
    for owner in (ids[node_id], result if isinstance(result, dict) else {}):
        history = owner.get("human_review_history") if isinstance(owner, dict) else None
        if isinstance(history, list):
            candidates.extend(history)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("schema_version") or "") != HUMAN_REVIEW_SCHEMA_VERSION:
            continue
        try:
            generation = max(generation, max(0, int(candidate.get("generation") or 0)))
        except (TypeError, ValueError):
            continue
    if generation:
        return generation
    return 1 if _human_review_is_blocking(ids[node_id], result) else 0


def _status_rank(status: str) -> int:
    value = str(status or "pending").lower()
    if value in {"passed", "failed", "skipped", "cancelled"}:
        return 5
    if value == "reviewing":
        return 4
    if value in {"in_progress", "running", "working"}:
        return 3
    if value in {"dispatched", "sent"}:
        return 2
    if value in {"assigned", "queued"}:
        return 1
    return 0


def _node_has_active_repair_context(node: dict[str, Any]) -> bool:
    """Return true when a failed eval has opened a repair/re-eval generation.

    During repair, stale `node_results` from the failed evaluator can briefly
    disagree with the inline node state. The inline repair context is the
    authoritative signal that the failure is not terminal yet.
    """
    repair_context = node.get("repair_context")
    if not isinstance(repair_context, dict):
        return False
    inline_status = str(node.get("status", "") or "").strip().lower()
    if inline_status not in REPAIR_ACTIVE_STATUSES:
        return False
    return bool(repair_context.get("attempt") or repair_context.get("created_at"))


def _node_eval_json_candidates(graph: dict[str, Any], node_id: str) -> list[Path]:
    node = _node_map(graph)[node_id]
    result = _node_results(graph).get(node_id) if isinstance(_node_results(graph).get(node_id), dict) else {}
    sid = _sprint_id_for_graph(graph)
    artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), dict) else {}
    result_artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    raw_candidates = [
        node.get("eval_json"),
        result.get("eval_json"),
        artifacts.get("eval_json"),
        result_artifacts.get("eval_json"),
        str(SPRINTS_DIR / f"{sid}.{node_id}-eval.json") if sid else "",
    ]
    candidates: list[Path] = []
    for raw in raw_candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        try:
            candidates.append(Path(text).expanduser())
        except Exception:
            continue
    return candidates


def _first_existing_path(candidates: list[Path]) -> Path | None:
    for path in candidates:
        try:
            if path.exists():
                return path
        except Exception:
            continue
    return None


def _portable_artifact_ref(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
        sprint_root = SPRINTS_DIR.expanduser().resolve()
        if resolved.parent == sprint_root:
            return resolved.name
        return str(resolved)
    except Exception:
        return str(path)


def _workspace_root() -> str:
    explicit = str(os.environ.get("SOLAR_WORKSPACE_ROOT") or "").strip()
    if explicit:
        return explicit
    cwd = str(Path.cwd())
    if cwd:
        return cwd
    return str(HARNESS_DIR.parent)


def _normalize_eval_sidecar_payload(
    payload: dict[str, Any],
    *,
    sid: str,
    node_id: str,
    command_line: str,
) -> tuple[dict[str, Any], bool]:
    changed = False
    normalized = dict(payload)
    defaults = {
        "schema_version": "solar.eval.v1",
        "sprint_id": sid,
        "node_id": node_id,
        "generated_by": "graph_scheduler.doctor",
        "generation_mode": "repair_backfill",
        "command_line": command_line,
        "workspace_root": _workspace_root(),
    }
    verdict = str(normalized.get("verdict") or "").strip().upper()
    proof_level = "independent_verification" if verdict in {"PASS", "FAIL"} else "unknown"
    defaults["proof_level"] = proof_level
    for key, value in defaults.items():
        current = normalized.get(key)
        if current in (None, ""):
            normalized[key] = value
            changed = True
    return normalized, changed


def _sync_node_evidence_refs(
    graph: dict[str, Any],
    node_id: str,
    *,
    repair: bool = False,
    command_line: str = "python3 lib/graph_scheduler.py doctor --repair",
) -> dict[str, Any]:
    node = _node_map(graph)[node_id]
    sid = _sprint_id_for_graph(graph)
    graph.setdefault("node_results", {})
    result = graph["node_results"].setdefault(node_id, {})
    artifacts = node.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
        node["artifacts"] = artifacts
    result_artifacts = result.get("artifacts")
    if not isinstance(result_artifacts, dict):
        result_artifacts = {}
        result["artifacts"] = result_artifacts

    outcome = {"issues": [], "repairs": []}

    handoff_path = _first_existing_path(_node_handoff_candidates(graph, node_id))
    if handoff_path is not None:
        handoff_ref = _portable_artifact_ref(handoff_path)
        if node.get("handoff_md") != handoff_ref:
            outcome["issues"].append({"type": "handoff_exists_inline_missing", "node": node_id, "path": str(handoff_path)})
            if repair:
                node["handoff_md"] = handoff_ref
                artifacts["handoff_md"] = handoff_ref
                result_artifacts["handoff_md"] = handoff_ref
                outcome["repairs"].append({"type": "handoff_exists_inline_missing", "node": node_id, "repair": "backfilled_handoff_md"})

    eval_path = _first_existing_path(_node_eval_json_candidates(graph, node_id))
    if eval_path is None:
        stale_eval_values = {
            "node": node.get("eval_json"),
            "result": result.get("eval_json"),
            "artifact": artifacts.get("eval_json"),
            "result_artifact": result_artifacts.get("eval_json"),
        }
        if any(str(value or "").strip() for value in stale_eval_values.values()):
            outcome["issues"].append({"type": "stale_eval_ref_missing_file", "node": node_id, "values": stale_eval_values})
            if repair:
                node.pop("eval_json", None)
                result.pop("eval_json", None)
                artifacts.pop("eval_json", None)
                result_artifacts.pop("eval_json", None)
                outcome["repairs"].append({"type": "stale_eval_ref_missing_file", "node": node_id, "repair": "cleared_stale_eval_json_refs"})
        return outcome
    eval_ref = _portable_artifact_ref(eval_path)
    inline_values = {
        "node": node.get("eval_json"),
        "result": result.get("eval_json"),
        "artifact": artifacts.get("eval_json"),
        "result_artifact": result_artifacts.get("eval_json"),
    }
    if any(not value for value in inline_values.values()):
        outcome["issues"].append({"type": "eval_exists_inline_missing", "node": node_id, "path": str(eval_path)})
        if repair:
            node["eval_json"] = eval_ref
            result["eval_json"] = eval_ref
            artifacts["eval_json"] = eval_ref
            result_artifacts["eval_json"] = eval_ref
            outcome["repairs"].append({"type": "eval_exists_inline_missing", "node": node_id, "repair": "backfilled_eval_json"})
    elif any(str(value) != eval_ref for value in inline_values.values()):
        outcome["issues"].append({"type": "eval_ref_drift", "node": node_id, "path": str(eval_path), "values": inline_values})
        if repair:
            node["eval_json"] = eval_ref
            result["eval_json"] = eval_ref
            artifacts["eval_json"] = eval_ref
            result_artifacts["eval_json"] = eval_ref
            outcome["repairs"].append({"type": "eval_ref_drift", "node": node_id, "repair": "normalized_eval_json_ref"})

    try:
        payload = json.loads(eval_path.read_text(encoding="utf-8"))
    except Exception:
        return outcome
    if not isinstance(payload, dict):
        return outcome
    normalized, changed = _normalize_eval_sidecar_payload(
        payload,
        sid=sid,
        node_id=node_id,
        command_line=command_line,
    )
    if changed:
        outcome["issues"].append({"type": "eval_missing_provenance", "node": node_id, "path": str(eval_path)})
        if repair:
            tmp = eval_path.with_suffix(eval_path.suffix + ".tmp")
            tmp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, eval_path)
            outcome["repairs"].append({"type": "eval_missing_provenance", "node": node_id, "repair": "normalized_eval_sidecar_provenance"})
    return outcome


def _node_handoff_candidates(graph: dict[str, Any], node_id: str) -> list[Path]:
    node = _node_map(graph)[node_id]
    sid = _sprint_id_for_graph(graph)
    artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), dict) else {}
    raw_candidates = [
        node.get("handoff_md"),
        artifacts.get("handoff_md"),
        str(SPRINTS_DIR / f"{sid}.{node_id}-handoff.md") if sid else "",
    ]
    candidates: list[Path] = []
    for raw in raw_candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        try:
            candidates.append(Path(text).expanduser())
        except Exception:
            continue
    return candidates


def _node_has_eval_json(graph: dict[str, Any], node_id: str) -> bool:
    return any(path.exists() for path in _node_eval_json_candidates(graph, node_id))


def _node_has_handoff(graph: dict[str, Any], node_id: str) -> bool:
    return any(path.exists() for path in _node_handoff_candidates(graph, node_id))


def _node_has_independent_eval_report(graph: dict[str, Any], node_id: str) -> bool:
    """True if an INDEPENDENT evaluator reviewed this node -- a non-empty ``{node}-eval.md`` or an
    ``{node}-eval-dispatch`` sidecar exists (an evaluator other than the executing agent was run)."""
    for json_path in _node_eval_json_candidates(graph, node_id):
        name = json_path.name
        if not name.endswith("-eval.json"):
            continue
        stem = name[: -len("-eval.json")]
        try:
            md_path = json_path.with_name(f"{stem}-eval.md")
            if md_path.exists() and md_path.stat().st_size > 0:
                return True
            if any(json_path.parent.glob(f"{stem}-eval-dispatch*.md")):
                return True
        except Exception:
            continue
    return False


def _node_eval_is_self_graded(graph: dict[str, Any], node_id: str) -> bool:
    """The node's verdict was written by the EXECUTING agent itself (generation_mode=manual_node_eval)
    with no independent evaluator report. A self-graded verdict is not a genuine evaluation and must
    not certify PASS -- the back-half of a DAG was passing on self-reported JSON with no eval.md (the
    eval-backfill false-positive vector)."""
    if _node_has_independent_eval_report(graph, node_id):
        return False
    # Gate/verifier nodes verify via a write_scope verdict artifact (e.g. review_decision.yaml) consumed
    # by _node_gate_verdict_ok, not a per-node eval.md, and produce NO handoff. Only EXECUTOR nodes (which
    # produce a handoff) are at risk of self-grading their own work; gate nodes are governed by the
    # verdict-artifact gate, so do not flag them here.
    if not _node_has_handoff(graph, node_id):
        return False
    # The executor produced a handoff AND a verdict (eval.json) but NO independent evaluator report
    # (no non-empty {node}-eval.md, no {node}-eval-dispatch). The verdict is self-graded/backfilled
    # regardless of how it was written (generation_mode varies / may be absent) -- not a genuine eval.
    return _node_has_eval_json(graph, node_id)


def _passed_without_required_eval(graph: dict[str, Any], node_id: str) -> bool:
    """Treat handoff-backed passed nodes without a GENUINE eval as not yet passed (fail-closed)."""
    if _node_has_handoff(graph, node_id) and not _node_has_eval_json(graph, node_id):
        return True
    # Fail-closed on the eval-backfill vector: a self-graded verdict (executing agent wrote its own
    # manual_node_eval with no independent evaluator report) is NOT a genuine evaluation -> unverified.
    return _node_eval_is_self_graded(graph, node_id)


def _validate_contract_closeout_receipt(
    graph: dict[str, Any],
    node_id: str,
    receipt: dict[str, Any] | None,
) -> None:
    """Validate the dispatcher-owned receipt required to commit contracted PASS.

    The scheduler remains the low-level status writer, but it is no longer a
    second verdict authority.  Only the dispatcher closeout transaction can
    assemble this receipt after consuming evaluator evidence, persisting the
    artifact manifest, checking proof/quality gates, and completing any
    required workspace publication.
    """
    if not isinstance(receipt, dict):
        raise ValueError(f"contracted_pass_requires_closeout_authority:{node_id}")
    sid = _sprint_id_for_graph(graph)
    required_scalars = {
        "schema": "solar.node_closeout.v1",
        "sid": sid,
        "node_id": node_id,
        "verdict": "passed",
    }
    for key, expected in required_scalars.items():
        if str(receipt.get(key) or "") != str(expected or ""):
            raise ValueError(f"contracted_pass_invalid_closeout_receipt:{node_id}:{key}")

    eval_receipt = receipt.get("eval") if isinstance(receipt.get("eval"), dict) else {}
    if (
        eval_receipt.get("consumable") is not True
        or not str(eval_receipt.get("record_id") or "").strip()
        or not str(eval_receipt.get("path") or "").strip()
    ):
        raise ValueError(f"contracted_pass_invalid_closeout_receipt:{node_id}:eval")
    eval_snapshot = (
        eval_receipt.get("artifact_snapshot")
        if isinstance(eval_receipt.get("artifact_snapshot"), dict)
        else {}
    )
    snapshot_digest = str(eval_snapshot.get("snapshot_digest") or "")
    try:
        eval_generation = int(eval_receipt.get("generation"))
        snapshot_generation = int(eval_snapshot.get("generation"))
    except (TypeError, ValueError):
        eval_generation = -1
        snapshot_generation = -2
    if (
        eval_snapshot.get("required") is not True
        or eval_snapshot.get("ok") is not True
        or str(eval_snapshot.get("schema") or "") != "solar.eval_artifact_snapshot.v1"
        or not str(eval_snapshot.get("path") or "").strip()
        or len(snapshot_digest) != 64
        or any(char not in "0123456789abcdef" for char in snapshot_digest)
        or snapshot_generation != eval_generation
    ):
        raise ValueError(f"contracted_pass_invalid_closeout_receipt:{node_id}:eval_snapshot")

    manifest = receipt.get("manifest") if isinstance(receipt.get("manifest"), dict) else {}
    manifest_digest = str(manifest.get("content_digest") or "")
    try:
        manifest_generation = int(manifest.get("generation"))
    except (TypeError, ValueError):
        manifest_generation = -2
    if (
        manifest.get("ok") is not True
        or str(manifest.get("schema") or "") != "solar.artifact_manifest.v1"
        or not str(manifest.get("path") or "").strip()
        or manifest.get("eval_snapshot_match") is not True
        or len(manifest_digest) != 64
        or any(char not in "0123456789abcdef" for char in manifest_digest)
        or manifest_generation != eval_generation
    ):
        raise ValueError(f"contracted_pass_invalid_closeout_receipt:{node_id}:manifest")

    for key in ("proof", "research_quality", "publication"):
        gate = receipt.get(key) if isinstance(receipt.get(key), dict) else {}
        if gate.get("ok") is not True:
            raise ValueError(f"contracted_pass_invalid_closeout_receipt:{node_id}:{key}")
    publication = receipt.get("publication") if isinstance(receipt.get("publication"), dict) else {}
    if publication.get("required") is True:
        published_digest = str(publication.get("published_digest") or "")
        publication_manifest_digest = str(publication.get("manifest_digest") or "")
        try:
            published_count = int(publication.get("published_count") or 0)
        except (TypeError, ValueError):
            published_count = 0
        if (
            published_count < 1
            or publication_manifest_digest != manifest_digest
            or len(published_digest) != 64
            or any(char not in "0123456789abcdef" for char in published_digest)
        ):
            raise ValueError(f"contracted_pass_invalid_closeout_receipt:{node_id}:publication_digest")


def _assert_pass_mark_allowed(
    graph: dict[str, Any],
    node_id: str,
    status: str,
    *,
    closeout_receipt: dict[str, Any] | None = None,
) -> None:
    normalized = str(status or "").lower()
    if normalized != "passed":
        return
    if bool(str((graph or {}).get("workflow_contract_id") or "").strip()):
        _validate_contract_closeout_receipt(graph, node_id, closeout_receipt)
        return
    if _passed_without_required_eval(graph, node_id):
        raise ValueError(f"passed_requires_eval_json:{node_id}")


def _assert_human_review_status_write_allowed(
    graph: dict[str, Any],
    node_id: str,
    status: str,
) -> None:
    ids = _node_map(graph)
    if node_id not in ids:
        raise ValueError(f"unknown node: {node_id}")
    normalized = str(status or "").strip().lower()
    result = _node_results(graph).get(node_id)
    blocked = _human_review_is_blocking(ids[node_id], result)
    if blocked and normalized != HUMAN_REVIEW_STATUS:
        generation = human_review_generation(graph, node_id)
        raise ValueError(
            f"needs_human_review_requires_explicit_human_resume:{node_id}:generation={generation}"
        )
    if normalized == HUMAN_REVIEW_STATUS and not blocked:
        raise ValueError(f"needs_human_review_requires_authoritative_entry:{node_id}")


def assert_node_status_write_allowed(
    graph: dict[str, Any],
    node_id: str,
    status: str,
) -> None:
    """Guard low-level status writers that cannot carry special authority.

    Contracted PASS must use :func:`commit_verified_node_pass`, and human
    escalation/resume must use their dedicated generation-bearing seams.
    """
    _assert_human_review_status_write_allowed(graph, node_id, status)
    _assert_pass_mark_allowed(graph, node_id, status)


def _ensure_required_gate_node_mapping(graph: dict[str, Any]) -> int:
    ids = _node_map(graph)
    if not ids:
        return 0
    required = [str(g) for g in (graph.get("required_gates") or []) if g]
    if not required:
        return 0
    required_set = set(required)
    dag_variant = str(graph.get("dag_variant") or "").strip().lower()
    mapping: dict[str, str] = {}
    if dag_variant == "short" or required_set == {"G_IMPL", "G_TEST", "G_REVIEW"}:
        mapping = {"S1": "G_IMPL", "S2": "G_TEST", "S3": "G_REVIEW"}
    elif dag_variant == "parallel_spec":
        mapping = {
            "S1": "G_PLAN",
            "S2": "G_IMPL",
            "S3": "G_IMPL",
            "S4": "G_VERIFY",
            "S5": "G_REVIEW",
        }
    elif dag_variant == "standard" or required_set == {"G_PLAN", "G_IMPL", "G_VERIFY", "G_REVIEW"}:
        mapping = {
            "S1": "G_PLAN",
            "S2": "G_IMPL",
            "S3": "G_VERIFY",
            "S4": "G_REVIEW",
            "S5": "G_REVIEW",
        }
    elif dag_variant == "research" or required_set == {"G_SOURCE", "G_EVIDENCE", "G_SYNTHESIS", "G_REVIEW"}:
        mapping = {
            "R1": "G_SOURCE",
            "R2": "G_EVIDENCE",
            "R3": "G_EVIDENCE",
            "R4": "G_SYNTHESIS",
            "R5": "G_REVIEW",
            "R6": "G_REVIEW",
        }

    assigned = 0
    for node_id, node in ids.items():
        if node.get("gate"):
            continue
        gate = mapping.get(node_id)
        if gate and gate in required_set:
            node["gate"] = gate
            assigned += 1

    owners: dict[str, list[str]] = {gate: [] for gate in required}
    for node_id, node in ids.items():
        gate = str(node.get("gate") or "")
        if gate in owners:
            owners[gate].append(node_id)

    missing = [gate for gate in required if not owners.get(gate)]
    if not missing:
        return assigned

    try:
        ordered_ids = topo_order(graph)
    except Exception:
        ordered_ids = list(ids.keys())
    unassigned = [node_id for node_id in ordered_ids if not ids[node_id].get("gate")]
    for gate, node_id in zip(missing, unassigned):
        ids[node_id]["gate"] = gate
        assigned += 1
    return assigned


def node_recorded_status(graph: dict[str, Any], node_id: str) -> str:
    """The node's RECORDED status — the inline/node_results/gate_results fold
    WITHOUT node_status()'s fail-closed passed-without-required-eval downgrade.

    This is the AC-R4.1 hold discriminator (round-4 G1): the real v5 shape
    (handoff present, eval.json missing) is exactly the state that produces a
    mechanical ``research_eval_json_missing`` FAIL, and the downgrade projects
    it as effective "reviewing" while the writers recorded "passed". Policy
    rules about "a passed node" must consult what was recorded, not the
    downgraded view, or they self-bypass on the very shape they exist for."""
    _ensure_required_gate_node_mapping(graph)
    results = _node_results(graph)
    node = _node_map(graph)[node_id]
    result = results.get(node_id) if isinstance(results.get(node_id), dict) else {}
    if _human_review_is_blocking(node, result):
        return HUMAN_REVIEW_STATUS
    gate = node.get("gate")
    gate_results = graph.get("gate_results") or {}
    gate_passed = bool(
        gate
        and isinstance(gate_results.get(gate), dict)
        and gate_results[gate].get("status") == "passed"
    )
    if node_id in results and isinstance(results[node_id], dict):
        result_status = str(results[node_id].get("status", "") or "").lower()
        node_status_value = str(node.get("status", "pending") or "pending").lower()
        if _node_has_active_repair_context(node) and result_status in (TERMINAL_STATUSES | {"needs_human_review"}):
            status = node_status_value or "failed_review"
        elif gate_passed and "failed" not in {result_status, node_status_value}:
            status = "passed"
        else:
            result_rank = _status_rank(result_status)
            node_rank = _status_rank(node_status_value)
            if result_rank != node_rank:
                status = result_status if result_rank > node_rank else node_status_value
            else:
                result_ts = _parse_ts(results[node_id].get("updated_at"))
                node_ts = _parse_ts(node.get("updated_at"))
                if result_ts and node_ts and node_ts > result_ts:
                    status = node_status_value
                else:
                    status = result_status
    elif gate_passed and str(node.get("status", "pending") or "pending").lower() != "failed":
        status = "passed"
    else:
        status = str(node.get("status", "pending") or "pending").lower()
    return status


def node_status(graph: dict[str, Any], node_id: str) -> str:
    status = node_recorded_status(graph, node_id)
    if status == "passed" and _passed_without_required_eval(graph, node_id):
        return "reviewing"
    return status


def _depends_on(node: dict[str, Any]) -> list[str]:
    deps = node.get("depends_on", [])
    if deps is None:
        return []
    if not isinstance(deps, list):
        raise ValueError(f"{node.get('id')}.depends_on must be a list")
    return [str(d) for d in deps]


def _is_external_dependency(dep: str) -> bool:
    return str(dep or "").startswith("external:")


def _internal_depends_on(node: dict[str, Any]) -> list[str]:
    return [dep for dep in _depends_on(node) if not _is_external_dependency(dep)]


def _estimated_cost(node: dict[str, Any]) -> float:
    try:
        return float(node.get("estimated_cost", 1) or 1)
    except Exception:
        return 1.0


def graph_parallelism_metrics(graph: dict[str, Any]) -> dict[str, Any]:
    ids = _node_map(graph)
    source_nodes: list[str] = []
    missing_write_scope: list[str] = []
    for node_id, node in ids.items():
        if not _internal_depends_on(node):
            source_nodes.append(node_id)
        if "write_scope" not in node or not node.get("write_scope"):
            missing_write_scope.append(node_id)
    initial_ready: list[str] = []
    for node_id, node in ids.items():
        status = node_status(graph, node_id)
        if status in TERMINAL_STATUSES or status in ACTIVE_STATUSES or status not in READY_STATUSES:
            continue
        deps = _internal_depends_on(node)
        if all(_is_passed(graph, dep) for dep in deps):
            initial_ready.append(node_id)
    return {
        "initial_ready_width": len(initial_ready),
        "initial_ready_nodes": initial_ready,
        "source_width": len(source_nodes),
        "source_nodes": source_nodes,
        "missing_write_scope_count": len(missing_write_scope),
        "missing_write_scope_nodes": missing_write_scope,
    }


def validate_graph(graph: dict[str, Any]) -> dict[str, Any]:
    ids = _node_map(graph)
    errors: list[str] = []
    warnings: list[str] = []

    for node_id, node in ids.items():
        for dep in _depends_on(node):
            if _is_external_dependency(dep):
                continue
            if dep not in ids:
                errors.append(f"{node_id} depends on missing node {dep}")
        if "write_scope" not in node or not node.get("write_scope"):
            warnings.append(f"{node_id} missing write_scope; scheduler will serialize it")
        if "acceptance" not in node:
            warnings.append(f"{node_id} missing acceptance")
        if "required_capabilities" not in node:
            try:
                from capability_inference import infer_node_capabilities  # noqa: WPS433

                inferred = infer_node_capabilities(node)
                if inferred.get("capabilities"):
                    caps = ",".join(inferred["capabilities"])
                    warnings.append(f"{node_id} inferred capabilities available but missing required_capabilities: {caps}")
            except Exception:
                pass

    try:
        topo_order(graph)
    except ValueError as exc:
        errors.append(str(exc))

    try:
        from architecture_guard import assess_graph  # noqa: WPS433

        arch = assess_graph(graph)
        errors.extend(f"architecture_guard:{e}" for e in arch.get("errors", []))
        warnings.extend(f"architecture_guard:{w}" for w in arch.get("warnings", []))
    except Exception as exc:
        warnings.append(f"architecture_guard unavailable: {type(exc).__name__}")

    parallelism = graph_parallelism_metrics(graph) if not errors else {}
    quality = graph.get("quality_gates") if isinstance(graph.get("quality_gates"), dict) else {}
    parallelism_gate = quality.get("parallelism") if isinstance(quality.get("parallelism"), dict) else {}
    min_ready_width = int(
        parallelism_gate.get("min_ready_width")
        or quality.get("min_ready_width")
        or graph.get("min_ready_width")
        or 0
    )
    if min_ready_width > 0 and parallelism.get("initial_ready_width", 0) < min_ready_width:
        errors.append(
            "parallelism_quality:"
            f" initial_ready_width={parallelism.get('initial_ready_width', 0)}"
            f" < min_ready_width={min_ready_width}"
        )

    return {
        "ok": not errors,
        "sprint_id": graph.get("sprint_id"),
        "node_count": len(ids),
        "parallelism": parallelism,
        "errors": errors,
        "warnings": warnings,
    }


def topo_order(graph: dict[str, Any]) -> list[str]:
    ids = _node_map(graph)
    indegree = {node_id: 0 for node_id in ids}
    outgoing = {node_id: [] for node_id in ids}

    for node_id, node in ids.items():
        for dep in _depends_on(node):
            if _is_external_dependency(dep):
                continue
            if dep not in ids:
                raise ValueError(f"{node_id} depends on missing node {dep}")
            indegree[node_id] += 1
            outgoing[dep].append(node_id)

    queue = sorted([node_id for node_id, deg in indegree.items() if deg == 0])
    order: list[str] = []
    while queue:
        node_id = queue.pop(0)
        order.append(node_id)
        for child in sorted(outgoing[node_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
                queue.sort()

    if len(order) != len(ids):
        cycle_nodes = sorted([node_id for node_id, deg in indegree.items() if deg > 0])
        raise ValueError("cycle detected: " + ", ".join(cycle_nodes))
    return order


def topo_layers(graph: dict[str, Any]) -> list[list[str]]:
    ids = _node_map(graph)
    remaining = set(ids)
    passed: set[str] = set()
    layers: list[list[str]] = []

    while remaining:
        layer = sorted([
            node_id for node_id in remaining
            if all(dep in passed for dep in _internal_depends_on(ids[node_id]))
        ])
        if not layer:
            raise ValueError("cycle detected while building layers")
        layers.append(layer)
        remaining -= set(layer)
        passed.update(layer)
    return layers


def critical_path(graph: dict[str, Any]) -> dict[str, Any]:
    ids = _node_map(graph)
    order = topo_order(graph)
    best_cost: dict[str, float] = {}
    best_path: dict[str, list[str]] = {}

    for node_id in order:
        node = ids[node_id]
        deps = _internal_depends_on(node)
        if not deps:
            best_cost[node_id] = _estimated_cost(node)
            best_path[node_id] = [node_id]
            continue
        parent = max(deps, key=lambda dep: best_cost.get(dep, 0))
        best_cost[node_id] = best_cost.get(parent, 0) + _estimated_cost(node)
        best_path[node_id] = best_path.get(parent, [parent]) + [node_id]

    if not order:
        return {"cost": 0, "path": []}
    end = max(order, key=lambda node_id: best_cost.get(node_id, 0))
    return {"cost": best_cost[end], "path": best_path[end]}


def _is_passed(graph: dict[str, Any], node_id: str) -> bool:
    return node_status(graph, node_id) in PASS_STATUSES


def blocked_external_prerequisites(graph: dict[str, Any]) -> list[dict[str, Any]]:
    blocked = list(iter_blocked(graph, SPRINTS_DIR))
    seen = {str(item.get("requirement") or "") for item in blocked}
    for node in graph.get("nodes") or []:
        node_id = str(node.get("id") or "")
        for dep in _depends_on(node):
            if not _is_external_dependency(dep):
                continue
            ok, detail = evaluate_prerequisite(dep, SPRINTS_DIR)
            detail["source"] = "depends_on"
            detail["node_id"] = node_id
            key = str(detail.get("requirement") or dep)
            if not ok and key not in seen:
                blocked.append(detail)
                seen.add(key)
    return blocked


def node_admission_status(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the final scheduler admission decision for a single node."""
    validation = validate_graph(graph)
    runtime_errors = [
        str(error)
        for error in validation.get("errors", [])
        if not str(error).startswith("parallelism_quality:")
    ]
    if runtime_errors:
        return {
            "admitted": False,
            "reason": "graph_validation_failed",
            "errors": runtime_errors,
        }

    ids = _node_map(graph)
    if node_id not in ids:
        return {"admitted": False, "reason": "unknown_node", "node": node_id}

    node = ids[node_id]
    status = node_status(graph, node_id)
    if status in TERMINAL_STATUSES:
        return {"admitted": False, "reason": "terminal_status", "node": node_id, "status": status}
    if status in ACTIVE_STATUSES:
        return {"admitted": False, "reason": "active_status", "node": node_id, "status": status}
    if status not in READY_STATUSES:
        return {"admitted": False, "reason": "not_ready_status", "node": node_id, "status": status}

    blocked_external = [
        item
        for item in blocked_external_prerequisites(graph)
        if not item.get("node_id") or str(item.get("node_id")) == node_id
    ]
    if blocked_external:
        return {
            "admitted": False,
            "reason": "external_prerequisite_blocked",
            "node": node_id,
            "status": status,
            "blocked_prerequisites": blocked_external,
        }

    unmet: list[str] = []
    nonblocking_human_review: list[str] = []
    for dep in _internal_depends_on(node):
        if _is_passed(graph, dep):
            continue
        if (
            dep in ids
            and node_status(graph, dep) == HUMAN_REVIEW_STATUS
            and not _human_review_blocks_dependents(graph, ids.get(dep))
        ):
            nonblocking_human_review.append(dep)
            continue
        unmet.append(dep)
    if unmet:
        return {
            "admitted": False,
            "reason": "dependencies_unmet",
            "node": node_id,
            "status": status,
            "unmet_dependencies": unmet,
            "dependencies": _internal_depends_on(node),
        }

    return {
        "admitted": True,
        "reason": "ready",
        "node": node_id,
        "status": status,
        "dependencies": _internal_depends_on(node),
        "nonblocking_human_review_dependencies": nonblocking_human_review,
    }


def ready_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    validation = validate_graph(graph)
    runtime_errors = [
        str(error)
        for error in validation.get("errors", [])
        if not str(error).startswith("parallelism_quality:")
    ]
    if runtime_errors:
        raise ValueError("; ".join(runtime_errors))
    if blocked_external_prerequisites(graph):
        return []

    ids = _node_map(graph)
    ready: list[dict[str, Any]] = []
    for node_id in topo_order(graph):
        status = node_status(graph, node_id)
        if status in TERMINAL_STATUSES or status in ACTIVE_STATUSES:
            continue
        if status not in READY_STATUSES:
            continue
        deps = _internal_depends_on(ids[node_id])
        if all(
            _is_passed(graph, dep)
            or (
                # warn_and_continue (design §2 change 2): a needs_human_review dep
                # with the non-blocking contract policy does not gate readiness —
                # without this half, the policy would trade the skip-cascade for a
                # silent pending wedge (an R7 violation).
                dep in ids
                and node_status(graph, dep) == "needs_human_review"
                and not _human_review_blocks_dependents(graph, ids.get(dep))
            )
            for dep in deps
        ):
            ready.append(deepcopy(ids[node_id]))
    return ready


def _scope_list(node: dict[str, Any]) -> list[str]:
    scopes = node.get("write_scope")
    if not scopes:
        return []
    if isinstance(scopes, str):
        return [scopes]
    if not isinstance(scopes, list):
        raise ValueError(f"{node.get('id')}.write_scope must be a string or list")
    return [str(scope) for scope in scopes if str(scope)]


def _scope_overlap(a: str, b: str) -> bool:
    if a == b:
        return True
    a_norm = a.rstrip("/") + "/"
    b_norm = b.rstrip("/") + "/"
    return a_norm.startswith(b_norm) or b_norm.startswith(a_norm)


def write_scope_conflict(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a_scopes = _scope_list(a)
    b_scopes = _scope_list(b)

    # Missing write_scope means exclusive writer. It cannot safely share a batch.
    if not a_scopes or not b_scopes:
        return True
    return any(_scope_overlap(sa, sb) for sa in a_scopes for sb in b_scopes)


def _node_effect_union(node: dict[str, Any]) -> dict[str, list[str]]:
    for key in ("effect_union",):
        raw = node.get(key)
        if isinstance(raw, dict):
            return {str(k): [str(item) for item in (v or [])] for k, v in raw.items()}
    for key in ("physical_plan_ir", "capsule_plan_ir"):
        raw = node.get(key)
        if isinstance(raw, dict):
            effect_union = raw.get("effect_union")
            if isinstance(effect_union, dict):
                return {str(k): [str(item) for item in (v or [])] for k, v in effect_union.items()}
    return {}


def _node_has_exclusive_effect(node: dict[str, Any]) -> bool:
    effect_union = _node_effect_union(node)
    risks = {str(item) for item in effect_union.get("risk", [])}
    writes = {str(item) for item in effect_union.get("write", [])}
    executes = {str(item) for item in effect_union.get("execute", [])}
    if risks & {"secrets_access", "destructive_shell", "git_push", "patch_scope_drift"}:
        return True
    if "repo.worktree" in writes and executes:
        return True
    return False


def effect_conflict(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return _node_has_exclusive_effect(a) or _node_has_exclusive_effect(b)


def _batch_ready_nodes(nodes: list[dict[str, Any]], max_parallel: int | None = None) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    for node in nodes:
        placed = False
        for batch in batches:
            if max_parallel and len(batch) >= max_parallel:
                continue
            if any(write_scope_conflict(node, other) for other in batch):
                continue
            if any(effect_conflict(node, other) for other in batch):
                continue
            batch.append(node)
            placed = True
            break
        if not placed:
            batches.append([node])
    return batches


def make_batches(graph: dict[str, Any], max_parallel: int | None = None) -> dict[str, Any]:
    blocked = blocked_external_prerequisites(graph)
    nodes = ready_nodes(graph)
    effective_max_parallel = max_parallel if max_parallel is not None else _effective_graph_max_parallel(None)
    batches = _batch_ready_nodes(nodes, max_parallel=effective_max_parallel)
    return {
        "ok": True,
        "sprint_id": graph.get("sprint_id"),
        "blocked_prerequisites": blocked,
        "batch_count": len(batches),
        "batches": [
            {
                "id": f"batch-{idx + 1}",
                "join_gate": [node.get("gate") for node in batch if node.get("gate")],
                "nodes": [node["id"] for node in batch],
            }
            for idx, batch in enumerate(batches)
        ],
    }


def _worker_busy(worker: dict[str, Any]) -> bool:
    return bool(worker.get("busy")) or str(worker.get("status", "")).lower() in {"busy", "leased", "running"}


def _worker_unavailable_reason(worker: dict[str, Any]) -> str:
    return str(worker.get("unavailable_reason") or "").strip()


def _worker_quota_exhausted(worker: dict[str, Any], preferred_model: str | None = None) -> bool:
    exhausted = worker.get("quota_exhausted", False)
    if isinstance(exhausted, bool):
        return exhausted
    if isinstance(exhausted, list):
        exhausted_aliases: set[str] = set()
        for item in exhausted:
            exhausted_aliases.update(_model_aliases(str(item)))
        if preferred_model:
            return bool(_model_aliases(preferred_model) & exhausted_aliases)
        model_aliases = [_model_aliases(str(model)) for model in worker.get("models", []) or []]
        model_aliases = [aliases for aliases in model_aliases if aliases]
        return bool(model_aliases) and all(aliases & exhausted_aliases for aliases in model_aliases)
    return False


def _model_aliases(value: str | None) -> set[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return set()
    aliases = {raw}
    if raw in {"sonnet", "claude-sonnet", "anthropic-sonnet"}:
        aliases.update({"sonnet", "claude-sonnet", "anthropic-sonnet", "claude", "anthropic"})
    elif raw in {"opus", "claude-opus", "anthropic-opus", "opus-4.7", "opus-4-7", "claude-opus-4.7", "claude-opus-4-7"}:
        aliases.update({"opus", "claude-opus", "anthropic-opus", "opus-4.7", "opus-4-7", "claude", "anthropic"})
    elif raw in {"glm", "glm-5", "glm-5.1", "zhipu", "zhipu-glm-5.1"}:
        aliases.update({"glm", "glm-5", "glm-5.1", "zhipu", "zhipu-glm-5.1"})
    elif raw in {"deepseek", "deepseek-v4", "deepseek-v4-pro"}:
        aliases.update({"deepseek", "deepseek-v4", "deepseek-v4-pro"})
    return aliases


def _model_match(worker: dict[str, Any], preferred_model: str | None) -> bool:
    if not preferred_model:
        return True
    models = [str(m).lower() for m in worker.get("models", [])]
    if not models:
        return True
    preferred = _model_aliases(preferred_model)
    available: set[str] = set()
    for model in models:
        available.update(_model_aliases(model))
    return bool(preferred & available)


def _model_requires_strict_match(preferred_model: str | None, strict_model: bool = False) -> bool:
    if not preferred_model or not strict_model:
        return False
    normalized = preferred_model.lower()
    return normalized in {"glm", "glm-5", "glm-5.1", "zhipu"}


def _label_aliases(value: Any) -> set[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return set()
    aliases = {raw}
    normalized = raw.replace("-", ".").replace("_", ".").replace(" ", ".")
    aliases.add(normalized)
    aliases.add(raw.replace("-", "_"))
    aliases.add(raw.replace(".", "-"))
    parts = [part.strip() for part in raw.split(".") if part.strip()]
    normalized_parts = [part.strip() for part in normalized.split(".") if part.strip()]
    if len(parts) > 1:
        for end in range(1, len(parts)):
            aliases.add(".".join(parts[:end]))
        aliases.add(parts[-1])
        if parts[-1] == "design":
            aliases.add("architecture")
    if len(normalized_parts) > 1:
        for end in range(1, len(normalized_parts)):
            aliases.add(".".join(normalized_parts[:end]))
        aliases.add(normalized_parts[-1])
        aliases.add("-".join(normalized_parts))
        aliases.add("_".join(normalized_parts))
        if normalized_parts[-1] == "design":
            aliases.add("architecture")
    # Alias groups are direct equivalence declarations, not a graph whose
    # overlapping members should be transitively closed.  Expanding a group
    # into all of its labels made matching order-dependent: algorithm_design
    # reached api-design, the later API group then reached python, and a
    # Python-only worker falsely satisfied an algorithm-design requirement.
    # A stable group key preserves direct synonyms while preventing one group
    # from using labels introduced by another group as a bridge.
    direct_aliases = set(aliases)
    for index, group in enumerate(LABEL_ALIAS_GROUPS):
        normalized_group = {str(item).strip().lower() for item in group}
        if direct_aliases & normalized_group:
            aliases.add(f"alias-group:{index}")
    return aliases


def _skill_aliases(value: Any) -> set[str]:
    return _label_aliases(value)


_REGISTERED_SKILLS_CACHE: set[str] | None = None


def _registered_skill_ids() -> set[str]:
    """Skill IDs defined in the operator-skill registry (skill-operator-bindings.yaml).

    Used to normalize node.required_skills: free-form/unregistered strings the planner
    invents are unenforceable (no worker advertises them) and would falsely strand nodes.
    Fail-open: if the registry is unreadable, return empty so normalization is a no-op.
    """
    global _REGISTERED_SKILLS_CACHE
    if _REGISTERED_SKILLS_CACHE is not None:
        return _REGISTERED_SKILLS_CACHE
    ids: set[str] = set()
    try:
        import yaml  # noqa: WPS433
        path = HARNESS_DIR / "config" / "skill-operator-bindings.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))

        def _collect(obj: Any) -> None:
            if isinstance(obj, dict):
                sid = obj.get("skill_id")
                if sid:
                    ids.add(str(sid))
                for value in obj.values():
                    _collect(value)
            elif isinstance(obj, list):
                for value in obj:
                    _collect(value)

        _collect(data)
    except Exception:
        return set()
    _REGISTERED_SKILLS_CACHE = ids
    return ids


def _is_registered_skill(skill: str) -> bool:
    registered = _registered_skill_ids()
    if not registered:
        return True  # fail-open: registry unreadable -> do not strip (preserve behavior)
    aliases = _skill_aliases(skill)
    for known in registered:
        if _skill_aliases(known) & aliases:
            return True
    return False


def _skill_match_count(worker: dict[str, Any], required_skills: list[str]) -> int:
    if not required_skills:
        return 0
    worker_aliases: set[str] = set()
    for skill in worker.get("skills", []) or []:
        worker_aliases.update(_skill_aliases(skill))

    matches = 0
    for required in required_skills:
        if _skill_aliases(required) & worker_aliases:
            matches += 1
    return matches


def _skills_match(worker: dict[str, Any], required_skills: list[str],
                  required_capabilities: list[str] | None = None) -> bool:
    if not required_skills:
        return True
    matched = _skill_match_count(worker, required_skills)
    if matched >= len(required_skills):
        return True
    if required_capabilities:
        threshold = max(1, (len(required_skills) + 1) // 2)
        return matched >= threshold
    return False


def _capability_list(obj: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("required_capabilities", "capabilities"):
        raw = obj.get(key, [])
        if isinstance(raw, str):
            values.append(raw)
        elif isinstance(raw, list):
            values.extend(str(item) for item in raw if str(item))
    return values


def _load_capability_scores() -> dict[str, float]:
    if not STATE_DB.exists():
        return {}
    try:
        conn = sqlite3.connect(str(STATE_DB), timeout=2.0)
        rows = conn.execute("SELECT capability, provider, score FROM capability_scorecards").fetchall()
        conn.close()
    except Exception:
        return {}
    scores: dict[str, float] = {}
    for capability, provider, score in rows:
        try:
            value = float(score)
        except Exception:
            value = 0.0
        scores[f"{provider}::{capability}"] = max(value, scores.get(f"{provider}::{capability}", 0.0))
        scores[f"cap::{capability}"] = max(value, scores.get(f"cap::{capability}", 0.0))
    return scores


def _worker_capabilities(worker: dict[str, Any]) -> list[str]:
    caps = _capability_list(worker)
    # Worker topology has historically mixed skill-like labels (for example
    # "cli" or "frontend") into required_capabilities. Match against both
    # fields so enriched DAG nodes are not stranded as no_matching_worker when
    # the worker advertises the ability under skills instead of capabilities.
    for item in worker.get("skills", []) or []:
        text = str(item)
        if text and text not in caps:
            caps.append(text)
    expanded: list[str] = []
    seen: set[str] = set()
    for item in caps:
        for alias in _label_aliases(item):
            if alias not in seen:
                seen.add(alias)
                expanded.append(alias)
    return expanded


def _capabilities_match(worker: dict[str, Any], required_capabilities: list[str]) -> bool:
    if not required_capabilities:
        return True
    caps = set(_worker_capabilities(worker))
    for item in required_capabilities:
        if not (_label_aliases(item) & caps):
            return False
    return True


def _missing_skills(worker: dict[str, Any], required_skills: list[str]) -> list[str]:
    worker_aliases: set[str] = set()
    for skill in worker.get("skills", []) or []:
        worker_aliases.update(_skill_aliases(skill))
    missing: list[str] = []
    for required in required_skills:
        if not (_skill_aliases(required) & worker_aliases):
            missing.append(str(required))
    return missing


def _missing_capabilities(worker: dict[str, Any], required_capabilities: list[str]) -> list[str]:
    worker_aliases = set(_worker_capabilities(worker))
    missing: list[str] = []
    for required in required_capabilities:
        if not (_label_aliases(required) & worker_aliases):
            missing.append(str(required))
    return missing


def _capability_score(worker: dict[str, Any], required_capabilities: list[str],
                      scores: dict[str, float]) -> float:
    if not required_capabilities:
        return 0.0
    provider = str(worker.get("provider") or worker.get("capability_provider") or "").strip()
    total = 0.0
    for cap in required_capabilities:
        if provider:
            total += scores.get(f"{provider}::{cap}", 0.0)
        total += scores.get(f"cap::{cap}", 0.0)
    if total:
        return total
    # Manual worker score escape hatch for tests/local topology files.
    try:
        return float(worker.get("capability_score", 0) or 0)
    except Exception:
        return 0.0


def _worker_role(worker: dict[str, Any]) -> str:
    return str(
        worker.get("dispatch_role")
        or worker.get("host_role")
        or worker.get("role")
        or "builder"
    ).strip().lower()


def node_dispatch_role(node: dict[str, Any]) -> str:
    """Return the logical execution role declared by a graph node.

    Worker/host role is deliberately not an input.  A planner or evaluator may
    execute on a compatible builder host, but that placement must never change
    the role used for operator selection, persona, or execution evidence.
    """
    return executable_dispatch_role(node)


def _role_penalty(node_role: str, worker_role: str) -> int | None:
    normalized_node = str(node_role or "").strip().lower() or "builder"
    normalized_worker = str(worker_role or "").strip().lower()
    if normalized_worker in {"lab", "lab-builder"}:
        normalized_worker = "builder"
    compatibility = {
        "planner": {"planner": 0, "architect": 1, "builder": 2},
        "architect": {"architect": 0, "planner": 1, "builder": 2},
        "builder": {"builder": 0},
        "evaluator": {"evaluator": 0, "builder": 1},
        "pm": {"pm": 0, "observer": 1},
    }
    return compatibility.get(normalized_node, {"builder": 0}).get(normalized_worker)


_FROZEN_PLANNING_AUTHORITY = "frozen_execution_plan_v1"


def _is_frozen_scheduler_node(graph: dict[str, Any], node: dict[str, Any]) -> bool:
    """Return whether runtime must preserve the node's frozen physical plan."""
    authority = str(node.get("planning_authority") or graph.get("planning_authority") or "").strip()
    return authority == _FROZEN_PLANNING_AUTHORITY


def _frozen_candidate_rank(candidate: dict[str, Any]) -> int:
    try:
        return int(candidate.get("rank") or 0)
    except (TypeError, ValueError):
        return 0


def _assign_frozen_worker(node: dict[str, Any], workers: list[dict[str, Any]]) -> dict[str, Any]:
    """Select only the first currently available frozen physical candidate.

    Static admission has already checked skills, capabilities, effects, and
    policy. Runtime therefore checks only exact operator identity and current
    availability; it must not replace the frozen choice with legacy relaxed
    role/capability/model matching.
    """
    node_id = str(node.get("id") or "")
    candidates = sorted(
        (item for item in (node.get("physical_candidates") or []) if isinstance(item, dict)),
        key=lambda item: (_frozen_candidate_rank(item), str(item.get("operator_id") or "")),
    )
    observations: list[dict[str, Any]] = []

    for candidate in candidates:
        operator_id = str(candidate.get("operator_id") or "").strip()
        rank = _frozen_candidate_rank(candidate)
        exact_workers = sorted(
            (
                worker
                for worker in workers
                if str(worker.get("operator_id") or "").strip() == operator_id
                and str(worker.get("pane") or "").strip()
            ),
            key=lambda worker: (int(worker.get("load", 0) or 0), str(worker.get("pane") or "")),
        )
        selected_worker: dict[str, Any] | None = None
        reasons: list[str] = []
        for worker in exact_workers:
            unavailable_reason = _worker_unavailable_reason(worker)
            if unavailable_reason:
                reasons.append(unavailable_reason)
                continue
            if _worker_quota_exhausted(worker):
                reasons.append("quota_exhausted")
                continue
            if _worker_busy(worker):
                reasons.append("worker_capacity_exhausted")
                continue
            selected_worker = worker
            break

        if selected_worker is None:
            reason = "operator_not_present" if not exact_workers else ",".join(dict.fromkeys(reasons))
            observations.append({
                "operator_id": operator_id,
                "rank": rank,
                "state": "UNAVAILABLE",
                "reason": reason or "operator_unavailable",
            })
            continue

        observations.append({
            "operator_id": operator_id,
            "rank": rank,
            "state": "READY",
        })
        observed_ids = {item["operator_id"] for item in observations}
        for remaining in candidates:
            remaining_id = str(remaining.get("operator_id") or "").strip()
            if remaining_id in observed_ids:
                continue
            observations.append({
                "operator_id": remaining_id,
                "rank": _frozen_candidate_rank(remaining),
                "state": "NOT_EVALUATED_AFTER_SELECTION",
            })
        return {
            "assigned": [{
                "node": node_id,
                "pane": selected_worker.get("pane"),
                "operator_id": operator_id,
                "candidate_rank": rank,
                "dispatch_role": node_dispatch_role(node),
                "worker_role": _worker_role(selected_worker),
                "frozen_candidate": True,
                "candidate_observations": observations,
            }],
            "queued": [],
        }

    return {
        "assigned": [],
        "queued": [{
            "node": node_id,
            "reason": "frozen_physical_candidates_unavailable",
            "details": {"candidate_observations": observations},
        }],
    }


# Capabilities that are PROVISIONED AT DISPATCH rather than advertised by a worker: resource/guard
# capsule capabilities (graph_node_dispatcher binds resource_binding + guard_decision per node) and
# eval-asserted compliance (the eval gate enforces scope_compliance). Requiring a worker to advertise
# these strands capsule-backed implementation/test/verify nodes as no_matching_worker before the
# binding/eval ever runs. The "resource."/"guard." prefixes are registry-safe (the capability-capsule
# registry only declares resource/guard caps under those prefixes).
_DISPATCH_PROVISIONED_CAP_PREFIXES = ("resource.", "guard.")
_DISPATCH_PROVISIONED_CAPS = frozenset({"scope_compliance", "repo-workspace"})
def _is_dispatch_provisioned_capability(cap: Any) -> bool:
    c = str(cap or "")
    return c in _DISPATCH_PROVISIONED_CAPS or c.startswith(_DISPATCH_PROVISIONED_CAP_PREFIXES)


def assign_workers(batch_nodes: list[dict[str, Any]], workers: list[dict[str, Any]]) -> dict[str, Any]:
    """Assign one batch to available workers.

    Matching order:
      1. exact preferred_model + required skills
      2. same skills with alternate model (Sonnet/DeepSeek fallback, etc.)
      3. queue when no safe worker exists
    """
    assigned: list[dict[str, Any]] = []
    queued: list[dict[str, Any]] = []
    used_panes: set[str] = set()
    capability_scores = _load_capability_scores()

    for node in batch_nodes:
        preferred_model = node.get("preferred_model")
        strict_model = bool(node.get("strict_model") or node.get("model_strict"))
        required_skills = [str(s) for s in node.get("required_skills", [])]
        required_capabilities = _capability_list(node)
        required_operator_id = str(node.get("required_operator_id") or "").strip()
        # Layer 0 (dispatch-provisioned): strip resource/guard capsule + eval-asserted caps that are
        # bound/asserted at dispatch, not advertised by a worker (see _is_dispatch_provisioned_capability).
        required_capabilities = [c for c in required_capabilities if not _is_dispatch_provisioned_capability(c)]
        node_role = node_dispatch_role(node)
        # Layer 1 (normalize): drop required_skills that are not in the operator-skill registry.
        # The planner emits unbounded free-form skill strings; unregistered ones are
        # unenforceable (no worker advertises them) and would falsely strand the node forever.
        required_skills = [s for s in required_skills if _is_registered_skill(s)]
        # Layer 2 (honest capability floor): an ImplementationWorker node genuinely needs
        # code_impl. Make the honest hard gate bite (it is otherwise empty for these nodes),
        # so a real capability gap strands honestly and the Layer-3 relaxed pass stays
        # capability-gated rather than role-only.
        if not required_capabilities and str(node.get("logical_operator") or "") == "ImplementationWorker":
            required_capabilities = ["code_impl"]
        candidates: list[tuple[int, float, int, int, int, str, dict[str, Any]]] = []
        relaxed_candidates: list[tuple[int, float, int, int, int, str, dict[str, Any]]] = []
        blocked_by_capacity = False
        blocked_by_runtime = False
        runtime_unavailable_reasons: set[str] = set()
        any_worker_seen = False
        missing_skill_union: set[str] = set()
        missing_cap_union: set[str] = set()
        role_candidates_seen = False

        for worker in workers:
            pane = str(worker.get("pane", ""))
            if not pane:
                continue
            any_worker_seen = True
            if required_operator_id and str(worker.get("operator_id") or "").strip() != required_operator_id:
                continue
            role_penalty = _role_penalty(node_role, _worker_role(worker))
            if role_penalty is None:
                continue
            role_candidates_seen = True
            for item in _missing_skills(worker, required_skills):
                missing_skill_union.add(item)
            for item in _missing_capabilities(worker, required_capabilities):
                missing_cap_union.add(item)
            # Capability match is the HONEST hard gate (never relaxed): a worker missing a
            # required capability is genuinely unqualified and is skipped for BOTH the strict
            # and the relaxed pass.
            if not _capabilities_match(worker, required_capabilities):
                continue
            if _worker_quota_exhausted(worker, preferred_model):
                continue
            if _model_requires_strict_match(preferred_model, strict_model) and not _model_match(worker, preferred_model):
                continue
            unavailable_reason = _worker_unavailable_reason(worker)
            if unavailable_reason:
                blocked_by_runtime = True
                runtime_unavailable_reasons.add(unavailable_reason)
                continue
            if pane in used_panes:
                blocked_by_capacity = True
                continue
            if _worker_busy(worker):
                blocked_by_capacity = True
                continue
            cap_score = _capability_score(worker, required_capabilities, capability_scores)
            skill_score = _skill_match_count(worker, required_skills)
            model_penalty = 0 if _model_match(worker, preferred_model) else 10
            load = int(worker.get("load", 0) or 0)
            entry = (role_penalty, -cap_score, -skill_score, model_penalty, load, pane, worker)
            # Skills are a PREFERENCE, not a hard gate. A worker that clears role + capability +
            # quota + model + runtime + capacity goes to the strict list if skills match, else to
            # the relaxed list (Layer 3 safety net) so the node can never permanently strand on
            # a skill string while a capability-qualified worker is free.
            if _skills_match(worker, required_skills, required_capabilities):
                candidates.append(entry)
            else:
                relaxed_candidates.append(entry)

        if not candidates and relaxed_candidates:
            # Layer 3 (liveness net): no worker matched the (possibly drifted/free-form) skill
            # strings, but capability-qualified role-appropriate workers ARE free. Dispatch to
            # the best one rather than permanently strand the DAG. Capabilities/role/quota/busy
            # were already enforced hard above, so this can NOT dispatch to an unqualified worker
            # (a genuine capability gap has empty relaxed_candidates and still strands honestly).
            relaxed_candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4], item[5]))
            role_rank, cap_rank, skill_rank, _model_penalty, _load, _pane, worker = relaxed_candidates[0]
            used_panes.add(str(worker.get("pane")))
            assigned.append({
                "node": node["id"],
                "pane": worker.get("pane"),
                "dispatch_role": node_role,
                "worker_role": _worker_role(worker),
                "preferred_model": preferred_model,
                "selected_models": worker.get("models", []),
                "fallback_model": not _model_match(worker, preferred_model),
                "required_capabilities": required_capabilities,
                "role_penalty": int(role_rank),
                "capability_score": round(-cap_rank, 3),
                "skill_match_count": int(-skill_rank),
                "skills_relaxed": True,
                "relaxed_unmatched_skills": sorted(missing_skill_union),
            })
            continue
        if not candidates:
            if blocked_by_runtime:
                if len(runtime_unavailable_reasons) == 1:
                    reason = next(iter(runtime_unavailable_reasons))
                else:
                    reason = "worker_runtime_unavailable"
            elif blocked_by_capacity:
                reason = "worker_capacity_exhausted"
            else:
                reason = "no_matching_worker"
            details: dict[str, Any] = {
                "required_role": node_role,
                "required_skills": required_skills,
                "required_capabilities": required_capabilities,
            }
            if required_operator_id:
                details["required_operator_id"] = required_operator_id
            if blocked_by_runtime:
                details["unavailable_reasons"] = sorted(runtime_unavailable_reasons)
            if reason == "no_matching_worker":
                details["any_worker_seen"] = any_worker_seen
                details["role_candidates_seen"] = role_candidates_seen
                details["missing_skills"] = sorted(missing_skill_union)
                details["missing_capabilities"] = sorted(missing_cap_union)
            queued.append({"node": node["id"], "reason": reason, "details": details})
            continue

        candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4], item[5]))
        role_rank, cap_rank, skill_rank, _model_penalty, _load, _pane, worker = candidates[0]
        used_panes.add(str(worker.get("pane")))
        assigned.append({
            "node": node["id"],
            "pane": worker.get("pane"),
            "dispatch_role": node_role,
            "worker_role": _worker_role(worker),
            "preferred_model": preferred_model,
            "selected_models": worker.get("models", []),
            "fallback_model": not _model_match(worker, preferred_model),
            "required_capabilities": required_capabilities,
            "role_penalty": int(role_rank),
            "capability_score": round(-cap_rank, 3),
            "skill_match_count": int(-skill_rank),
        })

    return {"ok": True, "assigned": assigned, "queued": queued}


def _workers_with_used_panes_marked_busy(workers: list[dict[str, Any]], used_panes: set[str]) -> list[dict[str, Any]]:
    if not used_panes:
        return workers
    patched: list[dict[str, Any]] = []
    for worker in workers:
        pane = str(worker.get("pane") or "")
        if pane in used_panes:
            copy = dict(worker)
            copy["busy"] = True
            patched.append(copy)
        else:
            patched.append(worker)
    return patched


def assign_ready(graph: dict[str, Any], workers: list[dict[str, Any]],
                 max_parallel: int | None = None,
                 graph_path: str | Path | None = None,
                 source: str | Path | None = None) -> dict[str, Any]:
    if graph.get("schema_version") == "solar.scheduler_runtime_projection.v1":
        import scheduler_input

        verification = scheduler_input.verify_runtime_projection(graph, graph_path=graph_path)
        if not verification.get("ok"):
            raise ValueError(
                "scheduler runtime projection refused: "
                + ",".join(str(item) for item in verification.get("errors") or [])
            )
    frozen_graph = str(graph.get("planning_authority") or "").strip() == _FROZEN_PLANNING_AUTHORITY
    if not frozen_graph:
        graph = auto_enrich_graph(graph, graph_path=graph_path, source=source)
    blocked = blocked_external_prerequisites(graph)
    if blocked:
        return {"ok": True, "assigned": [], "queued": [], "batch": [], "blocked_prerequisites": blocked}
    ready = ready_nodes(graph)
    if frozen_graph:
        ready = sorted(
            ready,
            key=lambda node: (-int(node.get("priority") or 0), str(node.get("id") or "")),
        )
    legacy_ready = [node for node in ready if not _is_frozen_scheduler_node(graph, node)]
    if legacy_ready:
        try:
            from apo_plan_compiler import compile_execution_plan_for_node  # noqa: WPS433

            for node in legacy_ready:
                if isinstance(node.get("effect_union"), dict) and isinstance(node.get("proof_obligations"), list):
                    continue
                try:
                    compiled = compile_execution_plan_for_node(
                        node,
                        request_type=str(graph.get("request_type") or node.get("type") or ""),
                        lane_hint=str(graph.get("lane") or ""),
                        registry_path=HARNESS_DIR / "config" / "capability-capsules.registry.yaml",
                        operators_path=HARNESS_DIR / "config" / "physical-operators.json",
                    )
                    capsule_plan = compiled.get("capsule_plan") or {}
                    physical_plan = compiled.get("physical_plan") or {}
                    if isinstance(capsule_plan, dict):
                        node["capsule_plan_ir"] = capsule_plan
                        node["effect_union"] = capsule_plan.get("effect_union", {})
                        node["proof_obligations"] = capsule_plan.get("proof_obligations", [])
                        node["artifact_types"] = capsule_plan.get("artifact_types", {})
                    if isinstance(physical_plan, dict):
                        node["physical_plan_ir"] = physical_plan
                except Exception:
                    continue
        except Exception:
            pass
    effective_max_parallel = max_parallel if max_parallel is not None else _effective_graph_max_parallel(None)
    max_selected = effective_max_parallel if effective_max_parallel and effective_max_parallel > 0 else len(ready)
    selected_nodes: list[dict[str, Any]] = []
    assigned: list[dict[str, Any]] = []
    queued: list[dict[str, Any]] = []
    used_panes: set[str] = set()

    for node in ready:
        if len(assigned) >= max_selected:
            break
        if any(write_scope_conflict(node, other) or effect_conflict(node, other) for other in selected_nodes):
            queued.append({
                "node": node["id"],
                "reason": "conflicts_with_selected_batch",
                "details": {"selected_nodes": [str(item.get("id") or "") for item in selected_nodes]},
            })
            continue
        available_workers = _workers_with_used_panes_marked_busy(workers, used_panes)
        if _is_frozen_scheduler_node(graph, node):
            result = _assign_frozen_worker(node, available_workers)
        else:
            result = assign_workers([node], available_workers)
        if result.get("assigned"):
            item = result["assigned"][0]
            assigned.append(item)
            selected_nodes.append(node)
            if item.get("pane"):
                used_panes.add(str(item.get("pane")))
            continue
        queued.extend(result.get("queued") or [])

    if not assigned and not queued:
        return {"ok": True, "assigned": [], "queued": [], "batch": []}
    result = {
        "ok": True,
        "assigned": assigned,
        "queued": queued,
        "batch": [node["id"] for node in selected_nodes],
    }
    result["work_conserving"] = True
    result["ready_width"] = len(ready)
    result["capability_enrichment"] = {
        "changed_nodes": [] if frozen_graph else _changed_nodes(graph),
        "auto": not frozen_graph,
    }
    return result


def _node_gate_verdict_ok(node: dict[str, Any]) -> tuple[bool, str]:
    """Consume a gate node's domain verdict artifact (verifier / critic).

    A gate must NOT be satisfied merely because its member nodes finished
    executing: a verifier/critic node is marked ``passed`` when it RAN
    correctly, regardless of whether its machine verdict approved or blocked.
    This reads the verdict artifact declared in the node's ``write_scope`` and
    returns ``(False, detail)`` when that verdict is FAIL/block.

    Fail-CLOSED: if a node declares a verdict artifact but it is missing or
    unparseable, the verdict is treated as NOT ok. Nodes that declare no verdict
    artifact return ``(True, ...)`` — nothing to consume, they pass on completion.
    """
    write_scope = node.get("write_scope") or []
    if isinstance(write_scope, str):
        write_scope = [write_scope]
    for entry in write_scope:
        name = Path(str(entry)).name
        if not name:
            continue
        path = SPRINTS_DIR / name
        # Verifier decision: strict allowlist, matching verification_gate.py policy.
        if name.endswith("verifier_decision.json"):
            try:
                decision = str(json.loads(path.read_text(encoding="utf-8")).get("decision", "")).strip().lower()
            except Exception as exc:  # missing / unparseable -> fail-closed
                return False, f"verifier_decision_unreadable:{name}:{type(exc).__name__}"
            if decision not in {"pass", "passed", "approved", "ok"}:
                return False, f"verifier_decision={decision or 'missing'}"
        # Critic gate: block on explicit negative tokens (avoid false-negatives on unknown pass tokens).
        elif name.endswith("contradictions.jsonl"):
            decision = None
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if str(obj.get("type") or "") == "gate_verdict":
                        decision = str(obj.get("gate_decision") or "").strip().lower()
                        break
            except Exception as exc:  # missing / unparseable -> fail-closed
                return False, f"contradictions_unreadable:{name}:{type(exc).__name__}"
            if decision is None:
                return False, f"critic_gate_verdict_missing:{name}"
            if decision in {"block", "blocked", "fail", "failed", "reject", "rejected"}:
                return False, f"critic_gate_decision={decision}"
    return True, "verdict_ok"


def _ledger_transition(graph: dict[str, Any], node_id: str, from_status: str, to_status: str,
                       writer: str, *, applied: bool = True, author_type: str = "scheduler",
                       note: str | None = None, **extra: Any) -> None:
    """Report a node-status write to the gate ledger (Lane 3, R4).

    No-op unless SOLAR_GATE_LEDGER=1; never raises into the scheduling hot path."""
    if _gate_ledger is None:
        return
    try:
        if not _gate_ledger.enabled():
            return
        sid = _sprint_id_for_graph(graph)
        if not sid:
            return
        _gate_ledger.record_status_transition(
            SPRINTS_DIR, sid, node_id,
            from_status=from_status, to_status=to_status,
            author_type=author_type, writer=writer, applied=applied, note=note,
            **extra,
        )
    except Exception:
        pass


def enter_node_human_review(
    graph: dict[str, Any],
    node_id: str,
    *,
    reason: str,
    next_action: str,
    writer: str,
    author_type: str = "policy",
) -> dict[str, Any]:
    """Enter one durable human-review generation through the sole authority.

    Re-observing an already blocked node is idempotent: it preserves the same
    generation and does not manufacture another transition.  A later genuine
    re-escalation after an explicit resume increments the generation.
    """
    ids = _node_map(graph)
    if node_id not in ids:
        raise ValueError(f"unknown node: {node_id}")
    reason = str(reason or "").strip()
    next_action = str(next_action or "").strip()
    writer = str(writer or "").strip()
    if not reason:
        raise ValueError("human_review_reason_required")
    if not next_action:
        raise ValueError("human_review_next_action_required")
    if not writer:
        raise ValueError("human_review_writer_required")

    node = ids[node_id]
    results = graph.setdefault("node_results", {})
    result = results.get(node_id) if isinstance(results.get(node_id), dict) else {}
    prior_status = node_recorded_status(graph, node_id)
    prior_record = _human_review_record(node, result)
    already_blocked = _human_review_is_blocking(node, result)
    prior_generation = human_review_generation(graph, node_id)
    generation = max(1, prior_generation if already_blocked else prior_generation + 1)
    now = _now()

    if already_blocked and str(prior_record.get("state") or "").lower() == "blocked":
        record = deepcopy(prior_record)
    else:
        record = {
            "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
            "generation": generation,
            "state": "blocked",
            "reason": reason,
            "next_action": next_action,
            "blocked_at": now,
            "writer": writer,
        }
        if prior_record:
            history = node.get("human_review_history")
            if not isinstance(history, list):
                history = []
            history = [deepcopy(item) for item in history if isinstance(item, dict)]
            history.append(deepcopy(prior_record))
            node["human_review_history"] = history[-HUMAN_REVIEW_HISTORY_LIMIT:]

    node["human_review"] = deepcopy(record)
    node["status"] = HUMAN_REVIEW_STATUS
    node["updated_at"] = now
    node["next_action"] = next_action
    results[node_id] = {
        "status": HUMAN_REVIEW_STATUS,
        "updated_at": now,
        "note": reason,
        "next_action": next_action,
        "human_review": deepcopy(record),
    }
    gate = str(node.get("gate") or "")
    if gate and isinstance(graph.get("gate_results"), dict):
        graph["gate_results"].pop(gate, None)
    if prior_status != HUMAN_REVIEW_STATUS:
        _ledger_transition(
            graph,
            node_id,
            prior_status,
            HUMAN_REVIEW_STATUS,
            writer,
            author_type=author_type,
            note=reason,
            human_review_generation=generation,
        )
    return deepcopy(record)


def validate_human_review_resume(
    graph: dict[str, Any],
    node_id: str,
    *,
    expected_generation: int,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    """Validate the one-shot authority without mutating graph or evidence."""
    ids = _node_map(graph)
    if node_id not in ids:
        raise ValueError(f"unknown node: {node_id}")
    actor = str(actor or "").strip()
    reason = str(reason or "").strip()
    if not actor:
        raise ValueError("human_resume_actor_required")
    if not reason:
        raise ValueError("human_resume_reason_required")
    result = _node_results(graph).get(node_id)
    if not _human_review_is_blocking(ids[node_id], result):
        raise ValueError("node_not_waiting_for_human_review")
    generation = human_review_generation(graph, node_id)
    try:
        requested_generation = int(expected_generation)
    except (TypeError, ValueError) as exc:
        raise ValueError("human_resume_generation_invalid") from exc
    if requested_generation != generation:
        raise ValueError(
            f"human_resume_generation_mismatch:expected={generation}:received={requested_generation}"
        )
    return {
        "node": node_id,
        "generation": generation,
        "actor": actor,
        "reason": reason,
    }


def commit_human_review_resume(
    graph: dict[str, Any],
    node_id: str,
    *,
    expected_generation: int,
    actor: str,
    reason: str,
    archived_sidecars: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Commit a validated, one-shot human resume after evidence quarantine.

    Callers must archive the old handoff/eval sidecars first.  The new repair
    generation makes any late old evaluator output mechanically stale.
    """
    validated = validate_human_review_resume(
        graph,
        node_id,
        expected_generation=expected_generation,
        actor=actor,
        reason=reason,
    )
    ids = _node_map(graph)
    actor = str(validated["actor"])
    reason = str(validated["reason"])
    node = ids[node_id]
    results = graph.setdefault("node_results", {})
    result = results.get(node_id) if isinstance(results.get(node_id), dict) else {}
    generation = int(validated["generation"])

    prior_record = _human_review_record(node, result) or {
        "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
        "generation": generation,
        "state": "blocked",
        "reason": str(node.get("dispatch_blocked_reason") or node.get("eval_blocked_reason") or "legacy_human_review"),
    }
    now = _now()
    resumed_record = deepcopy(prior_record)
    resumed_record.update(
        {
            "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
            "generation": generation,
            "state": "resumed",
            "resumed_at": now,
            "resumed_by": actor,
            "resume_reason": reason,
        }
    )
    history = node.get("human_review_history")
    if not isinstance(history, list):
        history = []
    history = [deepcopy(item) for item in history if isinstance(item, dict)]
    history.append(deepcopy(prior_record))
    node["human_review_history"] = history[-HUMAN_REVIEW_HISTORY_LIMIT:]

    try:
        prior_repair_attempt = max(0, int(node.get("repair_attempts") or 0))
    except (TypeError, ValueError):
        prior_repair_attempt = 0
    repair_attempt = prior_repair_attempt + 1
    try:
        configured_max = max(0, int(node.get("max_repair_attempts") or repair_attempt))
    except (TypeError, ValueError):
        configured_max = repair_attempt
    repair_context = {
        "attempt": repair_attempt,
        "max_attempts": configured_max,
        "verdict": "HUMAN_RESUME",
        "summary": reason[:2000],
        "failed_conditions": [],
        "errors": [],
        "archived_sidecars": deepcopy(archived_sidecars or {}),
        "created_at": now,
        "trigger": "explicit_human_resume",
        "human_review_generation": generation,
        "actor": actor,
    }

    for key in (
        "assigned_to",
        "dispatch_id",
        "eval_json",
        "eval_assigned_to",
        "eval_dispatch_id",
        "eval_dispatched_at",
        "eval_retry_reason",
        "eval_assignments",
        "eval_dispatch_group_id",
        "last_eval_closeout_failure",
        "last_eval_operator_cooldown_after_closeout",
        "handoff_md",
        "dispatch_retry_reason",
        "last_operator_closeout_failure",
        "dispatch_failure_streak",
        "last_dispatch_failure_reason",
        "last_dispatch_failure_at",
        "eval_dispatch_failures",
        "last_eval_dispatch_failure_reason",
        "last_eval_dispatch_failure_at",
        "dispatch_blocked_reason",
        "eval_blocked_reason",
        "next_action",
    ):
        node.pop(key, None)
    artifacts = node.get("artifacts")
    if isinstance(artifacts, dict):
        artifacts.pop("eval_json", None)
        artifacts.pop("handoff_md", None)

    node["human_review"] = deepcopy(resumed_record)
    node["repair_attempts"] = repair_attempt
    node["repair_context"] = repair_context
    repair_history = node.get("repair_history")
    if not isinstance(repair_history, list):
        repair_history = []
    repair_history = [deepcopy(item) for item in repair_history if isinstance(item, dict)]
    repair_history.append(deepcopy(repair_context))
    node["repair_history"] = repair_history
    node["status"] = "pending"
    node["updated_at"] = now
    results[node_id] = {
        "status": "pending",
        "updated_at": now,
        "note": f"explicit_human_resume:{reason}",
        "human_review": deepcopy(resumed_record),
        "repair_context": deepcopy(repair_context),
    }
    gate = str(node.get("gate") or "")
    if gate and isinstance(graph.get("gate_results"), dict):
        graph["gate_results"].pop(gate, None)
    _ledger_transition(
        graph,
        node_id,
        HUMAN_REVIEW_STATUS,
        "pending",
        "resume_human_review",
        author_type="human",
        note=reason,
        human_review_generation=generation,
        repair_attempt=repair_attempt,
        human_actor=actor,
    )
    return {
        "ok": True,
        "node": node_id,
        "from_status": HUMAN_REVIEW_STATUS,
        "status": "pending",
        "generation": generation,
        "repair_attempt": repair_attempt,
        "actor": actor,
        "reason": reason,
        "archived_sidecars": deepcopy(archived_sidecars or {}),
    }


def _human_review_blocks_dependents(graph: dict[str, Any], dep_node: dict[str, Any]) -> bool:
    """Per-node on_human_review policy consult (design §2 change 2 / review 7.2).

    On the contracted path (SOLAR_GATE_LEDGER + workflow_contract_id) a dep in
    needs_human_review blocks dependents per ITS OWN contract policy:
    warn_and_continue lets dependents proceed; block_dependents (or an absent
    policy) keeps the legacy behavior. Off the contracted path, needs_human_review
    always blocks — the global DEPENDENCY_BLOCK_STATUSES set is untouched.
    """
    if _gate_ledger is None:
        return True
    try:
        if not _gate_ledger.enabled() or not _gate_ledger.contracted(graph):
            return True
    except Exception:
        return True
    policy = str((dep_node or {}).get("on_human_review") or "").strip().lower()
    return policy != "warn_and_continue"


def _dependency_blocks(graph: dict[str, Any], ids: dict[str, Any], dep_id: str) -> bool:
    """Whether a dependency's status blocks its dependents (skip-propagation rule)."""
    dep_status = node_status(graph, dep_id)
    if dep_status not in DEPENDENCY_BLOCK_STATUSES:
        return False
    if dep_status == "needs_human_review" and not _human_review_blocks_dependents(graph, ids.get(dep_id)):
        return False
    return True


def _ledger_gate_verdict_block(graph: dict[str, Any], gate_node_ids: list[str]) -> tuple[str, str] | None:
    """Ledger consult for gate aggregation (AC-R4.2, contracted path only).

    A gate-consumable verdict record saying FAIL/block blocks the gate even when
    the member node's *status* is passed — the 5fcff602 verdict-content semantics
    locked structurally. Fail-open to legacy behavior off the contracted path."""
    if _gate_ledger is None:
        return None
    try:
        if not _gate_ledger.enabled() or not _gate_ledger.contracted(graph):
            return None
        sid = _sprint_id_for_graph(graph)
        if not sid:
            return None
        ids = _node_map(graph)
        for node_id in gate_node_ids:
            node = ids.get(node_id)
            generation = None
            if isinstance(node, dict):
                attempts = node.get("repair_attempts")
                if attempts is not None:
                    try:
                        generation = int(attempts)
                    except Exception:
                        generation = None
            latest = _gate_ledger.latest_consumable_verdict(
                SPRINTS_DIR, sid, node_id, current_generation=generation
            )
            if latest is None:
                continue
            verdict = str(latest.get("verdict") or "").strip().lower()
            if verdict not in {"fail", "failed", "block", "blocked"}:
                continue
            # Round-4 G2: gates consume verdict CONTENT (R4/AC-R4.1). A
            # mechanical/infrastructure FAIL is evidence-machinery failure, not
            # a content judgment, and never blocks; a human verdict always
            # does; a kind-less record keeps the stricter content effect (D6).
            verdict_kind = str(latest.get("verdict_kind") or "").strip().lower()
            is_human = str(latest.get("kind") or "") == "human_verdict"
            if not is_human and verdict_kind in {"mechanical", "infrastructure"}:
                continue
            return node_id, f"ledger_verdict_block:{verdict}"
    except Exception:
        return None
    return None


def _gate_verdicts_ok(graph: dict[str, Any], gate_node_ids: list[str]) -> tuple[bool, str, str]:
    """Aggregate verdict-consumption across a gate's member nodes.

    Returns ``(ok, blocking_node_id, detail)``. A gate is verdict-ok only when
    every member node that emits a verifier/critic verdict approved.
    """
    ids = _node_map(graph)
    for node_id in gate_node_ids:
        node = ids.get(node_id)
        if not isinstance(node, dict):
            continue
        ok, detail = _node_gate_verdict_ok(node)
        if not ok:
            return False, node_id, detail
    ledger_block = _ledger_gate_verdict_block(graph, gate_node_ids)
    if ledger_block is not None:
        return False, ledger_block[0], ledger_block[1]
    return True, "", "verdict_ok"


def _sprint_status_terminal(graph: dict[str, Any]) -> bool:
    """True when the sprint's status.json shows a TERMINAL pair
    (failed/failed or passed/completed|done) — the frozen states G3 runs
    11/12 established as truthful terminals."""
    sid = str(graph.get("sprint_id") or "").strip()
    if not sid:
        return False
    try:
        payload = json.loads((SPRINTS_DIR / f"{sid}.status.json").read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or "").strip().lower()
    phase = str(payload.get("phase") or payload.get("stage") or "").strip().lower()
    return (status == "failed" and phase == "failed") or (
        status == "passed" and phase in {"completed", "done"}
    )


def mark_node_result(
    graph: dict[str, Any],
    node_id: str,
    status: str,
    gate_status: str | None = None,
    note: str | None = None,
    *,
    _closeout_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ensure_required_gate_node_mapping(graph)
    ids = _node_map(graph)
    if node_id not in ids:
        raise ValueError(f"unknown node: {node_id}")
    _assert_human_review_status_write_allowed(graph, node_id, status)
    _assert_pass_mark_allowed(
        graph,
        node_id,
        status,
        closeout_receipt=_closeout_receipt,
    )
    _ledger_previous_status = node_status(graph, node_id)
    # A PROGRESS mark must never regress a passed node. The generated worker
    # runner marks `reviewing` AFTER the worker process exits, and the worker's
    # own closing instruction marks `reviewing` mid-run — two late progress
    # writers per node. With llm evals (minutes) the window between them and
    # node close was unhittable; the deterministic gate closes nodes in
    # seconds, so a late runner mark landed 4s after P3 run-3's D2 passed and
    # reopened it (ledger reopen:true) — the graph never reached all-terminal.
    # Repair reopens use their own path (failed_review -> assigned via
    # set_node_status) and terminal flips (passed -> failed by a human/eval
    # verdict) remain allowed — only forward-progress statuses are refused.
    if _ledger_previous_status in PASS_STATUSES and str(status or "").lower() in {
        "reviewing", "pending", "queued", "assigned", "dispatched", "in_progress", "running",
    }:
        refused = parent_ready_check(graph)
        refused["refused_progress_regression"] = {
            "node": node_id,
            "kept_status": _ledger_previous_status,
            "refused_status": status,
            "note": note or "",
        }
        return refused
    # G4-lite run 2 (drift evidence, p5-g4-lite-live-rung-20260710T133158Z):
    # the sprint terminalized failed/failed at 13:40:18Z; the surviving repair
    # builder ran its closing `graph-scheduler mark --status reviewing` at
    # 13:42:48Z and the projection refresh propagated the reopen onto the
    # TERMINAL sprint. A terminal sprint is frozen: late progress marks from
    # any straggler writer are refused (terminal verdict flips stay with the
    # generation-fenced verdict paths; this guards only progress statuses).
    if str(status or "").lower() in {
        "reviewing", "pending", "queued", "assigned", "dispatched", "in_progress", "running",
    } and _sprint_status_terminal(graph):
        refused = parent_ready_check(graph)
        refused["refused_terminal_sprint_write"] = {
            "node": node_id,
            "kept_status": _ledger_previous_status,
            "refused_status": status,
            "note": note or "",
        }
        return refused

    updated_at = _now()
    graph.setdefault("node_results", {})
    graph["node_results"][node_id] = {
        "status": status,
        "updated_at": updated_at,
    }
    if note:
        graph["node_results"][node_id]["note"] = note
    ids[node_id]["status"] = status
    ids[node_id]["updated_at"] = updated_at
    if _closeout_receipt is not None:
        receipt_copy = deepcopy(_closeout_receipt)
        ids[node_id]["closeout_receipt"] = receipt_copy
        graph["node_results"][node_id]["closeout_receipt"] = deepcopy(receipt_copy)
    _ledger_transition(graph, node_id, _ledger_previous_status, status, "mark_node_result", note=note)

    gate = ids[node_id].get("gate")
    if gate and status in {"failed", "cancelled"}:
        graph.setdefault("gate_results", {})
        graph["gate_results"][gate] = {
            "status": "blocked",
            "node": node_id,
            "reason": f"node_{status}",
            "updated_at": updated_at,
        }
    elif gate and (gate_status or status) == "passed":
        gate_nodes = [node for node in ids.values() if node.get("gate") == gate]
        open_gate_nodes = [
            str(node.get("id") or "")
            for node in gate_nodes
            if str(node.get("id") or "") != node_id and node_status(graph, str(node.get("id") or "")) != "passed"
        ]
        graph.setdefault("gate_results", {})
        if open_gate_nodes:
            graph["gate_results"][gate] = {
                "status": "blocked",
                "node": node_id,
                "reason": "waiting_for_shared_gate_nodes",
                "open_nodes": open_gate_nodes,
                "updated_at": updated_at,
            }
        else:
            verdicts_ok, blocking_node, verdict_detail = _gate_verdicts_ok(
                graph, [str(n.get("id") or "") for n in gate_nodes]
            )
            if verdicts_ok:
                graph["gate_results"][gate] = {"status": "passed", "node": node_id, "updated_at": updated_at}
            else:
                # member nodes all executed, but a verifier/critic verdict is FAIL/block.
                graph["gate_results"][gate] = {
                    "status": "blocked",
                    "node": blocking_node,
                    "reason": f"gate_verdict_block:{verdict_detail}",
                    "updated_at": updated_at,
                }

    if str(status or "").lower() in {"passed", "failed", "reviewing"}:
        _sync_node_evidence_refs(
            graph,
            node_id,
            repair=True,
            command_line=f"python3 lib/graph_scheduler.py mark --node {node_id} --status {status}",
        )

    return parent_ready_check(graph)


def commit_verified_node_pass(
    graph: dict[str, Any],
    node_id: str,
    *,
    closeout_receipt: dict[str, Any],
    note: str | None = None,
) -> dict[str, Any]:
    """Commit PASS after the dispatcher has completed the closeout transaction.

    This is intentionally narrower than ``mark_node_result``: it accepts only
    PASS and requires the full contracted receipt.  Keeping the final status
    mutation in the scheduler preserves its gate aggregation and parent-ready
    behavior without exposing the old CLI/manual shortcut.
    """
    return mark_node_result(
        graph,
        node_id,
        "passed",
        gate_status="passed",
        note=note,
        _closeout_receipt=closeout_receipt,
    )


def reconcile_legacy_write_scope_artifacts(
    graph: dict[str, Any],
    harness_dir: str | Path,
) -> dict[str, Any]:
    """Preserve the coordinator's artifact-exists shortcut for legacy graphs.

    Contracted graphs must wait for ``graph_node_dispatcher.node_verdict``;
    mere file existence is never evaluation, proof, or publication evidence.
    This helper replaces an untestable inline Python PASS writer in
    ``coordinator.sh`` and makes the compatibility boundary explicit.
    """
    if bool(str((graph or {}).get("workflow_contract_id") or "").strip()):
        return {
            "ok": True,
            "changed": [],
            "reason": "contracted_graph_requires_node_verdict",
        }

    root = Path(harness_dir)

    def artifact_exists(item: Any) -> bool:
        path = Path(str(item))
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            try:
                return path.stat().st_size > 0
            except OSError:
                return False
        if path.is_dir():
            try:
                return any(child.is_file() and child.stat().st_size > 0 for child in path.rglob("*"))
            except OSError:
                return False
        return False

    changed: list[str] = []
    for node in graph.get("nodes") or []:
        node_id = str(node.get("id") or "")
        if not node_id or node_status(graph, node_id) in {"passed", "done", "completed"}:
            continue
        write_scope = node.get("write_scope") or []
        if not write_scope or not all(artifact_exists(item) for item in write_scope):
            continue
        mark_node_result(
            graph,
            node_id,
            "passed",
            gate_status="passed" if node.get("gate") else None,
            note="coordinator legacy auto-reconcile from complete write_scope artifacts",
        )
        changed.append(node_id)
    return {"ok": True, "changed": changed, "reason": "legacy_write_scope_reconciled"}


def set_node_status(graph: dict[str, Any], node_id: str, status: str,
                    pane: str | None = None, dispatch_id: str | None = None) -> None:
    ids = _node_map(graph)
    if node_id not in ids:
        raise ValueError(f"unknown node: {node_id}")
    assert_node_status_write_allowed(graph, node_id, status)
    current = node_status(graph, node_id)
    reopening_from_pass = current in PASS_STATUSES and status in {
        "reviewing", "pending", "queued", "blocked", "worker_blocked", "assigned", "dispatched", "in_progress", "running",
    }
    if _status_rank(current) > _status_rank(status) and not reopening_from_pass:
        return
    updated_at = _now()
    ids[node_id]["status"] = status
    ids[node_id]["updated_at"] = updated_at
    if pane:
        ids[node_id]["assigned_to"] = pane
    if dispatch_id:
        ids[node_id]["dispatch_id"] = dispatch_id
    graph.setdefault("node_results", {})
    graph["node_results"][node_id] = {
        "status": status,
        "updated_at": updated_at,
    }
    if pane:
        graph["node_results"][node_id]["assigned_to"] = pane
    if dispatch_id:
        graph["node_results"][node_id]["dispatch_id"] = dispatch_id
    gate = str(ids[node_id].get("gate") or "")
    if gate and status not in PASS_STATUSES:
        gate_results = graph.get("gate_results")
        if isinstance(gate_results, dict) and gate in gate_results:
            gate_results.pop(gate, None)
    _ledger_transition(graph, node_id, current, status, "set_node_status")


def terminalize_dependency_blocked_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Close nodes that can never run because an internal dependency is terminal-nonpass.

    This does not pass work. It makes DAG failure explicit so runners can stop cleanly instead of
    spinning forever with downstream nodes left as `pending` after an upstream failure.
    """
    ids = _node_map(graph)
    changed: list[dict[str, Any]] = []
    for node_id, node in ids.items():
        status = node_status(graph, node_id)
        if status in TERMINAL_STATUSES or status in ACTIVE_STATUSES or status == "needs_human_review":
            continue
        blockers = [
            dep_id
            for dep_id in _internal_depends_on(node)
            if dep_id in ids and _dependency_blocks(graph, ids, dep_id)
        ]
        if not blockers:
            continue
        set_node_status(graph, node_id, "skipped")
        node["blocked_by_failed_dependency"] = blockers
        node["skip_reason"] = "blocked_by_failed_dependency"
        graph.setdefault("node_results", {})
        result = graph["node_results"].setdefault(node_id, {})
        result.update(
            {
                "status": "skipped",
                "updated_at": node.get("updated_at") or _now(),
                "note": "blocked_by_failed_dependency",
                "blocked_by": blockers,
            }
        )
        changed.append({"node": node_id, "status": "skipped", "reason": "blocked_by_failed_dependency", "blocked_by": blockers})
    return changed


def reopen_recovered_dependency_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Reopen nodes auto-skipped solely because an internal dependency failed.

    A dependency can recover after an explicit repair/human-review cycle.  The
    old terminalization marker must not leave its downstream nodes permanently
    skipped once every recorded blocker is healthy.  Only scheduler-authored
    ``blocked_by_failed_dependency`` skips are eligible; user cancellations and
    other terminal skips remain frozen.
    """
    ids = _node_map(graph)
    results = _node_results(graph)
    changed: list[dict[str, Any]] = []
    for node_id, node in ids.items():
        if node_status(graph, node_id) != "skipped":
            continue
        result = results.get(node_id) if isinstance(results.get(node_id), dict) else {}
        skip_reason = str(node.get("skip_reason") or (result or {}).get("note") or "").strip()
        if skip_reason != "blocked_by_failed_dependency":
            continue
        blockers = [
            dep_id
            for dep_id in _internal_depends_on(node)
            if dep_id in ids and _dependency_blocks(graph, ids, dep_id)
        ]
        if blockers:
            continue

        now = _now()
        _ledger_transition(
            graph,
            node_id,
            "skipped",
            "pending",
            "reopen_recovered_dependency_nodes",
            note="dependency_recovered",
        )
        node["status"] = "pending"
        node["updated_at"] = now
        node.pop("blocked_by_failed_dependency", None)
        node.pop("skip_reason", None)
        node.pop("assigned_to", None)
        node.pop("dispatch_id", None)
        results[node_id] = {
            "status": "pending",
            "updated_at": now,
            "note": "reopened_after_dependency_recovered",
        }
        gate = str(node.get("gate") or "")
        if gate and isinstance(graph.get("gate_results"), dict):
            graph["gate_results"].pop(gate, None)
        changed.append(
            {
                "node": node_id,
                "status": "pending",
                "reason": "dependency_recovered",
            }
        )
    return changed


def _enforce_contract_capsule_authority(graph: dict[str, Any], node: dict[str, Any],
                                        capsule_plan_ir: dict[str, Any]) -> None:
    """On a contracted graph the workflow contract is the capsule authority.

    The APO plan compiler re-classifies nodes from goal text at dispatch time
    (P2 smoke-4: code.cli_smoke S2, a 'code' node, classified TestRunner ->
    cap.requirement-compiler-verification). Letting that overwrite the
    contract-assigned capsule fails capsule task_type admission at operator
    submit AND trips _workflow_contract_guard on every subsequent dispatch
    attempt — a permanent assigned->pending wedge. The compiler's pick is
    preserved as apo_suggested_capsule_id for audit; uncontracted graphs keep
    the legacy behavior untouched."""
    if not str(graph.get("workflow_contract_id") or "").strip():
        return
    contract_capsule = str(node.get("capability_capsule_id") or "").strip()
    if not contract_capsule:
        return
    suggested = str(capsule_plan_ir.get("capability_capsule_id") or "").strip()
    if not suggested or suggested == contract_capsule:
        return
    capsule_plan_ir["apo_suggested_capsule_id"] = suggested
    capsule_plan_ir["capsule_authority"] = "workflow_contract"
    capsule_plan_ir["capability_capsule_id"] = contract_capsule


def enqueue_ready(graph: dict[str, Any], graph_path: str, workers: list[dict[str, Any]],
                  max_parallel: int | None = None, lease: bool = False,
                  ttl: int = 600, dry_run: bool = False) -> dict[str, Any]:
    """Assign ready graph nodes and enqueue them as old-control-plane payloads.

    This is the compatibility bridge: graph scheduler decides what is safe to
    run, while the existing queue/coordinator still performs the actual wake.
    """
    if graph.get("schema_version") == "solar.scheduler_runtime_projection.v1":
        import scheduler_input

        verification = scheduler_input.verify_runtime_projection(graph, graph_path=graph_path)
        if not verification.get("ok"):
            raise ValueError(
                "scheduler runtime projection refused: "
                + ",".join(str(item) for item in verification.get("errors") or [])
            )
    sys.path.insert(0, str(HARNESS_DIR / "lib"))
    if dry_run:
        enqueue = None
    else:
        from task_queue import enqueue  # noqa: WPS433

    if lease:
        from pane_lease import acquire  # noqa: WPS433
    else:
        acquire = None
    frozen_graph = str(graph.get("planning_authority") or "").strip() == _FROZEN_PLANNING_AUTHORITY
    if not frozen_graph:
        graph = auto_enrich_graph(graph, graph_path=graph_path)
    sid = str(graph.get("sprint_id") or Path(graph_path).stem.replace(".task_graph", ""))
    assignment = assign_ready(graph, workers, max_parallel=max_parallel, graph_path=graph_path)
    queued: list[dict[str, Any]] = list(assignment.get("queued", []))
    enqueued: list[dict[str, Any]] = []

    nodes_by_id = _node_map(graph)
    for item in assignment.get("assigned", []):
        node_id = item["node"]
        pane = item["pane"]
        node = nodes_by_id[node_id]
        admission = node_admission_status(graph, node_id)
        if not admission.get("admitted"):
            queued.append({
                "node": node_id,
                "pane": pane,
                "reason": "admission_rejected",
                "details": admission,
            })
            continue
        dispatch_id = f"graph-{sid}-{node_id}-{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
        frozen_node = _is_frozen_scheduler_node(graph, node)
        if frozen_node:
            capsule_binding = node.get("capsule_binding") if isinstance(node.get("capsule_binding"), dict) else {}
            capsule_ids = [str(value) for value in capsule_binding.get("capsule_ids") or [] if str(value)]
            compiled_plan = {
                "logical_plan_node": {
                    "node_id": node.get("id"),
                    "logical_operator": node.get("logical_operator"),
                    "goal": node.get("goal"),
                    "depends_on": list(node.get("depends_on", []) or []),
                }
            }
            capsule_plan_ir = {
                "schema_version": "solar.capsule_plan_node.v1",
                "node_id": node_id,
                "logical_operator": str(node.get("logical_operator") or ""),
                "selected": bool(capsule_ids),
                "capability_capsule_id": capsule_ids[0] if capsule_ids else "",
                "capsule_ids": capsule_ids,
                "composition_id": capsule_binding.get("composition_id"),
                "contract_sha256": capsule_binding.get("contract_sha256"),
                "capsule_authority": "frozen_scheduler_input",
            }
            physical_plan_ir = {
                "schema_version": "solar.physical_plan_node.v1",
                "node_id": node_id,
                "logical_operator": str(node.get("logical_operator") or ""),
                "selected_operator_id": str(item.get("operator_id") or ""),
                "execution_candidates": deepcopy(node.get("physical_candidates") or []),
                "attached_capsules": capsule_ids,
                "verifier_plans": [],
                "plan_authority": "frozen_scheduler_input",
            }
            plan_artifacts = {
                "authority": "frozen_scheduler_input",
                "scheduler_input_ref": deepcopy(graph.get("scheduler_input_ref") or {}),
            }
        else:
            try:
                from apo_plan_compiler import (  # noqa: WPS433
                    compile_execution_plan_for_node,
                    materialize_execution_plan_artifacts,
                )

                compiled_plan = compile_execution_plan_for_node(
                    node,
                    request_type=str(graph.get("request_type") or node.get("type") or ""),
                    lane_hint=str(graph.get("lane") or ""),
                    registry_path=HARNESS_DIR / "config" / "capability-capsules.registry.yaml",
                    operators_path=HARNESS_DIR / "config" / "physical-operators.json",
                )
                capsule_plan_ir = dict(compiled_plan.get("capsule_plan") or {})
                _enforce_contract_capsule_authority(graph, node, capsule_plan_ir)
                physical_plan_ir = dict(compiled_plan.get("physical_plan") or {})
                plan_artifacts = materialize_execution_plan_artifacts(
                    sid,
                    node_id,
                    capsule_plan=capsule_plan_ir,
                    physical_plan=physical_plan_ir,
                    base_dir=SPRINTS_DIR,
                )
                # Store APO supply-chain planning artifact for evidence ledger and downstream
                plan_artifacts["task_classification"] = compiled_plan.get("task_classification") or {}
                plan_artifacts["logical_workflow"] = compiled_plan.get("logical_workflow") or {}
                plan_artifacts["skill_plan"] = compiled_plan.get("skill_plan") or {}
                plan_artifacts["mcp_plan"] = compiled_plan.get("mcp_plan") or {}
                plan_artifacts["capsule_plan_artifact"] = compiled_plan.get("capsule_plan_artifact") or {}
                plan_artifacts["selection_rationale"] = compiled_plan.get("selection_rationale") or {}
                plan_artifacts["evidence_policy"] = compiled_plan.get("evidence_policy") or {}
            except Exception:
                compiled_plan = {
                    "logical_plan_node": {
                        "node_id": node.get("id"),
                        "logical_operator": node.get("logical_operator"),
                        "goal": node.get("goal"),
                        "depends_on": list(node.get("depends_on", []) or []),
                    }
                }
                capsule_plan_ir = {
                    "schema_version": "solar.capsule_plan_node.v1",
                    "node_id": node_id,
                    "logical_operator": str(node.get("logical_operator") or ""),
                    "selected": False,
                    "stages": [],
                }
                physical_plan_ir = {
                    "schema_version": "solar.physical_plan_node.v1",
                    "node_id": node_id,
                    "logical_operator": str(node.get("logical_operator") or ""),
                    "selected_operator_id": "",
                    "execution_candidates": [],
                    "attached_capsules": [],
                    "verifier_plans": [],
                }
                plan_artifacts = materialize_execution_plan_artifacts(
                    sid,
                    node_id,
                    capsule_plan=capsule_plan_ir,
                    physical_plan=physical_plan_ir,
                    base_dir=SPRINTS_DIR,
                )
        node["logical_plan_node"] = dict(compiled_plan.get("logical_plan_node") or {})
        node["capsule_plan_ir"] = capsule_plan_ir
        node["physical_plan_ir"] = physical_plan_ir
        if capsule_plan_ir.get("capability_capsule_id"):
            node["capability_native"] = True
            node["capability_capsule_id"] = str(capsule_plan_ir.get("capability_capsule_id") or "")
        if not frozen_node:
            artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), dict) else {}
            artifacts["capsule_plan_ir"] = plan_artifacts["capsule_plan_ir_path"]
            artifacts["physical_plan_ir"] = plan_artifacts["physical_plan_ir_path"]
            if physical_plan_ir.get("selected_operator_id"):
                artifacts["selected_operator_id"] = str(physical_plan_ir.get("selected_operator_id") or "")
            node["artifacts"] = artifacts

        lease_result = {"acquired": True, "reason": "lease_disabled"}
        if pane.startswith("operator-pool:"):
            lease_result = {"acquired": True, "reason": "operator_pool_virtual_pane"}
        elif pane.startswith("operator:"):
            # Direct physical operators are not tmux panes.  Their process-safe
            # lease is acquired by operator_runtime.submit at the inbox seam.
            lease_result = {"acquired": True, "reason": "physical_operator_virtual_pane"}
        elif acquire is not None and not dry_run:
            lease_result = acquire(pane, sid, dispatch_id, ttl)
            if not lease_result.get("acquired"):
                set_node_status(graph, node_id, "queued")
                graph.setdefault("node_results", {}).setdefault(node_id, {})
                graph["node_results"][node_id]["blocking_reason"] = lease_result.get("reason", "lease_failed")
                graph["node_results"][node_id]["queued_pane"] = pane
                graph["node_results"][node_id]["updated_at"] = _now()
                queued.append({
                    "node": node_id,
                    "pane": pane,
                    "reason": lease_result.get("reason", "lease_failed"),
                })
                continue

        payload = {
            "type": "graph_node",
            "graph": graph_path,
            "graph_state": str(_state_path_for_graph(graph, graph_path)),
            "closure_record": str(_closure_path_for_graph(graph, graph_path)),
            "sprint_id": sid,
            "node": node,
            "assignment": item,
            "admission": admission,
            "dispatch_id": dispatch_id,
            "lease": lease_result,
            "logical_plan_node": dict(compiled_plan.get("logical_plan_node") or {}),
            "capsule_plan_ir": capsule_plan_ir,
            "physical_plan_ir": physical_plan_ir,
            "plan_artifacts": plan_artifacts,
        }
        if dry_run:
            q = {"ok": True, "result": "dry_run", "id": ""}
        else:
            assert enqueue is not None
            q = enqueue(sid, f"graph_node|node_id={node_id}|pane={pane}|dispatch_id={dispatch_id}", 80, payload)
            # Queueing is not dispatch. The graph node becomes "dispatched"
            # only after graph_node_dispatcher writes the instruction file and
            # successfully submits it to the pane. Marking it dispatched here
            # creates a false-positive state when queue drain/send fails.
            set_node_status(graph, node_id, "assigned", pane=pane, dispatch_id=dispatch_id)
        enqueued_item = {"node": node_id, "pane": pane, "queue": q, "dispatch_id": dispatch_id}
        if dry_run:
            # Dry-run callers still need the exact payload so they can render
            # node dispatch files and validate worker-visible context without
            # mutating the persistent queue.
            enqueued_item["payload"] = payload
        enqueued.append(enqueued_item)

    blocked_workers: list[dict[str, Any]] = []
    for item in queued:
        if item.get("reason") == "frozen_physical_candidates_unavailable":
            node_id = str(item.get("node") or "")
            if node_id and node_id in nodes_by_id:
                set_node_status(graph, node_id, "queued")
                graph.setdefault("node_results", {}).setdefault(node_id, {})
                graph["node_results"][node_id]["blocking_reason"] = item["reason"]
                graph["node_results"][node_id]["candidate_observations"] = (
                    item.get("details", {}).get("candidate_observations", [])
                )
                graph["node_results"][node_id]["updated_at"] = _now()
            continue
        if item.get("reason") != "no_matching_worker":
            continue
        node_id = str(item.get("node") or "")
        if not node_id or node_id not in nodes_by_id:
            continue
        set_node_status(graph, node_id, "worker_blocked")
        graph.setdefault("node_results", {}).setdefault(node_id, {})
        graph["node_results"][node_id]["blocking_reason"] = "no_matching_worker"
        graph["node_results"][node_id]["worker_match_details"] = item.get("details", {})
        graph["node_results"][node_id]["updated_at"] = _now()
        blocked_workers.append({"node": node_id, "reason": "no_matching_worker", "details": item.get("details", {})})

    return {
        "ok": True,
        "sprint_id": sid,
        "batch": assignment.get("batch", []),
        "blocked_prerequisites": assignment.get("blocked_prerequisites", []),
        "capability_enrichment": assignment.get("capability_enrichment", {}),
        "enqueued": enqueued,
        "queued": queued,
        "worker_blocked": blocked_workers,
        "dry_run": dry_run,
    }


def enrich_backlog(sprints_dir: str | Path, dry_run: bool = False,
                   backup_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(sprints_dir).expanduser()
    if not root.exists():
        raise ValueError(f"sprints dir not found: {root}")
    graphs = sorted(root.glob("*.task_graph.json"))
    backup_root = Path(backup_dir).expanduser() if backup_dir else (
        HARNESS_DIR / "state" / "task-graph-enrich-backups" / datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    )
    changed: list[dict[str, Any]] = []
    unchanged: list[str] = []
    errors: list[dict[str, str]] = []

    for graph_path in graphs:
        try:
            before_text = graph_path.read_text(encoding="utf-8")
            graph = json.loads(before_text)
            before_caps = _required_capability_snapshot(graph)
            enriched = auto_enrich_graph(graph, graph_path=graph_path)
            after_caps = _required_capability_snapshot(enriched)
            after_text = json.dumps(enriched, indent=2, ensure_ascii=False) + "\n"
            nodes = [node_id for node_id, caps in after_caps.items() if caps != before_caps.get(node_id, [])]
            if not nodes:
                unchanged.append(graph_path.name)
                continue
            if not dry_run:
                backup_root.mkdir(parents=True, exist_ok=True)
                shutil.copy2(graph_path, backup_root / graph_path.name)
                save_graph(graph_path, enriched)
            changed.append({
                "graph": str(graph_path),
                "changed_nodes": nodes,
                "node_count": len(_nodes(enriched)),
            })
        except Exception as exc:
            errors.append({"graph": str(graph_path), "error": str(exc)})

    return {
        "ok": not errors,
        "sprints_dir": str(root),
        "graph_count": len(graphs),
        "changed_count": len(changed),
        "unchanged_count": len(unchanged),
        "backup_dir": str(backup_root) if changed and not dry_run else "",
        "dry_run": dry_run,
        "changed": changed,
        "errors": errors,
    }


def parent_ready_check(graph: dict[str, Any]) -> dict[str, Any]:
    _ensure_required_gate_node_mapping(graph)
    ids = _node_map(graph)
    open_nodes = [
        node_id for node_id in ids
        if node_status(graph, node_id) not in (PASS_STATUSES | CLOSED_NON_PASS_STATUSES)
    ]
    failed_nodes = [node_id for node_id in ids if node_status(graph, node_id) == "failed"]
    human_review_nodes = [
        node_id for node_id in ids
        if node_status(graph, node_id) == HUMAN_REVIEW_STATUS
    ]
    terminal_blocker_nodes = set(failed_nodes) | set(human_review_nodes)
    terminal_status = ""
    if open_nodes and all(node_id in terminal_blocker_nodes for node_id in open_nodes):
        terminal_status = "failed" if failed_nodes else HUMAN_REVIEW_STATUS

    required_gates = graph.get("required_gates")
    if required_gates is None:
        required_gates = [node.get("gate") for node in ids.values() if node.get("gate")]
    required_gates = [str(g) for g in required_gates if g]

    graph.setdefault("gate_results", {})
    gate_results = graph.get("gate_results") or {}
    for gate in required_gates:
        gate_nodes = [node_id for node_id, node in ids.items() if str(node.get("gate") or "") == gate]
        if gate_nodes and all(node_status(graph, node_id) in PASS_STATUSES for node_id in gate_nodes):
            verdicts_ok, blocking_node, verdict_detail = _gate_verdicts_ok(graph, gate_nodes)
            current_gate = gate_results.get(gate)
            if not verdicts_ok:
                # All member nodes executed, but a verifier/critic verdict is FAIL/block:
                # consume verdict CONTENT, not just node completion -> do NOT self-heal to passed.
                if not isinstance(current_gate, dict) or current_gate.get("status") != "blocked":
                    graph["gate_results"][gate] = {
                        "status": "blocked",
                        "node": blocking_node,
                        "updated_at": _now(),
                        "reason": f"gate_verdict_block:{verdict_detail}",
                    }
            elif not isinstance(current_gate, dict) or current_gate.get("status") != "passed":
                graph["gate_results"][gate] = {
                    "status": "passed",
                    "node": gate_nodes[-1],
                    "updated_at": _now(),
                    "reason": "parent_ready_self_heal",
                }
    gate_results = graph.get("gate_results") or {}
    missing_gates = [
        gate for gate in required_gates
        if not isinstance(gate_results.get(gate), dict) or gate_results[gate].get("status") != "passed"
    ]

    ready = not open_nodes and not failed_nodes and not missing_gates and bool(ids)
    return {
        "ok": True,
        "sprint_id": graph.get("sprint_id"),
        "ready": ready,
        "node_count": len(ids),
        "open_nodes": open_nodes,
        "failed_nodes": failed_nodes,
        "human_review_nodes": human_review_nodes,
        "terminal_status": terminal_status or None,
        "required_gates": required_gates,
        "missing_gates": missing_gates,
    }


def epic_child_activation(graph: dict[str, Any]) -> dict[str, Any]:
    """Return per-child activation state for an epic-level task graph.

    Used by autopilot/wake to decide which child sprint to dispatch next
    without skipping cross-sprint dependencies. Locks in the policy:

      - A child is ``ready`` only when **every** entry in its ``depends_on``
        list points to a sibling child whose status is in PASS_STATUSES.
      - A child is ``blocked`` if any dependency is not yet passed; the
        ``unmet`` list records exactly which deps still need to clear.
      - The parent epic ``can_close`` only when every child has reached a
        terminal status and at least one is passed (i.e. all required work
        landed). Failed children prevent closure.

    Works on any graph that follows the in-sprint conventions (``nodes``
    with ``id``/``status``/``depends_on``), including
    ``solar.epic.task_graph.v1`` graphs whose nodes are sprint IDs.
    """
    ids = _node_map(graph)
    ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    done: list[str] = []
    failed: list[str] = []
    pending_or_active: list[str] = []

    for child_id, node in ids.items():
        status = node_status(graph, child_id)
        if status in PASS_STATUSES:
            done.append(child_id)
            continue
        if status == "failed":
            failed.append(child_id)
            continue
        if status in CLOSED_NON_PASS_STATUSES:
            # skipped/cancelled children neither block nor unlock siblings.
            continue
        pending_or_active.append(child_id)

        deps = _internal_depends_on(node)
        unmet = [dep for dep in deps if not _is_passed(graph, dep)]
        record = {
            "child_id": child_id,
            "status": status,
            "depends_on": deps,
            "unmet": unmet,
        }
        if unmet:
            blocked.append(record)
        else:
            ready.append(record)

    epic_done = bool(ids) and not pending_or_active and not failed
    can_close = epic_done and bool(done)

    return {
        "ok": True,
        "epic_id": graph.get("epic_id") or graph.get("sprint_id"),
        "schema_version": graph.get("schema_version"),
        "children_total": len(ids),
        "ready": ready,
        "blocked": blocked,
        "done": done,
        "failed": failed,
        "epic_done": epic_done,
        "can_close": can_close,
    }


def _epic_node_for_child(epic_graph: dict[str, Any], child_sprint_id: str) -> dict[str, Any] | None:
    nodes = epic_graph.get("nodes") if isinstance(epic_graph.get("nodes"), list) else []
    for node in nodes:
        if isinstance(node, dict) and str(node.get("child_sprint_id") or "") == child_sprint_id:
            return node
    return None


def child_sprint_dependency_blockers(
    child_sprint_id: str,
    epic_graph: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return unmet parent-epic dependencies for a child sprint."""
    if not child_sprint_id or not isinstance(epic_graph, dict):
        return []
    child_node = _epic_node_for_child(epic_graph, child_sprint_id)
    if not child_node:
        return []
    epic_ids = _node_map(epic_graph)
    blockers: list[dict[str, Any]] = []
    for dep_id in child_node.get("depends_on") or []:
        dep_key = str(dep_id or "")
        dep_node = epic_ids.get(dep_key)
        dep_status = node_status(epic_graph, dep_key) if dep_node else "missing"
        if dep_status not in (PASS_STATUSES | {"completed", "eval_passed"}):
            blockers.append({
                "node": dep_key,
                "child_sprint_id": (dep_node or {}).get("child_sprint_id"),
                "current_status": dep_status,
                "required_status": "passed",
            })
    return blockers


def activation_route_decision(
    graph: dict[str, Any],
    *,
    graph_path: str | Path | None = None,
    child_status: dict[str, Any] | None = None,
    epic_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute a graph-backed autopilot route decision without mutating queues."""
    child_status = child_status if isinstance(child_status, dict) else {}
    sprint_id = str(graph.get("sprint_id") or child_status.get("sprint_id") or child_status.get("id") or "")
    try:
        validation = validate_graph(graph)
    except Exception as exc:
        validation = {"ok": False, "errors": [str(exc)], "warnings": []}
    parent_blockers = [] if not validation.get("ok") else child_sprint_dependency_blockers(sprint_id, epic_graph)
    external_blockers = [] if not validation.get("ok") else blocked_external_prerequisites(graph)
    ready = [] if not validation.get("ok") or parent_blockers or external_blockers else ready_nodes(graph)
    phase = str(child_status.get("phase") or "").strip()
    target_role = str(child_status.get("target_role") or child_status.get("handoff_to") or "").strip()
    if not target_role and phase == "planning_complete":
        target_role = "builder_main"
    route_role = "builder_main" if target_role == "builder_main" or phase == "planning_complete" else "planner"

    blocked_reason = ""
    if not validation.get("ok"):
        blocked_reason = "task_graph_validation_failed"
    elif parent_blockers:
        blocked_reason = "parent_dependency_blocked"
    elif external_blockers:
        blocked_reason = "external_prerequisite_blocked"
    elif not ready:
        blocked_reason = "no_ready_nodes"

    return {
        "ok": True,
        "sprint_id": sprint_id,
        "graph_path": str(graph_path or ""),
        "phase": phase,
        "route_role": route_role,
        "target_role": target_role,
        "ready_nodes": [str(node.get("id") or "") for node in ready],
        "ready_count": len(ready),
        "can_dispatch": bool(ready) and not blocked_reason and target_role == "builder_main",
        "blocked_reason": blocked_reason,
        "validation": {
            "ok": bool(validation.get("ok")),
            "errors": validation.get("errors") or [],
            "warnings": validation.get("warnings") or [],
        },
        "parent_blockers": parent_blockers,
        "external_blockers": external_blockers,
    }


def doctor_graph(graph: dict[str, Any], repair: bool = False) -> dict[str, Any]:
    """Detect and optionally repair graph state drift.

    The scheduler historically stored status in both inline node fields and
    node_results. If the two disagree, a stale node_results entry can make a
    passed node look open forever. This doctor treats newer timestamps as the
    winner and can repair the older side.
    """
    issues: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    # Lane 3 (R4 / review 3.1): on the contracted path the doctor is neutralized
    # independent of the feature-flag state. Its would-be writes are returned as
    # suppressed records and, when the ledger is enabled, also recorded there as
    # author.type=doctor / gate_consumable=false / applied=false.
    doctor_neutralized = bool(
        repair
        and str((graph or {}).get("workflow_contract_id") or "").strip()
    )

    def _doctor_write_suppressed(
        node_id: str,
        from_status: str,
        to_status: str,
        repair_name: str,
        *,
        reason: str = "doctor_neutralized_on_contracted_path",
    ) -> None:
        _ledger_transition(
            graph, node_id, from_status, to_status, "doctor_graph",
            applied=False, author_type="doctor", note=repair_name,
        )
        suppressed.append({
            "node": node_id,
            "would_write": to_status,
            "from": from_status,
            "repair": repair_name,
            "reason": reason,
        })

    ids = _node_map(graph)
    results = _node_results(graph)

    for node_id, node in ids.items():
        evidence_sync = _sync_node_evidence_refs(graph, node_id, repair=repair)
        issues.extend(evidence_sync["issues"])
        repairs.extend(evidence_sync["repairs"])
        inline_status = str(node.get("status", "") or "").lower()
        result = results.get(node_id) if isinstance(results.get(node_id), dict) else {}
        result_status = str((result or {}).get("status", "") or "").lower()
        if _human_review_is_blocking(node, result) and inline_status != result_status:
            issue = {
                "type": "human_review_status_drift",
                "node": node_id,
                "inline_status": inline_status,
                "inline_updated_at": node.get("updated_at", ""),
                "result_status": result_status,
                "result_updated_at": result.get("updated_at", ""),
                "effective_status": HUMAN_REVIEW_STATUS,
            }
            issues.append(issue)
            if repair:
                refused_status = result_status if result_status != HUMAN_REVIEW_STATUS else inline_status
                _doctor_write_suppressed(
                    node_id,
                    HUMAN_REVIEW_STATUS,
                    refused_status,
                    "human_review_exit_refused",
                    reason="needs_human_review_requires_explicit_resume",
                )
            continue
        if _passed_without_required_eval(graph, node_id) and ("passed" in {inline_status, result_status}):
            issue = {
                "type": "passed_missing_eval",
                "node": node_id,
                "inline_status": inline_status,
                "inline_updated_at": node.get("updated_at", ""),
                "result_status": result_status,
                "result_updated_at": result.get("updated_at", ""),
                "effective_status": "reviewing",
            }
            issues.append(issue)
            if repair and doctor_neutralized:
                _doctor_write_suppressed(node_id, node_status(graph, node_id), "reviewing", "reopened_passed_missing_eval")
            elif repair:
                now = _now()
                _ledger_transition(graph, node_id, node_status(graph, node_id), "reviewing",
                                   "doctor_graph", author_type="doctor", note="reopened_passed_missing_eval")
                node["status"] = "reviewing"
                node["updated_at"] = now
                graph.setdefault("node_results", {})
                graph["node_results"].setdefault(node_id, {})
                graph["node_results"][node_id]["status"] = "reviewing"
                graph["node_results"][node_id]["updated_at"] = now
                repairs.append({**issue, "repair": "reopened_passed_missing_eval"})
            continue
        if not inline_status or not result_status or inline_status == result_status:
            continue
        inline_ts = _parse_ts(node.get("updated_at"))
        result_ts = _parse_ts(result.get("updated_at"))
        effective = node_status(graph, node_id)
        issue = {
            "type": "node_status_drift",
            "node": node_id,
            "inline_status": inline_status,
            "inline_updated_at": node.get("updated_at", ""),
            "result_status": result_status,
            "result_updated_at": result.get("updated_at", ""),
            "effective_status": effective,
        }
        issues.append(issue)
        if not repair:
            continue

        if doctor_neutralized:
            if inline_ts and result_ts and inline_ts > result_ts:
                _doctor_write_suppressed(node_id, effective, inline_status, "node_results_updated_from_inline")
            elif result_ts and inline_ts and result_ts > inline_ts:
                _doctor_write_suppressed(node_id, effective, result_status, "inline_updated_from_node_results")
            elif inline_status == "passed":
                _doctor_write_suppressed(node_id, effective, inline_status, "node_results_updated_from_inline_passed")
            elif result_status == "passed":
                _doctor_write_suppressed(node_id, effective, result_status, "inline_updated_from_node_results_passed")
            continue

        if inline_ts and result_ts and inline_ts > result_ts:
            _ledger_transition(graph, node_id, effective, inline_status, "doctor_graph",
                               author_type="doctor", note="node_results_updated_from_inline")
            result["status"] = inline_status
            result["updated_at"] = node.get("updated_at")
            repairs.append({**issue, "repair": "node_results_updated_from_inline"})
        elif result_ts and inline_ts and result_ts > inline_ts:
            _ledger_transition(graph, node_id, effective, result_status, "doctor_graph",
                               author_type="doctor", note="inline_updated_from_node_results")
            node["status"] = result_status
            node["updated_at"] = result.get("updated_at")
            repairs.append({**issue, "repair": "inline_updated_from_node_results"})
        elif inline_status == "passed":
            _ledger_transition(graph, node_id, effective, inline_status, "doctor_graph",
                               author_type="doctor", note="node_results_updated_from_inline_passed")
            result["status"] = inline_status
            result["updated_at"] = node.get("updated_at") or result.get("updated_at") or _now()
            repairs.append({**issue, "repair": "node_results_updated_from_inline_passed"})
        elif result_status == "passed":
            _ledger_transition(graph, node_id, effective, result_status, "doctor_graph",
                               author_type="doctor", note="inline_updated_from_node_results_passed")
            node["status"] = result_status
            node["updated_at"] = result.get("updated_at") or node.get("updated_at") or _now()
            repairs.append({**issue, "repair": "inline_updated_from_node_results_passed"})

    parent = parent_ready_check(graph)
    result_payload = {
        "ok": not issues,
        "sprint_id": graph.get("sprint_id"),
        "issues": issues,
        "repairs": repairs,
        "parent": parent,
        "repaired": bool(repairs),
    }
    if suppressed:
        result_payload["suppressed"] = suppressed
    return result_payload


def _workers_from_file(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        workers = data.get("workers", [])
        if not isinstance(workers, list):
            return []
        return [_normalize_worker_entry(worker) for worker in workers if isinstance(worker, dict)]
    if isinstance(data, list):
        return [_normalize_worker_entry(worker) for worker in data if isinstance(worker, dict)]
    raise ValueError("workers file must be a list or {workers: [...]}")


def _normalize_worker_entry(worker: dict[str, Any]) -> dict[str, Any]:
    """Accept both scheduler workers and multi_task_screen.workers.v1 rows."""
    normalized = dict(worker)
    pane = str(normalized.get("pane") or normalized.get("id") or "").strip()
    if pane and not normalized.get("pane"):
        normalized["pane"] = pane
    role = str(normalized.get("role") or "").lower()
    if role == "planner" and not normalized.get("skills"):
        normalized["skills"] = [
            "workflow.planning",
            "browser.qa",
            "debug.systematic",
            "skill.methodology",
        ]
    if role == "planner" and not normalized.get("capabilities"):
        normalized["capabilities"] = [
            "harness.context_preflight",
            "harness.dispatch_visibility",
            "harness.dag",
            "artifact.requirement_trace",
            "browser.browse",
            "code.review",
            "test.tdd",
        ]
    if (role in {"builder", "lab", "lab-builder", "evaluator"} or "harness-lab" in pane) and not normalized.get("skills"):
        normalized["skills"] = [
            "bash",
            "shell",
            "python",
            "sqlite",
            "sqlite3",
            "ffmpeg",
            "testing",
            "test_execution",
            "code_impl",
            "test_generation",
            "planning",
            "state-machine",
            "state_machine",
            "data.modeling",
            "data-modeling",
            "observability",
            "optimization",
            "runtime_design",
            "solar-harness-verification",
            "solar-harness-compat-review",
            "compat-review",
            "compatibility",
            "harness.verification",
            "verification",
            "verifier",
            "review",
            "ai-rag-pipeline",
            "reporting",
        ]
    if (role in {"builder", "lab", "lab-builder", "evaluator"} or "harness-lab" in pane) and not normalized.get("capabilities"):
        normalized["capabilities"] = [
            "bash",
            "python",
            "sqlite",
            "sqlite3",
            "ffmpeg",
            "testing",
            "test_execution",
            "code_impl",
            "test_generation",
            "state-machine",
            "state_machine",
            "data.modeling",
            "data-modeling",
            "repair.pr-cot",
            "failure.structured_repair",
            "routing.complexity_budget",
            "optimization",
            "runtime_design",
            "solar-harness-verification",
            "solar-harness-compat-review",
            "compat-review",
            "compatibility",
            "harness.verification",
            "verification",
            "code.review",
            "ai-rag-pipeline",
            "reporting",
            "model.routing",
            "harness.model_routing",
        ]
    if not normalized.get("models"):
        if "lab" in pane or role in {"lab", "lab-builder"}:
            normalized["models"] = ["glm", "glm-5", "glm-5.1", "zhipu"]
        elif pane.endswith(".2") or pane.endswith(".3"):
            normalized["models"] = ["opus", "claude-opus", "anthropic-opus"]
    return normalized


def main() -> int:
    ap = argparse.ArgumentParser(prog="graph_scheduler.py")
    sub = ap.add_subparsers(dest="cmd")

    def add_graph(p: argparse.ArgumentParser) -> None:
        p.add_argument("--graph", required=True)

    p = sub.add_parser("validate")
    add_graph(p)

    p = sub.add_parser("topo")
    add_graph(p)

    p = sub.add_parser("layers")
    add_graph(p)

    p = sub.add_parser("critical-path")
    add_graph(p)

    p = sub.add_parser("ready")
    add_graph(p)

    p = sub.add_parser("batches")
    add_graph(p)
    p.add_argument("--max-parallel", type=int)
    p.add_argument("--out")

    p = sub.add_parser("enrich-capabilities")
    add_graph(p)
    p.add_argument("--source")
    p.add_argument("--out")
    p.add_argument("--in-place", action="store_true")
    p.add_argument("--overwrite", action="store_true")

    p = sub.add_parser("assign")
    add_graph(p)
    p.add_argument("--workers", required=True)
    p.add_argument("--max-parallel", type=int)
    p.add_argument("--source")

    p = sub.add_parser("mark")
    add_graph(p)
    p.add_argument("--node", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--note")
    p.add_argument("--in-place", action="store_true")

    p = sub.add_parser("parent-check")
    add_graph(p)

    p = sub.add_parser("doctor")
    add_graph(p)
    p.add_argument("--repair", action="store_true")
    p.add_argument("--in-place", action="store_true")

    p = sub.add_parser("enqueue-ready")
    add_graph(p)
    p.add_argument("--workers", required=True)
    p.add_argument("--max-parallel", type=int)
    p.add_argument("--lease", action="store_true")
    p.add_argument("--ttl", type=int, default=600)
    p.add_argument("--in-place", action="store_true")

    p = sub.add_parser("enrich-backlog")
    p.add_argument("--sprints-dir", default=str(HARNESS_DIR / "sprints"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--backup-dir")

    args = ap.parse_args()

    try:
        if args.cmd == "validate":
            print(json.dumps(validate_graph(load_graph(args.graph)), ensure_ascii=False))

        elif args.cmd == "topo":
            graph = load_graph(args.graph)
            print(json.dumps({"ok": True, "order": topo_order(graph)}, ensure_ascii=False))

        elif args.cmd == "layers":
            graph = load_graph(args.graph)
            print(json.dumps({"ok": True, "layers": topo_layers(graph)}, ensure_ascii=False))

        elif args.cmd == "critical-path":
            graph = load_graph(args.graph)
            result = critical_path(graph)
            result["ok"] = True
            print(json.dumps(result, ensure_ascii=False))

        elif args.cmd == "ready":
            graph = load_graph(args.graph)
            print(json.dumps({
                "ok": True,
                "nodes": [n["id"] for n in ready_nodes(graph)],
                "blocked_prerequisites": blocked_external_prerequisites(graph),
            }, ensure_ascii=False))

        elif args.cmd == "batches":
            graph = load_graph(args.graph)
            result = make_batches(graph, args.max_parallel)
            if args.out:
                Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
            print(json.dumps(result, ensure_ascii=False))

        elif args.cmd == "enrich-capabilities":
            from capability_inference import enrich_graph  # noqa: WPS433

            graph = load_graph(args.graph)
            source_text = ""
            if args.source:
                source_text = Path(args.source).read_text(encoding="utf-8", errors="replace")
            result_graph = enrich_graph(graph, source_text=source_text, overwrite=args.overwrite)
            if args.in_place:
                save_graph(args.graph, result_graph)
            elif args.out:
                save_graph(args.out, result_graph)
            print(json.dumps(result_graph.get("capability_inference", {"ok": True}), ensure_ascii=False))

        elif args.cmd == "assign":
            graph = load_graph(args.graph)
            workers = _workers_from_file(args.workers)
            print(json.dumps(assign_ready(graph, workers, args.max_parallel, args.graph, args.source), ensure_ascii=False))

        elif args.cmd == "mark":
            graph = load_graph(args.graph)
            result = mark_node_result(graph, args.node, args.status, note=args.note)
            if args.in_place:
                save_graph(args.graph, graph)
                result["status_sync"] = sync_status_cache_from_graph(
                    graph,
                    args.graph,
                    event=f"graph_mark_{args.node}_{args.status}",
                )
            print(json.dumps(result, ensure_ascii=False))

        elif args.cmd == "parent-check":
            print(json.dumps(parent_ready_check(load_graph(args.graph)), ensure_ascii=False))

        elif args.cmd == "doctor":
            graph = load_graph(args.graph)
            result = doctor_graph(graph, repair=args.repair)
            if args.in_place and result.get("repaired"):
                save_graph(args.graph, graph)
            if args.in_place and args.repair:
                result["status_sync"] = sync_status_cache_from_graph(
                    graph,
                    args.graph,
                    event="graph_doctor_repair_sync",
                )
            print(json.dumps(result, ensure_ascii=False))

        elif args.cmd == "enqueue-ready":
            graph = load_graph(args.graph)
            workers = _workers_from_file(args.workers)
            result = enqueue_ready(graph, args.graph, workers, args.max_parallel, args.lease, args.ttl)
            if args.in_place:
                save_graph(args.graph, graph)
            print(json.dumps(result, ensure_ascii=False))

        elif args.cmd == "enrich-backlog":
            print(json.dumps(enrich_backlog(args.sprints_dir, args.dry_run, args.backup_dir), ensure_ascii=False))

        else:
            ap.print_help()
            return 1

    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
