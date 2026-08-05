"""Production composition root for Solar-owned research orchestration."""

from __future__ import annotations

import hashlib
import re
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .dispatch import dispatch_research_node
from .evaluator import evaluate_production_result
from .orchestrator import ResearchOrchestrator
from .resolver import PhysicalOperatorBinding, PhysicalOperatorResolver
from .routing import (
    ResearchRouteDecision,
    normalize_seed_inputs,
    select_production_route,
    workflow_from_entry_stage,
)
from .selection import load_and_normalize_workflow, load_workflow_selection, select_research_workflow
from .state_store import ResearchStateStore


class ResearchRuntimeError(ValueError):
    """Raised when the production research runtime cannot proceed safely."""


_HARNESS_ROOT = Path(__file__).resolve().parents[2]
_REQUEST_SCHEMA = _HARNESS_ROOT / "schemas" / "draft" / "research_node_request.v1.schema.json"
_RESULT_SCHEMA = _HARNESS_ROOT / "schemas" / "evidence" / "research_node_result.v1.schema.json"
_DEFAULT_SELECTION = _HARNESS_ROOT / "config" / "research-workflow-selection.v1.json"
_PROMPT_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)


class FileWorkflowCatalog:
    """Load configured workflows and resolve semantic entry stages explicitly."""

    def __init__(
        self,
        *,
        harness_root: Path = _HARNESS_ROOT,
        selection_path: Path = _DEFAULT_SELECTION,
        entrypoint_aliases: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.harness_root = Path(harness_root).resolve()
        self.selection = load_workflow_selection(Path(selection_path))
        self.entrypoint_aliases = deepcopy(entrypoint_aliases or {})

    def load(self, decision: ResearchRouteDecision) -> dict:
        selected = select_research_workflow(decision.to_dict(), self.selection, self.harness_root)
        configured = load_and_normalize_workflow(
            selected,
            self.harness_root,
            preserve_all_nodes=True,
        )
        aliases = self.entrypoint_aliases.get(decision.workflow_kind, {})
        return workflow_from_entry_stage(configured, decision, entrypoint_aliases=aliases)


class SolarResearchRuntime:
    """Compose routing, physical dispatch, evaluation, and durable Solar state."""

    def __init__(
        self,
        *,
        artifact_root: Path,
        workflow_loader: Callable[[ResearchRouteDecision], dict],
        operator_resolver: PhysicalOperatorResolver,
        authorization: dict | None = None,
    ) -> None:
        self.artifact_root = Path(artifact_root).expanduser().resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.workflow_loader = workflow_loader
        self.operator_resolver = operator_resolver
        self.authorization = deepcopy(authorization or {})
        self.state_store = ResearchStateStore(self.artifact_root / "state")

    def run(
        self,
        *,
        prompt: str,
        run_id: str,
        seed_inputs: list[dict] | None = None,
        run_mode: str = "execute",
        explicit_workflow: str | None = None,
        supplied_evidence: list[dict] | None = None,
        imported_result: dict | None = None,
        output_language: str = "",
        max_steps: int = 100,
    ) -> dict[str, Any]:
        normalized_seeds = _complete_seed_inputs(
            prompt,
            seed_inputs,
            artifact_root=self.artifact_root,
            run_id=run_id,
        )
        evidence = deepcopy(supplied_evidence or [])
        if run_mode == "resume" and not evidence:
            evidence = [self._state_provenance_ref(run_id)]
        if run_mode == "import_evidence":
            if not evidence:
                raise ResearchRuntimeError("import_evidence requires at least one evidence artifact")
            first = deepcopy(evidence[0])
            normalized_seeds = [
                {
                    "seed_id": "imported-evidence-1",
                    "seed_kind": "external_evidence",
                    "value": str(first.get("path") or "imported evidence"),
                    "artifact_ref": first,
                },
                *normalized_seeds,
            ]
        decision = select_production_route(
            prompt,
            seed_inputs=normalized_seeds,
            explicit_workflow=explicit_workflow,
            run_mode=run_mode,
        )
        try:
            workflow = self.workflow_loader(decision)
        except Exception as exc:
            raise ResearchRuntimeError(f"workflow route resolution failed: {exc}") from exc
        task_contract = build_task_contract(
            prompt=prompt,
            run_id=run_id,
            decision=decision,
            seed_inputs=normalized_seeds,
            supplied_evidence=evidence,
            output_language=output_language,
        )
        runtime_authorization = deepcopy(self.authorization)
        approved = set(runtime_authorization.get("approved_capabilities") or [])
        approved.update(
            capability
            for node in workflow.get("nodes") or []
            for capability in node.get("required_capabilities") or []
            if capability != "execute_experiment"
            and not node.get("allow_network")
            and not node.get("allow_live_provider")
        )
        runtime_authorization["approved_capabilities"] = sorted(approved)

        def dispatch(request: dict) -> dict:
            return dispatch_research_node(
                request,
                runner=self.operator_resolver.execute,
                request_schema_path=_REQUEST_SCHEMA,
                result_schema_path=_RESULT_SCHEMA,
                artifact_root=self.artifact_root,
                operator_resolver=self.operator_resolver.resolve,
                secret_values=_secret_values(runtime_authorization),
            )

        def evaluator(request: dict, result: dict, state: dict) -> dict:
            return evaluate_production_result(
                request,
                result,
                state,
                artifact_root=self.artifact_root,
            )

        orchestrator = ResearchOrchestrator(
            task_contract=task_contract,
            workflow_selector=workflow,
            state_store=self.state_store,
            dispatch_callable=dispatch,
            evaluator_callable=evaluator,
            authorization=runtime_authorization,
            artifact_root=self.artifact_root,
        )
        if run_mode == "execute":
            state = orchestrator.run_until_blocked(max_steps=max_steps)
        elif run_mode == "resume":
            state = orchestrator.resume(node_result=imported_result) if imported_result else orchestrator.resume()
            if state.get("final_status") not in {
                "completed", "failed", "blocked", "cancelled", "awaiting_human", "awaiting_external"
            }:
                state = orchestrator.run_until_blocked(max_steps=max_steps)
        elif run_mode == "import_evidence":
            state = orchestrator.run_until_blocked(max_steps=max_steps)
        else:  # route classification should already reject this
            raise ResearchRuntimeError(f"unsupported run_mode: {run_mode}")
        state_path = self.artifact_root / "state" / f"{run_id}.research_run_state.json"
        return {
            "schema": "solar_research_runtime_result.v1",
            "task_id": task_contract["task_id"],
            "run_id": run_id,
            "prompt": prompt,
            "route": decision.to_dict(),
            "workflow_id": workflow.get("workflow_id"),
            "start_node": workflow.get("start_node"),
            "run_mode": run_mode,
            "final_status": state.get("final_status"),
            "state_path": str(state_path),
            "final_status_evidence_refs": list(state.get("final_status_evidence_refs") or []),
            "node_states": deepcopy(state.get("node_states") or {}),
            "current_blockers": deepcopy(state.get("current_blockers") or []),
        }

    def _state_provenance_ref(self, run_id: str) -> dict:
        path = self.artifact_root / "state" / f"{run_id}.research_run_state.json"
        if not path.is_file():
            raise ResearchRuntimeError(f"cannot resume missing run: {run_id}")
        return artifact_reference(path, artifact_root=self.artifact_root, artifact_id=f"state-{run_id}")


def build_task_contract(
    *,
    prompt: str,
    run_id: str,
    decision: ResearchRouteDecision,
    seed_inputs: list[dict],
    supplied_evidence: list[dict] | None = None,
    output_language: str = "",
) -> dict:
    """Build the frozen Phase 0 task contract without truncating user intent."""

    language = str(output_language or "").strip() or "preserve_user_request"
    return {
        "schema": "research_task_contract.v1",
        "task_id": f"{run_id}.research",
        "run_id": run_id,
        "user_intent": prompt,
        "seed_inputs": deepcopy(seed_inputs),
        "deliverable": {
            "kind": "evidence_backed_research_report",
            "description": "A non-empty, structurally usable report relevant to the complete user request.",
            "language": language,
            "artifact_expectations": ["report", "evidence_lineage", "evaluation"],
        },
        "workflow_kind": decision.workflow_kind,
        "run_mode": decision.run_mode,
        "constraints": {
            "no_live_provider_without_approval": True,
            "no_secret_logging": True,
        },
        "provider_requirements": [],
        "platform_requirements": [],
        "success_criteria": [
            "The complete user prompt is preserved in the run contract.",
            "Every accepted output artifact is non-empty, hash-verified, and linked to evidence.",
            "The final status is derived from evaluated node evidence.",
        ],
        "supplied_evidence": deepcopy(supplied_evidence or []),
    }


def artifact_reference(path: Path, *, artifact_root: Path, artifact_id: str | None = None) -> dict:
    resolved = Path(path).expanduser().resolve()
    root = Path(artifact_root).expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ResearchRuntimeError(f"imported evidence escapes artifact root: {resolved}") from exc
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ResearchRuntimeError(f"imported evidence is missing or empty: {resolved}")
    captured_at = datetime.fromtimestamp(resolved.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z")
    return {
        "artifact_id": artifact_id or f"import-{hashlib.sha256(str(resolved).encode('utf-8')).hexdigest()[:16]}",
        "path": str(resolved),
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "provenance": {"source": "user_supplied_evidence", "captured_at": captured_at},
    }


def default_synthesis_resolver(*, services: dict | None = None) -> PhysicalOperatorResolver:
    """Expose the seven Phase 2 operators through explicit production bindings."""

    try:
        from harness.plugins.autosci.operators.research_synthesis.registry import execute_operator
    except ModuleNotFoundError:  # direct execution with harness/ as sys.path root
        from plugins.autosci.operators.research_synthesis.registry import execute_operator

    injected = deepcopy(services or {})

    def run(request: dict) -> dict:
        return execute_operator(request, services=injected)

    operator_ids = (
        "seed_fetch_operator",
        "source_discovery_operator",
        "source_validation_operator",
        "evidence_synthesis_operator",
        "report_draft_operator",
        "independent_review_operator",
        "final_acceptance_operator",
    )
    return PhysicalOperatorResolver(
        [PhysicalOperatorBinding(operator_id=operator_id, runner=run, version="research_synthesis.v1") for operator_id in operator_ids]
    )


def default_production_resolver(
    *,
    services: dict | None = None,
    workspace_root: Path | None = None,
) -> PhysicalOperatorResolver:
    """Compose all Phase 2/3 bounded operators into one fail-closed registry."""

    try:
        from harness.plugins.autosci.operators.scientific_lifecycle.registry import production_bindings
    except ModuleNotFoundError:  # direct execution with harness/ as sys.path root
        from plugins.autosci.operators.scientific_lifecycle.registry import production_bindings

    return PhysicalOperatorResolver(
        production_bindings(
            services=deepcopy(services or {}),
            workspace_root=Path(workspace_root or Path.cwd()).resolve(),
            binding_factory=PhysicalOperatorBinding,
        )
    )


def load_evidence_references(paths: list[str] | tuple[str, ...], *, artifact_root: Path) -> list[dict]:
    root = Path(artifact_root).expanduser().resolve()
    return [
        artifact_reference(
            Path(path) if Path(path).is_absolute() else root / Path(path),
            artifact_root=root,
        )
        for path in paths
    ]


def _complete_seed_inputs(
    prompt: str,
    seed_inputs: list[dict] | None,
    *,
    artifact_root: Path,
    run_id: str,
) -> list[dict]:
    normalized = normalize_seed_inputs(seed_inputs)
    if not normalized:
        url = _PROMPT_URL_RE.search(prompt)
        normalized = [{"seed_kind": "url", "value": url.group(0)}] if url else [
            {"seed_kind": "topic", "value": prompt}
        ]
    completed: list[dict] = []
    for index, item in enumerate(normalized, start=1):
        value = str(item.get("value") or "").strip()
        if not value:
            raise ResearchRuntimeError("seed input value must be non-empty")
        record = deepcopy(item)
        record["seed_id"] = str(record.get("seed_id") or f"seed-{index}")
        if record.get("seed_kind") in {"pdf", "markdown"}:
            source = Path(value).expanduser().resolve()
            if not source.is_file() or source.stat().st_size <= 0:
                raise ResearchRuntimeError(f"local research source is missing or empty: {source}")
            snapshot_dir = artifact_root / "inputs" / _safe_component(run_id)
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            snapshot = snapshot_dir / f"{index:02d}-{_safe_component(source.name)}"
            shutil.copyfile(source, snapshot)
            record["value"] = str(snapshot)
            captured_at = datetime.fromtimestamp(source.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z")
            provenance = {
                "source": "explicit_local_research_input",
                "captured_at": captured_at,
                "original_path": str(source),
            }
            record["provenance"] = provenance
            record["artifact_ref"] = {
                "artifact_id": f"input-{_safe_component(run_id)}-{index}",
                "path": str(snapshot),
                "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                "provenance": provenance,
            }
        else:
            record["value"] = value
        completed.append(record)
    return completed


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip(".-")
    return cleaned[:120] or "research-input"


def _secret_values(authorization: dict) -> tuple[str, ...]:
    values = authorization.get("secret_values") if isinstance(authorization, dict) else None
    if isinstance(values, dict):
        return tuple(str(item) for item in values.values() if str(item))
    if isinstance(values, list):
        return tuple(str(item) for item in values if str(item))
    return ()
