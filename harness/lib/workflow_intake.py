"""Contracted intake — explicit workflow_id -> instantiated contract sprint.

P2 smoke cause 1 (design §0): ``code.cli_smoke``'s trigger is deliberately
"explicit workflow_id only", but no intake seam could carry a workflow_id, so
the live smoke fell through to the generic planner path. This module is that
seam. Given a registered fixed-stages contract it:

1. instantiates the contract (Lane 1 ``workflow_contract.instantiate``) into
   ``sprints/<sid>.task_graph.json`` — the graph carries
   ``workflow_contract_id``/``version``/``hash`` so the Lane 3 dispatcher guard
   applies;
2. writes the drafting sprint scaffold the coordinator's pickup loop expects
   (``status.json`` shape mirrors ``pm_dispatch.ensure_compiled_sprint_status``
   — that helper lives in the runtime tools tree, which this module must not
   import) plus the planner artifacts (prd/contract/design/plan) the drafting
   auto-promote requires, all honestly derived from the contract;
3. fails CLOSED on an unknown or planner-generated workflow_id — never a
   silent fall-through to the generic path (exit 3 / 4 at the CLI).

Pure like the rest of the Lane 1 family: stdlib + workflow_contract only, no
runtime imports, atomic writes.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import secrets
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import workflow_contract as wc  # noqa: E402


class WorkflowIntakeError(Exception):
    """Fail-closed intake error; ``code`` maps to the CLI exit code."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", str(value or "")).strip("-").lower()[:40] or "wf"


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, str(path))


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    _write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _append_event(path: Path, event: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _intake_request_id() -> str:
    """Return the sanitized dashboard intake request id, if one was supplied.

    The status server exports ``SOLAR_INTAKE_REQUEST_ID`` for the intake it
    invokes and writes a matching receipt under
    ``HARNESS_DIR/run/intake-requests/``.  The value is caller-supplied, so it
    is re-sanitized here with the same character class and length bound the
    server applies rather than trusted as-is.  An empty or fully-rejected value
    yields ``""`` and leaves the sprint status unstamped.
    """

    raw = str(os.environ.get("SOLAR_INTAKE_REQUEST_ID") or "").strip()
    if not raw:
        return ""
    return re.sub(r"[^A-Za-z0-9_.:-]", "-", raw)[:96]


def _stage_table(contract: Dict[str, Any]) -> str:
    lines = ["| stage | goal | depends_on | task_type | gate |", "|---|---|---|---|---|"]
    for stage in contract.get("stages") or []:
        gate = (stage.get("evaluator_gate") or {}).get("kind") or "none"
        lines.append(
            f"| {stage.get('id')} | {str(stage.get('goal') or stage.get('dashboard_label') or '').strip()[:80]} "
            f"| {', '.join(stage.get('depends_on') or []) or '-'} | {stage.get('task_type')} | {gate} |"
        )
    return "\n".join(lines)


def create_contract_sprint(
    *,
    workflow_id: str,
    request: str,
    workspace_root: Optional[str] = None,
    inputs: Optional[Dict[str, str]] = None,
    sprints_dir: Optional[os.PathLike] = None,
    workflows_dir: Optional[os.PathLike] = None,
    intent_id: Optional[str] = None,
) -> Dict[str, Any]:
    workflow_id = str(workflow_id or "").strip()
    request = str(request or "").strip()
    if not workflow_id:
        raise WorkflowIntakeError("WORKFLOW_ID_MISSING: empty workflow_id", code=2)
    if not request:
        raise WorkflowIntakeError("REQUEST_MISSING: empty request text", code=2)

    contract = wc.find_contract(workflow_id, workflows_dir)
    if contract is None:
        raise WorkflowIntakeError(
            f"WORKFLOW_ID_UNREGISTERED: {workflow_id!r} is not a registered contract", code=3
        )
    if contract.get("stages_mode", "fixed") == getattr(wc, "STAGES_MODE_PLANNER", "planner_generated"):
        raise WorkflowIntakeError(
            f"WORKFLOW_PLANNER_GENERATED: {workflow_id!r} declares planner-generated stages — "
            "it goes through the generic intake + plan_validator, not contracted intake",
            code=4,
        )

    now = _utc_now()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    collision_suffix = f"-{secrets.token_hex(6)}" if workflow_id == "research.evidence_to_poc.v1" else ""
    sid = f"sprint-{stamp}-wf-{_slug(workflow_id)}{collision_suffix}"
    workspace = str(
        workspace_root
        or os.environ.get("SOLAR_INTAKE_WORKSPACE_ROOT")
        or os.getcwd()
    )

    substitutions: Dict[str, Any] = {
        "sprint_id": sid,
        "sid": sid,
        "workspace_root": workspace,
    }
    for key, value in (inputs or {}).items():
        key = str(key).strip()
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", key):
            raise WorkflowIntakeError(f"INPUT_KEY_INVALID: {key!r}", code=2)
        substitutions[key] = str(value)

    sprints = Path(sprints_dir) if sprints_dir else _default_sprints_dir()
    bound_intent_id = str(intent_id or "").strip()
    if bound_intent_id and not re.fullmatch(r"[A-Za-z0-9._-]+", bound_intent_id):
        raise WorkflowIntakeError("INTENT_ID_INVALID: intent_id must be a simple identifier", code=2)

    fixed_research = workflow_id == "research.evidence_to_poc.v1"
    if fixed_research:
        try:
            from fixed_research_workflow import (
                FixedResearchContractError,
                build_fixed_research_graph,
            )

            # The source authority is controller-owned.  Workflow payload
            # inputs and the caller-selectable workspace_root never choose it.
            supplied_source_pack = str(substitutions.get("source_pack_root") or "").strip()
            if supplied_source_pack and not bound_intent_id:
                raise FixedResearchContractError(
                    "an executable fixed research intake requires a controller-bound intent_id"
                )
            policy_source_root = None
            if supplied_source_pack:
                policy_source_root = Path(
                    os.environ.get("SOLAR_RESEARCH_SOURCE_PACK_ROOT")
                    or (_default_sprints_dir().parent / "sources")
                ).resolve(strict=True)
            graph = build_fixed_research_graph(
                sprint_id=sid,
                request=request,
                execution_profile=str(substitutions.get("execution_profile") or ""),
                acquisition_mode=str(substitutions.get("acquisition_mode") or ""),
                source_pack_root=supplied_source_pack or None,
                authority_root=str(policy_source_root) if policy_source_root else None,
                workflows_dir=workflows_dir,
                snapshot_root=(sprints / sid / "workdir" / "inputs" / "source-pack"),
                allow_unavailable_source_pack=not bool(supplied_source_pack),
                experiment_policy=str(substitutions.get("experiment_policy") or ""),
                experiment_policy_actor=str(substitutions.get("experiment_policy_actor") or ""),
                experiment_policy_statement=str(substitutions.get("experiment_policy_statement") or ""),
                retrieval_policy=str(substitutions.get("retrieval_policy") or ""),
            )
        except (FixedResearchContractError, OSError) as exc:
            # The fixed intake reserves a collision-resistant SID before it
            # snapshots controller-owned inputs.  If either snapshot or graph
            # construction fails, remove only that newly reserved sprint tree
            # so a rejected intake cannot leave authoritative-looking bytes.
            shutil.rmtree(sprints / sid, ignore_errors=True)
            raise WorkflowIntakeError(f"FIXED_RESEARCH_INTAKE_REJECTED: {exc}", code=6) from exc
    else:
        graph = wc.instantiate(contract, substitutions)

    if fixed_research and bound_intent_id:
        graph["intent_binding"] = {
            "required": True,
            "status": "pending",
            "intent_id": bound_intent_id,
        }
        graph["workflow_contract_hash"] = wc.graph_contract_hash(graph)

    # Fail closed on any placeholder the caller did not resolve — a graph with
    # literal <tool>-style paths would dispatch builders at nonsense write scopes.
    leftover = sorted(set(re.findall(r"<([a-z_][a-z0-9_]*)>", json.dumps(graph))))
    if leftover:
        raise WorkflowIntakeError(
            f"UNRESOLVED_PLACEHOLDERS: {leftover} — pass --input key=value for each",
            code=5,
        )

    sprints.mkdir(parents=True, exist_ok=True)

    _write_json_atomic(sprints / f"{sid}.task_graph.json", graph)

    title = f"[{workflow_id}] {request[:80]}"
    version = str(contract.get("version") or "")
    header = (
        f"> Generated from workflow contract `{workflow_id}` v{version} "
        f"(hash `{graph.get('workflow_contract_hash')}`) at {now}. Stages are\n"
        "> contract-determined; the planner is not involved (design §0 contracted path).\n\n"
    )
    _write_text_atomic(
        sprints / f"{sid}.prd.md",
        f"# PRD — {title}\n\n{header}## Request\n\n{request}\n",
    )
    _write_text_atomic(
        sprints / f"{sid}.contract.md",
        f"# Contract — {workflow_id} v{version}\n\n{header}{_stage_table(contract)}\n",
    )
    _write_text_atomic(
        sprints / f"{sid}.design.md",
        f"# Design — {title}\n\n{header}The task graph is the contract's fixed stage DAG:\n\n{_stage_table(contract)}\n",
    )
    _write_text_atomic(
        sprints / f"{sid}.plan.md",
        f"# Plan — {title}\n\n{header}Execution follows the contract stages in dependency order.\n\n{_stage_table(contract)}\n",
    )

    # Drafting scaffold — shape mirrors pm_dispatch.ensure_compiled_sprint_status
    # (kept in lockstep by test_workflow_intake; this module must not import the
    # runtime tools tree).
    fixed_research_ready = False
    if fixed_research:
        acquisition_mode = str((graph.get("acquisition_mode") or {}).get("kind") or "")
        source_pack_verified = (
            (graph.get("source_pack_authority") or {}).get("status") == "verified"
        )
        retrieval_policy_bound = bool(
            (graph.get("retrieval_policy") or {}).get("policy_id")
            and (graph.get("retrieval_policy") or {}).get("path")
            and (graph.get("retrieval_policy") or {}).get("sha256")
        )
        fixed_research_ready = (
            source_pack_verified
            if acquisition_mode == "source_pack"
            else source_pack_verified and retrieval_policy_bound
            if acquisition_mode == "hybrid"
            else retrieval_policy_bound
            if acquisition_mode == "live_search"
            else False
        )
    binding_pending = bool(fixed_research and bound_intent_id)
    # The dashboard/status-server front door creates the sprint through this
    # CLI and exports the request id it already wrote to its own intake
    # receipt.  Record that id on the authoritative sprint status so a
    # downstream controller can attribute the sprint to the exact dashboard
    # submission without guessing by title, time, or file order.
    intake_request_id = _intake_request_id()
    status = {
        "id": sid,
        "title": title,
        "summary": request[:200],
        "created_at": now,
        "round": 0,
        "status": ("blocked" if binding_pending else ("active" if fixed_research_ready else "blocked")) if fixed_research else "drafting",
        "phase": ("intent_binding_pending" if binding_pending else ("planning_complete" if fixed_research_ready else "needs_human_review")) if fixed_research else "prd_ready",
        "handoff_to": ("workflow_intake" if binding_pending else ("builder_main" if fixed_research_ready else "human")) if fixed_research else "planner",
        "target_role": ("workflow_intake" if binding_pending else ("builder_main" if fixed_research_ready else "human")) if fixed_research else "planner",
        "updated_at": now,
        "history": [
            {"ts": now, "event": "contract_sprint_instantiated", "by": "workflow-intake",
             "note": f"{workflow_id} v{version}"},
        ],
    }
    if intake_request_id:
        status["request_id"] = intake_request_id
    _write_json_atomic(sprints / f"{sid}.status.json", status)

    _append_event(
        sprints / f"{sid}.events.jsonl",
        {
            "ts": now,
            "actor": "workflow_intake",
            "event": "contract_sprint_instantiated",
            "sid": sid,
            "status": "info",
            "detail": {
                "workflow_contract_id": workflow_id,
                "workflow_contract_version": version,
                "workflow_contract_hash": graph.get("workflow_contract_hash"),
                "stages": [n.get("id") for n in graph.get("nodes") or []],
                "workspace_root": workspace,
            },
        },
    )

    binding_manifest: Dict[str, Any] = {}
    if fixed_research and bound_intent_id:
        binding_path: Path | None = None
        claim_path: Path | None = None
        try:
            import intent_gateway

            intent_gateway.SPRINTS_DIR = sprints
            binding_path = intent_gateway.INTENTS_DIR / bound_intent_id / "binding.json"
            if binding_path.exists() or binding_path.is_symlink():
                raise WorkflowIntakeError(
                    f"INTENT_ALREADY_BOUND: {bound_intent_id} already has a binding record", code=6
                )
            claim_path = binding_path.with_name("binding.claim")
            claim_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                claim_fd = os.open(claim_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as exc:
                raise WorkflowIntakeError(
                    f"INTENT_BIND_IN_PROGRESS: {bound_intent_id} is already being bound", code=6
                ) from exc
            with os.fdopen(claim_fd, "w", encoding="utf-8") as claim:
                claim.write(sid + "\n")
            binding_manifest = intent_gateway.bind_intent_artifacts(bound_intent_id, sid)
            graph["intent_binding"] = {
                "required": True,
                "status": "bound",
                "intent_id": bound_intent_id,
                "manifest": str(binding_path),
            }
            graph["workflow_contract_hash"] = wc.graph_contract_hash(graph)
            _write_json_atomic(sprints / f"{sid}.task_graph.json", graph)
            status["status"] = "active" if fixed_research_ready else "blocked"
            status["phase"] = "planning_complete" if fixed_research_ready else "needs_human_review"
            status["handoff_to"] = "builder_main" if fixed_research_ready else "human"
            status["target_role"] = status["handoff_to"]
            status["history"].append({
                "ts": _utc_now(),
                "event": "intent_bound_to_fixed_sprint",
                "by": "workflow-intake",
                "note": bound_intent_id,
            })
            _write_json_atomic(sprints / f"{sid}.status.json", status)
            _append_event(
                sprints / f"{sid}.events.jsonl",
                {
                    "ts": _utc_now(),
                    "actor": "workflow_intake",
                    "event": "intent_bound_to_fixed_sprint",
                    "sid": sid,
                    "status": "info",
                    "detail": {"intent_id": bound_intent_id, "binding": binding_manifest},
                },
            )
            claim_path.unlink(missing_ok=True)
        except (Exception, SystemExit) as exc:
            # This sprint id is freshly generated by this invocation.  Remove
            # only its files/tree so a failed attribution cannot leave an
            # active or dispatchable orphan.
            for path in sprints.glob(f"{sid}.*"):
                if path.is_file() or path.is_symlink():
                    path.unlink(missing_ok=True)
            shutil.rmtree(sprints / sid, ignore_errors=True)
            if binding_path is not None and binding_path.is_file():
                try:
                    recorded = json.loads(binding_path.read_text(encoding="utf-8"))
                    if str(recorded.get("sprint_id") or "") == sid:
                        binding_path.unlink(missing_ok=True)
                except Exception:
                    pass
            if claim_path is not None and claim_path.is_file():
                try:
                    if claim_path.read_text(encoding="utf-8").strip() == sid:
                        claim_path.unlink(missing_ok=True)
                except Exception:
                    pass
            if isinstance(exc, WorkflowIntakeError):
                raise
            raise WorkflowIntakeError(f"INTENT_BIND_FAILED: {exc}", code=6) from exc

    return {
        "ok": True,
        "sprint_id": sid,
        "workflow_contract_id": workflow_id,
        "workflow_contract_version": version,
        "workflow_contract_hash": graph.get("workflow_contract_hash"),
        "stages": [n.get("id") for n in graph.get("nodes") or []],
        "sprints_dir": str(sprints),
        "workspace_root": workspace,
        "intent_binding": binding_manifest,
    }


def _default_sprints_dir() -> Path:
    env_sprints = os.environ.get("HARNESS_SPRINTS_DIR")
    if env_sprints:
        return Path(env_sprints)
    harness_dir = os.environ.get("HARNESS_DIR") or os.environ.get("SOLAR_HARNESS_DIR")
    if harness_dir:
        return Path(harness_dir) / "sprints"
    return Path.home() / ".solar" / "harness" / "sprints"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="workflow_intake",
        description="Contracted intake: instantiate a registered fixed-stages workflow "
                    "contract into a dispatchable sprint (fail-closed on unknown ids).",
    )
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--workspace-root", default=None)
    parser.add_argument("--input", action="append", default=[], metavar="KEY=VALUE",
                        help="contract placeholder input (repeatable); also read from "
                             "the SOLAR_INTAKE_WORKFLOW_INPUTS env var (JSON object)")
    parser.add_argument("--sprints-dir", default=None)
    parser.add_argument("--workflows-dir", default=None)
    parser.add_argument("--intent-id", default=None,
                        help="captured RawIntent id that must be transactionally bound before return")
    args = parser.parse_args(argv)
    inputs: Dict[str, str] = {}
    env_inputs = os.environ.get("SOLAR_INTAKE_WORKFLOW_INPUTS", "").strip()
    if env_inputs:
        try:
            parsed = json.loads(env_inputs)
            if isinstance(parsed, dict):
                inputs.update({str(k): str(v) for k, v in parsed.items()})
        except Exception:
            print("workflow_intake: SOLAR_INTAKE_WORKFLOW_INPUTS is not valid JSON", file=sys.stderr)
            return 2
    for item in args.input:
        if "=" not in item:
            print(f"workflow_intake: --input needs KEY=VALUE, got {item!r}", file=sys.stderr)
            return 2
        key, _, value = item.partition("=")
        inputs[key.strip()] = value
    try:
        result = create_contract_sprint(
            workflow_id=args.workflow_id,
            request=args.request,
            workspace_root=args.workspace_root,
            inputs=inputs,
            sprints_dir=args.sprints_dir,
            workflows_dir=args.workflows_dir,
            intent_id=args.intent_id,
        )
    except WorkflowIntakeError as exc:
        print(f"workflow_intake: {exc}", file=sys.stderr)
        return int(exc.code)
    # "Sprint created: <sid>" is the attribution line the status-server's
    # _extract_intake_id parses — keep both this line and the JSON blob.
    print(f"Sprint created: {result['sprint_id']}")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
