from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[3]
BRIDGE = HARNESS / "plugins" / "autosci" / "bin" / "autosci_bridge.py"


def run_bridge(args: list[str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, str(BRIDGE), *args],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_help_lists_required_actions(tmp_path: Path) -> None:
    proc = run_bridge(["run", "--help"], tmp_path)
    assert proc.returncode == 0, proc.stderr
    for action in [
        "discover_literature",
        "ingest_paper",
        "analyze_paper",
        "update_memory",
        "update_graph",
        "extract_claims",
        "extract_methods",
        "generate_ideas",
        "evaluate_ideas",
        "map_code_evidence",
        "design_experiment",
        "monitor_experiment",
        "run_experiment",
        "verify_claim",
        "write_report",
        "evolve_workflow",
    ]:
        assert action in proc.stdout


def test_smoke_writes_result_and_evidence_jsonl(tmp_path: Path) -> None:
    proc = run_bridge(["smoke"], tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["ok"] is True
    result_path = tmp_path / out["result_path"]
    ledger_path = tmp_path / out["evidence_jsonl"]
    assert result_path.exists()
    assert ledger_path.exists()
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["schema"] == "research_claims.v1"
    assert "AutoSciRunner" not in json.dumps(result)


def test_validate_accepts_smoke_result(tmp_path: Path) -> None:
    smoke = run_bridge(["smoke"], tmp_path)
    assert smoke.returncode == 0, smoke.stderr
    out = json.loads(smoke.stdout)
    validate = run_bridge(["validate", "--result", out["result_path"]], tmp_path)
    assert validate.returncode == 0, validate.stderr
    assert json.loads(validate.stdout)["ok"] is True


def test_phase9_ingest_writes_foundation_sidecars(tmp_path: Path) -> None:
    proc = run_bridge(
        [
            "run",
            "--action",
            "ingest_paper",
            "--envelope",
            "plugins/autosci/tests/fixtures/envelope.ingest_paper.json",
        ],
        tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["ok"] is True
    assert out["schema"] == "research_paper.v1"
    assert out["sidecar_evidence_paths"] == [
        "artifacts/scientific/smoke/research_memory_update.json",
        "artifacts/scientific/smoke/research_graph_update.json",
    ]
    for rel_path, schema in {
        "artifacts/scientific/smoke/research_paper.json": "research_paper.v1",
        "artifacts/scientific/smoke/research_memory_update.json": "research_memory_update.v1",
        "artifacts/scientific/smoke/research_graph_update.json": "research_graph_update.v1",
    }.items():
        payload = json.loads((tmp_path / rel_path).read_text(encoding="utf-8"))
        assert payload["schema"] == schema
        assert payload["status"] == "completed"


def test_phase9_analyze_paper_preserves_analysis(tmp_path: Path) -> None:
    proc = run_bridge(
        [
            "run",
            "--action",
            "analyze_paper",
            "--envelope",
            "plugins/autosci/tests/fixtures/envelope.analyze_paper.json",
        ],
        tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    payload = json.loads((tmp_path / out["evidence_path"]).read_text(encoding="utf-8"))
    analysis = payload["outputs"]["paper"]["analysis"]
    assert "Solar Evidence ABI" in analysis["summary"]
    assert analysis["evidence_ids"]


def test_phase10_claim_method_and_code_actions_write_canonical_evidence(tmp_path: Path) -> None:
    actions = [
        ("extract_claims", "envelope.extract_claims.json", "artifacts/scientific/smoke/research_claims.json", "research_claims.v1"),
        ("extract_methods", "envelope.extract_methods.json", "artifacts/scientific/smoke/research_method.json", "research_method.v1"),
        ("map_code_evidence", "envelope.map_code_evidence.json", "artifacts/scientific/smoke/code_evidence_map.json", "code_evidence_map.v1"),
    ]
    for action, envelope, rel_path, schema in actions:
        proc = run_bridge(
            [
                "run",
                "--action",
                action,
                "--envelope",
                f"plugins/autosci/tests/fixtures/{envelope}",
            ],
            tmp_path,
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["schema"] == schema
        payload = json.loads((tmp_path / rel_path).read_text(encoding="utf-8"))
        assert payload["schema"] == schema
    code_payload = json.loads((tmp_path / "artifacts/scientific/smoke/code_evidence_map.json").read_text(encoding="utf-8"))
    mapping = code_payload["outputs"]["mappings"][0]
    assert mapping["mapping_status"] == "mapped"
    assert mapping["relevance_label"] == "related"
    assert mapping["relevance_reason"]
    assert mapping["files"] == ["plugins/autosci/tests/fixtures/sample_repo/bridge_fixture.py"]
    assert mapping["symbols"] == ["run_fixture_bridge"]
    handoff = tmp_path / "artifacts/scientific/smoke/handoff.md"
    assert handoff.exists()
    assert "Code Evidence" in handoff.read_text(encoding="utf-8")


def test_phase10_claims_and_methods_use_input_paper_anchors(tmp_path: Path) -> None:
    for action, output_name in [
        ("extract_claims", "research_claims.json"),
        ("extract_methods", "research_method.json"),
    ]:
        envelope = tmp_path / f"skillgen-{action}.json"
        envelope.write_text(
            json.dumps({
                "task_id": f"skillgen-{action}",
                "sprint_id": "phase10-test",
                "node_id": f"node-{action}",
                "mode": "fixture",
                "output_dir": "artifacts/scientific/skillgen",
                "inputs": {
                    "paper_path": "plugins/autosci/tests/fixtures/skillgen_sample_paper.md",
                },
                "outputs": {
                    "evidence_payload_path": f"artifacts/scientific/skillgen/{output_name}",
                },
            }),
            encoding="utf-8",
        )
        proc = run_bridge(["run", "--action", action, "--envelope", str(envelope)], tmp_path)
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        payload = json.loads((tmp_path / out["evidence_path"]).read_text(encoding="utf-8"))
        if action == "extract_claims":
            anchors = [claim["source_anchor"] for claim in payload["outputs"]["claims"]]
        else:
            anchors = [method["source_anchor"] for method in payload["outputs"]["methods"]]
        assert anchors
        assert all(anchor.startswith("skillgen_sample_paper.md#") for anchor in anchors)

    claims = json.loads((tmp_path / "artifacts/scientific/skillgen/research_claims.json").read_text(encoding="utf-8"))
    methods = json.loads((tmp_path / "artifacts/scientific/skillgen/research_method.json").read_text(encoding="utf-8"))
    assert any("SkillGen" in claim["text"] or "SKILLGEN" in claim["text"] for claim in claims["outputs"]["claims"])
    assert methods["outputs"]["methods"][0]["source_anchor"] == "skillgen_sample_paper.md#method"


def test_phase10_code_mapping_marks_missing_repo_unknown(tmp_path: Path) -> None:
    envelope = tmp_path / "missing-repo-envelope.json"
    envelope.write_text(
        json.dumps({
            "task_id": "missing-repo-map",
            "sprint_id": "phase10-test",
            "node_id": "node-map-code-evidence",
            "mode": "fixture",
            "output_dir": "artifacts/scientific/smoke",
            "inputs": {
                "claim_id": "claim-001",
                "repo_path": "plugins/autosci/tests/fixtures/does-not-exist",
            },
            "outputs": {
                "evidence_payload_path": "artifacts/scientific/smoke/missing_repo_code_evidence_map.json",
            },
        }),
        encoding="utf-8",
    )
    proc = run_bridge(["run", "--action", "map_code_evidence", "--envelope", str(envelope)], tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    payload = json.loads((tmp_path / out["evidence_path"]).read_text(encoding="utf-8"))
    mapping = payload["outputs"]["mappings"][0]
    assert mapping["mapping_status"] == "unknown"
    assert mapping["relevance_label"] == "unknown"
    assert mapping["relevance_reason"]
    assert mapping["files"] == ["N/A"]
    assert mapping["unknown_reason"]


def test_phase11_generate_and_evaluate_ideas_write_native_evidence(tmp_path: Path) -> None:
    setup_actions = [
        ("ingest_paper", "envelope.ingest_paper.json"),
        ("extract_claims", "envelope.extract_claims.json"),
        ("extract_methods", "envelope.extract_methods.json"),
        ("generate_ideas", "envelope.generate_ideas.json"),
        ("evaluate_ideas", "envelope.evaluate_ideas.json"),
    ]
    for action, envelope in setup_actions:
        proc = run_bridge(
            [
                "run",
                "--action",
                action,
                "--envelope",
                f"plugins/autosci/tests/fixtures/{envelope}",
            ],
            tmp_path,
        )
        assert proc.returncode == 0, proc.stderr
    ideas = json.loads((tmp_path / "artifacts/scientific/smoke/idea_candidate.json").read_text(encoding="utf-8"))
    evaluations = json.loads((tmp_path / "artifacts/scientific/smoke/idea_evaluation.json").read_text(encoding="utf-8"))
    memory_update = json.loads((tmp_path / "artifacts/scientific/smoke/research_memory_update.ideas.json").read_text(encoding="utf-8"))
    assert ideas["schema"] == "idea_candidate.v1"
    assert evaluations["schema"] == "idea_evaluation.v1"
    assert memory_update["schema"] == "research_memory_update.v1"
    assert any(idea["duplicate_status"] == "duplicate" and idea["status"] == "filtered" for idea in ideas["outputs"]["ideas"])
    for evaluation in evaluations["outputs"]["evaluations"]:
        assert evaluation["evidence_ids"]
        assert evaluation["novelty_rationale"]
        assert evaluation["feasibility_rationale"]
    rejected = [item for item in evaluations["outputs"]["evaluations"] if item["recommendation"] == "reject"]
    assert rejected and rejected[0]["risks"]
    assert all(change["operation"] == "propose" for change in memory_update["outputs"]["changes"])


def test_phase12_design_run_and_monitor_experiment_write_native_evidence(tmp_path: Path) -> None:
    setup_actions = [
        ("design_experiment", "envelope.design_experiment.json"),
        ("run_experiment", "envelope.run_experiment.fixture.json"),
        ("monitor_experiment", "envelope.monitor_experiment.json"),
    ]
    for action, envelope in setup_actions:
        proc = run_bridge(
            [
                "run",
                "--action",
                action,
                "--envelope",
                f"plugins/autosci/tests/fixtures/{envelope}",
            ],
            tmp_path,
        )
        assert proc.returncode == 0, proc.stderr
    plan = json.loads((tmp_path / "artifacts/scientific/smoke/experiment_plan.json").read_text(encoding="utf-8"))
    result = json.loads((tmp_path / "artifacts/scientific/smoke/experiment_result.json").read_text(encoding="utf-8"))
    status = json.loads((tmp_path / "artifacts/scientific/smoke/experiment_status.json").read_text(encoding="utf-8"))
    assert plan["schema"] == "experiment_plan.v1"
    assert result["schema"] == "experiment_result.v1"
    assert status["schema"] == "experiment_status.v1"
    experiment_plan = plan["outputs"]["experiment_plan"]
    assert experiment_plan["execution_mode"] == "fixture"
    assert experiment_plan["baseline"]
    assert experiment_plan["success_criteria"]
    experiment_result = result["outputs"]["result"]
    assert experiment_result["command_run"]
    assert experiment_result["logs"]
    assert experiment_result["metrics"]
    status_report = status["outputs"]["status_report"]
    assert status_report["state"] == "completed"
    assert status_report["evidence_ids"]


def test_phase12_unapproved_external_experiment_is_failed_evidence(tmp_path: Path) -> None:
    envelope = tmp_path / "unapproved-external-run.json"
    envelope.write_text(
        json.dumps({
            "task_id": "unapproved-external-run",
            "sprint_id": "phase12-test",
            "node_id": "node-run-experiment",
            "mode": "fixture",
            "output_dir": "artifacts/scientific/smoke",
            "inputs": {
                "execution_mode": "approved-external",
            },
            "outputs": {
                "evidence_payload_path": "artifacts/scientific/smoke/unapproved_experiment_result.json",
            },
        }),
        encoding="utf-8",
    )
    proc = run_bridge(["run", "--action", "run_experiment", "--envelope", str(envelope)], tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    payload = json.loads((tmp_path / out["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["schema"] == "experiment_result.v1"
    assert payload["status"] == "failed"
    assert payload["outputs"]["result"]["outcome"] == "failed"
    assert payload["outputs"]["result"]["metrics"][0]["name"] == "approval_present"
    assert payload["limitations"]


def test_phase12_design_without_target_does_not_default_to_idea_001(tmp_path: Path) -> None:
    envelope = tmp_path / "design-missing-target.json"
    envelope.write_text(
        json.dumps({
            "task_id": "design-missing-target",
            "sprint_id": "phase12-test",
            "node_id": "node-design-experiment",
            "mode": "solar_native",
            "output_dir": "artifacts/scientific/smoke",
            "inputs": {},
            "outputs": {
                "evidence_payload_path": "artifacts/scientific/smoke/design_missing_target.json",
            },
        }),
        encoding="utf-8",
    )
    proc = run_bridge(["run", "--action", "design_experiment", "--envelope", str(envelope)], tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    payload = json.loads((tmp_path / out["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["schema"] == "experiment_plan.v1"
    assert payload["status"] == "inconclusive"
    plan = payload["outputs"]["experiment_plan"]
    assert plan["experiment_id"] == "experiment-unresolved"
    assert "idea-001" not in plan["objective"]
    assert "no default idea-001 fallback" in " ".join(payload["limitations"])


def test_phase12_run_without_plan_does_not_default_to_exp_001(tmp_path: Path) -> None:
    envelope = tmp_path / "run-missing-plan.json"
    envelope.write_text(
        json.dumps({
            "task_id": "run-missing-plan",
            "sprint_id": "phase12-test",
            "node_id": "node-run-experiment",
            "mode": "solar_native",
            "output_dir": "artifacts/scientific/smoke",
            "inputs": {},
            "outputs": {
                "evidence_payload_path": "artifacts/scientific/smoke/run_missing_plan.json",
            },
        }),
        encoding="utf-8",
    )
    proc = run_bridge(["run", "--action", "run_experiment", "--envelope", str(envelope)], tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    payload = json.loads((tmp_path / out["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["schema"] == "experiment_result.v1"
    assert payload["status"] == "inconclusive"
    result = payload["outputs"]["result"]
    assert result["experiment_id"] == "experiment-unresolved"
    assert result["outcome"] == "inconclusive"
    assert all("exp-001" not in item for item in result["logs"])
    assert "no default exp-001 fallback" in " ".join(payload["limitations"])


def test_phase13_verify_claim_maps_experiment_outcomes_to_verdicts(tmp_path: Path) -> None:
    for action, envelope in [
        ("extract_claims", "envelope.extract_claims.json"),
        ("map_code_evidence", "envelope.map_code_evidence.json"),
    ]:
        proc = run_bridge(
            [
                "run",
                "--action",
                action,
                "--envelope",
                f"plugins/autosci/tests/fixtures/{envelope}",
            ],
            tmp_path,
        )
        assert proc.returncode == 0, proc.stderr

    cases = [
        ("envelope.verify_claim.supported.json", "supported", "supports", "claim_verdict.json"),
        ("envelope.verify_claim.partially_supported.json", "partially_supported", "partially_supports", "claim_verdict.partially_supported.json"),
        ("envelope.verify_claim.not_supported.json", "not_supported", "refutes", "claim_verdict.not_supported.json"),
        ("envelope.verify_claim.inconclusive.json", "inconclusive", "inconclusive", "claim_verdict.inconclusive.json"),
    ]
    for envelope, expected_verdict, expected_outcome, output_name in cases:
        proc = run_bridge(
            [
                "run",
                "--action",
                "verify_claim",
                "--envelope",
                f"plugins/autosci/tests/fixtures/{envelope}",
            ],
            tmp_path,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads((tmp_path / "artifacts/scientific/smoke" / output_name).read_text(encoding="utf-8"))
        verdict = payload["outputs"]["verdicts"][0]
        assert verdict["verdict"] == expected_verdict
        assert verdict["evidence_outcome"] == expected_outcome
        assert verdict["claim_id"] in verdict["evidence_ids"]
        assert any(item != verdict["claim_id"] for item in verdict["evidence_ids"])
        assert verdict["limitations"]


def test_phase14_write_report_outputs_report_and_publication_bundle(tmp_path: Path) -> None:
    setup_actions = [
        ("extract_claims", "envelope.extract_claims.json"),
        ("map_code_evidence", "envelope.map_code_evidence.json"),
        ("run_experiment", "envelope.run_experiment.fixture.json"),
        ("verify_claim", "envelope.verify_claim.supported.json"),
        ("write_report", "envelope.write_report.json"),
    ]
    for action, envelope in setup_actions:
        proc = run_bridge(
            [
                "run",
                "--action",
                action,
                "--envelope",
                f"plugins/autosci/tests/fixtures/{envelope}",
            ],
            tmp_path,
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
    assert out["schema"] == "scientific_report.v1"
    assert out["publication_bundle_path"] == "artifacts/scientific/smoke/publication_bundle.json"
    report = json.loads((tmp_path / "artifacts/scientific/smoke/scientific_report.json").read_text(encoding="utf-8"))
    bundle = json.loads((tmp_path / "artifacts/scientific/smoke/publication_bundle.json").read_text(encoding="utf-8"))
    assert report["schema"] == "scientific_report.v1"
    assert bundle["schema"] == "publication_bundle.v1"
    assert report["outputs"]["report"]["sections"]
    assert any(section["title"] == "Limitations" for section in report["outputs"]["report"]["sections"])
    assert report["outputs"]["report"]["figures"][0]["artifact_path"] == "artifacts/scientific/smoke/optional_poster.html"
    assert report["outputs"]["report"]["tables"][0]["artifact_path"] == "artifacts/scientific/smoke/report_evidence_index.json"
    bundle_files = bundle["outputs"]["bundle"]["files"]
    assert {item["type"] for item in bundle_files} == {
        "markdown_report",
        "optional_poster_html",
        "optional_rebuttal_markdown",
        "report_evidence_index_json",
        "report_plan_json",
    }
    for rel_path in [
        "artifacts/scientific/smoke/report_plan.json",
        "artifacts/scientific/smoke/report.md",
        "artifacts/scientific/smoke/report_evidence_index.json",
        "artifacts/scientific/smoke/optional_poster.html",
        "artifacts/scientific/smoke/optional_rebuttal.md",
    ]:
        assert (tmp_path / rel_path).exists()


def test_phase16_evolve_workflow_outputs_reviewable_proposal(tmp_path: Path) -> None:
    proc = run_bridge(
        [
            "run",
            "--action",
            "evolve_workflow",
            "--envelope",
            "plugins/autosci/tests/fixtures/envelope.evolve_workflow.failed_run.json",
        ],
        tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["schema"] == "workflow_evolution.v1"
    assert out["recommended_changes_path"] == "artifacts/scientific/smoke/recommended_changes.md"
    assert out["patch_candidates_path"] == "artifacts/scientific/smoke/patch_candidates"
    proposal = json.loads((tmp_path / "artifacts/scientific/smoke/workflow_evolution.json").read_text(encoding="utf-8"))
    evolution = proposal["outputs"]["evolution"]
    assert evolution["approval_state"] == "proposed"
    assert evolution["patch_candidates_path"] == "artifacts/scientific/smoke/patch_candidates"
    assert evolution["collected"]["failed_nodes"][0]["node_id"] == "experiment_run"
    categories = {change["category"] for change in evolution["proposed_changes"]}
    assert "manual" in categories
    assert {"schema", "gate"} & categories
    assert all(change["review_required"] is True for change in evolution["proposed_changes"])
    assert evolution["review"]["protected_core_edits_applied"] is False
    changes = tmp_path / "artifacts/scientific/smoke/recommended_changes.md"
    assert changes.exists()
    assert "Failed Nodes" in changes.read_text(encoding="utf-8")
    patch_candidates = tmp_path / "artifacts/scientific/smoke/patch_candidates"
    assert patch_candidates.is_dir()
    assert {
        artifact["type"] for artifact in proposal["artifacts"]
    } >= {"recommended_changes_markdown", "patch_candidates_directory"}
