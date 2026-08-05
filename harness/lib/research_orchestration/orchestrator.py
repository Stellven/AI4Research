"""Solar-owned research orchestration runtime core."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Callable


class ResearchOrchestrationError(ValueError):
    """Raised when orchestration cannot proceed safely."""


NODE_STATUSES = {
    "pending",
    "ready",
    "running",
    "awaiting_human",
    "awaiting_external",
    "completed",
    "failed",
    "blocked",
    "cancelled",
}
RUN_STATUSES = {
    "pending",
    "running",
    "awaiting_human",
    "awaiting_external",
    "completed",
    "failed",
    "blocked",
    "cancelled",
}
TERMINAL_NODE_STATUSES = {"completed", "failed", "blocked", "cancelled"}
TERMINAL_RUN_STATUSES = {"completed", "failed", "blocked", "cancelled"}
STOPPING_RUN_STATUSES = TERMINAL_RUN_STATUSES | {"awaiting_human", "awaiting_external"}


class ResearchOrchestrator:
    """Execute a research task contract while keeping Solar as state owner."""

    def __init__(
        self,
        *,
        task_contract: dict,
        workflow_selector: Callable[[dict], dict] | dict,
        state_store: Any,
        dispatch_callable: Callable[[dict], dict],
        evaluator_callable: Callable[[dict, dict, dict], dict],
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.task_contract = deepcopy(task_contract)
        self.workflow_selector = workflow_selector
        self.state_store = state_store
        self.dispatch_callable = dispatch_callable
        self.evaluator_callable = evaluator_callable
        self.clock = clock or _default_clock
        self._workflow: dict | None = None

    def initialize(self) -> dict:
        """Create and persist the initial Solar-owned run state."""

        self._validate_task_contract()
        workflow = self._load_workflow()
        validation_error = self._validate_workflow(workflow)
        if validation_error:
            state = self._failed_initial_state(workflow, validation_error)
            self.state_store.create(state)
            return deepcopy(state)

        now = self.clock()
        node_states = {}
        completed_deps: set[str] = set()
        for node in workflow["nodes"]:
            status = "ready" if not node["depends_on"] else "pending"
            node_states[node["node_id"]] = {
                "node_id": node["node_id"],
                "required_for_completion": bool(node.get("required_for_completion", True)),
                "previous_status": None,
                "status": status,
                "depends_on": list(node.get("depends_on") or []),
                "result_ref": None,
                "updated_at": now,
            }
            if status == "completed":
                completed_deps.add(node["node_id"])
        state = {
            "schema": "research_run_state.v1",
            "task_id": self.task_contract["task_id"],
            "run_id": self.task_contract["run_id"],
            "workflow_id": workflow["workflow_id"],
            "graph_identity": {
                "graph_id": workflow["workflow_id"],
                "graph_version": 1,
                "workflow_kind": workflow["workflow_kind"],
            },
            "node_states": node_states,
            "ready_nodes": self._calculate_ready_nodes_from_states(node_states),
            "current_blockers": [],
            "resume_import_provenance": self._resume_import_provenance(),
            "final_status": "pending",
            "status_updated_at": now,
            "final_status_evidence_refs": [],
        }
        self.state_store.create(state)
        return deepcopy(state)

    def step(self) -> dict:
        """Dispatch at most one ready node, evaluate its evidence, and commit state."""

        state = self._load_or_initialize()
        if state["final_status"] in STOPPING_RUN_STATUSES:
            return deepcopy(state)
        workflow = self._load_workflow()
        state = self._refresh_ready_and_status(state, workflow)
        if state["final_status"] in STOPPING_RUN_STATUSES:
            self.state_store.save(state)
            return deepcopy(state)

        ready_nodes = list(state.get("ready_nodes") or [])
        if not ready_nodes:
            state["final_status"] = "running"
            state["status_updated_at"] = self.clock()
            self.state_store.save(state)
            return deepcopy(state)

        node_id = ready_nodes[0]
        node = self._node_by_id(workflow, node_id)
        node_state = state["node_states"][node_id]
        if node_state["status"] == "completed":
            return deepcopy(self._refresh_ready_and_status(state, workflow))

        request = self._node_request(node, state)
        self._transition_node(state, node_id, "running")
        state["final_status"] = "running"
        state["ready_nodes"] = self._calculate_ready_nodes_from_states(state["node_states"])
        state["status_updated_at"] = self.clock()
        self.state_store.save(state)

        result = self._dispatch(request)
        decision = self._evaluate(request, result, state)
        state = self._commit_evaluation(state, node_id, result, decision)
        state = self._refresh_ready_and_status(state, workflow)
        self.state_store.save(state)
        return deepcopy(state)

    def run_until_blocked(self, max_steps: int = 100) -> dict:
        """Run until terminal, awaiting external input, or max_steps is reached."""

        if max_steps < 1:
            raise ResearchOrchestrationError("max_steps must be >= 1")
        state = self._load_or_initialize()
        for _ in range(max_steps):
            if state["final_status"] in STOPPING_RUN_STATUSES:
                return deepcopy(state)
            before = deepcopy(state)
            state = self.step()
            if state["final_status"] in STOPPING_RUN_STATUSES:
                return deepcopy(state)
            if before == state:
                break
        if state["final_status"] not in STOPPING_RUN_STATUSES:
            state["current_blockers"] = [
                {
                    "blocker_id": "max_steps_exceeded",
                    "node_id": "__run__",
                    "reason": f"run did not finish within max_steps={max_steps}",
                }
            ]
            state["final_status"] = "blocked"
            state["status_updated_at"] = self.clock()
            self.state_store.save(state)
        return deepcopy(state)

    def resume(self) -> dict:
        """Load persisted state and continue readiness calculation without rerunning completed nodes."""

        state = self.state_store.load(self.task_contract["run_id"])
        if state is None:
            return self.initialize()
        workflow = self._load_workflow()
        state = self._refresh_ready_and_status(state, workflow)
        self.state_store.save(state)
        return deepcopy(state)

    def _load_or_initialize(self) -> dict:
        state = self.state_store.load(self.task_contract["run_id"])
        if state is None:
            return self.initialize()
        return deepcopy(state)

    def _validate_task_contract(self) -> None:
        required = {"task_id", "run_id", "workflow_kind", "run_mode", "seed_inputs"}
        missing = sorted(key for key in required if key not in self.task_contract)
        if missing:
            raise ResearchOrchestrationError(f"task contract missing fields: {', '.join(missing)}")
        run_mode = self.task_contract["run_mode"]
        if run_mode == "execute":
            if self.task_contract.get("supplied_evidence"):
                raise ResearchOrchestrationError("execute mode cannot consume supplied evidence")
            for seed in self.task_contract.get("seed_inputs") or []:
                if isinstance(seed, dict) and seed.get("seed_kind") == "external_evidence":
                    raise ResearchOrchestrationError("execute mode cannot consume imported evidence seeds")
        elif run_mode in {"resume", "import_evidence"}:
            supplied = self.task_contract.get("supplied_evidence") or []
            external_seeds = [
                seed for seed in self.task_contract.get("seed_inputs") or []
                if isinstance(seed, dict) and seed.get("seed_kind") == "external_evidence"
            ]
            if not supplied and not external_seeds:
                raise ResearchOrchestrationError(f"{run_mode} requires imported evidence provenance")
        else:
            raise ResearchOrchestrationError(f"unsupported run_mode: {run_mode}")

    def _load_workflow(self) -> dict:
        if self._workflow is not None:
            return deepcopy(self._workflow)
        if callable(self.workflow_selector):
            workflow = self.workflow_selector(deepcopy(self.task_contract))
        else:
            workflow = deepcopy(self.workflow_selector)
        if not isinstance(workflow, dict):
            raise ResearchOrchestrationError("workflow_selector must return a workflow object")
        self._workflow = workflow
        return deepcopy(workflow)

    def _validate_workflow(self, workflow: dict) -> str:
        nodes = workflow.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            return "workflow must contain non-empty nodes"
        ids: set[str] = set()
        for node in nodes:
            if not isinstance(node, dict):
                return "workflow nodes must be objects"
            node_id = node.get("node_id")
            if not isinstance(node_id, str) or not node_id:
                return "workflow node missing node_id"
            if node_id in ids:
                return f"duplicate node id: {node_id}"
            ids.add(node_id)
        for node in nodes:
            for dep in node.get("depends_on") or []:
                if dep not in ids:
                    return f"{node['node_id']} depends on missing node {dep}"
        return self._cycle_error(workflow)

    def _cycle_error(self, workflow: dict) -> str:
        nodes = {node["node_id"]: node for node in workflow["nodes"]}
        indegree = {node_id: 0 for node_id in nodes}
        outgoing = {node_id: [] for node_id in nodes}
        for node_id, node in nodes.items():
            for dep in node.get("depends_on") or []:
                indegree[node_id] += 1
                outgoing[dep].append(node_id)
        queue = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
        seen = []
        while queue:
            node_id = queue.pop(0)
            seen.append(node_id)
            for child in sorted(outgoing[node_id]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
                    queue.sort()
        if len(seen) != len(nodes):
            cycle_nodes = sorted(node_id for node_id, degree in indegree.items() if degree > 0)
            return "cycle detected: " + ", ".join(cycle_nodes)
        return ""

    def _failed_initial_state(self, workflow: dict, reason: str) -> dict:
        now = self.clock()
        workflow_id = str(workflow.get("workflow_id") or "invalid_workflow")
        workflow_kind = str(workflow.get("workflow_kind") or self.task_contract.get("workflow_kind") or "research_synthesis")
        return {
            "schema": "research_run_state.v1",
            "task_id": self.task_contract["task_id"],
            "run_id": self.task_contract["run_id"],
            "workflow_id": workflow_id,
            "graph_identity": {"graph_id": workflow_id, "graph_version": 1, "workflow_kind": workflow_kind},
            "node_states": {
                "__workflow__": {
                    "node_id": "__workflow__",
                    "required_for_completion": True,
                    "previous_status": None,
                    "status": "blocked",
                    "depends_on": [],
                    "result_ref": None,
                    "updated_at": now,
                }
            },
            "ready_nodes": [],
            "current_blockers": [{"blocker_id": "invalid_workflow", "node_id": "__workflow__", "reason": reason}],
            "resume_import_provenance": self._resume_import_provenance(),
            "final_status": "blocked",
            "status_updated_at": now,
            "final_status_evidence_refs": [],
        }

    def _resume_import_provenance(self) -> dict:
        refs: list[str] = []
        source_runs: list[str] = []
        for artifact in self.task_contract.get("supplied_evidence") or []:
            if not isinstance(artifact, dict):
                continue
            artifact_id = artifact.get("artifact_id")
            if artifact_id:
                refs.append(str(artifact_id))
            provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
            source = provenance.get("source")
            if source:
                source_runs.append(str(source))
        for seed in self.task_contract.get("seed_inputs") or []:
            if isinstance(seed, dict) and seed.get("seed_kind") == "external_evidence":
                artifact = seed.get("artifact_ref") if isinstance(seed.get("artifact_ref"), dict) else {}
                artifact_id = artifact.get("artifact_id")
                if artifact_id:
                    refs.append(str(artifact_id))
                provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
                source = provenance.get("source")
                if source:
                    source_runs.append(str(source))
        return {
            "run_mode": self.task_contract["run_mode"],
            "imported_evidence_refs": _dedupe(refs),
            "source_run_ids": _dedupe(source_runs),
        }

    def _node_request(self, node: dict, state: dict) -> dict:
        allow_live_provider = bool(node.get("allow_live_provider") and self.task_contract.get("constraints", {}).get("allow_live_provider"))
        authorization = {
            "scope_id": f"{state['run_id']}:{node['node_id']}",
            "approved_capabilities": list(node.get("required_capabilities") or []),
            "allow_network": bool(node.get("allow_network", False)),
            "allow_live_provider": allow_live_provider,
            "secret_refs": [],
        }
        if allow_live_provider:
            authorization["approval_ref"] = str(self.task_contract.get("approval_ref") or "approved-by-task-contract")
            authorization["allow_network"] = True
        return {
            "schema": "research_node_request.v1",
            "task_id": state["task_id"],
            "run_id": state["run_id"],
            "workflow_id": state["workflow_id"],
            "node_id": node["node_id"],
            "logical_operator": {
                "operator_id": str(node.get("logical_operator") or node["node_id"]),
                "operator_kind": "logical",
                "capabilities": list(node.get("required_capabilities") or []),
            },
            "physical_operator": {
                "operator_id": str(node.get("physical_operator") or f"{node['node_id']}_worker"),
                "operator_kind": "physical",
                "capabilities": ["bounded_worker"],
            },
            "typed_inputs": {
                "input_schema": "research_node_input.v1",
                "payload": {
                    "task_contract": deepcopy(self.task_contract),
                    "node": deepcopy(node),
                },
            },
            "input_artifact_refs": [
                {"artifact_id": f"{node['node_id']}:input:{index}", "path": path}
                for index, path in enumerate(node.get("read_scope") or [])
            ],
            "authorization": authorization,
            "read_scope": list(node.get("read_scope") or []),
            "write_scope": list(node.get("write_scope") or []),
            "timeout_retry_policy": {
                "timeout_seconds": int(node.get("timeout_seconds") or 60),
                "max_attempts": int(node.get("max_attempts") or 1),
                "retry_on": [],
            },
        }

    def _dispatch(self, request: dict) -> dict:
        try:
            result = self.dispatch_callable(deepcopy(request))
        except Exception as exc:
            return {
                "schema": "research_node_result.v1",
                "task_id": request["task_id"],
                "run_id": request["run_id"],
                "workflow_id": request["workflow_id"],
                "node_id": request["node_id"],
                "status": "failed",
                "status_is_terminal": True,
                "output_artifacts": [],
                "evidence": [],
                "hashes": [],
                "model_provider_usage": [{"provider": "none", "model": "none", "usage_kind": "none"}],
                "errors": [{"error_id": "dispatch_exception", "error_type": type(exc).__name__, "message": str(exc)[:500]}],
                "limitations": ["Dispatch callable raised before returning node evidence."],
                "secret_redaction_assertion": {"no_secrets_observed": True, "redaction_review": "passed"},
            }
        if not isinstance(result, dict):
            raise ResearchOrchestrationError("dispatch_callable must return a result object")
        return result

    def _evaluate(self, request: dict, result: dict, state: dict) -> dict:
        decision = self.evaluator_callable(deepcopy(request), deepcopy(result), deepcopy(state))
        if not isinstance(decision, dict):
            raise ResearchOrchestrationError("evaluator_callable must return an object")
        accepted = bool(decision.get("accepted", False))
        status = str(decision.get("status") or "").strip()
        if status not in NODE_STATUSES - {"pending", "ready", "running"}:
            raise ResearchOrchestrationError(f"evaluator returned invalid status: {status}")
        if not accepted and status == "completed":
            status = "failed"
        return {
            "accepted": accepted,
            "status": status,
            "evidence_refs": [str(item) for item in decision.get("evidence_refs") or [] if str(item)],
            "errors": list(decision.get("errors") or []),
            "limitations": [str(item) for item in decision.get("limitations") or []],
        }

    def _commit_evaluation(self, state: dict, node_id: str, result: dict, decision: dict) -> dict:
        status = decision["status"]
        if status == "cancelled" and state["node_states"][node_id]["required_for_completion"]:
            status = "failed"
        self._transition_node(state, node_id, status)
        result_ref = self._result_ref(result, node_id, state["run_id"])
        if status == "completed":
            state["node_states"][node_id]["result_ref"] = result_ref
        elif status in {"failed", "blocked", "cancelled"} and result_ref:
            state["node_states"][node_id]["result_ref"] = result_ref
        if decision["errors"]:
            state["current_blockers"] = [
                {
                    "blocker_id": f"{node_id}_evaluation_error",
                    "node_id": node_id,
                    "reason": str(decision["errors"][0].get("message") if isinstance(decision["errors"][0], dict) else decision["errors"][0]),
                }
            ]
        return state

    def _refresh_ready_and_status(self, state: dict, workflow: dict) -> dict:
        state["ready_nodes"] = self._calculate_ready_nodes_from_states(state["node_states"])
        required = [
            node_state for node_state in state["node_states"].values()
            if node_state["required_for_completion"]
        ]
        optional = [
            node_state for node_state in state["node_states"].values()
            if not node_state["required_for_completion"]
        ]
        if any(item["status"] == "failed" for item in required):
            state["final_status"] = "failed"
        elif any(item["status"] == "blocked" for item in required):
            state["final_status"] = "blocked"
        elif any(item["status"] == "awaiting_human" for item in state["node_states"].values()):
            state["final_status"] = "awaiting_human"
        elif any(item["status"] == "awaiting_external" for item in state["node_states"].values()):
            state["final_status"] = "awaiting_external"
        elif all(item["status"] == "completed" for item in required) and all(
            item["status"] in {"completed", "cancelled"} for item in optional
        ):
            state["final_status"] = "completed"
            state["current_blockers"] = []
            evidence_refs = []
            for item in state["node_states"].values():
                if item["result_ref"]:
                    evidence_refs.append(item["result_ref"])
            state["final_status_evidence_refs"] = _dedupe(evidence_refs)
        else:
            state["final_status"] = "running" if any(
                item["status"] in {"running", "completed"} for item in state["node_states"].values()
            ) else "pending"
        state["status_updated_at"] = self.clock()
        return state

    def _calculate_ready_nodes_from_states(self, node_states: dict) -> list[str]:
        ready = []
        for node_id, node_state in sorted(node_states.items()):
            if node_state["status"] not in {"pending", "ready"}:
                continue
            if all(node_states[dep]["status"] == "completed" for dep in node_state["depends_on"]):
                if node_state["status"] == "pending":
                    node_state["previous_status"] = "pending"
                    node_state["status"] = "ready"
                    node_state["updated_at"] = self.clock()
                ready.append(node_id)
        return ready

    def _transition_node(self, state: dict, node_id: str, status: str) -> None:
        node_state = state["node_states"][node_id]
        if node_state["status"] == "completed" and status != "completed":
            return
        node_state["previous_status"] = node_state["status"]
        node_state["status"] = status
        node_state["updated_at"] = self.clock()

    def _node_by_id(self, workflow: dict, node_id: str) -> dict:
        for node in workflow.get("nodes") or []:
            if node.get("node_id") == node_id:
                return node
        raise ResearchOrchestrationError(f"unknown workflow node: {node_id}")

    def _result_ref(self, result: dict, node_id: str, run_id: str) -> str:
        artifacts = result.get("output_artifacts") if isinstance(result.get("output_artifacts"), list) else []
        for artifact in artifacts:
            if isinstance(artifact, dict) and artifact.get("path"):
                return str(artifact["path"])
        return f"artifacts/research/{run_id}/{node_id}/result.json"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _default_clock() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
