from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import jsonschema

from evidence import JourneyRecorder
from journey_runner import (
    action_evidence,
    bootstrap_live_environment,
    run_autosci,
    runtime_evidence,
    write_code_evidence,
    write_demo_paper,
    write_experiment_assets,
    write_json,
    write_research_claims,
)


def _load_json(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _ensure_fixture_source(target: Path, source: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return target
    return write_demo_paper(target)


def _write_review_proof(path: Path, artifact: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    source = path.with_suffix(".source.txt")
    claim = "The local report packet is persisted for deterministic evidence review."
    source.write_text(claim + "\n", encoding="utf-8")
    payload = {
        "schema": "scientific_review_proof.v1",
        "writer": {"provider": "local_fixture", "model": "phase22-journey"},
        "artifact": {"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()},
        "claims": [{
            "claim_id": "claim.j09.persisted-report",
            "claim": claim,
            "source": {"source_id": "j09-local-report-source", "path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
            "evidence_span": {"start": 0, "end": len(claim), "text": claim},
            "acceptance_criterion": "The reviewer must reload the persisted report, source, hashes, and exact span.",
            "residual_risk": "This is local journey evidence and does not establish external scientific validity.",
        }],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _walk_strings(value: object) -> list[str]:
    if isinstance(value, dict):
        items: list[str] = []
        for inner in value.values():
            items.extend(_walk_strings(inner))
        return items
    if isinstance(value, list):
        items = []
        for inner in value:
            items.extend(_walk_strings(inner))
        return items
    if isinstance(value, str):
        return [value]
    return []


def _resolve_report_path(raw: str, harness_dir: Path) -> Path | None:
    if not raw.lower().endswith(".md"):
        return None
    candidate = Path(raw)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    for base in (harness_dir, harness_dir / "artifacts" / "autosci"):
        resolved = base / raw
        if resolved.exists():
            return resolved
    return None


def _find_markdown_report(payload: dict, harness_dir: Path) -> Path | None:
    artifacts = payload.get("artifacts", []) if isinstance(payload, dict) else []
    for artifact in artifacts:
        if isinstance(artifact, dict):
            path = _resolve_report_path(str(artifact.get("path") or ""), harness_dir)
            if path is not None:
                return path
    for raw in _walk_strings(payload):
        path = _resolve_report_path(raw, harness_dir)
        if path is not None:
            return path
    return None


def _is_stable_evidence_id(value: object) -> bool:
    text = str(value).strip()
    if not text or any(separator in text for separator in ("\\", "/")) or any(char.isspace() for char in text):
        return False
    return text.startswith(("claim-", "claim:", "code:", "exp-", "local:", "paper-", "phase22-", "runtime:", "task-", "wiki:"))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "0" * 64


def _decision_request(verdict_path: Path, experiment_path: Path) -> dict:
    return {
        "schema": "decision_request.v1",
        "decision_id": "phase22-j09-bounded-rollout",
        "title": "Choose the evidence-supported SkillGen rollout scope",
        "problem": "Choose between a bounded local continuation and an unsupported generalized rollout.",
        "alternatives": [
            {
                "alternative_id": "bounded-local",
                "title": "Continue with a bounded local validation",
                "description": "Retain the measured scope and collect independent external-validity evidence.",
            },
            {
                "alternative_id": "generalized-rollout",
                "title": "Generalize the result immediately",
                "description": "Treat the local result as sufficient for a broad rollout.",
            },
        ],
        "criteria": [
            {"criterion_id": "measured-support", "name": "Measured evidence support", "weight": 0.6},
            {"criterion_id": "external-validity", "name": "External-validity risk", "weight": 0.4},
        ],
        "evidence": [
            {
                "evidence_id": "j09-claim-verdict",
                "evidence_type": "claim_verdict",
                "claim_id": "claim-supported",
                "supporting_experiment_evidence_id": "j09-experiment-result",
                "source_path": str(verdict_path),
                "expected_sha256": _file_sha256(verdict_path),
                "summary": "The persisted claim verdict supports the bounded local claim.",
            },
            {
                "evidence_id": "j09-experiment-result",
                "evidence_type": "experiment_result",
                "source_path": str(experiment_path),
                "expected_sha256": _file_sha256(experiment_path),
                "summary": "The approved local experiment completed and produced persisted result evidence.",
            },
        ],
        "assessments": [
            {
                "alternative_id": "bounded-local",
                "criterion_id": "measured-support",
                "score": 5,
                "rationale": "This option stays within the supported claim and completed experiment.",
                "evidence_ids": ["j09-claim-verdict", "j09-experiment-result"],
            },
            {
                "alternative_id": "bounded-local",
                "criterion_id": "external-validity",
                "score": 3,
                "rationale": "The option explicitly keeps external validity unresolved.",
                "evidence_ids": ["j09-claim-verdict"],
            },
            {
                "alternative_id": "generalized-rollout",
                "criterion_id": "measured-support",
                "score": 0,
                "rationale": "Neither evidence source supports generalization beyond the local dataset.",
                "evidence_ids": ["j09-claim-verdict", "j09-experiment-result"],
            },
            {
                "alternative_id": "generalized-rollout",
                "criterion_id": "external-validity",
                "score": 0,
                "rationale": "The local result provides no independent external-validity evidence for a broad rollout.",
                "evidence_ids": ["j09-claim-verdict", "j09-experiment-result"],
            },
        ],
        "risks": [
            {
                "risk_id": "external-validity",
                "description": "A local result could be overstated as a general result.",
                "mitigation": "Keep the recommendation bounded and require independent review before rollout.",
                "evidence_ids": ["j09-claim-verdict", "j09-experiment-result"],
            }
        ],
        "recommendation": {
            "alternative_id": "bounded-local",
            "rationale": "Only the bounded continuation is explicitly supported by the measured result and claim verdict.",
            "criterion_ids": ["measured-support", "external-validity"],
            "evidence_ids": ["j09-claim-verdict", "j09-experiment-result"],
        },
        "limitations": [
            "The evidence comes from one deterministic local experiment and does not establish external validity."
        ],
        "unresolved_review_items": [
            "An independent reviewer must assess external validity and the proposed rollout boundary."
        ],
    }


def test_p22_j09_report_delivery(repo_root: Path, tmp_path: Path, phase22_python: str) -> None:
    rec = JourneyRecorder(repo_root, "P22-J09")
    sandbox = tmp_path / "p22-j09"
    paper_fixture = (
        repo_root / "tests" / "journeys" / "phase22" / "fixtures" / "j09" / "phase22-paper.md"
    )
    paper = _ensure_fixture_source(sandbox / "raw" / "phase22-paper.md", paper_fixture)
    ingest, _ = run_autosci(rec, sandbox, "ingest", ["--paper", str(paper), "--run-id", "p22-j09-ingest"], timeout=90)

    assets = write_experiment_assets(sandbox / "experiment", phase22_python)
    exp_proc = rec.run(
        "local-python-experiment",
        [phase22_python, str(assets["runner"]), str(assets["data"]), str(assets["result"])],
        cwd=repo_root,
        timeout=60,
    )
    result_payload = json.loads(assets["result"].read_text(encoding="utf-8")) if assets["result"].exists() else {}
    runtime_path = runtime_evidence(sandbox / "experiment" / "runtime-evidence.json", exp_proc.args, assets["result"], result_payload)
    exp_run, _ = run_autosci(
        rec,
        sandbox,
        "exp-run",
        [
            "phase22-j09-local",
            "--env",
            "local",
            "--approval-ref",
            "phase22-local-approval",
            "--allowlist-evidence",
            str(assets["allowlist"]),
            "--runtime-evidence",
            str(runtime_path),
            "--before-artifact",
            str(assets["data"]),
            "--after-artifact",
            str(assets["result"]),
            "--run-id",
            "p22-j09-exp-run",
        ],
        timeout=90,
    )
    exp_result_ev = action_evidence(exp_run, "run_experiment")
    claims = write_research_claims(
        sandbox / "claims.json",
        [
            {
                "claim_id": "claim-supported",
                "text": "The normalization variant improves exact-match accuracy by at least 20 percentage points on the local dataset.",
                "source_anchor": "phase22-local-experiment#results",
                "testability": "testable",
                "verification_status": "unverified",
                "evidence_ids": ["claim:phase22-supported"],
            }
        ],
        task_id="phase22-j09-claims",
    )
    code_ev = write_code_evidence(sandbox / "code-supported.json", claim_id="claim-supported", files=[str(assets["runner"])])
    verify, _ = run_autosci(
        rec,
        sandbox,
        "exp-eval",
        [
            "claim-supported",
            "--experiment-result-evidence",
            str(exp_result_ev),
            "--claims-evidence",
            str(claims),
            "--code-evidence",
            str(code_ev),
            "--run-id",
            "p22-j09-exp-eval",
        ],
        timeout=90,
    )
    verdict_ev = action_evidence(verify, "verify_claim")
    verdict_payload = _load_json(verdict_ev)
    verdict_boundary = verdict_payload.get("outputs", {}).get("final_verdict_boundary", {})
    if verdict_ev:
        rec.add_artifact(Path(verdict_ev), "claim_verdict")
        recorded_verdict = Path(rec.artifacts[-1]["path"])
        if not recorded_verdict.is_absolute():
            recorded_verdict = rec.run_dir / recorded_verdict
    else:
        recorded_verdict = rec.artifact_dir / "missing-claim-verdict.json"
    if exp_result_ev:
        rec.add_artifact(Path(exp_result_ev), "experiment_result_evidence")
        recorded_experiment = Path(rec.artifacts[-1]["path"])
        if not recorded_experiment.is_absolute():
            recorded_experiment = rec.run_dir / recorded_experiment
    else:
        recorded_experiment = rec.artifact_dir / "missing-experiment-result.json"
    decision_request_path = write_json(
        rec.artifact_dir / "decision-request.json",
        _decision_request(recorded_verdict, recorded_experiment),
    )
    decision_output = rec.artifact_dir / "decision-artifact.json"
    decision_proc = rec.run(
        "decision-artifact-construction",
        [
            phase22_python,
            str(repo_root / "harness" / "tools" / "decision_artifact.py"),
            "--input",
            str(decision_request_path),
            "--output",
            str(decision_output),
            "--source-root",
            str(rec.run_dir),
        ],
        cwd=repo_root,
        timeout=60,
    )
    decision_payload = _load_json(decision_output)
    decision_schema = _load_json(
        repo_root / "harness" / "schemas" / "evidence" / "decision_artifact.v1.schema.json"
    )
    decision_schema_error = ""
    try:
        jsonschema.Draft202012Validator(decision_schema).validate(decision_payload)
    except jsonschema.ValidationError as exc:
        decision_schema_error = exc.message
    negative_verdict_payload = copy.deepcopy(verdict_payload)
    negative_verdict_payload["outputs"]["verdicts"][0]["verdict"] = "not_supported"
    negative_verdict_path = write_json(
        rec.artifact_dir / "decision-negative-claim-verdict.json",
        negative_verdict_payload,
    )
    negative_request = _decision_request(negative_verdict_path, recorded_experiment)
    negative_request_path = write_json(
        rec.artifact_dir / "decision-request-unsupported.json", negative_request
    )
    negative_output = rec.artifact_dir / "decision-artifact-unsupported.json"
    negative_output.write_text(
        '{"schema":"decision_artifact.v1","stale":true}\n', encoding="utf-8"
    )
    negative_proc = rec.run(
        "decision-artifact-unsupported-evidence",
        [
            phase22_python,
            str(repo_root / "harness" / "tools" / "decision_artifact.py"),
            "--input",
            str(negative_request_path),
            "--output",
            str(negative_output),
            "--source-root",
            str(rec.run_dir),
        ],
        cwd=repo_root,
        timeout=60,
    )
    rec.add_artifact(decision_request_path, "decision_request")
    rec.add_artifact(decision_output, "decision_artifact")
    discovery = write_json(
        sandbox / "literature-discovery.json",
        {
            "schema": "literature_discovery.v1",
            "task_id": "phase22-j09-local-discovery",
            "sprint_id": "phase22-real-journeys",
            "node_id": "local-discovery",
            "status": "completed",
            "inputs": {"query": "verifier-guided skill learning"},
            "outputs": {
                "query": "verifier-guided skill learning",
                "candidates": [
                    {
                        "candidate_id": "local:phase22-paper",
                        "title": "Verifier-Guided Skill Learning for LLM Agents",
                        "summary": "Local upstream paper fixture used as durable handoff evidence.",
                        "source_ref": str(paper),
                    }
                ],
            },
            "artifacts": [],
            "provenance": {"operator_id": "phase22-journey-test", "implementation_package": "tests.journeys.phase22.code", "timestamp": "2026-07-28T00:00:00Z"},
            "limitations": ["Local discovery surrogate; live literature provider was not invoked."],
        },
    )
    allowlist = write_json(sandbox / "compile-allowlist.json", {"approved": True, "scope": "phase22-j09-compile-handoff"})
    before = write_json(sandbox / "paper-before.json", {"source": str(paper)})
    wiki_root = sandbox / "wiki"
    for name in ("ideas", "experiments", "methods", "concepts", "topics", "papers", "graph", "outputs"):
        (wiki_root / name).mkdir(parents=True, exist_ok=True)
    (wiki_root / "ideas/phase22-skillgen.md").write_text(
        "---\nidea_id: phase22-skillgen\nslug: phase22-skillgen\nstatus: validated\nnovelty_score: 4\nlinked_experiments: [exp-phase22-skillgen]\n---\n# Phase22 SkillGen\n\nA validated local idea grounded in paper and experiment evidence.\n",
        encoding="utf-8",
    )
    (wiki_root / "experiments/exp-phase22-skillgen.md").write_text(
        "---\nstatus: succeeded\nkey_result: local normalization improved accuracy\n---\n# Local Experiment\n\nExperiment result evidence is linked from the journey handoff.\n",
        encoding="utf-8",
    )
    (wiki_root / "methods/verifier-normalization.md").write_text(
        "# Verifier Normalization\n\nLocal method evidence used in the report handoff.\n",
        encoding="utf-8",
    )
    handoff = sandbox / "phase22-report-handoff.md"
    handoff.write_text(
        "\n".join(
            [
                "# Phase22 Report Handoff",
                "",
                f"- paper: {paper}",
                f"- ingest summary: {ingest.get('evidence_path', '')}",
                f"- experiment result: {exp_result_ev}",
                f"- claim verdict: {verdict_ev}",
                f"- discovery evidence: {discovery}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    for path, typ in (
        (paper, "source_paper"),
        (handoff, "report_handoff_manifest"),
        (claims, "research_claims"),
        (code_ev, "code_evidence"),
        (discovery, "discovery_evidence"),
    ):
        if path:
            rec.add_artifact(Path(path), typ)

    source_evidence_args: list[str] = []
    for flag, path in (
        ("--claims-evidence", claims),
        ("--code-evidence", code_ev),
        ("--experiment-result-evidence", exp_result_ev),
    ):
        if path:
            source_evidence_args.extend([flag, str(path)])

    common_args = [
        "phase22-skillgen",
        "--title",
        "Verifier-Guided Skill Learning Report",
        "--wiki-root",
        str(wiki_root),
        "--discovery-evidence",
        str(discovery),
        *source_evidence_args,
        "--approval-ref",
        "phase22-paper-compile",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
    ]
    plan, _ = run_autosci(rec, sandbox, "paper-plan", [*common_args, "--run-id", "p22-j09-plan-pre-review"], timeout=90)
    draft, harness_dir = run_autosci(rec, sandbox, "paper-draft", [*common_args, "--run-id", "p22-j09-draft"], timeout=90)
    draft_ev = action_evidence(draft, "write_report")
    review_target = draft_ev or paper
    review_proof = _write_review_proof(sandbox / "review-proof.json", Path(review_target))
    review_args = [
        str(review_target),
        "--proof-bundle",
        str(review_proof),
        "--focus",
        "method",
    ]
    live_env = bootstrap_live_environment(repo_root)
    review_provider = live_env.get("AUTOSCI_LIVE_REVIEW_LLM_PROVIDER") or live_env.get("AUTOSCI_REVIEW_LLM_PROVIDER")
    review_model = live_env.get("AUTOSCI_LIVE_REVIEW_LLM_MODEL") or live_env.get("AUTOSCI_REVIEW_LLM_MODEL")
    if review_provider:
        review_args.extend(["--review", "--review-llm-provider", review_provider])
        if review_model:
            review_args.extend(["--review-llm-model", review_model])
    review, _ = run_autosci(
        rec,
        sandbox,
        "review",
        [*review_args, "--run-id", "p22-j09-review"],
        timeout=120,
        allow_live=bool(review_provider),
    )
    review_ev = action_evidence(review, "review_artifact")
    reviewed_common_args = [*common_args]
    if review_ev:
        reviewed_common_args.extend(["--review-llm-evidence", str(review_ev)])
        plan, _ = run_autosci(
            rec,
            sandbox,
            "paper-plan",
            [*reviewed_common_args, "--run-id", "p22-j09-plan-reviewed"],
            timeout=90,
        )
    compile_args = [str(review_target), "--checklist"]
    if review_ev:
        compile_args.extend(["--review-llm-evidence", str(review_ev)])
    compile_result, _ = run_autosci(rec, sandbox, "paper-compile", [*compile_args, "--run-id", "p22-j09-compile"], timeout=90)

    plan_ev = action_evidence(plan, "plan_report")
    compile_ev = action_evidence(compile_result, "compile_paper")
    for path, typ in (
        (plan_ev, "report_plan"),
        (draft_ev, "report_draft"),
        (review_ev, "artifact_review"),
        (compile_ev, "compile_evidence"),
    ):
        if path:
            rec.add_artifact(path, typ)

    draft_payload = _load_json(draft_ev)
    markdown_report = _find_markdown_report(draft_payload, harness_dir)
    markdown_text = markdown_report.read_text(encoding="utf-8", errors="replace") if markdown_report else ""
    if markdown_report:
        rec.add_artifact(markdown_report, "readable_markdown_report")
    pdf_report = rec.run_dir / "verifier-guided-skill-learning-report.pdf"
    pdf_tool = repo_root / "harness" / "tools" / "markdown_pdf.py"
    pdf_build = rec.run(
        "publication-pdf-build",
        [phase22_python, str(pdf_tool), "build", "--input", str(markdown_report), "--output", str(pdf_report)]
        if markdown_report else [phase22_python, str(pdf_tool), "verify", "--input", str(pdf_report)],
        cwd=repo_root,
        timeout=60,
    )
    pdf_verify = rec.run(
        "publication-pdf-verify",
        [phase22_python, str(pdf_tool), "verify", "--input", str(pdf_report)],
        cwd=repo_root,
        timeout=60,
    )
    pdf_payload = json.loads(pdf_build.stdout) if pdf_build.returncode == 0 else {}
    if pdf_report.is_file():
        rec.add_artifact(pdf_report, "compiled_pdf_report")
    draft_report = draft_payload.get("outputs", {}).get("report", {}) if isinstance(draft_payload, dict) else {}
    draft_sections = draft_report.get("sections", []) if isinstance(draft_report, dict) else []
    draft_section_ids = {section.get("section_id") for section in draft_sections if isinstance(section, dict)}
    draft_section_text = " ".join(section.get("body", "") for section in draft_sections if isinstance(section, dict))
    report_evidence_ids = draft_report.get("evidence_ids", []) if isinstance(draft_report, dict) else []
    draft_status = draft_payload.get("status") if isinstance(draft_payload, dict) else "missing"

    plan_payload = _load_json(plan_ev)
    plan_status = plan_payload.get("status") if isinstance(plan_payload, dict) else "missing"
    review_payload = _load_json(review_ev)
    review_boundary = review_payload.get("outputs", {}).get("final_acceptance_boundary", {}) if isinstance(review_payload, dict) else {}
    review_output = review_payload.get("outputs", {}).get("review", {}) if isinstance(review_payload, dict) else {}

    compile_payload = _load_json(compile_ev)
    compile_status = compile_payload.get("status") if isinstance(compile_payload, dict) else "missing"
    compile_limits = compile_payload.get("limitations", []) if isinstance(compile_payload, dict) else []
    compile_policy_blocked = compile_payload.get("outputs", {}).get("policy_decision", {}).get("blocked", False) if isinstance(compile_payload, dict) else False

    def recorded_artifact_path(artifact_type: str) -> Path:
        entry = next(item for item in rec.artifacts if item.get("type") == artifact_type)
        path = Path(str(entry["path"]))
        return path if path.is_absolute() else rec.run_dir / path

    external_delivery_audit = Path(os.environ.get("PHASE22_J09_EXTERNAL_DELIVERY_AUDIT", "") or "")
    external_delivery_enabled = external_delivery_audit.is_file()
    stable_external_delivery_audit = (
        rec.add_artifact(external_delivery_audit, "external_delivery_audit", "Approved external Gmail delivery audit.")
        if external_delivery_enabled
        else None
    )
    delivery_permissions = (
        {
            "distribution_scope": "external_email",
            "approval_required": True,
            "approval_state": "approved",
            "approval_ref": "approval-phase22-gmail-handoff",
            "approved_by": "user:j50058254",
            "approved_at": "2026-08-12T00:00:00Z",
        }
        if external_delivery_enabled
        else {"distribution_scope": "local_only", "approval_required": True, "approval_state": "not_requested"}
    )
    external_delivery_spec = (
        {
            "channel": "gmail",
            "recipient": "jms.duck1020@gmail.com",
            "runtime_evidence_path": str(stable_external_delivery_audit),
            "recipient_acceptance_required": False,
        }
        if external_delivery_enabled
        else None
    )
    request_payload = {
        "schema": "publication_delivery_request.v1",
        "delivery_id": "phase22-j09-technical-lead-handoff",
        "audience": {"role": "technical_lead", "description": "Technical decision-maker reviewing the bounded local SkillGen result."},
        "delivery_format": "mixed_bundle",
        "content_scope": ["report", "compiled-pdf", "delivery-plan", "provider-review", "decision-artifact"],
        "permissions": delivery_permissions,
        "files": [
            {"file_id": "report", "type": "readable_markdown_report", "source_path": str(recorded_artifact_path("readable_markdown_report")), "evidence_ids": ["report:phase22-j09"]},
            {"file_id": "compiled-pdf", "type": "compiled_pdf_report", "source_path": str(recorded_artifact_path("compiled_pdf_report")), "evidence_ids": ["report:phase22-j09", "compile:phase22-j09"]},
            {"file_id": "plan", "type": "report_plan", "source_path": str(recorded_artifact_path("report_plan")), "evidence_ids": ["plan:phase22-j09"]},
            {"file_id": "review", "type": "provider_review", "source_path": str(recorded_artifact_path("artifact_review")), "evidence_ids": ["review:phase22-j09", *[str(item) for item in review_boundary.get("evidence_ids") or []]]},
            {"file_id": "decision", "type": "decision_artifact", "source_path": str(recorded_artifact_path("decision_artifact")), "evidence_ids": ["decision:phase22-j09"]},
        ],
    }
    if external_delivery_spec:
        request_payload["external_delivery"] = external_delivery_spec
    delivery_request = write_json(
        rec.artifact_dir / "publication-delivery-request.json",
        request_payload,
    )
    delivery_dir = rec.run_dir / "publication-delivery"
    delivery_tool = repo_root / "harness" / "tools" / "publication_delivery_bundle.py"
    delivery_build = rec.run(
        "publication-delivery-build",
        [phase22_python, str(delivery_tool), "build", "--request", str(delivery_request), "--output-dir", str(delivery_dir), "--source-root", str(rec.run_dir)],
        cwd=repo_root,
        timeout=60,
    )
    delivery_verify = rec.run(
        "publication-delivery-verify",
        [phase22_python, str(delivery_tool), "verify", "--bundle-dir", str(delivery_dir)],
        cwd=repo_root,
        timeout=60,
    )
    delivery_manifest = delivery_dir / "publication-delivery-manifest.json"
    delivery_payload = _load_json(delivery_manifest)
    tamper_target = delivery_dir / delivery_payload.get("files", [{}])[0].get("path", "missing")
    tamper_original = tamper_target.read_bytes() if tamper_target.is_file() else b""
    if tamper_original:
        tamper_target.write_bytes(tamper_original + b"\ntampered\n")
    delivery_tamper = rec.run(
        "publication-delivery-tamper-rejected",
        [phase22_python, str(delivery_tool), "verify", "--bundle-dir", str(delivery_dir)],
        cwd=repo_root,
        timeout=60,
    )
    if tamper_original:
        tamper_target.write_bytes(tamper_original)
    delivery_restored = rec.run(
        "publication-delivery-restored-verify",
        [phase22_python, str(delivery_tool), "verify", "--bundle-dir", str(delivery_dir)],
        cwd=repo_root,
        timeout=60,
    )
    rec.add_artifact(delivery_request, "publication_delivery_request")
    rec.add_artifact(delivery_manifest, "publication_delivery_manifest")

    rec.add_assertion("upstream_ingest_completed", not ingest.get("_error"), ingest.get("_error"))
    rec.add_assertion("upstream_experiment_result_available", exp_result_ev is not None, exp_run.get("_error"))
    rec.add_assertion("upstream_claim_verdict_available", verdict_ev is not None, verify.get("_error"))
    rec.add_assertion("claim_verdict_completed", verdict_payload.get("status") == "completed", verdict_payload.get("status"))
    rec.add_assertion("decision_constructor_completed", decision_proc.returncode == 0, decision_proc.stderr)
    rec.add_assertion("decision_artifact_schema_valid", not decision_schema_error, decision_schema_error)
    rec.add_assertion(
        "decision_recommendation_traces_to_criteria_and_evidence",
        set(decision_payload.get("recommendation", {}).get("criterion_ids", [])) == {"measured-support", "external-validity"}
        and set(decision_payload.get("recommendation", {}).get("evidence_ids", []))
        == {"j09-claim-verdict", "j09-experiment-result"},
        decision_payload.get("recommendation"),
    )
    evidence_links = decision_payload.get("evidence_links", [])
    rec.add_assertion(
        "decision_evidence_provenance_reloaded_and_hashed",
        len(evidence_links) == 2
        and all(item.get("sha256") and Path(item.get("source_path", "")).is_file() for item in evidence_links),
        evidence_links,
    )
    request_payload = _load_json(decision_request_path)
    expected_evidence = {
        item["evidence_id"]: item
        for item in request_payload.get("evidence", [])
        if isinstance(item, dict) and item.get("evidence_id")
    }
    evidence_links_by_id = {
        item["evidence_id"]: item
        for item in evidence_links
        if isinstance(item, dict) and item.get("evidence_id")
    }
    rec.add_assertion(
        "decision_typed_evidence_matches_expected_hashes",
        {item.get("evidence_type") for item in evidence_links}
        == {"claim_verdict", "experiment_result"}
        and all(
            item.get("sha256")
            == expected_evidence.get(item.get("evidence_id"), {}).get("expected_sha256")
            == _file_sha256(Path(item.get("source_path", "")))
            for item in evidence_links
        )
        and evidence_links_by_id.get("j09-claim-verdict", {}).get("observed_support")
        == "supported"
        and evidence_links_by_id.get("j09-claim-verdict", {}).get(
            "supporting_evidence_ids"
        )
        == ["j09-experiment-result"]
        and evidence_links_by_id.get("j09-experiment-result", {}).get(
            "observed_support"
        )
        == "supports",
        {"request": expected_evidence, "artifact": evidence_links},
    )
    expected_pairs = {
        (alternative["alternative_id"], criterion["criterion_id"])
        for alternative in decision_payload.get("alternatives", [])
        for criterion in decision_payload.get("criteria", [])
    }
    actual_pairs = {
        (assessment.get("alternative_id"), assessment.get("criterion_id"))
        for assessment in decision_payload.get("assessments", [])
    }
    rec.add_assertion(
        "decision_assessment_matrix_complete",
        actual_pairs == expected_pairs,
        {"expected": sorted(expected_pairs), "actual": sorted(actual_pairs)},
    )
    rec.add_assertion(
        "decision_request_provenance_matches_persisted_bytes",
        decision_payload.get("provenance", {}).get("request_sha256")
        == _file_sha256(decision_request_path),
        decision_payload.get("provenance"),
    )
    rec.add_assertion(
        "decision_review_and_approval_state_truthful",
        decision_payload.get("decision_status") == "review_required"
        and decision_payload.get("review", {}).get("status") == "pending"
        and decision_payload.get("review", {}).get("reviewed_by") is None
        and decision_payload.get("approval", {}).get("status") == "not_requested"
        and decision_payload.get("approval", {}).get("approved_by") is None,
        {"review": decision_payload.get("review"), "approval": decision_payload.get("approval")},
    )
    rec.add_assertion(
        "unsupported_recommendation_fails_closed",
        negative_proc.returncode == 2 and not negative_output.exists(),
        negative_proc.stderr,
    )
    rec.add_assertion("paper_plan_recorded", plan_ev is not None and plan_status in {"completed", "inconclusive"}, plan_status or plan.get("_error"))
    rec.add_assertion("paper_draft_completed", draft_ev is not None, draft.get("_error"))
    rec.add_assertion("paper_draft_status_understood", draft_status in {"completed", "inconclusive"}, draft_status)
    rec.add_assertion("review_output_exists", review_ev is not None, review.get("_error"))
    rec.add_assertion("review_artifact_status_understood", review_payload.get("status") in {"completed", "inconclusive"}, review_payload.get("status"))
    rec.add_assertion("compile_or_checklist_evidence_recorded", compile_ev is not None, compile_result.get("_error"))
    rec.add_assertion("paper_compile_status_understood", compile_status in {"completed", "inconclusive"}, compile_status)
    rec.add_assertion(
        "compiled_pdf_report_structurally_verified",
        pdf_build.returncode == 0
        and pdf_verify.returncode == 0
        and pdf_payload.get("valid") is True
        and pdf_payload.get("page_count", 0) >= 1
        and len(str(pdf_payload.get("sha256") or "")) == 64
        and pdf_report.stat().st_size > 500,
        {"build": pdf_build.returncode, "verify": pdf_verify.returncode, "result": pdf_payload},
    )
    rec.add_assertion(
        "publication_delivery_contract_complete",
        delivery_build.returncode == 0
        and delivery_verify.returncode == 0
        and delivery_payload.get("audience", {}).get("role") == "technical_lead"
        and delivery_payload.get("permissions") == delivery_permissions
        and len(delivery_payload.get("handoff_checklist") or []) >= 5
        and len(delivery_payload.get("files") or []) == (6 if external_delivery_enabled else 5)
        and len(delivery_payload.get("evidence_index") or []) >= 4,
        {"build": delivery_build.returncode, "verify": delivery_verify.returncode, "manifest": delivery_payload},
    )
    if external_delivery_enabled:
        external_delivery = delivery_payload.get("external_delivery", {})
        rec.add_assertion(
            "publication_delivery_external_gmail_verified",
            external_delivery.get("channel") == "gmail"
            and external_delivery.get("recipient") == "jms.duck1020@gmail.com"
            and external_delivery.get("delivered") is True
            and external_delivery.get("approval_ref") == "approval-phase22-gmail-handoff",
            external_delivery,
        )
    rec.add_assertion(
        "publication_delivery_integrity_fails_closed",
        delivery_tamper.returncode == 2 and delivery_restored.returncode == 0,
        {"tamper_exit": delivery_tamper.returncode, "restored_exit": delivery_restored.returncode, "tamper_stderr": delivery_tamper.stderr},
    )
    rec.add_assertion(
        "draft_report_required_sections",
        {"summary", "findings", "evidence-map", "limitations"}.issubset(draft_section_ids),
        sorted({"summary", "findings", "evidence-map", "limitations"} - draft_section_ids),
    )
    rec.add_assertion("draft_report_substantive", len(markdown_text.split()) >= 50, len(markdown_text.split()))
    rec.add_assertion(
        "readable_markdown_report_saved",
        markdown_report is not None and markdown_report.exists() and markdown_report.stat().st_size > 0,
        str(markdown_report) if markdown_report else "missing",
    )
    rec.add_assertion(
        "readable_markdown_report_relevant",
        "Verifier-Guided Skill Learning" in markdown_text and "Evidence ids" in markdown_text,
        markdown_text[:400],
    )
    verdict = (
        verdict_payload.get("outputs", {}).get("verdicts", [{}])[0]
        if isinstance(verdict_payload, dict)
        else {}
    )
    verdict_id = verdict.get("claim_id") if isinstance(verdict, dict) else None
    exact_verdict_evidence_ids = {
        str(value)
        for key in ("evidence_ids", "claim_evidence_ids", "experiment_evidence_ids", "code_evidence_ids")
        for value in (verdict.get(key) or [])
        if _is_stable_evidence_id(value)
    } if isinstance(verdict, dict) else set()
    exact_report_evidence_ids = {str(value) for value in report_evidence_ids if _is_stable_evidence_id(value)}
    if verdict_id:
        rec.add_assertion(
            "draft_report_references_exact_claim_verdict_id",
            str(verdict_id) in exact_report_evidence_ids,
            {"expected": verdict_id, "actual": sorted(exact_report_evidence_ids)},
        )
        rec.add_assertion(
            "draft_report_references_exact_verdict_evidence_ids",
            exact_verdict_evidence_ids.issubset(exact_report_evidence_ids),
            {
                "expected": sorted(exact_verdict_evidence_ids),
                "missing": sorted(exact_verdict_evidence_ids - exact_report_evidence_ids),
                "actual": sorted(exact_report_evidence_ids),
            },
        )
    else:
        rec.add_assertion("draft_report_references_exact_claim_verdict_id", False, "missing claim id")
        rec.add_assertion("draft_report_references_exact_verdict_evidence_ids", False, "missing claim verdict")

    limitations = []
    if compile_status == "inconclusive" and compile_policy_blocked:
        limitations.append("Paper compile is inconclusive because compile execution is policy/HITL gated.")
    if compile_status == "inconclusive":
        limitations.append("Paper compile checklist output indicates a limited readiness state; see compile evidence for tool-blocking details.")
    if any("review" in str(item).lower() and "unavailable" in str(item).lower() for item in compile_limits):
        limitations.append("Compile evidence indicates review/compile readiness is limited by environment.")
    if review_boundary.get("review_mode") == "local_surrogate":
        limitations.append("Review used local_surrogate mode and did not execute Review LLM.")
    if review_boundary.get("review_llm_status") == "unavailable":
        limitations.append("Review LLM was unavailable and final acceptance was not completed.")
    if review_boundary.get("final_acceptance_ready") is not True:
        limitations.append("Review final acceptance boundary is not complete in the non-live run.")
    if review_boundary.get("review_mode") != "review_llm" or review_boundary.get("review_llm_status") != "completed":
        limitations.append("No provider-backed Review LLM completion was available; report review is limited to local product evidence.")
    if verdict_boundary.get("final_verdict_ready") is not True:
        limitations.append("Claim verdict final boundary is incomplete even though local verdict evidence was produced.")
    if plan_status == "inconclusive":
        limitations.append("Paper plan route returned inconclusive status while still producing plan evidence.")
    if draft_status == "inconclusive":
        limitations.append("Paper draft route returned inconclusive status while still producing a readable Markdown report.")
    if verdict_id and str(verdict_id) not in exact_report_evidence_ids:
        limitations.append("Draft report evidence ids do not directly include the exact claim verdict id.")
    missing_verdict_evidence_ids = exact_verdict_evidence_ids - exact_report_evidence_ids
    if missing_verdict_evidence_ids:
        limitations.append(
            "Draft report evidence ids do not directly include exact verifier evidence ids: "
            + ", ".join(sorted(missing_verdict_evidence_ids))
        )

    rec.add_l2(
        "Workflow",
        "User-Facing Deliverable Generation",
        "paper-plan, draft, review, and compile/checklist routes were executed with local upstream evidence",
        draft_ev or rec.run_dir,
        "partial",
    )
    rec.add_l2(
        "Foundation",
        "Decision Artifact Construction",
        "The production constructor built a schema-valid decision whose recommendation is bound to criteria and reloaded upstream evidence; unresolved review and approval remained explicit.",
        decision_output,
        True,
    )

    status = "PASS_WITH_KNOWN_LIMITATIONS" if limitations and all(item["passed"] for item in rec.assertions) else "PASS"
    if not all(item["passed"] for item in rec.assertions):
        status = "FAIL"
    rec.finalize(status, limitations=limitations)
