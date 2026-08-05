"""Solar-owned research orchestration runtime core."""

from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable

import jsonschema


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
TERMINAL_NODE_STATUSES = {"completed", "failed", "blocked", "cancelled"}
TERMINAL_RUN_STATUSES = {"completed", "failed", "blocked", "cancelled"}
STOPPING_RUN_STATUSES = TERMINAL_RUN_STATUSES | {"awaiting_human", "awaiting_external"}
_SHA256_RE = re.compile(r"^[A-Fa-f0-9]{64}$")
_SENSITIVE_KEY_RE = re.compile(r"(?:api[_-]?key|access[_-]?token|password|credential|client[_-]?secret)", re.I)
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|password|client[_-]?secret)\s*[:=]\s*['\"]?[^\s,'\"}]+"),
)
_SAFE_SECRET_METADATA_KEYS = {"secret_refs", "secret_redaction_assertion", "no_secrets_observed"}
_HARNESS_ROOT = Path(__file__).resolve().parents[2]
_TASK_SCHEMA_PATH = _HARNESS_ROOT / "schemas" / "draft" / "research_task_contract.v1.schema.json"
_RESULT_SCHEMA_PATH = _HARNESS_ROOT / "schemas" / "evidence" / "research_node_result.v1.schema.json"


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
        authorization: dict | None = None,
        artifact_root: Path | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.task_contract = deepcopy(task_contract)
        self.workflow_selector = workflow_selector
        self.state_store = state_store
        self.dispatch_callable = dispatch_callable
        self.evaluator_callable = evaluator_callable
        normalized_authorization = self._normalize_authorization(authorization or {})
        self._secret_values = tuple(normalized_authorization.pop("secret_values"))
        self.authorization = normalized_authorization
        if isinstance(artifact_root, str) and not artifact_root.strip():
            raise ResearchOrchestrationError("artifact_root must be a non-empty stable path")
        trusted_root = artifact_root
        if trusted_root is None and isinstance(getattr(state_store, "state_root", None), Path):
            trusted_root = state_store.state_root.parent
        if trusted_root is None:
            raise ResearchOrchestrationError("artifact_root must be explicit or derived from a trusted state store root")
        self.artifact_root = Path(trusted_root).expanduser().resolve()
        self.clock = clock or _default_clock
        self._workflow: dict | None = None
        self._state_revision: str | None = None

    def initialize(self) -> dict:
        """Create and persist the initial Solar-owned run state."""

        self._validate_task_contract()
        workflow = self._load_workflow()
        validation_error = self._validate_workflow(workflow)
        state = self._failed_initial_state(workflow, validation_error) if validation_error else self._initial_state(workflow)
        if hasattr(self.state_store, "create_with_revision"):
            _path, self._state_revision = self.state_store.create_with_revision(state)
        else:  # compatibility for injected stores outside this package
            self.state_store.create(state)
        return deepcopy(state)

    def step(self) -> dict:
        """Dispatch at most one ready node, evaluate it, and commit accepted evidence."""

        state = self._load_or_initialize()
        if state["final_status"] in STOPPING_RUN_STATUSES:
            return deepcopy(state)
        workflow = self._load_workflow()
        before_refresh = deepcopy(state)
        state = self._refresh_ready_and_status(state, workflow)
        if state != before_refresh:
            self._save_state(state)
        if state["final_status"] in STOPPING_RUN_STATUSES:
            return deepcopy(state)

        ready_nodes = list(state.get("ready_nodes") or [])
        if not ready_nodes:
            state["final_status"] = "running"
            state["status_updated_at"] = self.clock()
            self._save_state(state)
            return deepcopy(state)

        node_id = ready_nodes[0]
        node = self._node_by_id(workflow, node_id)
        authorization_error = self._authorization_gate_reason(node)
        if authorization_error:
            self._transition_node(state, node_id, "running")
            self._transition_node(state, node_id, "awaiting_external")
            state["current_blockers"] = [
                {
                    "blocker_id": f"{node_id}_authorization_required",
                    "node_id": node_id,
                    "reason": authorization_error,
                }
            ]
            state = self._refresh_ready_and_status(state, workflow)
            self._save_state(state)
            return deepcopy(state)

        try:
            request = self._node_request(node, state, workflow)
        except Exception as exc:
            self._transition_node(state, node_id, "running")
            self._transition_node(state, node_id, "blocked")
            state["current_blockers"] = [
                {
                    "blocker_id": f"{node_id}_request_evidence_invalid",
                    "node_id": node_id,
                    "reason": _scrub_text(str(exc), self._secret_values)[:500] or "node request evidence is invalid",
                }
            ]
            state = self._refresh_ready_and_status(state, workflow)
            self._save_state(state)
            return deepcopy(state)
        self._transition_node(state, node_id, "running")
        state["final_status"] = "running"
        state["ready_nodes"] = self._calculate_ready_nodes_from_states(state["node_states"])
        state["status_updated_at"] = self.clock()
        self._save_state(state)

        result = self._dispatch(request)
        decision = self._evaluate(request, result, state)
        state = self._commit_evaluation(state, node_id, result, decision)
        state = self._refresh_ready_and_status(state, workflow)
        self._save_state(state)
        return deepcopy(state)

    def run_until_blocked(self, max_steps: int = 100) -> dict:
        """Run until terminal, awaiting explicit input, or max_steps is reached."""

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
            self._save_state(state)
        return deepcopy(state)

    def resume(
        self,
        *,
        node_result: dict | None = None,
        redispatch_node_id: str | None = None,
        authorization: dict | None = None,
    ) -> dict:
        """Resume only with validated evidence or an explicit redispatch request.

        Calling ``resume()`` without either input is read-only with respect to
        an awaiting/running node.  This prevents a restart from relabelling an
        unfulfilled provider or human gate as ready.
        """

        self._validate_task_contract()
        if authorization is not None:
            normalized_authorization = self._normalize_authorization(authorization)
            self._secret_values = tuple(normalized_authorization.pop("secret_values"))
            self.authorization = normalized_authorization
        state = self._load_state()
        if state is None:
            if node_result is not None or redispatch_node_id is not None:
                raise ResearchOrchestrationError("cannot resume a run that has not been initialized")
            return self.initialize()
        workflow = self._load_workflow()

        if node_result is not None:
            if redispatch_node_id is not None:
                raise ResearchOrchestrationError("supply node_result or redispatch_node_id, not both")
            return self._resume_with_result(state, workflow, node_result)

        if redispatch_node_id is not None:
            node = self._node_by_id(workflow, redispatch_node_id)
            node_state = state["node_states"].get(redispatch_node_id)
            if not isinstance(node_state, dict) or node_state.get("status") not in {
                "awaiting_human",
                "awaiting_external",
                "running",
                "failed",
                "blocked",
            }:
                raise ResearchOrchestrationError("redispatch target is not resumable")
            authorization_error = self._authorization_gate_reason(node)
            if authorization_error:
                raise ResearchOrchestrationError(authorization_error)
            if node_state["status"] == "running":
                self._transition_node(state, redispatch_node_id, "failed")
            self._transition_node(state, redispatch_node_id, "ready")
            state["current_blockers"] = [
                blocker for blocker in state.get("current_blockers") or []
                if blocker.get("node_id") != redispatch_node_id
            ]
            state = self._refresh_ready_and_status(state, workflow)
            self._save_state(state)
            return self.step()

        # A plain restart must not silently clear awaiting or crash state.
        refreshed = self._refresh_ready_and_status(deepcopy(state), workflow)
        if refreshed != state:
            self._save_state(refreshed)
        return deepcopy(refreshed)

    def _resume_with_result(self, state: dict, workflow: dict, raw_result: dict) -> dict:
        node_id = str(raw_result.get("node_id") or "") if isinstance(raw_result, dict) else ""
        node_state = state["node_states"].get(node_id)
        if not isinstance(node_state, dict) or node_state.get("status") not in {
            "awaiting_human",
            "awaiting_external",
            "running",
        }:
            raise ResearchOrchestrationError("imported result does not target an awaiting/running node")
        node = self._node_by_id(workflow, node_id)
        request = self._node_request(node, state, workflow)
        result = self._sanitize_result(deepcopy(raw_result))
        self._validate_result_boundary(request, result)
        self._verify_completed_artifacts(request, result)
        if result["status"] not in TERMINAL_NODE_STATUSES:
            raise ResearchOrchestrationError("imported result must be terminal evidence")
        decision = self._evaluate(request, result, state)
        if node_state["status"] != "running":
            self._transition_node(state, node_id, "running")
        state = self._commit_evaluation(state, node_id, result, decision)
        state = self._refresh_ready_and_status(state, workflow)
        self._save_state(state)
        return deepcopy(state)

    def _load_or_initialize(self) -> dict:
        self._validate_task_contract()
        state = self._load_state()
        return self.initialize() if state is None else deepcopy(state)

    def _load_state(self) -> dict | None:
        run_id = self.task_contract["run_id"]
        if hasattr(self.state_store, "load_with_revision"):
            state, self._state_revision = self.state_store.load_with_revision(run_id)
            return state
        return self.state_store.load(run_id)

    def _save_state(self, state: dict) -> None:
        if hasattr(self.state_store, "save_with_revision"):
            _path, self._state_revision = self.state_store.save_with_revision(
                state,
                expected_revision=self._state_revision,
            )
        else:
            self.state_store.save(state)

    def _validate_task_contract(self) -> None:
        required = {"task_id", "run_id", "workflow_kind", "run_mode", "seed_inputs"}
        missing = sorted(key for key in required if key not in self.task_contract)
        if missing:
            raise ResearchOrchestrationError(f"task contract missing fields: {', '.join(missing)}")
        if _contains_secret_material(self.task_contract, self._secret_values):
            raise ResearchOrchestrationError("task contract must contain secret references, not secret values")
        self._validate_json_schema(self.task_contract, _TASK_SCHEMA_PATH, "task contract")
        run_mode = self.task_contract["run_mode"]
        if run_mode == "execute":
            if self.task_contract.get("supplied_evidence"):
                raise ResearchOrchestrationError("execute mode cannot consume supplied evidence")
            for seed in self.task_contract.get("seed_inputs") or []:
                if isinstance(seed, dict) and seed.get("seed_kind") == "external_evidence":
                    raise ResearchOrchestrationError("execute mode cannot consume imported evidence seeds")
        elif run_mode in {"resume", "import_evidence"}:
            supplied = self.task_contract.get("supplied_evidence") or []
            external = [
                seed for seed in self.task_contract.get("seed_inputs") or []
                if isinstance(seed, dict) and seed.get("seed_kind") == "external_evidence"
            ]
            if not supplied and not external:
                raise ResearchOrchestrationError(f"{run_mode} requires imported evidence provenance")
        else:
            raise ResearchOrchestrationError(f"unsupported run_mode: {run_mode}")

    def _load_workflow(self) -> dict:
        if self._workflow is not None:
            return deepcopy(self._workflow)
        workflow = self.workflow_selector(deepcopy(self.task_contract)) if callable(self.workflow_selector) else deepcopy(self.workflow_selector)
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
        seen: list[str] = []
        while queue:
            node_id = queue.pop(0)
            seen.append(node_id)
            for child in sorted(outgoing[node_id]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
                    queue.sort()
        if len(seen) != len(nodes):
            return "cycle detected: " + ", ".join(sorted(node_id for node_id, degree in indegree.items() if degree > 0))
        return ""

    def _initial_state(self, workflow: dict) -> dict:
        now = self.clock()
        node_states = {
            node["node_id"]: {
                "node_id": node["node_id"],
                "required_for_completion": bool(node.get("required_for_completion", True)),
                "previous_status": None,
                "status": "ready" if not node.get("depends_on") else "pending",
                "depends_on": list(node.get("depends_on") or []),
                "result_ref": None,
                "updated_at": now,
            }
            for node in workflow["nodes"]
        }
        return {
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
        artifacts = list(self.task_contract.get("supplied_evidence") or [])
        artifacts.extend(
            seed.get("artifact_ref") for seed in self.task_contract.get("seed_inputs") or []
            if isinstance(seed, dict) and seed.get("seed_kind") == "external_evidence" and isinstance(seed.get("artifact_ref"), dict)
        )
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            if artifact.get("artifact_id"):
                refs.append(str(artifact["artifact_id"]))
            provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
            if provenance.get("source"):
                source_runs.append(str(provenance["source"]))
        return {
            "run_mode": self.task_contract["run_mode"],
            "imported_evidence_refs": _dedupe(refs),
            "source_run_ids": _dedupe(source_runs),
        }

    def _node_request(self, node: dict, state: dict, workflow: dict) -> dict:
        live = bool(node.get("allow_live_provider"))
        required_capabilities = list(node.get("required_capabilities") or [])
        approved_capabilities = set(self.authorization.get("approved_capabilities") or [])
        authorization_error = self._authorization_gate_reason(node)
        if authorization_error:
            raise ResearchOrchestrationError(authorization_error)
        auth = {
            "scope_id": str(self.authorization.get("scope_id") or f"{state['run_id']}:{node['node_id']}"),
            "approved_capabilities": [item for item in required_capabilities if item in approved_capabilities],
            "allow_network": bool((node.get("allow_network", False) or live) and self.authorization.get("allow_network") is True),
            "allow_live_provider": bool(live and self.authorization.get("allow_live_provider") is True),
            "secret_refs": list(self.authorization.get("secret_refs") or []),
        }
        if (live or node.get("approval_gate")) and self._explicit_approval_ref():
            auth["approval_ref"] = self._explicit_approval_ref()
        typed_payload = {
            "task_contract": deepcopy(self.task_contract),
            "node": deepcopy(node),
            "topic": str(self.task_contract.get("user_intent") or ""),
            "title": str(self.task_contract.get("user_intent") or ""),
        }
        seeds = self.task_contract.get("seed_inputs") or []
        primary_seed = seeds[0] if seeds and isinstance(seeds[0], dict) else {}
        seed_value = str(primary_seed.get("value") or "")
        seed_kind = str(primary_seed.get("seed_kind") or "")
        if seed_value and node["node_id"] == workflow.get("start_node"):
            typed_payload["source"] = seed_value
            if seed_kind == "url":
                typed_payload["url"] = seed_value
                typed_payload["allow_network_fetch"] = auth["allow_network"]
            elif seed_kind == "pdf":
                typed_payload["paper_path"] = seed_value
            elif seed_kind == "markdown":
                typed_payload["material_path"] = seed_value
        return {
            "schema": "research_node_request.v1",
            "task_id": state["task_id"],
            "run_id": state["run_id"],
            "workflow_id": state["workflow_id"],
            "node_id": node["node_id"],
            "logical_operator": {
                "operator_id": str(node.get("logical_operator") or node["node_id"]),
                "operator_kind": "logical",
                "capabilities": required_capabilities,
            },
            "physical_operator": {
                "operator_id": str(node.get("physical_operator") or f"{node['node_id']}_worker"),
                "operator_kind": "physical",
                "capabilities": ["bounded_worker"],
            },
            "typed_inputs": {
                "input_schema": "research_node_input.v1",
                "payload": typed_payload,
            },
            "input_artifact_refs": self._upstream_artifacts(node, state, workflow),
            "authorization": auth,
            "read_scope": list(node.get("read_scope") or []),
            "write_scope": list(node.get("write_scope") or []),
            "timeout_retry_policy": {
                "timeout_seconds": int(node.get("timeout_seconds") or 60),
                "max_attempts": int(node.get("max_attempts") or 1),
                "retry_on": [],
            },
        }

    def _upstream_artifacts(self, node: dict, state: dict, workflow: dict) -> list[dict]:
        reachable = self._reachable_dependencies(node["node_id"], workflow)
        order = [item["node_id"] for item in workflow["nodes"] if item["node_id"] in reachable]
        read_scope = list(node.get("read_scope") or [])
        artifacts: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for upstream_id in order:
            upstream_state = state["node_states"].get(upstream_id) or {}
            if upstream_state.get("status") != "completed" or not upstream_state.get("result_ref"):
                continue
            try:
                record = self.state_store.load_node_record(
                    upstream_state["result_ref"],
                    expected_run_id=state["run_id"],
                    expected_node_id=upstream_id,
                )
                upstream_node = self._node_by_id(workflow, upstream_id)
                validation_request = self._artifact_validation_request(upstream_node, state)
                upstream_result = record.get("result") or {}
                if self._sanitize_result(deepcopy(upstream_result)) != upstream_result:
                    raise ResearchOrchestrationError("accepted node record contains unsanitized content")
                self._validate_result_boundary(validation_request, upstream_result)
                self._verify_completed_artifacts(validation_request, upstream_result)
                self._validate_record_evaluation(record.get("evaluation"), upstream_result)
            except Exception as exc:
                raise ResearchOrchestrationError(
                    f"accepted upstream node record {upstream_id} failed integrity verification: "
                    f"{_scrub_text(str(exc), self._secret_values)[:300]}"
                ) from exc
            evaluation = record.get("evaluation") or {}
            result = upstream_result
            if evaluation.get("accepted") is not True or result.get("status") != "completed":
                continue
            for artifact in result.get("output_artifacts") or []:
                if not isinstance(artifact, dict) or not artifact.get("artifact_id") or not artifact.get("path"):
                    continue
                if read_scope and not any(_path_within_scope(str(artifact["path"]), scope) for scope in read_scope):
                    continue
                key = (str(artifact["artifact_id"]), str(artifact["path"]))
                if key in seen:
                    continue
                seen.add(key)
                artifacts.append(deepcopy(artifact))
        return artifacts

    def _artifact_validation_request(self, node: dict, state: dict) -> dict:
        return {
            "schema": "research_node_request.v1",
            "task_id": state["task_id"],
            "run_id": state["run_id"],
            "workflow_id": state["workflow_id"],
            "node_id": node["node_id"],
            "typed_inputs": {"payload": {"node": deepcopy(node)}},
            "write_scope": list(node.get("write_scope") or []),
        }

    def _validate_record_evaluation(self, raw: Any, result: dict) -> None:
        if not isinstance(raw, dict):
            raise ResearchOrchestrationError("node record evaluation must be an object")
        if _sanitize_payload(deepcopy(raw), secret_values=self._secret_values) != raw:
            raise ResearchOrchestrationError("node record evaluation contains unsanitized content")
        if not isinstance(raw.get("accepted"), bool):
            raise ResearchOrchestrationError("node record evaluation accepted flag must be boolean")
        if raw.get("status") not in NODE_STATUSES - {"pending", "ready", "running"}:
            raise ResearchOrchestrationError("node record evaluation status is invalid")
        if any(not isinstance(raw.get(field), list) for field in ("evidence_refs", "errors", "limitations")):
            raise ResearchOrchestrationError("node record evaluation lists are malformed")
        if raw.get("accepted") is True and (
            raw.get("status") != "completed" or result.get("status") != "completed"
        ):
            raise ResearchOrchestrationError("node record acceptance contradicts result status")

    def _reachable_dependencies(self, node_id: str, workflow: dict) -> set[str]:
        by_id = {item["node_id"]: item for item in workflow["nodes"]}
        result: set[str] = set()
        stack = list(by_id[node_id].get("depends_on") or [])
        while stack:
            dependency = stack.pop()
            if dependency in result:
                continue
            result.add(dependency)
            stack.extend(by_id[dependency].get("depends_on") or [])
        return result

    def _dispatch(self, request: dict) -> dict:
        try:
            result = self.dispatch_callable(deepcopy(request))
            if not isinstance(result, dict):
                raise ResearchOrchestrationError("dispatch_callable returned a non-object result")
            result = self._sanitize_result(result)
            self._validate_result_boundary(request, result)
            self._verify_completed_artifacts(request, result)
            return result
        except Exception as exc:
            failure = self._failure_result(request, "dispatch_exception", type(exc).__name__, str(exc))
            self._validate_result_boundary(request, failure)
            return failure

    def _sanitize_result(self, result: dict) -> dict:
        sanitized = _sanitize_payload(deepcopy(result), secret_values=self._secret_values)
        if _contains_secret_material(sanitized, self._secret_values):
            raise ResearchOrchestrationError("result contains secret material after sanitization")
        sanitized["secret_redaction_assertion"] = {
            "no_secrets_observed": True,
            "redaction_review": "passed",
        }
        return sanitized

    def _validate_result_boundary(self, request: dict, result: dict) -> None:
        self._validate_json_schema(result, _RESULT_SCHEMA_PATH, "worker result")
        if result.get("schema") != "research_node_result.v1":
            raise ResearchOrchestrationError("worker result has invalid schema identity")
        for key in ("task_id", "run_id", "workflow_id", "node_id"):
            if result.get(key) != request.get(key):
                raise ResearchOrchestrationError(f"worker result {key} does not match request")
        status = result.get("status")
        if status not in NODE_STATUSES:
            raise ResearchOrchestrationError("worker result has invalid status")
        terminal = result.get("status_is_terminal")
        if not isinstance(terminal, bool) or terminal != (status in TERMINAL_NODE_STATUSES):
            raise ResearchOrchestrationError("worker result terminal flag contradicts status")
        list_fields = ("output_artifacts", "evidence", "hashes", "model_provider_usage", "errors", "limitations")
        if any(not isinstance(result.get(field), list) for field in list_fields):
            raise ResearchOrchestrationError("worker result list fields are malformed")
        if status == "completed" and (not result["evidence"] or result["errors"]):
            raise ResearchOrchestrationError("completed worker result requires evidence and no errors")
        if status == "failed" and not result["errors"]:
            raise ResearchOrchestrationError("failed worker result requires an error")
        for artifact in result["output_artifacts"]:
            if not isinstance(artifact, dict) or not str(artifact.get("artifact_id") or "").strip() or not str(artifact.get("path") or "").strip():
                raise ResearchOrchestrationError("worker result contains malformed artifact reference")
            if artifact.get("sha256") is not None and not _SHA256_RE.match(str(artifact["sha256"])):
                raise ResearchOrchestrationError("worker artifact sha256 is malformed")
        for evidence in result["evidence"]:
            if not isinstance(evidence, dict) or any(
                not str(evidence.get(field) or "").strip() for field in ("evidence_id", "kind", "summary")
            ):
                raise ResearchOrchestrationError("worker result contains malformed evidence")
        for error in result["errors"]:
            if not isinstance(error, dict) or any(
                not str(error.get(field) or "").strip() for field in ("error_id", "error_type", "message")
            ):
                raise ResearchOrchestrationError("worker result contains malformed error")
        assertion = result.get("secret_redaction_assertion")
        if not isinstance(assertion, dict) or assertion.get("no_secrets_observed") is not True:
            raise ResearchOrchestrationError("worker result lacks a verified secret-redaction assertion")

    def _verify_completed_artifacts(self, request: dict, result: dict) -> None:
        if result.get("status") != "completed":
            return
        write_scopes = list(request.get("write_scope") or [])
        node = request.get("typed_inputs", {}).get("payload", {}).get("node") or {}
        required_for_completion = bool(node.get("required_for_completion", True))
        expected_outputs = _dedupe([
            *[str(item) for item in node.get("expected_output_artifacts") or [] if str(item)],
            *([str(node.get("gate_deliverable"))] if str(node.get("gate_deliverable") or "") else []),
        ])
        artifacts = list(result.get("output_artifacts") or [])
        if not write_scopes:
            if artifacts or expected_outputs:
                raise ResearchOrchestrationError("completed artifacts require a declared write scope")
            return
        if required_for_completion and write_scopes and not artifacts:
            raise ResearchOrchestrationError("completed required node with declared write intent must produce an artifact")
        resolved_scopes = [self._resolve_scoped_path(scope, must_exist=False) for scope in write_scopes]
        for scope in resolved_scopes:
            if not _is_under_or_equal(scope, self.artifact_root):
                raise ResearchOrchestrationError("declared write scope escapes artifact_root")
        evidence_artifact_ids = {
            str(item.get("artifact_id")) for item in result.get("evidence") or []
            if isinstance(item, dict) and item.get("artifact_id")
        }
        for artifact in artifacts:
            artifact_path = self._resolve_scoped_path(artifact.get("path"), must_exist=True)
            if not artifact_path.is_file():
                raise ResearchOrchestrationError("completed artifact must be an existing regular file")
            if not _is_under_or_equal(artifact_path, self.artifact_root):
                raise ResearchOrchestrationError("completed artifact escapes artifact_root")
            if not any(_is_under_or_equal(artifact_path, scope) for scope in resolved_scopes):
                raise ResearchOrchestrationError("completed artifact escapes node write_scope")
            declared_hash = str(artifact.get("sha256") or "")
            if not _SHA256_RE.match(declared_hash):
                raise ResearchOrchestrationError("completed artifact must declare sha256")
            actual_hash = _sha256_file(artifact_path)
            if actual_hash.casefold() != declared_hash.casefold():
                raise ResearchOrchestrationError("completed artifact sha256 does not match file content")
            artifact_id = str(artifact.get("artifact_id") or "")
            if artifact_id not in evidence_artifact_ids:
                raise ResearchOrchestrationError("completed artifact is not linked by accepted evidence artifact_id")
            if expected_outputs and not any(
                self._artifact_matches_expected_path(artifact_path, expected) for expected in expected_outputs
            ):
                raise ResearchOrchestrationError("completed artifact does not match workflow-declared output deliverable")
            self._verify_embedded_artifact_identity(artifact_path, artifact, request)
        for expected in expected_outputs:
            if not any(
                self._artifact_matches_expected_path(
                    self._resolve_scoped_path(artifact.get("path"), must_exist=True),
                    expected,
                )
                for artifact in artifacts
            ):
                raise ResearchOrchestrationError("workflow-declared output deliverable was not produced")

    def _artifact_matches_expected_path(self, artifact_path: Path, expected: str) -> bool:
        expected_path = self._resolve_scoped_path(expected, must_exist=False)
        return artifact_path == expected_path

    def _verify_embedded_artifact_identity(self, path: Path, artifact: dict, request: dict) -> None:
        if path.suffix.casefold() != ".json":
            return
        try:
            embedded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResearchOrchestrationError("declared JSON artifact is not a valid JSON document") from exc
        if not isinstance(embedded, dict):
            raise ResearchOrchestrationError("declared JSON artifact must contain an object")
        provenance = embedded.get("provenance") if isinstance(embedded.get("provenance"), dict) else {}
        identity_fields = {
            "artifact_id": artifact.get("artifact_id"),
            "schema": artifact.get("schema"),
            "task_id": request.get("task_id"),
            "run_id": request.get("run_id"),
            "workflow_id": request.get("workflow_id"),
            "node_id": request.get("node_id"),
        }
        missing = [
            field
            for field, expected in identity_fields.items()
            if expected is None or (field not in embedded and field not in provenance)
        ]
        if missing:
            raise ResearchOrchestrationError(
                f"JSON artifact is missing required embedded identity: {', '.join(missing)}"
            )
        for field, expected in identity_fields.items():
            observed = embedded[field] if field in embedded else provenance.get(field)
            if observed != expected:
                raise ResearchOrchestrationError(f"JSON artifact embedded {field} does not match declared identity")

    def _resolve_scoped_path(self, raw: Any, *, must_exist: bool) -> Path:
        if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
            raise ResearchOrchestrationError("artifact path must be a non-empty safe string")
        text = raw.strip().replace("\\", "/")
        windows_absolute = PureWindowsPath(text).is_absolute()
        posix_absolute = PurePosixPath(text).is_absolute()
        if PureWindowsPath(text).drive and not windows_absolute:
            raise ResearchOrchestrationError("drive-relative artifact paths are not allowed")
        if os.name == "nt" and posix_absolute and not windows_absolute:
            raise ResearchOrchestrationError("foreign POSIX absolute artifact path is not valid on Windows")
        if os.name != "nt" and windows_absolute:
            raise ResearchOrchestrationError("foreign Windows absolute artifact path is not valid on POSIX")
        if windows_absolute or posix_absolute:
            candidate = Path(text)
        else:
            candidate = self.artifact_root / text
        try:
            return candidate.resolve(strict=must_exist)
        except (OSError, RuntimeError) as exc:
            raise ResearchOrchestrationError("completed artifact path does not exist or cannot be resolved") from exc

    def _validate_json_schema(self, value: dict, schema_path: Path, label: str) -> None:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(schema).validate(value)
        except (OSError, json.JSONDecodeError) as exc:
            raise ResearchOrchestrationError(f"{label} schema is unavailable") from exc
        except jsonschema.ValidationError as exc:
            location = ".".join(str(part) for part in exc.path)
            prefix = f"{location}: " if location else ""
            message = _scrub_text(exc.message, self._secret_values)
            raise ResearchOrchestrationError(f"{label} violates frozen Phase 0 schema: {prefix}{message}") from exc

    def _evaluate(self, request: dict, result: dict, state: dict) -> dict:
        try:
            raw = self.evaluator_callable(deepcopy(request), deepcopy(result), deepcopy(state))
            if not isinstance(raw, dict):
                raise ResearchOrchestrationError("evaluator_callable must return an object")
            raw = _sanitize_payload(raw, secret_values=self._secret_values)
            if any(not isinstance(raw.get(field, []), list) for field in ("evidence_refs", "errors", "limitations")):
                raise ResearchOrchestrationError("evaluator evidence/errors/limitations must be lists")
            if not isinstance(raw.get("accepted"), bool):
                raise ResearchOrchestrationError("evaluator accepted flag must be boolean")
            accepted = raw["accepted"]
            status = str(raw.get("status") or "").strip()
            if status not in NODE_STATUSES - {"pending", "ready", "running"}:
                raise ResearchOrchestrationError(f"evaluator returned invalid status: {status}")
            # An evaluator may reject a completed result, but cannot promote a
            # failed/nonterminal worker result into completed evidence.
            if result["status"] != "completed" and (accepted or status == "completed"):
                accepted = False
                status = result["status"] if result["status"] not in {"pending", "ready", "running"} else "failed"
                raw["evidence_refs"] = []
            if not accepted and status == "completed":
                status = "failed"
            if status != "completed":
                accepted = False
            evidence_refs = _dedupe([str(item) for item in raw.get("evidence_refs") or [] if isinstance(item, str) and item])
            if accepted and not evidence_refs:
                evidence_refs = _dedupe([
                    str(item.get("evidence_id")) for item in result.get("evidence") or []
                    if isinstance(item, dict) and item.get("evidence_id")
                ])
            if accepted:
                accepted_evidence = set(evidence_refs)
                for artifact in result.get("output_artifacts") or []:
                    artifact_id = str(artifact.get("artifact_id") or "")
                    linked = {
                        str(item.get("evidence_id"))
                        for item in result.get("evidence") or []
                        if isinstance(item, dict)
                        and item.get("artifact_id") == artifact_id
                        and item.get("evidence_id")
                    }
                    if not linked.intersection(accepted_evidence):
                        raise ResearchOrchestrationError(
                            "evaluator accepted result without accepting evidence linked to every artifact"
                        )
            return {
                "accepted": accepted,
                "status": status,
                "evidence_refs": evidence_refs,
                "errors": deepcopy(raw.get("errors") or []),
                "limitations": [str(item) for item in raw.get("limitations") or []],
            }
        except Exception as exc:
            return {
                "accepted": False,
                "status": "failed",
                "evidence_refs": [],
                "errors": [{"message": _scrub_text(str(exc), self._secret_values)[:500] or "evaluator failed"}],
                "limitations": ["Evaluator did not return a valid acceptance decision."],
            }

    def _commit_evaluation(self, state: dict, node_id: str, result: dict, decision: dict) -> dict:
        status = decision["status"]
        if status == "cancelled" and state["node_states"][node_id]["required_for_completion"]:
            status = "failed"
        self._transition_node(state, node_id, status)
        result_ref = self.state_store.store_node_record(
            run_id=state["run_id"],
            node_id=node_id,
            result=result,
            evaluation=decision,
        )
        state["node_states"][node_id]["result_ref"] = result_ref
        if decision["errors"]:
            first = decision["errors"][0]
            reason = first.get("message") if isinstance(first, dict) else first
            state["current_blockers"] = [
                {
                    "blocker_id": f"{node_id}_evaluation_error",
                    "node_id": node_id,
                    "reason": _scrub_text(str(reason), self._secret_values)[:500] or "evaluation failed",
                }
            ]
        elif status in {"awaiting_human", "awaiting_external"}:
            state["current_blockers"] = [
                {
                    "blocker_id": f"{node_id}_{status}",
                    "node_id": node_id,
                    "reason": f"Node is {status.replace('_', ' ')} and requires explicit resume input.",
                }
            ]
        else:
            state["current_blockers"] = [
                blocker for blocker in state.get("current_blockers") or []
                if blocker.get("node_id") != node_id
            ]
        return state

    def _refresh_ready_and_status(self, state: dict, workflow: dict) -> dict:
        state["ready_nodes"] = self._calculate_ready_nodes_from_states(state["node_states"])
        required = [item for item in state["node_states"].values() if item["required_for_completion"]]
        optional = [item for item in state["node_states"].values() if not item["required_for_completion"]]
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
            try:
                evidence_refs = self._accepted_evidence_refs(state, workflow)
            except Exception as exc:
                state["final_status"] = "blocked"
                state["final_status_evidence_refs"] = []
                state["current_blockers"] = [
                    {
                        "blocker_id": "accepted_node_record_integrity_failure",
                        "node_id": "__run__",
                        "reason": _scrub_text(str(exc), self._secret_values)[:500],
                    }
                ]
            else:
                state["final_status"] = "completed"
                state["current_blockers"] = []
                state["final_status_evidence_refs"] = evidence_refs
        else:
            state["final_status"] = "running" if any(
                item["status"] in {"running", "completed"} for item in state["node_states"].values()
            ) else "pending"
        state["status_updated_at"] = self.clock()
        return state

    def _accepted_evidence_refs(self, state: dict, workflow: dict) -> list[str]:
        refs: list[str] = []
        for node_id in sorted(state["node_states"]):
            item = state["node_states"][node_id]
            if item.get("status") != "completed" or not item.get("result_ref"):
                continue
            record = self.state_store.load_node_record(
                item["result_ref"],
                expected_run_id=state["run_id"],
                expected_node_id=node_id,
            )
            node = self._node_by_id(workflow, node_id)
            validation_request = self._artifact_validation_request(node, state)
            if self._sanitize_result(deepcopy(record.get("result") or {})) != (record.get("result") or {}):
                raise ResearchOrchestrationError("accepted node record contains unsanitized content")
            self._validate_result_boundary(validation_request, record.get("result") or {})
            self._verify_completed_artifacts(validation_request, record.get("result") or {})
            self._validate_record_evaluation(record.get("evaluation"), record.get("result") or {})
            if (record.get("evaluation") or {}).get("accepted") is not True:
                continue
            refs.extend(str(ref) for ref in (record.get("evaluation") or {}).get("evidence_refs") or [] if str(ref))
            refs.extend(
                str(artifact.get("artifact_id")) for artifact in (record.get("result") or {}).get("output_artifacts") or []
                if isinstance(artifact, dict) and artifact.get("artifact_id")
            )
        return _dedupe(refs)

    def _calculate_ready_nodes_from_states(self, node_states: dict) -> list[str]:
        ready: list[str] = []
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
            raise ResearchOrchestrationError("completed nodes are immutable")
        node_state["previous_status"] = node_state["status"]
        node_state["status"] = status
        node_state["updated_at"] = self.clock()

    def _node_by_id(self, workflow: dict, node_id: str) -> dict:
        for node in workflow.get("nodes") or []:
            if node.get("node_id") == node_id:
                return node
        raise ResearchOrchestrationError(f"unknown workflow node: {node_id}")

    def _has_live_provider_approval(self) -> bool:
        return (
            self.authorization.get("allow_live_provider") is True
            and self.authorization.get("allow_network") is True
            and bool(self._explicit_approval_ref())
        )

    def _authorization_gate_reason(self, node: dict) -> str:
        required = set(node.get("required_capabilities") or [])
        approved = set(self.authorization.get("approved_capabilities") or [])
        missing = sorted(required - approved)
        if missing:
            return "Authorization envelope does not approve required capabilities: " + ", ".join(missing)
        if node.get("allow_network") and self.authorization.get("allow_network") is not True:
            return "Workflow node requires network access but authorization allow_network is false."
        if node.get("allow_live_provider"):
            if self.authorization.get("allow_live_provider") is not True:
                return "Workflow node requires live-provider access but authorization allow_live_provider is false."
            if self.authorization.get("allow_network") is not True:
                return "Live-provider access requires authorization allow_network=true."
            if not self._explicit_approval_ref():
                return "Live-provider access requires a non-empty explicit approval_ref."
        return ""

    def _explicit_approval_ref(self) -> str:
        value = self.authorization.get("approval_ref")
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _normalize_authorization(value: dict) -> dict:
        if not isinstance(value, dict):
            raise ResearchOrchestrationError("authorization must be an object")
        result = {
            "approved_capabilities": _normalize_capabilities(value.get("approved_capabilities")),
            "allow_live_provider": value.get("allow_live_provider") is True,
            "allow_network": value.get("allow_network") is True,
            "approval_ref": str(value.get("approval_ref") or "").strip(),
            "scope_id": str(value.get("scope_id") or "").strip(),
            "secret_refs": _normalize_secret_refs(value.get("secret_refs")),
            "secret_values": _normalize_secret_values(value.get("secret_values")),
        }
        if _contains_secret_material(result["approval_ref"], result["secret_values"]):
            raise ResearchOrchestrationError("approval_ref resembles secret material")
        if _contains_secret_material(result["scope_id"], result["secret_values"]):
            raise ResearchOrchestrationError("scope_id must not contain secret material")
        if any(_contains_secret_material(item, result["secret_values"]) for item in result["approved_capabilities"]):
            raise ResearchOrchestrationError("approved_capabilities must not contain secret material")
        if any(_contains_secret_material(item, result["secret_values"]) for item in result["secret_refs"]):
            raise ResearchOrchestrationError("secret_refs must contain names, not secret values")
        return result

    def _failure_result(self, request: dict, error_id: str, error_type: str, message: str) -> dict:
        clean_message = _scrub_text(message, self._secret_values)[:500] or "dispatch failed"
        payload = {
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
            "model_provider_usage": [],
            "errors": [{"error_id": error_id, "error_type": _scrub_text(error_type, self._secret_values)[:120], "message": clean_message}],
            "limitations": ["Dispatch failed before accepted node evidence was produced."],
            "secret_redaction_assertion": {"no_secrets_observed": True, "redaction_review": "passed"},
        }
        if _contains_secret_material(payload, self._secret_values):
            payload["errors"][0]["message"] = "dispatch failed; sensitive exception text was discarded"
        return payload


def _sanitize_payload(value: Any, key: str = "", secret_values: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        clean: dict = {}
        for child_key, child_value in value.items():
            text_key = str(child_key)
            if text_key not in _SAFE_SECRET_METADATA_KEYS and _SENSITIVE_KEY_RE.search(text_key):
                clean[child_key] = "[REDACTED]"
            else:
                clean[child_key] = _sanitize_payload(child_value, text_key, secret_values)
        return clean
    if isinstance(value, list):
        return [_sanitize_payload(item, key, secret_values) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item, key, secret_values) for item in value]
    if isinstance(value, str):
        return _scrub_text(value, secret_values)
    return value


def _scrub_text(value: str, secret_values: tuple[str, ...] = ()) -> str:
    result = str(value)
    for secret in sorted(secret_values, key=len, reverse=True):
        result = result.replace(secret, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)(api"):
            result = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


def _contains_secret_material(value: Any, secret_values: tuple[str, ...] = ()) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) not in _SAFE_SECRET_METADATA_KEYS and _SENSITIVE_KEY_RE.search(str(key)) and child != "[REDACTED]":
                return True
            if _contains_secret_material(child, secret_values):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_secret_material(item, secret_values) for item in value)
    if isinstance(value, str):
        return any(secret in value for secret in secret_values) or any(pattern.search(value) for pattern in _SECRET_PATTERNS)
    return False


def _path_within_scope(path: str, scope: str) -> bool:
    candidate = str(PurePosixPath(path.replace("\\", "/"))).rstrip("/")
    allowed = str(PurePosixPath(str(scope).replace("\\", "/"))).rstrip("/")
    if candidate == allowed:
        return True
    return candidate.startswith(allowed + "/")


def _is_under_or_equal(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


def _path_parts_contained(child: str, parent: str, *, case_sensitive: bool) -> bool:
    child_parts = PurePosixPath(child.replace("\\", "/")).parts
    parent_parts = PurePosixPath(parent.replace("\\", "/")).parts
    if not case_sensitive:
        child_parts = tuple(part.casefold() for part in child_parts)
        parent_parts = tuple(part.casefold() for part in parent_parts)
    return len(child_parts) >= len(parent_parts) and child_parts[: len(parent_parts)] == parent_parts


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_secret_values(raw: Any) -> list[str]:
    if raw is None:
        values: list[Any] = []
    elif isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        raise ResearchOrchestrationError("secret_values must be a list or object of in-memory values")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ResearchOrchestrationError("secret_values must contain non-empty strings")
        if value not in normalized:
            normalized.append(value)
    return normalized


def _normalize_capabilities(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple, set)):
        raise ResearchOrchestrationError("approved_capabilities must be a list")
    capabilities: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            raise ResearchOrchestrationError("approved_capabilities must contain non-empty strings")
        if value not in capabilities:
            capabilities.append(value)
    return capabilities


def _normalize_secret_refs(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple, set)):
        raise ResearchOrchestrationError("secret_refs must be a list of reference names")
    references: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            raise ResearchOrchestrationError("secret_refs must contain non-empty strings")
        if value not in references:
            references.append(value)
    return references


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
