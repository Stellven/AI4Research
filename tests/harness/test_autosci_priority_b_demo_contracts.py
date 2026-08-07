from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path


HARNESS = (Path(__file__).resolve().parents[2] / 'harness')
REPO = HARNESS.parent
SOLAR_HARNESS = HARNESS / "solar-harness.sh"


def _prepare_isolated_harness(tmp_path: Path) -> Path:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    for name in ("bin", "config", "personas", "tools", "plugins", "evaluators", "schemas", "lib", "templates"):
        target = HARNESS / name
        link = harness_dir / name
        if not link.exists():
            link.symlink_to(target, target_is_directory=target.is_dir())
    (harness_dir / "run").mkdir(exist_ok=True)
    (harness_dir / "artifacts").mkdir(exist_ok=True)
    return harness_dir


def _env_for(harness_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(harness_dir)
    env["SOLAR_OPERATORD_ONCE_MAX_WAIT_SECONDS"] = "20"
    env.pop("AUTOSCI_ARTIFACT_ROOT", None)
    env.pop("SCIENTIFIC_ARTIFACT_ROOT", None)
    env.pop("SOLAR_AUTOSCI_OUTPUT_HARNESS", None)
    return env


def test_skills_product_entry_lists_route_statuses(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)

    proc = subprocess.run(
        [
            "bash",
            str(SOLAR_HARNESS),
            "autosci",
            "$skills",
        ],
        cwd=REPO,
        env=_env_for(harness_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 28
    skills = {item["skill"]: item for item in payload["skills"]}
    expected_demo_skills = {"ingest", "review", "ideate", "research", "paper-draft", "exp-run"}
    assert expected_demo_skills <= set(skills)
    assert {item["coverage_status"] for item in payload["skills"]} <= {"full", "partial", "gated", "missing"}
    assert {item["side_effect_policy"] for item in payload["skills"]} <= {"none", "dry_run_only", "approval_required"}
    assert any(item["coverage_status"] != "full" for item in payload["skills"])
    assert skills["exp-run"]["side_effect_policy"] == "approval_required"
    assert skills["paper-draft"]["coverage_status"] in {"full", "partial"}


def test_research_scheduler_run_projects_human_lifecycle_summary(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    run_id = f"priority-b-lifecycle-workspace-{uuid.uuid4().hex}"
    paper = harness_dir / "raw" / "priority-b-paper.md"
    paper.parent.mkdir()
    paper.write_text(
        "# Priority B Lifecycle Workspace\n\n"
        "## Abstract\n"
        "This paper verifies a human-facing lifecycle summary projection.\n\n"
        "## Results\n"
        "The scheduler run should produce node, gate, and evidence summary output.\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            "bash",
            str(SOLAR_HARNESS),
            "autosci",
            f"$research priority-b lifecycle --paper {paper} --scheduler-run --scheduler-timeout 20 --run-id {run_id}",
        ],
        cwd=REPO,
        env=_env_for(harness_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["scheduler_dispatch_boundary_status"] == "generic_workflow_runner"
    assert summary["scheduler_lifecycle_status"] == "passed"

    wiki_root = harness_dir / "artifacts" / "autosci" / "workspace" / "wiki"
    lifecycle_page = wiki_root / "outputs" / "lifecycle_summary.md"
    assert lifecycle_page.exists()
    page = lifecycle_page.read_text(encoding="utf-8")
    assert f"Lifecycle Summary: `{run_id}`" in page
    assert "Lifecycle status: `passed`" in page
    assert "Dispatch boundary: `generic_workflow_runner`" in page
    assert "Runtime manifest:" in page
    assert "## Node Results" in page
    assert "paper_ingest" in page
    assert "## Blocked Nodes" in page
    assert "Missing provider, model, approval, or runtime evidence remains visible" in page

    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert "outputs/lifecycle_summary.md" in index_text
    assert not (HARNESS / "artifacts" / "autosci" / "runs" / run_id).exists()


def test_review_projects_human_diagnostics_summary(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    run_id = f"priority-b-review-workspace-{uuid.uuid4().hex}"
    wiki_root = harness_dir / "artifacts" / "autosci" / "workspace" / "wiki"
    review_target = wiki_root / "outputs" / "priority-b-review.md"
    review_target.parent.mkdir(parents=True)
    review_target.write_text(
        "---\ntitle: Priority B Review Target\n---\n# Priority B Review Target\n\n"
        "The method describes a dataset, metric, baseline, evidence artifact, and reproducible result table.\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            "bash",
            str(SOLAR_HARNESS),
            "autosci",
            f"$review priority-b-review --from-wiki --difficulty hard --focus method --run-id {run_id}",
        ],
        cwd=REPO,
        env=_env_for(harness_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "review"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1

    review_page = wiki_root / "outputs" / "review.md"
    assert review_page.exists()
    page = review_page.read_text(encoding="utf-8")
    assert f"Review Diagnostics: `{run_id}`" in page
    assert "- Review mode: `local_surrogate`" in page
    assert "- Review available: `False`" in page
    assert "- Final acceptance ready: `False`" in page
    assert "Review LLM" in page
    assert "review_llm_incomplete" in page
    assert "Review LLM evidence from supplied evidence, command bridge, or provider mode" in page

    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert "outputs/review.md" in index_text
    assert not (HARNESS / "artifacts" / "autosci" / "runs" / run_id).exists()


def test_discover_projects_human_shortlist_summary(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    run_id = f"priority-b-discover-workspace-{uuid.uuid4().hex}"
    wiki_root = harness_dir / "artifacts" / "autosci" / "workspace" / "wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "papers" / "skillgen-seed.md").write_text(
        "---\ntitle: SkillGen Seed\narxiv: 2401.00001\n---\n# SkillGen Seed\n\n"
        "Skill generation and agent adaptation need provider-backed literature discovery before promotion.\n",
        encoding="utf-8",
    )
    env = _env_for(harness_dir)
    env["AUTOSCI_DISABLE_NETWORK_FETCH"] = "1"

    proc = subprocess.run(
        [
            "bash",
            str(SOLAR_HARNESS),
            "autosci",
            f"$discover agent skill learning --from-wiki --limit 3 --run-id {run_id}",
        ],
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "discover"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1
    assert summary["workspace_updated_count"] > 0

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    assert [action["action"] for action in actions] == ["discover_literature"]
    discovery = json.loads(Path(actions[0]["evidence_path"]).read_text(encoding="utf-8"))
    assert discovery["schema"] == "literature_discovery.v1"
    assert discovery["status"] == "inconclusive"
    assert discovery["outputs"]["mode"] == "wiki"
    assert discovery["outputs"]["limit"] == 3
    boundary = discovery["outputs"]["source_provider_boundary"]["final_shortlist_boundary"]
    assert boundary["final_shortlist_ready"] is False
    assert "discovery shortlist is empty" in boundary["blocking_reasons"]
    assert "provider-backed source channel is missing" in boundary["blocking_reasons"]

    discovery_page = wiki_root / "outputs" / "discovery.md"
    assert discovery_page.exists()
    page = discovery_page.read_text(encoding="utf-8")
    assert f"Discovery Summary: `{run_id}`" in page
    assert "- Evidence status: `inconclusive`" in page
    assert "- Mode: `wiki`" in page
    assert "- Limit: `3`" in page
    assert "- Final shortlist ready: `False`" in page
    assert "literature_discovery.json" in page
    assert "discovery shortlist is empty" in page
    assert "provider-backed source channel is missing" in page
    assert "Final discovery shortlist requires non-empty candidates" in page

    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert "outputs/discovery.md" in index_text
    assert not (HARNESS / "artifacts" / "autosci" / "runs" / run_id).exists()


def test_ideate_projects_human_candidate_and_evaluation_summary(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    run_id = f"priority-b-ideate-workspace-{uuid.uuid4().hex}"
    wiki_root = harness_dir / "artifacts" / "autosci" / "workspace" / "wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "methods").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "papers" / "skillgen.md").write_text(
        "---\ntitle: SkillGen Paper\n---\n# SkillGen Paper\n\n"
        "Skill generation exposes an inference-time adaptation gap with measurable validation needs.\n",
        encoding="utf-8",
    )
    (wiki_root / "methods" / "adaptation.md").write_text(
        "---\ntitle: Inference-Time Adaptation\n---\n# Inference-Time Adaptation\n\n"
        "A reusable method with open evaluation and robustness questions.\n",
        encoding="utf-8",
    )
    (wiki_root / "graph" / "open_questions.md").write_text(
        "# Open Questions\n\n- How should generated skills be validated against baseline tools?\n",
        encoding="utf-8",
    )
    discovery_dir = harness_dir / "artifacts" / "autosci" / "runs" / "priority-b-discover-seed"
    discovery_dir.mkdir(parents=True)
    discovery_path = discovery_dir / "literature_discovery.json"
    discovery_path.write_text(
        json.dumps(
            {
                "schema": "literature_discovery.v1",
                "task_id": "priority-b-discover-seed",
                "sprint_id": "test",
                "node_id": "discover",
                "status": "completed",
                "inputs": {},
                "outputs": {
                    "candidates": [
                        {
                            "paper_id": "paper-discovery-001",
                            "title": "Recent Agent Skill Adaptation",
                            "summary": "A recent paper about adapting agent skills at inference time.",
                        }
                    ]
                },
                "artifacts": [],
                "provenance": {
                    "operator_id": "test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            "bash",
            str(SOLAR_HARNESS),
            "autosci",
            (
                "$ideate agent skill learning --from-wiki "
                f"--wiki-root {wiki_root} --discovery-evidence {discovery_path} "
                f"--max-ideas 2 --run-id {run_id}"
            ),
        ],
        cwd=REPO,
        env=_env_for(harness_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ideate"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 2

    ideas_page = wiki_root / "outputs" / "ideas.md"
    assert ideas_page.exists()
    page = ideas_page.read_text(encoding="utf-8")
    assert f"Idea Summary: `{run_id}`" in page
    assert "- Candidate evidence status: `completed`" in page
    assert "- Evaluation evidence status: `completed`" in page
    assert "idea_promotion_incomplete" in page or "novelty_acceptance_incomplete" in page
    assert "external_novelty status is" in page
    assert "review_llm status is" in page
    assert "Independent Review LLM and live external search are still required before promotion." in page
    assert "N/A" not in page.split("## Ideas", maxsplit=1)[0]

    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert "outputs/ideas.md" in index_text
    assert not (HARNESS / "artifacts" / "autosci" / "runs" / run_id).exists()


def test_paper_draft_projects_demo_visible_report_summary(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    run_id = f"priority-b-paper-draft-workspace-{uuid.uuid4().hex}"

    proc = subprocess.run(
        [
            "bash",
            str(SOLAR_HARNESS),
            "autosci",
            f"$paper-draft --topic 'agentic scientific workflow' --title 'Priority B Paper Draft' --run-id {run_id}",
        ],
        cwd=REPO,
        env=_env_for(harness_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "paper-draft"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1
    assert summary["schema_only_count"] == 1
    assert summary["workspace_updated_count"] > 0

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "write_report"
    assert action["schema"] == "scientific_report.v1"
    assert action["gate_status"] == "schema_only"
    report_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert report_evidence["status"] == "inconclusive"
    report = report_evidence["outputs"]["report"]
    assert report["title"] == "Priority B Paper Draft"
    artifacts = {artifact["type"]: artifact["path"] for artifact in report_evidence["artifacts"]}
    assert {
        "markdown_report",
        "latex_source",
        "paper_sections_directory",
        "citation_map_json",
        "paper_draft_final_manuscript_boundary_json",
    } <= set(artifacts)
    boundary = json.loads((harness_dir / artifacts["paper_draft_final_manuscript_boundary_json"]).read_text(encoding="utf-8"))
    assert boundary["final_manuscript_ready"] is False
    assert boundary["publication_ready_claim_allowed"] is False
    assert "completed Review LLM boundary evidence is missing" in boundary["blocking_reasons"]
    assert "verified compile/PDF handoff is missing" in boundary["blocking_reasons"]

    wiki_root = harness_dir / "artifacts" / "autosci" / "workspace" / "wiki"
    report_page = wiki_root / "outputs" / "report.md"
    assert report_page.exists()
    page = report_page.read_text(encoding="utf-8")
    assert "# Priority B Paper Draft" in page
    assert "scientific_report.json" in page
    assert "report.md" in page
    assert "Evidence ids:" in page
    assert "No source-backed citation entries were available." in page
    assert "Publication-ready claim allowed: `False`" in page
    assert "Final manuscript readiness requires source evidence" in page

    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert "outputs/report.md" in index_text
    assert not (HARNESS / "artifacts" / "autosci" / "runs" / run_id).exists()


def test_exp_run_projects_demo_runtime_boundary_summary(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    run_id = f"priority-b-exp-run-workspace-{uuid.uuid4().hex}"

    proc = subprocess.run(
        [
            "bash",
            str(SOLAR_HARNESS),
            "autosci",
            f"$exp-run exp-demo --run-id {run_id}",
        ],
        cwd=REPO,
        env=_env_for(harness_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-run"
    assert summary["execution_status"] == "gated"
    assert summary["action_count"] >= 2
    assert summary["schema_only_count"] >= 1
    assert summary["workspace_updated_count"] > 0

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    action_names = [action["action"] for action in actions]
    assert "design_experiment" in action_names
    assert "run_experiment" in action_names
    result_action = next(action for action in actions if action["action"] == "run_experiment")
    assert result_action["schema"] == "experiment_result.v1"
    assert result_action["gate_status"] == "schema_only"
    result_evidence = json.loads(Path(result_action["evidence_path"]).read_text(encoding="utf-8"))
    assert result_evidence["status"] == "inconclusive"
    result = result_evidence["outputs"]["result"]
    assert result["experiment_id"] == "exp-demo"
    assert result["outcome"] == "inconclusive"
    assert result["execution_mode"] == "human_approved"
    assert "fixture result collected" not in "\n".join(result["logs"])
    assert any("approval is required and absent" in item for item in result_evidence["limitations"])
    boundary = result["final_runtime_audit_boundary"]
    assert boundary["schema"] == "autosci_experiment_run_final_runtime_audit_boundary.v1"
    assert boundary["final_runtime_audit_ready"] is False
    assert boundary["approval_contract_verified"] is False
    assert boundary["runtime_semantic_verified"] is False
    artifact_types = {artifact["type"] for artifact in result_evidence["artifacts"]}
    assert "approval_contract_json" in artifact_types
    assert "experiment_run_final_runtime_audit_boundary_json" in artifact_types

    wiki_root = harness_dir / "artifacts" / "autosci" / "workspace" / "wiki"
    experiment_page = wiki_root / "outputs" / "experiment.md"
    assert experiment_page.exists()
    page = experiment_page.read_text(encoding="utf-8")
    assert f"Experiment Summary: `{run_id}`" in page
    assert "- Experiment id: `exp-demo`" in page
    assert "- Result evidence status: `inconclusive`" in page
    assert "- Final runtime audit ready: `False`" in page
    assert "- Approval contract verified: `False`" in page
    assert "Experiment execution was blocked because approval is required and absent" in page
    assert "Final runtime audit requires semantic runtime verification to pass." in page

    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert "outputs/experiment.md" in index_text
    assert not (HARNESS / "artifacts" / "autosci" / "runs" / run_id).exists()


def test_workspace_index_explains_demo_entry_points(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    run_id = f"priority-b-workspace-index-{uuid.uuid4().hex}"

    proc = subprocess.run(
        [
            "bash",
            str(SOLAR_HARNESS),
            "autosci",
            f"$paper-draft --topic 'agentic scientific workflow' --title 'Priority B Workspace Index' --run-id {run_id}",
        ],
        cwd=REPO,
        env=_env_for(harness_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "paper-draft"
    assert summary["workspace_updated_count"] > 0

    wiki_root = harness_dir / "artifacts" / "autosci" / "workspace" / "wiki"
    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert "## Demo Entry Points" in index_text
    for question in (
        "what ran",
        "what was produced",
        "what is blocked",
        "what evidence exists",
        "what remains incomplete",
    ):
        assert question in index_text
    for page in (
        "outputs/lifecycle_summary.md",
        "outputs/report.md",
        "outputs/review.md",
        "outputs/ideas.md",
        "outputs/experiment.md",
    ):
        assert page in index_text
    assert "| what was produced | ok | [report](outputs/report.md) |" in index_text
    assert "| what ran | pending | [lifecycle_summary](outputs/lifecycle_summary.md) |" in index_text
    assert "Approval/runtime audit, collection, and remote proof status." in index_text
    assert not (HARNESS / "artifacts" / "autosci" / "runs" / run_id).exists()


def test_ingest_projects_human_paper_workspace_page(tmp_path: Path) -> None:
    harness_dir = _prepare_isolated_harness(tmp_path)
    run_id = f"priority-b-ingest-workspace-{uuid.uuid4().hex}"
    paper = harness_dir / "raw" / "priority-b-ingest-paper.md"
    paper.parent.mkdir()
    paper.write_text(
        "# Priority B Product Ingest\n\n"
        "## Abstract\n"
        "This source verifies direct product entry for AutoSci paper ingestion.\n\n"
        "## Method\n"
        "The ingest route should emit research_paper.v1 evidence and a human-facing workspace paper page.\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            "bash",
            str(SOLAR_HARNESS),
            "autosci",
            f"$ingest --paper {paper} --run-id {run_id}",
        ],
        cwd=REPO,
        env=_env_for(harness_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ingest"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 2
    assert summary["workspace_updated_count"] > 0

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    assert [action["action"] for action in actions] == ["ingest_paper", "analyze_paper"]
    ingest_evidence = json.loads(Path(actions[0]["evidence_path"]).read_text(encoding="utf-8"))
    assert ingest_evidence["schema"] == "research_paper.v1"
    assert ingest_evidence["status"] == "completed"
    paper_output = ingest_evidence["outputs"]["paper"]
    assert paper_output["parse_status"] == "parsed"
    assert "Priority B Product Ingest" in paper_output["title"]
    boundary = paper_output["final_source_registration_boundary"]
    assert boundary["source_preparation_verified"] is True
    assert boundary["raw_artifact_provenance_ready"] is True

    wiki_root = harness_dir / "artifacts" / "autosci" / "workspace" / "wiki"
    paper_pages = sorted((wiki_root / "papers").glob("*.md"))
    assert len(paper_pages) == 1
    page = paper_pages[0].read_text(encoding="utf-8")
    assert "# Priority B Product Ingest" in page
    assert "Evidence:" in page
    assert "research_paper.analyzed.json" in page or "research_paper.json" in page

    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert f"papers/{paper_pages[0].name}" in index_text
    assert not (HARNESS / "artifacts" / "autosci" / "runs" / run_id).exists()
