"""Deterministic Part-B operators for the fixed evidence-to-PoC workflow."""
from __future__ import annotations

import hashlib
import json
import re
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import jsonschema

from harness.plugins.autosci.operators.research_synthesis.base import (
    OperatorContext,
    ResearchOperatorError,
    build_node_result,
    evidence_ref,
    sha256_bytes,
    stable_json_sha256,
    validate_scoped_path,
    write_artifact,
)
from harness.plugins.autosci.services.experiment_executor import SandboxedBenchmarkExecutor


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "evidence" / "fixed_research_part_b.v1.schema.json"
BENCHMARK_SCRIPT = Path(__file__).resolve().parents[3] / "tools" / "fixed_research_benchmark.py"
BENCHMARK_ID = "evidence-lineage-integrity-v1"
APPROVED_CAPABILITIES = ["execute:fixed_evidence_lineage_benchmark", "network:none"]
PART_A_IDS = {
    "seed_fetch",
    "source_discovery",
    "source_validation",
    "evidence_synthesis",
    "report_draft",
    "independent_review",
    "report_revision",
    "final_acceptance",
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dependency(dependencies: list[dict[str, Any]], node_id: str) -> dict[str, Any]:
    row = next((item for item in dependencies if str(item.get("artifact_id") or "") == node_id), None)
    if not isinstance(row, dict):
        raise ResearchOperatorError(f"Missing accepted dependency: {node_id}", error_type="missing_input")
    return row


def _load(context: OperatorContext, row: dict[str, Any]) -> dict[str, Any]:
    return context.load_json_artifact(row)


def _validated_payload(payload: dict[str, Any]) -> dict[str, Any]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(payload)
    return payload


def _write(
    context: OperatorContext,
    primary_rel: str,
    payload: dict[str, Any],
    *,
    artifact_id: str,
    schema: str,
    extra_artifacts: list[dict[str, Any]] | None = None,
    extra_hashes: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    _validated_payload(payload)
    artifact, digest = write_artifact(
        context,
        primary_rel,
        payload,
        artifact_id=artifact_id,
        schema=schema,
    )
    artifacts = [artifact, *(extra_artifacts or [])]
    return build_node_result(
        context,
        status="completed",
        output_artifacts=artifacts,
        evidence=[
            evidence_ref(
                f"evidence.{str(item.get('artifact_id') or artifact_id)}",
                "fixed_part_b",
                f"Produced {str(item.get('schema') or schema)}.",
                str(item.get("artifact_id") or artifact_id),
            )
            for item in artifacts
        ],
        hashes=[digest, *(extra_hashes or [])],
        limitations=limitations or [],
    )


def _file_artifact(path: Path, context: OperatorContext, artifact_id: str, schema: str) -> tuple[dict[str, Any], dict[str, Any]]:
    digest = _sha(path)
    relative = str(path.relative_to(context.workspace_root)).replace("\\", "/")
    return (
        {"artifact_id": artifact_id, "path": relative, "schema": schema, "sha256": digest},
        {"hash_id": artifact_id, "algorithm": "sha256", "value": digest},
    )


_HEADING_RE = re.compile(r"(?m)^##\s+(.+)$")


def report_sections(report: dict[str, Any]) -> list[dict[str, str]]:
    """Split an accepted report body into the sections AutoSci reads.

    `research_paper.v1` wants `sections[{title, text, source_anchor}]`. The
    accepted report carries markdown, so it is split on level-2 headings and each
    section keeps an anchor back to where it came from. Structured
    `report.sections` is preferred when present, since it is the writer's own
    division rather than one inferred from formatting.
    """
    structured = report.get("sections") if isinstance(report.get("sections"), list) else []
    rows: list[dict[str, str]] = []
    for item in structured:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        text = str(item.get("body") or item.get("text") or "").strip()
        if title and text:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            rows.append({"title": title, "text": text, "source_anchor": f"report.md#{slug}"})
    if rows:
        return rows
    body = str(report.get("body") or "")
    parts = _HEADING_RE.split(body)
    for index in range(1, len(parts), 2):
        title = str(parts[index]).strip()
        text = str(parts[index + 1]).strip() if index + 1 < len(parts) else ""
        if title and text:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            rows.append({"title": title, "text": text, "source_anchor": f"report.md#{slug}"})
    return rows


def extract_report_claims(
    context: OperatorContext,
    stage_dir: Path,
    research_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Run AutoSci's own claim extractor over the accepted research report.

    Rebound, not reimplemented: this calls `execute_claim_extract`, the operator
    registered as `autosci-evidence-claim-extract`, so the claims, their
    testability tags and their source anchors are AutoSci's, and the call goes
    through the same evidence discipline as any other -- hash-verified input,
    scoped paths, idempotent replay.

    Before this, Part B never read the research report at all: it selected a
    hardcoded benchmark idea and verified artifact digests. The claims returned
    here are what make Part B derive from the research it is supposed to follow.
    """
    from ..operators.scientific_lifecycle.evidence.registry import execute_claim_extract

    sections = research_report.get("sections") or []
    if not sections:
        return [], [], []

    paper_path = stage_dir / "research_paper.v1.json"
    paper_rel = str(paper_path.relative_to(context.workspace_root)).replace("\\", "/")
    paper_document = {
        "schema": "research_paper.v1",
        "task_id": str(context.node_request.get("task_id") or ""),
        "sprint_id": str(context.node_request.get("sprint_id") or context.node_request.get("run_id") or ""),
        "node_id": "claim_extract",
        "status": "completed",
        "outputs": {
            "paper": {
                "paper_id": "accepted-research-report",
                "title": str(research_report.get("title") or "Accepted research report"),
                "source_type": "markdown",
                "source_ref": str(research_report.get("source_ref") or "report.md"),
                "abstract": "",
                "parse_status": "parsed",
                "sections": sections,
            }
        },
        "limitations": [],
    }
    body = (json.dumps(paper_document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    paper_path.parent.mkdir(parents=True, exist_ok=True)
    paper_path.write_bytes(body)

    stage_rel = str(stage_dir.relative_to(context.workspace_root)).replace("\\", "/") + "/"
    request = {
        "schema": "research_node_request.v1",
        "task_id": str(context.node_request.get("task_id") or ""),
        "run_id": str(context.node_request.get("run_id") or ""),
        "sprint_id": str(context.node_request.get("sprint_id") or context.node_request.get("run_id") or ""),
        "workflow_id": str(context.node_request.get("workflow_id") or ""),
        "node_id": "claim_extract",
        "read_scope": [paper_rel],
        "write_scope": [stage_rel],
        "input_artifact_refs": [
            {
                "artifact_id": "research_paper",
                "path": paper_rel,
                "schema": "research_paper.v1",
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        ],
        "payload": {"limit": 12},
    }
    result = execute_claim_extract(request, workspace_root=context.workspace_root)
    if str(result.get("status") or "") != "completed":
        errors = result.get("errors") or []
        message = str((errors[0] or {}).get("message") or "") if errors else ""
        raise ResearchOperatorError(
            f"AutoSci claim extraction did not complete: {message}"[:200],
            error_type="claim_extraction_failed",
        )

    claims_path = stage_dir / "research_claims.v1.json"
    claims: list[dict[str, Any]] = []
    if claims_path.is_file():
        payload = json.loads(claims_path.read_text(encoding="utf-8"))
        claims = [item for item in ((payload.get("outputs") or {}).get("claims") or []) if isinstance(item, dict)]

    artifacts: list[dict[str, Any]] = []
    hashes: list[dict[str, Any]] = []
    for path, artifact_id, schema in (
        (paper_path, "research-paper", "research_paper.v1"),
        (claims_path, "research-claims", "research_claims.v1"),
    ):
        if path.is_file():
            artifact, digest = _file_artifact(path, context, artifact_id, schema)
            artifacts.append(artifact)
            hashes.append(digest)
    return claims, artifacts, hashes


def _poc_handoff(
    context: OperatorContext,
    primary_rel: str,
    dependencies: list[dict[str, Any]],
) -> dict[str, Any]:
    indexed = {str(item.get("artifact_id") or ""): item for item in dependencies}
    if set(indexed) != PART_A_IDS:
        raise ResearchOperatorError("PoC handoff requires the exact evaluator-accepted A1-A8 chain.", error_type="lineage_incomplete")
    final = _load(context, indexed["final_acceptance"])
    accepted = bool(final.get("accepted")) or str(final.get("decision") or "").lower() in {"accept", "accepted"}
    gate_pass = str(final.get("gate_outcome") or final.get("status") or "").lower() in {"pass", "passed", "accepted", "completed"}
    if not accepted or not gate_pass:
        raise ResearchOperatorError("A8 did not record an accepted PASS outcome.", error_type="acceptance_not_passed")
    artifacts: list[dict[str, Any]] = []
    upstream_limitations: list[str] = []
    review_scope_notes: list[str] = []
    # Which stages speak about the EVIDENCE, and which speak about their own
    # process. A reviewer's note that it "had no access to the original draft"
    # is a fact about the review, not a limitation of the research; carrying it
    # into the delivery as a scientific limitation is how the delivery shipped
    # a sentence contradicting the report's own source count.
    evidence_limitation_nodes = {
        "seed_fetch",
        "source_discovery",
        "source_validation",
        "evidence_synthesis",
        "report_draft",
        "report_revision",
    }
    for node_id in sorted(PART_A_IDS):
        item = indexed[node_id]
        path = context.workspace_root / str(item["path"])
        closeout = item.get("controller_closeout") if isinstance(item.get("controller_closeout"), dict) else {}
        if not closeout.get("eval_record_id") or not closeout.get("manifest_content_digest"):
            raise ResearchOperatorError(f"Dependency lacks controller closeout binding: {node_id}", error_type="lineage_incomplete")
        artifacts.append(
            {
                "node_id": node_id,
                "artifact_id": node_id,
                "path": str(item["path"]),
                "schema": str(item["schema"]),
                "sha256": str(item["sha256"]),
                "bytes": path.stat().st_size,
                "controller_closeout": closeout,
            }
        )
        try:
            upstream = _load(context, item)
        except ResearchOperatorError:
            upstream = {}
        recorded = [str(value) for value in upstream.get("limitations") or [] if str(value).strip()]
        if node_id in evidence_limitation_nodes:
            upstream_limitations.extend(recorded)
        else:
            review_scope_notes.extend(recorded)
        review_scope_notes.extend(
            str(value)
            for value in upstream.get("review_recorded_limitations") or []
            if str(value).strip()
        )
    # The accepted report, in the shape AutoSci reads. It travels through the
    # handoff because idea_evaluation's read scope is exactly its declared
    # dependencies, which is the handoff alone -- it cannot open report_revision
    # itself.
    research_report: dict[str, Any] = {}
    for source_node in ("report_revision", "report_draft"):
        reference = indexed.get(source_node)
        if not isinstance(reference, dict):
            continue
        try:
            document = _load(context, reference)
        except ResearchOperatorError:
            continue
        report = document.get("revised_report") if source_node == "report_revision" else document.get("report")
        if not isinstance(report, dict):
            continue
        sections = report_sections(report)
        if sections:
            research_report = {
                "title": str(report.get("title") or ""),
                "source_ref": "report.md",
                "source_node": source_node,
                "sections": sections,
            }
            break

    payload = {
        "schema": "solar.fixed_research.poc_handoff.v1",
        "status": "accepted",
        "research_report": research_report,
        "part_a_final_acceptance": {
            "path": indexed["final_acceptance"]["path"],
            "sha256": indexed["final_acceptance"]["sha256"],
            "decision": str(final.get("decision") or "accepted"),
            "gate_outcome": str(final.get("gate_outcome") or "pass"),
        },
        "artifacts": artifacts,
        "limitations": list(dict.fromkeys([
            *upstream_limitations,
            "Part B replays evidence-lineage digests and each published claim's "
            "grounding from retained bytes; it does not independently establish "
            "external scientific validity.",
        ])),
        # Preserved for audit, never merged into limitations: these sentences
        # describe how the review was conducted, not what the evidence shows.
        "review_scope_notes": list(dict.fromkeys(review_scope_notes)),
    }
    return _write(context, primary_rel, payload, artifact_id="poc-handoff", schema=payload["schema"], limitations=payload["limitations"])


def _idea_evaluation(context: OperatorContext, primary_rel: str, dependencies: list[dict[str, Any]]) -> dict[str, Any]:
    handoff_ref = _dependency(dependencies, "poc_handoff")
    handoff = _load(context, handoff_ref)
    inputs = [
        {"path": str(item["path"]), "sha256": str(item["sha256"]), "schema": str(item["schema"])}
        for item in handoff.get("artifacts") or []
        if isinstance(item, dict)
    ]
    if not inputs:
        raise ResearchOperatorError("Handoff contains no benchmark inputs.", error_type="lineage_incomplete")

    stage_dir = (context.workspace_root / primary_rel).parent
    report_claims, extra_artifacts, extra_hashes = extract_report_claims(
        context, stage_dir, handoff.get("research_report") or {}
    )
    testable = [item for item in report_claims if str(item.get("testability") or "") == "testable"]

    limitations = [
        "Selection is deterministic and bounded to what this environment can execute: "
        "evidence integrity and claim-grounding replication, not scientific effect replication.",
    ]
    if report_claims:
        limitations.append(
            f"AutoSci extracted {len(report_claims)} claim(s) from the accepted report, "
            f"{len(testable)} of them testable as domain experiments; none is executed "
            "as a domain experiment because that would require external data and methods. "
            "The benchmark below re-hashes the retained lineage and replays every "
            "published claim's grounding from retained source texts."
        )
    else:
        limitations.append(
            "No claim was extracted from the accepted report, so Part B rests on the "
            "lineage and grounding-replication benchmark alone."
        )

    payload = {
        "schema": "solar.fixed_research.idea_evaluation.v1",
        "status": "selected",
        "selected_idea": {
            "idea_id": BENCHMARK_ID,
            "title": "Verify accepted artifact lineage and replay published claim grounding under deterministic replay",
            "hypothesis": (
                "Every artifact accepted into the Part-A handoff still matches its "
                "controller-bound SHA-256 digest, and every published claim's grounding "
                "replays from the retained source texts."
            ),
            "falsification": (
                "Any missing artifact, digest mismatch, non-verbatim recorded quote, "
                "unsupported claim, or non-verbatim contradiction quote falsifies the PoC claim."
            ),
            "selection_basis": (
                "The accepted A1-A8 handoff exposes an exact, bounded integrity claim that can be "
                "tested without network access. It is selected because it is the only claim this "
                "environment can actually execute, not because it is the strongest claim available."
            ),
        },
        # What AutoSci found in the research report. Recorded whether or not it is
        # executed, so the gap between what was claimed and what was tested is
        # visible rather than absent.
        "report_claims": report_claims,
        "testable_report_claims": [str(item.get("claim_id") or "") for item in testable],
        "handoff": {"path": handoff_ref["path"], "sha256": handoff_ref["sha256"]},
        "benchmark_inputs": inputs,
        "rejected_alternatives": [
            {"idea_id": "scientific-effect-replication", "reason": "Would require domain-specific data, methods, and authority outside this bounded workflow."},
            *[
                {
                    "idea_id": str(item.get("claim_id") or ""),
                    "claim_text": str(item.get("text") or "")[:400],
                    "source_anchor": str(item.get("source_anchor") or ""),
                    "reason": "Extracted from the accepted report and testable, but no experiment executor is bound to run it.",
                }
                for item in testable
            ],
        ],
        "limitations": limitations,
    }
    return _write(
        context,
        primary_rel,
        payload,
        artifact_id="idea-evaluation",
        schema=payload["schema"],
        extra_artifacts=extra_artifacts,
        extra_hashes=extra_hashes,
        limitations=payload["limitations"],
    )


def _experiment_design(context: OperatorContext, primary_rel: str, dependencies: list[dict[str, Any]]) -> dict[str, Any]:
    idea_ref = _dependency(dependencies, "idea_evaluation")
    idea = _load(context, idea_ref)
    if str((idea.get("selected_idea") or {}).get("idea_id") or "") != BENCHMARK_ID:
        raise ResearchOperatorError("Idea is not the allowlisted benchmark.", error_type="unsupported_experiment")
    inputs = idea.get("benchmark_inputs") if isinstance(idea.get("benchmark_inputs"), list) else []
    payload = {
        "schema": "solar.fixed_research.experiment_plan.v1",
        "status": "awaiting_human_approval",
        "experiment_id": BENCHMARK_ID,
        "idea": {"path": idea_ref["path"], "sha256": idea_ref["sha256"]},
        "benchmark": {
            "benchmark_id": BENCHMARK_ID,
            "runner": "harness/tools/fixed_research_benchmark.py",
            "sandbox": "linux_user_and_network_namespace",
            "network": "disabled",
            "timeout_seconds": 60,
            "inputs": inputs,
            "success_criteria": {"integrity_rate": 1.0, "exit_code": 0, "claims_refuted": 0},
        },
        "approval_scope": {
            "capabilities": APPROVED_CAPABILITIES,
            "benchmark_id": BENCHMARK_ID,
            "input_sha256": sorted(str(item.get("sha256") or "") for item in inputs),
        },
        "limitations": [
            "The benchmark tests retained-artifact digest lineage and replays every "
            "published claim's grounding (verbatim quotes, lexical support, contradiction "
            "quotes) against retained source texts; it does not reproduce the claims' "
            "subject matter experimentally.",
        ],
    }
    return _write(context, primary_rel, payload, artifact_id="experiment-plan", schema=payload["schema"], limitations=payload["limitations"])


def _experiment_approval(
    context: OperatorContext,
    primary_rel: str,
    dependencies: list[dict[str, Any]],
    approval_controls: dict[str, Any],
) -> dict[str, Any]:
    plan_ref = _dependency(dependencies, "experiment_design")
    plan_path = context.workspace_root / str(plan_ref["path"])
    request_ref = approval_controls.get("request") if isinstance(approval_controls.get("request"), dict) else {}
    approval_ref = approval_controls.get("approval") if isinstance(approval_controls.get("approval"), dict) else {}
    request = context.load_json_artifact(request_ref)
    approval = context.load_json_artifact(approval_ref)
    request_path = validate_scoped_path(
        request_ref.get("path", ""),
        context.read_scope,
        workspace_root=context.workspace_root,
        must_exist=True,
    )
    current_request_sha256 = _sha(request_path)
    approval_mode = str(approval.get("approval_mode") or "interactive_exact_plan")
    policy_exact = True
    policy_ref = approval_controls.get("policy") if isinstance(approval_controls.get("policy"), dict) else {}
    policy_output: dict[str, Any] = {}
    if approval_mode == "policy_preauthorized":
        policy = context.load_json_artifact(policy_ref)
        policy_path = validate_scoped_path(
            policy_ref.get("path", ""),
            context.read_scope,
            workspace_root=context.workspace_root,
            must_exist=True,
        )
        benchmark_policy = policy.get("benchmark_policy") if isinstance(policy.get("benchmark_policy"), dict) else {}
        plan = context.load_json_artifact(plan_ref)
        benchmark = plan.get("benchmark") if isinstance(plan.get("benchmark"), dict) else {}
        plan_inputs = benchmark.get("inputs") if isinstance(benchmark.get("inputs"), list) else []
        approval_scope = plan.get("approval_scope") if isinstance(plan.get("approval_scope"), dict) else {}
        policy_exact = bool(
            policy.get("schema") == "solar.fixed_research.experiment_policy_authorization.v1"
            and policy.get("policy_id") == "evidence_lineage_integrity_v1"
            and policy.get("decision") == "preauthorized"
            and str(policy.get("sprint_id") or "") == str(context.node_request.get("run_id") or "")
            and policy.get("node_id") == "experiment_approval"
            and int(policy.get("generation") or 0) == int(approval.get("generation") or -1) == 1
            and str(policy.get("actor") or "") == str(approval.get("actor") or "")
            and str(policy.get("statement") or "") == str(approval.get("statement") or "")
            and _sha(policy_path) == str(policy_ref.get("sha256") or "")
            and approval.get("preauthorization") == {
                "policy_id": "evidence_lineage_integrity_v1",
                "path": str(policy_ref.get("path") or ""),
                "sha256": str(policy_ref.get("sha256") or ""),
            }
            and benchmark.get("benchmark_id") == benchmark_policy.get("benchmark_id") == BENCHMARK_ID
            and benchmark.get("runner") == benchmark_policy.get("runner") == "harness/tools/fixed_research_benchmark.py"
            and str(benchmark_policy.get("runner_sha256") or "") == _sha(BENCHMARK_SCRIPT)
            and benchmark.get("sandbox") == benchmark_policy.get("sandbox") == "linux_user_and_network_namespace"
            and benchmark.get("network") == "disabled"
            and benchmark_policy.get("network") == "none"
            and 0 < int(benchmark.get("timeout_seconds") or 0) <= int(benchmark_policy.get("timeout_max_seconds") or 0) <= 60
            and benchmark_policy.get("capabilities") == APPROVED_CAPABILITIES
            and approval_scope == {
                "capabilities": APPROVED_CAPABILITIES,
                "benchmark_id": BENCHMARK_ID,
                "input_sha256": sorted(str(item.get("sha256") or "") for item in plan_inputs if isinstance(item, dict)),
            }
        )
        policy_output = {
            "path": str(policy_ref.get("path") or ""),
            "sha256": str(policy_ref.get("sha256") or ""),
            "policy_id": "evidence_lineage_integrity_v1",
        }
    elif approval_mode != "interactive_exact_plan" or policy_ref:
        policy_exact = False
    exact = (
        request.get("schema") == "solar.fixed_research.approval_request.v1"
        and approval.get("schema") == "solar.fixed_research.human_approval.v1"
        and current_request_sha256 == str(request_ref.get("sha256") or "").lower()
        and current_request_sha256 == str(approval.get("approval_request_sha256") or "").lower()
        and str(request.get("plan_sha256") or "") == _sha(plan_path) == str(approval.get("plan_sha256") or "")
        and str(request.get("sprint_id") or "") == str(approval.get("sprint_id") or "") == str(context.node_request.get("run_id") or "")
        and str(request.get("node_id") or "") == str(approval.get("node_id") or "") == "experiment_approval"
        and int(request.get("generation") or 0) == int(approval.get("generation") or -1)
        and request.get("approved_scope") == approval.get("approved_scope")
        and request.get("approved_capabilities") == approval.get("approved_capabilities") == APPROVED_CAPABILITIES
        and str(approval.get("actor") or "").strip()
        and str(approval.get("statement") or "").strip()
        and str(approval.get("decision") or "") == "approved"
        and policy_exact
    )
    if not exact:
        raise ResearchOperatorError("Human approval does not match the exact plan, generation, scope, and capabilities.", error_type="approval_mismatch")
    payload = {
        "schema": "solar.fixed_research.experiment_approval.v1",
        "status": "approved",
        "experiment_id": BENCHMARK_ID,
        "plan": {"path": plan_ref["path"], "sha256": plan_ref["sha256"]},
        "approval_request": {"path": request_ref["path"], "sha256": current_request_sha256},
        "human_approval": {
            "path": approval_ref["path"],
            "sha256": approval_ref["sha256"],
            "actor": approval["actor"],
            "statement": approval["statement"],
            "generation": approval["generation"],
            "mode": approval_mode,
        },
        "approved_scope": approval["approved_scope"],
        "approved_capabilities": APPROVED_CAPABILITIES,
        "limitations": ["Approval authorizes only the exact no-network benchmark plan digest."],
    }
    if policy_output:
        payload["human_approval"]["preauthorization"] = policy_output
    return _write(context, primary_rel, payload, artifact_id="experiment-approval", schema=payload["schema"], limitations=payload["limitations"])


def _lifecycle_document(
    context: OperatorContext,
    *,
    schema: str,
    node_id: str,
    outputs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": schema,
        "task_id": str(context.node_request.get("task_id") or ""),
        "run_id": str(context.node_request.get("run_id") or ""),
        "sprint_id": str(context.node_request.get("run_id") or ""),
        "workflow_id": str(context.node_request.get("workflow_id") or ""),
        "node_id": node_id,
        "status": "completed",
        "outputs": outputs,
        "limitations": [],
    }


def _write_lifecycle_input(
    context: OperatorContext,
    directory: Path,
    name: str,
    document: dict[str, Any],
) -> dict[str, Any]:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(body)
    return {
        "artifact_id": Path(name).stem,
        "path": str(path.relative_to(context.workspace_root)).replace("\\", "/"),
        "schema": str(document.get("schema") or ""),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _run_autosci_experiment(
    context: OperatorContext,
    *,
    stage_dir: Path,
    stage_rel: str,
    executor: SandboxedBenchmarkExecutor,
    hypothesis: str,
) -> tuple[dict[str, Any], Path, list[dict[str, Any]]]:
    """Execute B5 through AutoSci's registered ScientificExperimentRunner.

    The contract's logical operator for this stage binds to
    `experiment_run_worker`, whose implementation is
    scientific_lifecycle.action.experiment.run_experiment. That operator
    demands a hash-bound approval for the exact lifecycle plan and a real
    `experiment_executor` service; both are supplied here, so the operator the
    DAG declares is the operator that executes. The executor runs the pinned
    benchmark under unshare -Urn -- execute, then convert; the result is never
    invented by an adapter.
    """
    from .scientific_lifecycle.action import registry as action_registry

    autosci_dir = stage_dir / "autosci"
    autosci_rel = stage_rel.rstrip("/") + "/autosci/"
    lifecycle_plan = {
        "experiment_id": BENCHMARK_ID,
        "objective": "Replay the accepted evidence lineage and the published claims' grounding from retained bytes.",
        "hypothesis": hypothesis,
        "variables": ["retained_artifact_bytes", "published_claim_grounding"],
        "metrics": ["integrity_rate", "claims_refuted"],
        "procedure": [
            "Re-hash every Part-A artifact in the accepted handoff against its controller-bound digest.",
            "Re-test every published claim's verbatim quotes, lexical support, and contradiction quotes against retained source texts.",
        ],
        "approval_required": True,
        "expected_artifacts": ["experiment_result.v1.json"],
        "success_criteria": ["integrity_rate is 1.0", "no published claim is refuted"],
        "safety_checks": ["no network access", "writes remain in declared scope"],
        "sandbox": {"mode": "isolated", "network": False, "write_scope": [autosci_rel]},
        "resource_limits": {"timeout_seconds": 60, "max_output_bytes": 1_000_000},
        "source_idea_id": BENCHMARK_ID,
        "origin_evidence_ids": [],
    }
    plan_sha = stable_json_sha256(lifecycle_plan)
    fixed_approval_ref = _dependency(list(context.node_request.get("input_artifact_refs") or []), "experiment_approval")
    approval_ref_token = f"{fixed_approval_ref['path']}#{fixed_approval_ref['sha256']}"
    lifecycle_approval = {
        "experiment_id": BENCHMARK_ID,
        "decision": "approved",
        "approval_ref": approval_ref_token,
        "plan_sha256": plan_sha,
        "approved_capabilities": sorted({"execute_experiment", "research_poc"}),
        "sandbox": dict(lifecycle_plan["sandbox"]),
        "reasons": [],
    }
    plan_doc_ref = _write_lifecycle_input(
        context,
        autosci_dir,
        "experiment_plan.v1.json",
        _lifecycle_document(context, schema="experiment_plan.v1", node_id="experiment_design", outputs={"experiment_plan": lifecycle_plan}),
    )
    approval_doc_ref = _write_lifecycle_input(
        context,
        autosci_dir,
        "experiment_approval.v1.json",
        _lifecycle_document(context, schema="experiment_approval.v1", node_id="experiment_approval_gate", outputs={"approval": lifecycle_approval}),
    )
    sub_request = {
        "schema": "research_node_request.v1",
        "task_id": str(context.node_request.get("task_id") or ""),
        "run_id": str(context.node_request.get("run_id") or ""),
        "workflow_id": str(context.node_request.get("workflow_id") or ""),
        "node_id": "experiment_run",
        "logical_operator": {
            "operator_id": "ScientificExperimentRunner",
            "operator_kind": "logical",
            "capabilities": ["research_poc", "execute_experiment"],
        },
        "physical_operator": {
            "operator_id": "experiment_run_worker",
            "operator_kind": "physical",
            "capabilities": ["research_poc", "execute_experiment"],
        },
        "typed_inputs": {"input_schema": "experiment_run.fixed_research.v1", "payload": {}},
        "input_artifact_refs": [plan_doc_ref, approval_doc_ref],
        "authorization": {
            "scope_id": f"{context.node_request.get('run_id')}:experiment_run:autosci",
            "approved_capabilities": ["research_poc", "execute_experiment"],
            "approval_ref": approval_ref_token,
            "allow_network": False,
            "allow_live_provider": False,
            "secret_refs": [],
        },
        "read_scope": [plan_doc_ref["path"], approval_doc_ref["path"]],
        "write_scope": [autosci_rel],
        "timeout_retry_policy": {"timeout_seconds": 90, "max_attempts": 1, "retry_on": []},
    }
    sub_result = action_registry.execute_operator(
        sub_request,
        services={"experiment_executor": executor},
        workspace_root=context.workspace_root,
    )
    if str(sub_result.get("status") or "") != "completed":
        errors = sub_result.get("errors") or []
        message = str((errors[0] or {}).get("message") or "") if errors else ""
        raise ResearchOperatorError(
            f"AutoSci experiment run did not complete: {message}"[:300],
            error_type="experiment_failed",
        )
    result_path = autosci_dir / "experiment_result.v1.json"
    if not result_path.is_file():
        raise ResearchOperatorError("AutoSci experiment run wrote no result document.", error_type="experiment_failed")
    document = json.loads(result_path.read_text(encoding="utf-8"))
    lifecycle_result = (document.get("outputs") or {}).get("result") or {}
    if str(lifecycle_result.get("plan_sha256") or "") != plan_sha:
        raise ResearchOperatorError("AutoSci experiment result is not bound to the executed plan.", error_type="approval_mismatch")
    doc_refs = [plan_doc_ref, approval_doc_ref]
    return {"result": lifecycle_result, "document": document, "limitations": [str(item) for item in document.get("limitations") or []]}, result_path, doc_refs


def _experiment_run(
    context: OperatorContext,
    primary_rel: str,
    stage_dir: Path,
    dependencies: list[dict[str, Any]],
) -> dict[str, Any]:
    handoff_ref = _dependency(dependencies, "poc_handoff")
    plan_ref = _dependency(dependencies, "experiment_design")
    approval_ref = _dependency(dependencies, "experiment_approval")
    plan = _load(context, plan_ref)
    approval = _load(context, approval_ref)
    plan_path = context.workspace_root / str(plan_ref["path"])
    if (
        str(approval.get("status") or "") != "approved"
        or str((approval.get("plan") or {}).get("sha256") or "") != _sha(plan_path)
        or (plan.get("benchmark") or {}).get("runner") != "harness/tools/fixed_research_benchmark.py"
        or (plan.get("benchmark") or {}).get("sandbox") != "linux_user_and_network_namespace"
        or (plan.get("benchmark") or {}).get("network") != "disabled"
    ):
        raise ResearchOperatorError("Experiment plan/approval is not the fixed allowlisted benchmark.", error_type="approval_mismatch")
    raw_path = stage_dir / "benchmark_raw.json"
    stdout_path = stage_dir / "stdout.txt"
    stderr_path = stage_dir / "stderr.json"
    handoff_path = context.workspace_root / str(handoff_ref["path"])
    stage_rel = str(stage_dir.relative_to(context.workspace_root)).replace("\\", "/") + "/"
    executor = SandboxedBenchmarkExecutor(
        work_dir=context.workspace_root,
        runner=BENCHMARK_SCRIPT,
        runner_sha256=_sha(BENCHMARK_SCRIPT),
        handoff_path=handoff_path,
        plan_path=plan_path,
        raw_output_path=raw_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        sandbox_home=stage_dir / "sandbox-home",
        environment_path=os.environ.get("PATH", "/usr/bin:/bin"),
    )
    autosci, autosci_result_path, autosci_doc_refs = _run_autosci_experiment(
        context,
        stage_dir=stage_dir,
        stage_rel=stage_rel,
        executor=executor,
        hypothesis=(
            "Every artifact accepted into the Part-A handoff still matches its "
            "controller-bound SHA-256 digest, and every published claim's grounding "
            "replays from the retained source texts."
        ),
    )
    lifecycle_result = autosci["result"]
    execution = dict(executor.last_execution)
    if not raw_path.is_file():
        raise ResearchOperatorError("Benchmark did not produce raw evidence.", error_type="experiment_failed")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    outcome = str(lifecycle_result.get("outcome") or "")
    passed = (
        int(execution.get("exit_code", 1)) == 0
        and raw.get("passed") is True
        and outcome == "supports"
    )
    payload = {
        "schema": "solar.fixed_research.experiment_result.v1",
        "status": "completed" if passed else "failed",
        "experiment_id": BENCHMARK_ID,
        "plan": {"path": plan_ref["path"], "sha256": plan_ref["sha256"]},
        "approval": {"path": approval_ref["path"], "sha256": approval_ref["sha256"]},
        "sandbox": {"kind": "linux_user_and_network_namespace", "network": "disabled", "command_allowlisted": True},
        "execution": {
            "command": list(execution.get("command") or []),
            "exit_code": int(execution.get("exit_code", 1)),
            "duration_ms": float(execution.get("duration_ms") or 0.0),
            "stdout_path": str(stdout_path.relative_to(context.workspace_root)).replace("\\", "/"),
            "stderr_path": str(stderr_path.relative_to(context.workspace_root)).replace("\\", "/"),
            "raw_result_path": str(raw_path.relative_to(context.workspace_root)).replace("\\", "/"),
        },
        "metrics": raw.get("metrics") or {},
        "raw_result_sha256": _sha(raw_path),
        # The registered AutoSci runner's own verdict, bound by plan digest and
        # approval reference. The outer status above must agree with it.
        "autosci_experiment": {
            "operator": "experiment_run_worker",
            "implementation": "scientific_lifecycle.action.experiment.run_experiment",
            "result_path": str(autosci_result_path.relative_to(context.workspace_root)).replace("\\", "/"),
            "result_sha256": _sha(autosci_result_path),
            "outcome": outcome,
            "criteria_results": dict(lifecycle_result.get("criteria_results") or {}),
            "evidence_ids": [str(item) for item in lifecycle_result.get("evidence_ids") or []],
            "plan_sha256": str(lifecycle_result.get("plan_sha256") or ""),
            "approval_ref": str(lifecycle_result.get("approval_ref") or ""),
        },
        "tested": str(raw.get("tested") or ""),
        "not_tested": str(raw.get("not_tested") or ""),
        "limitations": [
            f"Tested: {raw.get('tested') or 'retained-artifact digest lineage'}.",
            f"Not tested: {raw.get('not_tested') or 'external scientific validity of the sources or experimental reproduction of the claims'}.",
        ],
    }
    extra_artifacts: list[dict[str, Any]] = []
    extra_hashes: list[dict[str, Any]] = []
    for path, artifact_id, schema in (
        (raw_path, "benchmark-raw", "solar.fixed_research.benchmark_raw.v1"),
        (stdout_path, "benchmark-stdout", "text/plain"),
        (stderr_path, "benchmark-stderr", "solar.fixed_research.command_stream.v1"),
        (autosci_result_path, "autosci-experiment-result", "experiment_result.v1"),
    ):
        artifact, digest = _file_artifact(path, context, artifact_id, schema)
        extra_artifacts.append(artifact)
        extra_hashes.append(digest)
    for reference in autosci_doc_refs:
        extra_artifacts.append(dict(reference))
        extra_hashes.append({"hash_id": str(reference["artifact_id"]), "algorithm": "sha256", "value": str(reference["sha256"])})
    result = _write(
        context,
        primary_rel,
        payload,
        artifact_id="experiment-result",
        schema=payload["schema"],
        extra_artifacts=extra_artifacts,
        extra_hashes=extra_hashes,
        limitations=payload["limitations"],
    )
    if not passed:
        result["status"] = "failed"
        result["status_is_terminal"] = True
        result["errors"] = [{
            "error_id": "experiment.failed",
            "error_type": "experiment_failed",
            "message": f"The fixed benchmark did not pass (autosci outcome: {outcome or 'missing'}).",
        }]
    return result


def _verified_controller_artifact(
    context: OperatorContext,
    row: dict[str, Any],
    *,
    artifact_id: str,
    schema: str,
) -> Path:
    path = validate_scoped_path(
        row.get("path", ""),
        context.read_scope,
        workspace_root=context.workspace_root,
        must_exist=True,
    )
    digest = _sha(path)
    closeout = row.get("controller_closeout") if isinstance(row.get("controller_closeout"), dict) else {}
    binding = closeout.get("artifact_binding") if isinstance(closeout.get("artifact_binding"), dict) else {}
    manifest = binding.get("manifest") if isinstance(binding.get("manifest"), dict) else {}
    snapshot = binding.get("eval_snapshot") if isinstance(binding.get("eval_snapshot"), dict) else {}
    exact = (
        str(row.get("artifact_id") or "") == artifact_id
        and str(row.get("schema") or "") == schema
        and digest == str(row.get("sha256") or "").lower()
        and str(binding.get("artifact_id") or "") == artifact_id
        and str(binding.get("path") or "") == str(row.get("path") or "")
        and str(binding.get("schema") or "") == schema
        and str(binding.get("sha256") or "").lower() == digest
        and str(manifest.get("sha256") or "").lower() == digest
        and str(snapshot.get("sha256") or "").lower() == digest
        and str(closeout.get("eval_record_id") or "")
        and str(closeout.get("artifact_snapshot_digest") or "")
        and str(closeout.get("manifest_content_digest") or "")
        and str(closeout.get("gate_ledger_projected_status") or "") == "passed"
    )
    if not exact:
        raise ResearchOperatorError(
            f"Dependency is not bound to its controller-accepted manifest and evaluator snapshot: {artifact_id}",
            error_type="lineage_incomplete",
        )
    return path


def _run_autosci_claim_verifier(
    context: OperatorContext,
    *,
    stage_dir: Path,
    stage_rel: str,
    claim_checks: list[dict[str, Any]],
    raw_metrics: dict[str, Any],
    autosci_record: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Run ScientificClaimVerifier's implementation over the replicated claims.

    The contract declares ScientificClaimVerifier for B6; its registered
    implementation is scientific_lifecycle.action.delivery.verify_claim. The
    claims come from the raw benchmark's per-claim replication rows and the
    experiment evidence from the fixed result's AutoSci record, both of which
    B6 already holds as controller-accepted dependencies -- nothing outside
    B6's read scope is touched.
    """
    from .scientific_lifecycle.action import registry as action_registry

    autosci_dir = stage_dir / "autosci"
    autosci_rel = stage_rel.rstrip("/") + "/autosci/"
    claims_doc = _lifecycle_document(
        context,
        schema="research_claims.v1",
        node_id="claim_extract",
        outputs={
            "claims": [
                {
                    "claim_id": str(item.get("claim_id") or ""),
                    "text": str(item.get("text") or ""),
                    "acceptance_criteria": [f"{item.get('claim_id')}:grounding_replicated"],
                    "evidence_ids": ["benchmark-raw"],
                }
                for item in claim_checks
                if str(item.get("claim_id") or "")
            ]
        },
    )
    result_doc = _lifecycle_document(
        context,
        schema="experiment_result.v1",
        node_id="experiment_run",
        outputs={
            "result": {
                "experiment_id": BENCHMARK_ID,
                "outcome": str(autosci_record.get("outcome") or ""),
                "metrics": [
                    {"name": str(key), "value": raw_metrics.get(key)} for key in sorted(raw_metrics)
                ],
                "evidence_ids": [str(item) for item in autosci_record.get("evidence_ids") or []] or ["benchmark-raw"],
                "criteria_results": {
                    str(key): value
                    for key, value in (autosci_record.get("criteria_results") or {}).items()
                    if isinstance(value, bool)
                },
                "approval_ref": str(autosci_record.get("approval_ref") or ""),
                "plan_sha256": str(autosci_record.get("plan_sha256") or ""),
                "sandbox_enforced": True,
            }
        },
    )
    claims_ref = _write_lifecycle_input(context, autosci_dir, "research_claims.v1.json", claims_doc)
    result_ref = _write_lifecycle_input(context, autosci_dir, "experiment_result.v1.json", result_doc)
    sub_request = {
        "schema": "research_node_request.v1",
        "task_id": str(context.node_request.get("task_id") or ""),
        "run_id": str(context.node_request.get("run_id") or ""),
        "workflow_id": str(context.node_request.get("workflow_id") or ""),
        "node_id": "claim_verify",
        "logical_operator": {
            "operator_id": "ScientificClaimVerifier",
            "operator_kind": "logical",
            "capabilities": ["research_poc"],
        },
        "physical_operator": {
            "operator_id": "claim_verify_worker",
            "operator_kind": "physical",
            "capabilities": ["research_poc"],
        },
        "typed_inputs": {"input_schema": "claim_verify.fixed_research.v1", "payload": {}},
        "input_artifact_refs": [claims_ref, result_ref],
        "authorization": {
            "scope_id": f"{context.node_request.get('run_id')}:claim_verification:autosci",
            "approved_capabilities": ["research_poc"],
            "allow_network": False,
            "allow_live_provider": False,
            "secret_refs": [],
        },
        "read_scope": [claims_ref["path"], result_ref["path"]],
        "write_scope": [autosci_rel],
        "timeout_retry_policy": {"timeout_seconds": 60, "max_attempts": 1, "retry_on": []},
    }
    sub_result = action_registry.execute_operator(sub_request, services={}, workspace_root=context.workspace_root)
    if str(sub_result.get("status") or "") != "completed":
        errors = sub_result.get("errors") or []
        message = str((errors[0] or {}).get("message") or "") if errors else ""
        raise ResearchOperatorError(
            f"ScientificClaimVerifier did not complete: {message}"[:300],
            error_type="claim_not_verified",
        )
    verdict_path = autosci_dir / "claim_verdict.v1.json"
    if not verdict_path.is_file():
        raise ResearchOperatorError("ScientificClaimVerifier wrote no verdict document.", error_type="claim_not_verified")
    verdict_doc = json.loads(verdict_path.read_text(encoding="utf-8"))
    verdicts = [
        item for item in ((verdict_doc.get("outputs") or {}).get("verdicts") or [])
        if isinstance(item, dict)
    ]
    artifacts: list[dict[str, Any]] = []
    hashes: list[dict[str, Any]] = []
    for reference in (claims_ref, result_ref):
        artifacts.append(dict(reference))
        hashes.append({"hash_id": str(reference["artifact_id"]), "algorithm": "sha256", "value": str(reference["sha256"])})
    verdict_artifact, verdict_hash = _file_artifact(verdict_path, context, "claim-verdict-autosci", "claim_verdict.v1")
    artifacts.append(verdict_artifact)
    hashes.append(verdict_hash)
    return verdicts, artifacts, hashes


def _claim_verification(context: OperatorContext, primary_rel: str, dependencies: list[dict[str, Any]]) -> dict[str, Any]:
    plan_ref = _dependency(dependencies, "experiment_design")
    result_ref = _dependency(dependencies, "experiment_run")
    raw_ref = _dependency(dependencies, "experiment_run:benchmark_raw.json")
    stdout_ref = _dependency(dependencies, "experiment_run:stdout.txt")
    stderr_ref = _dependency(dependencies, "experiment_run:stderr.json")
    plan = _load(context, plan_ref)
    result_path = _verified_controller_artifact(
        context,
        result_ref,
        artifact_id="experiment_run",
        schema="solar.fixed_research.experiment_result.v1",
    )
    raw_path = _verified_controller_artifact(
        context,
        raw_ref,
        artifact_id="experiment_run:benchmark_raw.json",
        schema="solar.fixed_research.benchmark_raw.v1",
    )
    stdout_path = _verified_controller_artifact(
        context,
        stdout_ref,
        artifact_id="experiment_run:stdout.txt",
        schema="text/plain",
    )
    stderr_path = _verified_controller_artifact(
        context,
        stderr_ref,
        artifact_id="experiment_run:stderr.json",
        schema="solar.fixed_research.command_stream.v1",
    )
    result = _load(context, result_ref)
    raw = _load(context, raw_ref)
    stderr = _load(context, stderr_ref)
    stdout_path.read_bytes()
    criteria = (plan.get("benchmark") or {}).get("success_criteria") or {}
    metrics = result.get("metrics") or {}
    actual_exit_code = (result.get("execution") or {}).get("exit_code")
    expected_exit_code = criteria.get("exit_code")
    execution = result.get("execution") if isinstance(result.get("execution"), dict) else {}
    autosci_record = result.get("autosci_experiment") if isinstance(result.get("autosci_experiment"), dict) else {}
    claim_checks = [item for item in raw.get("claim_checks") or [] if isinstance(item, dict)]
    verified = (
        str(result.get("status") or "") == "completed"
        and raw.get("passed") is True
        and str(result.get("raw_result_sha256") or "") == str(raw_ref.get("sha256") or "")
        and str(execution.get("raw_result_path") or "") == str(raw_ref.get("path") or "")
        and str(execution.get("stdout_path") or "") == str(stdout_ref.get("path") or "")
        and str(execution.get("stderr_path") or "") == str(stderr_ref.get("path") or "")
        and stderr.get("schema") == "solar.fixed_research.command_stream.v1"
        and stderr.get("stream") == "stderr"
        and int(stderr.get("bytes") or 0) == len(str(stderr.get("content") or "").encode("utf-8"))
        and result.get("metrics") == raw.get("metrics")
        and isinstance(actual_exit_code, int)
        and actual_exit_code == int(expected_exit_code if expected_exit_code is not None else 0)
        and float(metrics.get("integrity_rate") or 0.0) >= float(criteria.get("integrity_rate") or 1.0)
        # The claim-replication half of the benchmark: at least one published
        # claim was actually tested and none was refuted, reconciled against
        # the raw per-claim rows rather than trusted from the summary.
        and int(metrics.get("claims_total") or 0) >= 1
        and int(metrics.get("claims_refuted") or 0) <= int(criteria.get("claims_refuted") or 0)
        and int(metrics.get("claims_total") or 0) == len(claim_checks)
        and int(metrics.get("claims_refuted") or 0)
        == sum(1 for item in claim_checks if str(item.get("outcome") or "") != "supported")
        # The registered AutoSci runner's verdict must agree with the raw
        # evidence -- a "supports" outcome over failed checks, or vice versa,
        # is a seam and must not verify.
        and str(autosci_record.get("outcome") or "") == "supports"
    )
    if not verified:
        raise ResearchOperatorError("Raw experiment evidence does not satisfy the fixed plan.", error_type="claim_not_verified")
    stage_dir = (context.workspace_root / primary_rel).parent
    stage_rel = str(stage_dir.relative_to(context.workspace_root)).replace("\\", "/") + "/"
    claim_verdicts, verdict_artifacts, verdict_hashes = _run_autosci_claim_verifier(
        context,
        stage_dir=stage_dir,
        stage_rel=stage_rel,
        claim_checks=claim_checks,
        raw_metrics=metrics,
        autosci_record=autosci_record,
    )
    unsupported_verdicts = [
        item for item in claim_verdicts if str(item.get("verdict") or "") != "supported"
    ]
    if unsupported_verdicts:
        raise ResearchOperatorError(
            "ScientificClaimVerifier did not support every replicated claim: "
            + ", ".join(sorted(str(item.get("claim_id") or "?") for item in unsupported_verdicts)),
            error_type="claim_not_verified",
        )
    evidence_refs = []
    for item in (result_ref, raw_ref, stdout_ref, stderr_ref):
        closeout = item.get("controller_closeout") if isinstance(item.get("controller_closeout"), dict) else {}
        evidence_refs.append(
            {
                "artifact_id": str(item["artifact_id"]),
                "path": str(item["path"]),
                "schema": str(item["schema"]),
                "sha256": str(item["sha256"]),
                "controller": {
                    "eval_record_id": str(closeout.get("eval_record_id") or ""),
                    "artifact_snapshot_digest": str(closeout.get("artifact_snapshot_digest") or ""),
                    "manifest_content_digest": str(closeout.get("manifest_content_digest") or ""),
                },
            }
        )
    payload = {
        "schema": "solar.fixed_research.claim_verification.v1",
        "status": "verified",
        "claim": (
            "Every retained Part-A artifact in the accepted handoff matched its "
            "controller-bound SHA-256 digest during replay, and every published "
            "claim's grounding replayed from the retained source texts."
        ),
        "plan": {"path": plan_ref["path"], "sha256": plan_ref["sha256"]},
        "experiment_result": {
            "path": result_ref["path"],
            "sha256": result_ref["sha256"],
            "raw_result_path": raw_ref["path"],
            "raw_result_sha256": result["raw_result_sha256"],
        },
        "experiment_evidence": evidence_refs,
        "metrics": metrics,
        # Per-claim verdicts from ScientificClaimVerifier's registered
        # implementation, reconciled above against the raw replication rows.
        "claim_verdicts": [
            {
                "claim_id": str(item.get("claim_id") or ""),
                "verdict": str(item.get("verdict") or ""),
                "support_classification": str(item.get("support_classification") or ""),
                "basis": str(item.get("basis") or ""),
                "acceptance_criteria_checked": [str(value) for value in item.get("acceptance_criteria_checked") or []],
            }
            for item in claim_verdicts
        ],
        "limitations": [
            "Verified: retained-artifact digest lineage and per-claim grounding "
            "replication from retained source texts, with ScientificClaimVerifier "
            "verdicts per claim.",
            "Not verified: the external scientific validity of the sources' own "
            "findings; no experiment reproduced the claims' subject matter.",
        ],
    }
    return _write(
        context,
        primary_rel,
        payload,
        artifact_id="claim-verification",
        schema=payload["schema"],
        extra_artifacts=verdict_artifacts,
        extra_hashes=verdict_hashes,
        limitations=payload["limitations"],
    )


def _delivery_lineage(
    context: OperatorContext,
    dependencies: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    required = ["final_acceptance", "report_revision", "poc_handoff", "experiment_run", "claim_verification"]
    refs = {node_id: _dependency(dependencies, node_id) for node_id in required}
    payloads: dict[str, dict[str, Any]] = {}
    bundle: list[dict[str, Any]] = []
    limitation_index: dict[str, list[dict[str, str]]] = {}
    for node_id in required:
        ref = refs[node_id]
        _verified_controller_artifact(
            context,
            ref,
            artifact_id=node_id,
            schema=str(ref.get("schema") or ""),
        )
        payload = _load(context, ref)
        payloads[node_id] = payload
        closeout = ref.get("controller_closeout") if isinstance(ref.get("controller_closeout"), dict) else {}
        source = {
            "artifact_id": node_id,
            "path": str(ref["path"]),
            "schema": str(ref["schema"]),
            "sha256": str(ref["sha256"]),
        }
        bundle.append(
            {
                **source,
                "controller": {
                    "eval_record_id": str(closeout.get("eval_record_id") or ""),
                    "artifact_snapshot_digest": str(closeout.get("artifact_snapshot_digest") or ""),
                    "manifest_content_digest": str(closeout.get("manifest_content_digest") or ""),
                },
            }
        )
        for value in payload.get("limitations") or []:
            limitation = str(value).strip()
            if limitation and source not in limitation_index.setdefault(limitation, []):
                limitation_index[limitation].append(source)
    limitations = list(limitation_index)
    if not limitations:
        raise ResearchOperatorError(
            "Final delivery has no accepted upstream limitations to preserve.",
            error_type="lineage_incomplete",
        )
    limitation_sources = [
        {"limitation": limitation, "sources": sources}
        for limitation, sources in limitation_index.items()
    ]
    return payloads, bundle, limitations, limitation_sources


def _render_final_delivery_markdown(
    bundle: list[dict[str, Any]],
    limitations: list[str],
) -> str:
    return (
        "# Research evidence-to-PoC delivery\n\n"
        "## Outcome\n\nThe Part-A report was accepted; its retained artifact lineage and each published claim's grounding passed the fixed no-network benchmark.\n\n"
        "## Boundary\n\nThis PoC validates evidence retention, hash lineage, and grounding replication from retained bytes. It does not independently reproduce or validate the report's external scientific claims.\n\n"
        "## Included evidence\n\n"
        + "\n".join(f"- `{item['artifact_id']}` — `{item['path']}` — `{item['sha256']}`" for item in bundle)
        + "\n\n## Limitations\n\n"
        + "\n".join(f"- {item}" for item in limitations)
        + "\n"
    )


def _final_delivery(
    context: OperatorContext,
    primary_rel: str,
    stage_dir: Path,
    dependencies: list[dict[str, Any]],
) -> dict[str, Any]:
    payloads, bundle, limitations, limitation_sources = _delivery_lineage(context, dependencies)
    verdict = payloads["claim_verification"]
    if str(verdict.get("status") or "") != "verified":
        raise ResearchOperatorError("Final delivery requires a verified PoC claim.", error_type="claim_not_verified")
    markdown_path = stage_dir / "final_delivery.md"
    markdown = _render_final_delivery_markdown(bundle, limitations)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    md_artifact, md_hash = _file_artifact(markdown_path, context, "final-delivery-markdown", "text/markdown")
    payload = {
        "schema": "solar.fixed_research.final_delivery.v1",
        "status": "completed",
        "bundle": bundle,
        "markdown": {"path": md_artifact["path"], "sha256": md_artifact["sha256"]},
        "claim_verdict": "verified",
        "limitations": limitations,
        "limitation_sources": limitation_sources,
    }
    return _write(
        context,
        primary_rel,
        payload,
        artifact_id="final-delivery",
        schema=payload["schema"],
        extra_artifacts=[md_artifact],
        extra_hashes=[md_hash],
        limitations=payload["limitations"],
    )


def verify_final_delivery_artifact(
    *,
    request: dict[str, Any],
    work_dir: Path,
    primary: Path,
    markdown_path: Path,
    dependencies: list[dict[str, Any]],
) -> None:
    context = OperatorContext.from_request(request, workspace_root=work_dir)
    payload = json.loads(primary.read_text(encoding="utf-8"))
    _payloads, bundle, limitations, limitation_sources = _delivery_lineage(context, dependencies)
    expected_markdown = _render_final_delivery_markdown(bundle, limitations)
    exact = (
        payload.get("bundle") == bundle
        and payload.get("limitations") == limitations
        and payload.get("limitation_sources") == limitation_sources
        and markdown_path.is_file()
        and markdown_path.read_text(encoding="utf-8") == expected_markdown
        and str((payload.get("markdown") or {}).get("sha256") or "") == _sha(markdown_path)
    )
    if not exact:
        raise ResearchOperatorError(
            "Final delivery does not preserve the exact accepted upstream bundle and limitations.",
            error_type="lineage_incomplete",
        )


def execute_operator(
    node_request: dict[str, Any],
    *,
    services: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Resolver-facing entry: run one fixed Part-B node from its request.

    This is what the `<node_id>_operator` bindings in the unified registry
    call, so the physical operator id the fixed contract's graph declares is
    the physical operator that executes -- previously the adapter bypassed the
    resolver for every Part-B stage and the declared identity never ran.

    The adapter's controller-verified dependency references (with their
    closeout bindings) and approval controls travel inside
    typed_inputs.payload.fixed_research, because they carry more than the
    4-key input_artifact_refs the request schema standardizes.
    """
    del services  # Part-B handlers execute deterministically or via sub-operators.
    root = Path(workspace_root or Path.cwd()).resolve()
    node_id = str(node_request.get("node_id") or "")
    typed_inputs = node_request.get("typed_inputs") if isinstance(node_request.get("typed_inputs"), dict) else {}
    payload = typed_inputs.get("payload") if isinstance(typed_inputs.get("payload"), dict) else {}
    fixed = payload.get("fixed_research") if isinstance(payload.get("fixed_research"), dict) else {}
    primary_rel = str(fixed.get("primary_rel") or "")
    if not primary_rel:
        raise ResearchOperatorError(
            f"fixed Part-B request is missing its primary output binding: {node_id}",
            error_type="invalid_input",
        )
    stage_dir = (root / primary_rel).parent
    dependencies = [item for item in fixed.get("dependencies") or [] if isinstance(item, dict)]
    approval_controls = fixed.get("approval_controls") if isinstance(fixed.get("approval_controls"), dict) else {}
    return execute_part_b(
        request=node_request,
        node_id=node_id,
        primary_rel=primary_rel,
        stage_dir=stage_dir,
        work_dir=root,
        dependencies=dependencies,
        approval_controls=approval_controls,
    )


def execute_part_b(
    *,
    request: dict[str, Any],
    node_id: str,
    primary_rel: str,
    stage_dir: Path,
    work_dir: Path,
    dependencies: list[dict[str, Any]],
    approval_controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = OperatorContext.from_request(request, workspace_root=work_dir)
    handlers = {
        "poc_handoff": lambda: _poc_handoff(context, primary_rel, dependencies),
        "idea_evaluation": lambda: _idea_evaluation(context, primary_rel, dependencies),
        "experiment_design": lambda: _experiment_design(context, primary_rel, dependencies),
        "experiment_approval": lambda: _experiment_approval(context, primary_rel, dependencies, approval_controls or {}),
        "experiment_run": lambda: _experiment_run(context, primary_rel, stage_dir, dependencies),
        "claim_verification": lambda: _claim_verification(context, primary_rel, dependencies),
        "final_delivery": lambda: _final_delivery(context, primary_rel, stage_dir, dependencies),
    }
    try:
        return handlers[node_id]()
    except KeyError as exc:
        raise ResearchOperatorError(f"Unsupported fixed Part-B node: {node_id}", error_type="wrong_node_identity") from exc
