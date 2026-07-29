from __future__ import annotations

import json
from pathlib import Path

from evidence import JourneyRecorder
from journey_runner import (
    action_evidence,
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
        (exp_result_ev, "experiment_result_evidence"),
        (verdict_ev, "claim_verdict"),
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
    plan, _ = run_autosci(rec, sandbox, "paper-plan", [*common_args, "--run-id", "p22-j09-plan"], timeout=90)
    draft, harness_dir = run_autosci(rec, sandbox, "paper-draft", [*common_args, "--run-id", "p22-j09-draft"], timeout=90)
    draft_ev = action_evidence(draft, "write_report")
    review_target = draft_ev or paper
    review, _ = run_autosci(rec, sandbox, "review", [str(review_target), "--focus", "method", "--run-id", "p22-j09-review"], timeout=90)
    compile_result, _ = run_autosci(rec, sandbox, "paper-compile", [str(review_target), "--checklist", "--run-id", "p22-j09-compile"], timeout=90)

    plan_ev = action_evidence(plan, "plan_report")
    review_ev = action_evidence(review, "review_artifact")
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

    rec.add_assertion("upstream_ingest_completed", not ingest.get("_error"), ingest.get("_error"))
    rec.add_assertion("upstream_experiment_result_available", exp_result_ev is not None, exp_run.get("_error"))
    rec.add_assertion("upstream_claim_verdict_available", verdict_ev is not None, verify.get("_error"))
    rec.add_assertion("claim_verdict_completed", verdict_payload.get("status") == "completed", verdict_payload.get("status"))
    rec.add_assertion("paper_plan_recorded", plan_ev is not None and plan_status in {"completed", "inconclusive"}, plan_status or plan.get("_error"))
    rec.add_assertion("paper_draft_completed", draft_ev is not None, draft.get("_error"))
    rec.add_assertion("paper_draft_status_understood", draft_status in {"completed", "inconclusive"}, draft_status)
    rec.add_assertion("review_output_exists", review_ev is not None, review.get("_error"))
    rec.add_assertion("review_artifact_status_understood", review_payload.get("status") in {"completed", "inconclusive"}, review_payload.get("status"))
    rec.add_assertion("compile_or_checklist_evidence_recorded", compile_ev is not None, compile_result.get("_error"))
    rec.add_assertion("paper_compile_status_understood", compile_status in {"completed", "inconclusive"}, compile_status)
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

    status = "PASS_WITH_KNOWN_LIMITATIONS" if limitations and all(item["passed"] for item in rec.assertions) else "PASS"
    if not all(item["passed"] for item in rec.assertions):
        status = "FAIL"
    rec.finalize(status, limitations=limitations)
