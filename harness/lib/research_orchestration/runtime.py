"""Production composition root for Solar-owned research orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
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
    apply_task_conditions,
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
_PROMPT_URL_RE = re.compile(
    r"https?://[^\s<>()\[\]{}\"'，。；：！？、（）【】《》「」『』\u4e00-\u9fff]+",
    re.IGNORECASE,
)
_PROMPT_PDF_RE = re.compile(r"(?<!\w)[^\s]+\.pdf\b", re.IGNORECASE)
_MARKDOWN_DELIVERABLE_RE = re.compile(r"\b(?:markdown|md)\b|\.md\b", re.IGNORECASE)
_PDF_DELIVERABLE_RE = re.compile(
    r"\b(?:deliver|produce|export|generate|output|format)\s+(?:as\s+)?(?:a\s+)?pdf\b|"
    r"\bpdf\s+(?:deliverable|report|output)\b",
    re.IGNORECASE,
)
_JSON_DELIVERABLE_RE = re.compile(r"\bjson\b", re.IGNORECASE)
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]|\b(?:chinese|zh-cn|mandarin)\b", re.IGNORECASE)
_ENGLISH_RE = re.compile(r"\b(?:english|en-us|en-gb)\b", re.IGNORECASE)
_AMBIGUOUS_RESEARCH_RE = re.compile(r"^\s*research\s+[\w\s-]{1,80}\s*$", re.IGNORECASE)
_CONFLICTING_LANGUAGE_RE = re.compile(
    r"(?:\b(?:chinese|zh-cn|mandarin)\b|[\u4e00-\u9fff].*?(?:中文|汉语)).*?\b(?:english|en-us|en-gb)\b|"
    r"\b(?:english|en-us|en-gb)\b.*?(?:中文|汉语|\b(?:chinese|zh-cn|mandarin)\b)",
    re.IGNORECASE,
)
_REPOSITORY_CODE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".go", ".h", ".hpp", ".java", ".js", ".jsx",
    ".kt", ".m", ".php", ".py", ".rb", ".rs", ".scala", ".sh", ".swift", ".ts", ".tsx",
}


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
        repository_paths: list[str] | None = None,
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
        repositories = _complete_repository_inputs(
            repository_paths or [],
            artifact_root=self.artifact_root,
            run_id=run_id,
        )
        decision = select_production_route(
            prompt,
            seed_inputs=normalized_seeds,
            explicit_workflow=explicit_workflow,
            run_mode=run_mode,
        )
        try:
            configured_workflow = self.workflow_loader(decision)
        except Exception as exc:
            raise ResearchRuntimeError(f"workflow route resolution failed: {exc}") from exc
        workflow_identity = {
            "workflow_id": str(configured_workflow.get("workflow_id") or "unavailable"),
            "workflow_version": configured_workflow.get("version", "unavailable"),
            "workflow_kind": str(configured_workflow.get("workflow_kind") or decision.workflow_kind),
        }
        task_contract = build_task_contract(
            prompt=prompt,
            run_id=run_id,
            decision=decision,
            seed_inputs=normalized_seeds,
            supplied_evidence=evidence,
            output_language=output_language,
            repository_inputs=repositories,
            workflow_identity=workflow_identity,
            run_provenance=_git_checkout_provenance(_HARNESS_ROOT.parent),
        )
        contract_path = _write_task_contract(self.artifact_root, run_id, task_contract)
        readiness_gate = task_contract["constraints"].get("readiness_gate", {})
        if readiness_gate.get("status") == "needs_clarification":
            return {
                "schema": "solar_research_runtime_result.v1",
                "task_id": task_contract["task_id"],
                "run_id": run_id,
                "prompt": prompt,
                "route": decision.to_dict(),
                "workflow_id": workflow_identity["workflow_id"],
                "start_node": None,
                "run_mode": run_mode,
                "run_provenance": deepcopy(task_contract["run_provenance"]),
                "task_contract_path": str(contract_path),
                "final_status": "awaiting_human",
                "state_path": "",
                "final_status_evidence_refs": [],
                "node_states": {},
                "current_blockers": [
                    {
                        "blocker_id": "research_readiness_needs_clarification",
                        "node_id": "__intake__",
                        "reason": "Core research requirements are missing or contradictory.",
                        "questions": deepcopy(readiness_gate.get("questions") or []),
                    }
                ],
                "conditionally_skipped_nodes": [],
            }
        try:
            workflow = apply_task_conditions(configured_workflow, task_contract)
        except Exception as exc:
            raise ResearchRuntimeError(f"workflow route resolution failed: {exc}") from exc
        runtime_authorization = deepcopy(self.authorization)
        approved = set(runtime_authorization.get("approved_capabilities") or [])
        approved.update(
            capability
            for node in workflow.get("nodes") or []
            for capability in node.get("required_capabilities") or []
            if capability != "execute_experiment"
            and (
                not node.get("allow_live_provider")
                or runtime_authorization.get("allow_live_provider") is True
            )
            and (
                not node.get("allow_network")
                or runtime_authorization.get("allow_network") is True
            )
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
            if (
                not imported_result
                and state.get("final_status") == "awaiting_human"
                and str(runtime_authorization.get("approval_ref") or "").strip()
            ):
                blocker = next(
                    (
                        item for item in state.get("current_blockers") or []
                        if isinstance(item, dict) and str(item.get("node_id") or "")
                    ),
                    None,
                )
                if blocker is not None:
                    state = orchestrator.resume(
                        redispatch_node_id=str(blocker["node_id"]),
                        authorization=runtime_authorization,
                    )
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
            "run_provenance": deepcopy(task_contract["run_provenance"]),
            "task_contract_path": str(contract_path),
            "final_status": state.get("final_status"),
            "state_path": str(state_path),
            "final_status_evidence_refs": list(state.get("final_status_evidence_refs") or []),
            "node_states": deepcopy(state.get("node_states") or {}),
            "current_blockers": deepcopy(state.get("current_blockers") or []),
            "conditionally_skipped_nodes": deepcopy(workflow.get("conditional_skips") or []),
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
    repository_inputs: list[dict] | None = None,
    workflow_identity: dict[str, Any] | None = None,
    run_provenance: dict[str, Any] | None = None,
) -> dict:
    """Build the frozen Phase 0 task contract without truncating user intent."""

    compiled = compile_research_requirements(
        prompt=prompt,
        decision=decision,
        seed_inputs=seed_inputs,
        output_language=output_language,
        repository_inputs=repository_inputs or [],
        supplied_evidence=supplied_evidence or [],
    )
    language = compiled["deliverable"]["language"]
    local_lifecycle = decision.workflow_kind in {"paper_ingestion", "scientific_lifecycle"}
    required_content: list[dict[str, Any]] = []
    lowered_prompt = prompt.lower()
    if re.search(r"\b(method|methods|methodology|procedure|approach)\b|方法|方法论", lowered_prompt):
        required_content.append({
            "requirement_id": "method_evidence",
            "description": "Render available method evidence, or explicitly disclose insufficient method evidence.",
            "required": True,
        })
    if re.search(r"\b(result|results|finding|findings|claim|claims|conclusion|conclusions)\b|结果|结论|发现", lowered_prompt):
        required_content.append({
            "requirement_id": "result_claims",
            "description": "Preserve source-grounded result or claim semantics in the final report.",
            "required": True,
        })
    if re.search(r"\b(limitation|limitations|caveat|caveats)\b|局限|限制|不足", lowered_prompt):
        required_content.append({
            "requirement_id": "limitations",
            "description": "Render known evidence limitations explicitly.",
            "required": True,
        })
    if local_lifecycle:
        artifact_expectations = [
            "report",
            "research_claims",
            "research_method",
            "artifact_review",
            "publication_bundle",
            "final_evaluation",
        ]
        success_criteria = [
            "At least 1 parsed, non-empty local source",
            "Every reported claim is linked to evidence sources",
            "The final report contains non-empty body content",
            "The local structural review is disclosed with its independent-review limitation",
        ]
        review_requirement = {
            "expected_mode": "local_surrogate",
            "independent_peer_review_required": False,
            "limitation_disclosure_required": True,
        }
    else:
        artifact_expectations = ["report", "evidence_synthesis", "source_validation", "independent_review"]
        success_criteria = [
            (
                "At least 2 validated sources"
                if decision.workflow_kind in {"research_synthesis", "literature_synthesis"}
                else "At least 1 parsed, non-empty local source"
            ),
            "At least 2 cited sources",
            "Every conclusion is linked to evidence sources",
            "The final report contains non-empty body content",
            "The independent review verdict is accept",
        ]
        review_requirement = {
            "expected_mode": "independent_model_review",
            "independent_peer_review_required": True,
            "limitation_disclosure_required": False,
        }
    provenance = deepcopy(run_provenance) if isinstance(run_provenance, dict) else _git_checkout_provenance(_HARNESS_ROOT.parent)
    provenance["workflow_identity"] = deepcopy(workflow_identity or {
        "workflow_id": "unavailable",
        "workflow_version": "unavailable",
        "workflow_kind": decision.workflow_kind,
    })
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
            "format": compiled["deliverable"]["format"],
            "delivery_type": compiled["deliverable"]["delivery_type"],
            "artifact_expectations": artifact_expectations,
            "required_content": required_content,
            "compiled_acceptance": compiled["deliverable"]["compiled_acceptance"],
            "review_requirement": review_requirement,
        },
        "workflow_kind": decision.workflow_kind,
        "run_mode": decision.run_mode,
        "constraints": {
            "no_live_provider_without_approval": True,
            "no_secret_logging": True,
            "repository_inputs": deepcopy(repository_inputs or []),
            "request_capture": compiled["request_capture"],
            "user_constraints": compiled["constraints"],
            "readiness_gate": compiled["readiness_gate"],
            "conditional_skips": [],
        },
        "provider_requirements": [],
        "platform_requirements": [],
        "success_criteria": success_criteria,
        "run_provenance": provenance,
        "supplied_evidence": deepcopy(supplied_evidence or []),
    }


def compile_research_requirements(
    *,
    prompt: str,
    decision: ResearchRouteDecision,
    seed_inputs: list[dict],
    output_language: str = "",
    repository_inputs: list[dict] | None = None,
    supplied_evidence: list[dict] | None = None,
) -> dict[str, Any]:
    """Compile user-facing research requirements into machine-checkable fields."""

    prompt_text = str(prompt or "")
    prompt_lower = prompt_text.lower()
    detected_urls = _dedupe_strings(_PROMPT_URL_RE.findall(prompt_text))
    detected_pdfs = _dedupe_strings(_PROMPT_PDF_RE.findall(prompt_text))
    language = _compile_output_language(prompt_text, output_language)
    delivery_format = _compile_delivery_format(prompt_text)
    minimum_sources = _requested_minimum(
        prompt_text,
        (
            r"at\s+least\s+(\d+)\s+(?:traceable\s+)?(?:public\s+)?(?:links?|sources?)",
            r"minimum\s+of\s+(\d+)\s+(?:traceable\s+)?(?:links?|sources?)",
            r"至少\s*(?:提供|包含)?\s*(\d+)\s*(?:个|条)?\s*(?:可追溯|公开)?(?:来源|链接)",
        ),
        1 if decision.seed_kind == "url" else 0,
    )
    minimum_trends = _requested_minimum(
        prompt_text,
        (
            r"at\s+least\s+(\d+)\s+(?:technical\s+)?trends?",
            r"minimum\s+of\s+(\d+)\s+(?:technical\s+)?trends?",
            r"至少\s*(?:总结|梳理|提炼|覆盖|列出)?\s*(\d+)\s*(?:个|项)?(?:相关|关键)?(?:技术)?趋势",
        ),
        0,
    )
    constraints = {
        "prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
        "prompt_length_chars": len(prompt_text),
        "detected_urls": detected_urls,
        "detected_pdfs": detected_pdfs,
        "output_language": language,
        "delivery_format": delivery_format,
        "minimum_traceable_sources": minimum_sources,
        "minimum_trends": minimum_trends,
        "online_retrieval_required": bool(detected_urls or re.search(r"\b(?:current|online|web|internet|live)\b|当前|互联网|公开网页|在线", prompt_lower)),
        "claim_evidence_separation_required": bool(
            re.search(
                r"claim.*evidence.*inference|separat(?:e|ing).*claims?.*evidence|"
                r"claims?.*evidence.*separat(?:e|ion)|事实.*证据.*推断|区分.*主张.*证据|证据.*推断",
                prompt_text,
                re.IGNORECASE,
            )
        ),
        "repository_input_count": len(repository_inputs or []),
        "supplied_evidence_count": len(supplied_evidence or []),
    }
    acceptance = [
        "Preserve the complete user prompt in user_intent and request_capture.",
        f"Select workflow_kind={decision.workflow_kind} and seed_kind={decision.seed_kind}.",
        f"Produce deliverable format={delivery_format} and language={language}.",
    ]
    if minimum_sources:
        acceptance.append(f"Preserve at least {minimum_sources} traceable sources or fail closed with explicit limitations.")
    if minimum_trends:
        acceptance.append(f"Cover at least {minimum_trends} trends or fail closed with explicit limitations.")
    if constraints["claim_evidence_separation_required"]:
        acceptance.append("Separate claims, evidence, and inference in the produced report.")

    readiness = _compile_readiness_gate(
        prompt_text=prompt_text,
        decision=decision,
        constraints=constraints,
        seed_inputs=seed_inputs,
        supplied_evidence=supplied_evidence or [],
    )
    return {
        "request_capture": {
            "raw_prompt": prompt_text,
            "raw_prompt_sha256": constraints["prompt_sha256"],
            "raw_prompt_length_chars": constraints["prompt_length_chars"],
            "seed_inputs": deepcopy(seed_inputs),
            "detected_urls": detected_urls,
            "detected_pdfs": detected_pdfs,
        },
        "deliverable": {
            "language": language,
            "format": delivery_format,
            "delivery_type": delivery_format,
            "compiled_acceptance": acceptance,
        },
        "constraints": constraints,
        "readiness_gate": readiness,
    }


def _compile_readiness_gate(
    *,
    prompt_text: str,
    decision: ResearchRouteDecision,
    constraints: dict[str, Any],
    seed_inputs: list[dict],
    supplied_evidence: list[dict],
) -> dict[str, Any]:
    missing: list[str] = []
    contradictions: list[str] = []
    questions: list[str] = []
    stripped = prompt_text.strip()
    if decision.requires_user_confirmation or _AMBIGUOUS_RESEARCH_RE.match(stripped):
        missing.append("research_goal_or_acceptance")
        questions.append("What exact research question, source scope, and acceptance criteria should Solar use?")
    if decision.seed_kind == "url" and not constraints["detected_urls"] and not any(item.get("seed_kind") == "url" for item in seed_inputs):
        missing.append("url_source")
        questions.append("Which URL should Solar read as the research seed?")
    if decision.seed_kind == "pdf" and not any(item.get("seed_kind") == "pdf" for item in seed_inputs):
        missing.append("pdf_source")
        questions.append("Which PDF file should Solar ingest?")
    if decision.run_mode in {"resume", "import_evidence"} and not supplied_evidence and not any(
        item.get("seed_kind") == "external_evidence" for item in seed_inputs
    ):
        missing.append("external_evidence")
        questions.append("Which existing evidence artifact should Solar resume from?")
    if _CONFLICTING_LANGUAGE_RE.search(prompt_text):
        contradictions.append("output_language")
        questions.append("Should the final deliverable be in Chinese or English?")
    status = "needs_clarification" if missing or contradictions else "ready"
    return {
        "status": status,
        "missing_core_requirements": missing,
        "contradictions": contradictions,
        "questions": _dedupe_strings(questions),
        "requires_user_confirmation": bool(decision.requires_user_confirmation),
    }


def _compile_output_language(prompt: str, explicit: str) -> str:
    requested = str(explicit or "").strip()
    if requested:
        return requested
    if _CHINESE_RE.search(prompt):
        return "zh-CN"
    if _ENGLISH_RE.search(prompt):
        return "en"
    return "preserve_user_request"


def _compile_delivery_format(prompt: str) -> str:
    if _JSON_DELIVERABLE_RE.search(prompt):
        return "json"
    if _PDF_DELIVERABLE_RE.search(prompt):
        return "pdf"
    if _MARKDOWN_DELIVERABLE_RE.search(prompt):
        return "markdown"
    return "request_format"


def _requested_minimum(text: str, patterns: tuple[str, ...], default: int) -> int:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return max(1, int(match.group(1)))
            except (TypeError, ValueError):
                continue
    return default


def _dedupe_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item)))


def _write_task_contract(artifact_root: Path, run_id: str, task_contract: dict[str, Any]) -> Path:
    path = artifact_root / "contracts" / f"{_safe_component(run_id)}.research_task_contract.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(task_contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _git_checkout_provenance(repo_root: Path) -> dict[str, Any]:
    """Capture only bounded, non-secret implementation identity from Git."""

    captured_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    root = Path(repo_root).resolve()
    if not (root / ".git").exists():
        return {
            "repo_head": "unavailable",
            "worktree_status": "unavailable",
            "captured_at": captured_at,
        }
    try:
        top_level = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        if os.path.normcase(str(Path(top_level).resolve())) != os.path.normcase(str(root)):
            raise subprocess.CalledProcessError(128, "git rev-parse --show-toplevel")
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=normal"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {
            "repo_head": "unavailable",
            "worktree_status": "unavailable",
            "captured_at": captured_at,
        }
    return {
        "repo_head": head if re.fullmatch(r"[0-9a-fA-F]{40,64}", head) else "unavailable",
        "worktree_status": "dirty" if status.strip() else "clean",
        "captured_at": captured_at,
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
    """Expose the Phase 2 research synthesis operators through explicit production bindings."""

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
        "report_revision_operator",
        "final_acceptance_operator",
    )
    return PhysicalOperatorResolver(
        [PhysicalOperatorBinding(operator_id=operator_id, runner=run, version="research_synthesis.v1.7") for operator_id in operator_ids]
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

    root = Path(workspace_root or Path.cwd()).resolve()
    injected = services
    if injected is None:
        try:
            from harness.plugins.autosci.services import production_services_from_environment
        except ModuleNotFoundError:
            from plugins.autosci.services import production_services_from_environment
        injected = production_services_from_environment(workspace_root=root)
    return PhysicalOperatorResolver(
        production_bindings(
            services=deepcopy(injected),
            workspace_root=root,
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


def _complete_repository_inputs(
    repository_paths: list[str],
    *,
    artifact_root: Path,
    run_id: str,
) -> list[dict[str, Any]]:
    """Snapshot a bounded code-only view so code mapping stays workspace scoped."""

    completed: list[dict[str, Any]] = []
    for index, raw in enumerate(repository_paths, start=1):
        source = Path(str(raw)).expanduser().resolve()
        if not source.exists():
            raise ResearchRuntimeError(f"repository input is missing: {source}")
        snapshot_root = artifact_root / "inputs" / _safe_component(run_id) / f"repository-{index:02d}"
        members = [source] if source.is_file() else sorted(item for item in source.rglob("*") if item.is_file())
        copied: list[dict[str, str]] = []
        total_bytes = 0
        for member in members:
            if member.suffix.lower() not in _REPOSITORY_CODE_SUFFIXES:
                continue
            size = member.stat().st_size
            if size > 1_000_000 or total_bytes + size > 50 * 1024 * 1024 or len(copied) >= 500:
                continue
            relative = Path(member.name) if source.is_file() else member.relative_to(source)
            target = snapshot_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(member, target)
            total_bytes += size
            copied.append({"path": target.relative_to(artifact_root).as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        if not copied:
            raise ResearchRuntimeError(f"repository input contains no bounded supported code files: {source}")
        captured_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        completed.append(
            {
                "repository_id": f"repository-{index}",
                "original_path": str(source),
                "snapshot_path": str(snapshot_root),
                "snapshot_sha256": hashlib.sha256(
                    repr(sorted((item["path"], item["sha256"]) for item in copied)).encode("utf-8")
                ).hexdigest(),
                "file_count": len(copied),
                "total_bytes": total_bytes,
                "captured_at": captured_at,
            }
        )
    return completed


def _secret_values(authorization: dict) -> tuple[str, ...]:
    values = authorization.get("secret_values") if isinstance(authorization, dict) else None
    if isinstance(values, dict):
        return tuple(str(item) for item in values.values() if str(item))
    if isinstance(values, list):
        return tuple(str(item) for item in values if str(item))
    return ()
