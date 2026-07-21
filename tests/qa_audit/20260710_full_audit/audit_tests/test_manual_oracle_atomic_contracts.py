from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
HARNESS = CHECKOUT / "harness"
BRIDGE = HARNESS / "plugins" / "autosci" / "bin" / "autosci_bridge.py"
SHIM = HARNESS / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"
FIXTURES = HARNESS / "plugins" / "autosci" / "tests" / "fixtures"


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "SOLAR_HOME": str(tmp_path / "solar-home"),
        "CLAUDE_DIR": str(tmp_path / "claude"),
        "HARNESS_DIR": str(tmp_path),
        "AUTOSCI_DISABLE_NETWORK_FETCH": "1",
    }


def _run_bridge(tmp_path: Path, action: str, envelope: str | Path) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    proc = subprocess.run(
        [sys.executable, str(BRIDGE), "run", "--action", action, "--envelope", str(envelope)],
        cwd=HARNESS,
        env=_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    payload = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    return proc, payload


def _run_shim(tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    proc = subprocess.run(
        [sys.executable, str(SHIM), *args],
        cwd=HARNESS,
        env=_env(tmp_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    payload = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    return proc, payload


def _action_evidence(summary: dict[str, object]) -> dict[str, object]:
    run = json.loads(Path(str(summary["evidence_path"])).read_text(encoding="utf-8"))
    action = run["outputs"]["skill_run"]["actions"][0]
    return json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))


def _write_envelope(tmp_path: Path, name: str, action: str, inputs: dict[str, object]) -> Path:
    path = tmp_path / f"{name}.envelope.json"
    path.write_text(
        json.dumps(
            {
                "task_id": f"task-{name}",
                "sprint_id": "sprint-manual-oracle-audit",
                "node_id": f"node-{action}",
                "mode": "fixture",
                "output_dir": f"artifacts/manual-oracle/{name}",
                "inputs": inputs,
                "outputs": {
                    "evidence_payload_path": f"artifacts/manual-oracle/{name}/{action}.evidence.json",
                    "result_path": f"artifacts/manual-oracle/{name}/{action}.result.json",
                    "evidence_jsonl": f"artifacts/manual-oracle/{name}/evidence.jsonl",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_rebuttal_nonfabrication(tmp_path: Path, run_id: str) -> None:
    review = tmp_path / f"{run_id}-review.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": f"review-{run_id}",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_available": True,
                        "review_mode": "review_llm",
                        "recommendation": "revise",
                        "evidence_ids": [f"review:{run_id}"],
                        "findings": [
                            {
                                "criterion": "evidence",
                                "issue": "The claimed improvement lacks a linked experiment result.",
                                "suggestion": "Add the exact experiment result or narrow the claim.",
                            }
                        ],
                        "review_llm": {"status": "completed"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    proc, summary = _run_shim(
        tmp_path,
        "$rebuttal",
        "review-comments",
        "--title",
        "Non-fabrication Audit",
        "--review-llm-evidence",
        str(review),
        "--run-id",
        run_id,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    evidence = _action_evidence(summary)
    files = evidence["outputs"]["bundle"]["files"]
    map_path = next(Path(str(tmp_path / item["path"])) for item in files if item["type"] == "rebuttal_response_map_json")
    response_map = json.loads(map_path.read_text(encoding="utf-8"))
    concern = response_map["mapped_concerns"][0]
    assert concern["mapping"]["evidence_status"] == "insufficient"
    assert concern["mapping"]["strategy"] == "B"
    assert "not sufficient" in concern["response"].lower()
    checks = {item["check"]: item["status"] for item in concern["safety_checks"]}
    assert checks["no_fabrication"] == "ok"
    assert checks["no_overpromise"] == "ok"


def test_rebuttal_slash_responses_avoid_fabricated_data_and_overpromises(tmp_path: Path) -> None:
    _assert_rebuttal_nonfabrication(tmp_path, "audit-rebuttal-slash-nonfabrication")


def test_draft_rebuttal_route_responses_avoid_fabricated_data_and_overpromises(tmp_path: Path) -> None:
    _assert_rebuttal_nonfabrication(tmp_path, "audit-rebuttal-route-nonfabrication")


def _assert_review_concrete_and_nonmutating(tmp_path: Path, run_id: str) -> None:
    wiki_root = tmp_path / "artifacts" / "autosci" / "workspace" / "wiki"
    target = wiki_root / "outputs" / f"{run_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Review Target\n\nMethod statement with a dataset and baseline.\n", encoding="utf-8")
    before = _sha(target)
    review = tmp_path / f"{run_id}-review.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": f"review-{run_id}",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "difficulty": "hard",
                        "focus": "method",
                        "score": 0.4,
                        "recommendation": "revise_required",
                        "evidence_ids": [f"review:{run_id}"],
                        "review_llm": {"status": "completed"},
                    },
                    "findings": [
                        {
                            "finding_id": f"{run_id}.ablation",
                            "severity": "high",
                            "category": "method",
                            "evidence": "The target names a baseline but provides no ablation result.",
                            "suggestion": "Add an ablation table with baseline, treatment, metric, and failure-mode columns.",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    proc, summary = _run_shim(
        tmp_path,
        "$review",
        run_id,
        "--from-wiki",
        "--difficulty",
        "hard",
        "--focus",
        "method",
        "--review-llm-evidence",
        str(review),
        "--run-id",
        run_id,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    evidence = _action_evidence(summary)
    assert _sha(target) == before
    finding = next(item for item in evidence["outputs"]["findings"] if item["finding_id"] == f"{run_id}.ablation")
    suggestion = finding["suggestion"].lower()
    assert "add" in suggestion and "ablation table" in suggestion and "metric" in suggestion


def test_review_slash_suggestions_are_concrete_and_do_not_mutate_target(tmp_path: Path) -> None:
    _assert_review_concrete_and_nonmutating(tmp_path, "audit-review-slash")


def test_review_artifact_route_suggestions_are_concrete_and_do_not_mutate_target(tmp_path: Path) -> None:
    _assert_review_concrete_and_nonmutating(tmp_path, "audit-review-route")


def test_each_literature_seed_mode_yields_ranked_candidates_with_channels_and_rationale(monkeypatch, tmp_path: Path) -> None:
    plugin = HARNESS / "plugins" / "autosci"
    sys.path.insert(0, str(plugin))
    from backends import literature_discover as ld  # type: ignore

    counter = {"value": 0}
    seen_negative: list[list[str]] = []

    def raw(channel: str = "mock") -> dict[str, object]:
        counter["value"] += 1
        n = counter["value"]
        return {
            "paperId": f"paper-{n}",
            "title": f"Candidate {n}",
            "abstract": "Evidence-grounded agent skill research.",
            "externalIds": {"ArXiv": f"2601.{n:05d}"},
            "citationCount": 10 + n,
            "year": 2026,
            "url": f"https://example.test/{channel}/{n}",
        }

    monkeypatch.setattr(ld, "HAS_REQUESTS", True)
    monkeypatch.setattr(ld, "_s2_search", lambda query, limit: [raw("topic")])

    def recommend(positive, negative, limit):
        seen_negative.append(list(negative))
        return [raw("recommend")]

    monkeypatch.setattr(ld, "_s2_recommend", recommend)
    monkeypatch.setattr(ld, "_s2_references", lambda anchor, limit: [])
    monkeypatch.setattr(ld, "_s2_citations", lambda anchor, limit: [])
    monkeypatch.setattr(ld.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        ld,
        "_venue_candidates",
        lambda venue, year, limit: [
            {
                "candidate_id": "arxiv:2601.99999",
                "arxiv_id": "2601.99999",
                "title": "Venue Candidate",
                "abstract": "Venue evidence.",
                "year": year,
                "venue": venue,
                "source_channels": ["paper_copilot"],
                "source_ref": "https://example.test/venue",
                "citation_count": 3,
            }
        ],
    )
    wiki = tmp_path / "wiki"
    (wiki / "papers").mkdir(parents=True)
    (wiki / "papers" / "seed.md").write_text("---\ntitle: Seed\narxiv: 2401.00001\n---\n", encoding="utf-8")
    common = {"limit": 3, "wiki_root": wiki, "workspace_root": tmp_path, "repository_root": HARNESS}
    results = [
        ld.discover_literature(mode="topic", query="agent skills", **common),
        ld.discover_literature(mode="anchors", anchors=["2401.00001"], negative_ids=["2401.99999"], **common),
        ld.discover_literature(mode="wiki", negative_ids=["2401.99999"], **common),
        ld.discover_literature(mode="venue", venue="neurips", year=2026, **common),
    ]
    assert seen_negative and all(items == ["2401.99999"] for items in seen_negative)
    for result in results:
        assert result["status"] == "completed"
        candidates = result["candidates"]
        assert candidates
        assert candidates == sorted(candidates, key=lambda item: item["ranking_score"], reverse=True)
        for candidate in candidates:
            assert candidate["source_channels"]
            assert isinstance(candidate["ranking_score"], (int, float))
            assert candidate["ranking_rationale"]


def _analyze_fixture(tmp_path: Path, name: str) -> dict[str, object]:
    proc, out = _run_bridge(tmp_path, "analyze_paper", FIXTURES / "envelope.analyze_paper.json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads((tmp_path / str(out["evidence_path"])).read_text(encoding="utf-8"))


def test_analysis_fields_are_populated_or_limitations_explain_incompleteness(tmp_path: Path) -> None:
    evidence = _analyze_fixture(tmp_path, "analysis-fields")
    paper = evidence["outputs"]["paper"]
    assert paper["paper_id"] and paper["title"] and paper["source_ref"]
    assert paper["sections"]
    analysis = paper.get("analysis") or {}
    assert analysis.get("summary") or evidence["limitations"]
    assert analysis.get("key_concepts") or evidence["limitations"]


def test_every_analysis_block_and_section_is_source_linked(tmp_path: Path) -> None:
    evidence = _analyze_fixture(tmp_path, "analysis-provenance")
    paper = evidence["outputs"]["paper"]
    analysis = paper["analysis"]
    assert paper["paper_id"] in analysis["evidence_ids"]
    assert paper["source_ref"] in analysis["evidence_ids"]
    assert all(section["source_anchor"] for section in paper["sections"])


def test_empty_paper_claim_extraction_returns_not_testable_evidence(tmp_path: Path) -> None:
    paper = tmp_path / "empty.md"
    paper.write_text("", encoding="utf-8")
    envelope = _write_envelope(tmp_path, "empty-claims", "extract_claims", {"paper_path": str(paper)})
    proc, out = _run_bridge(tmp_path, "extract_claims", envelope)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    evidence = json.loads((tmp_path / str(out["evidence_path"])).read_text(encoding="utf-8"))
    claim = evidence["outputs"]["claims"][0]
    assert claim["testability"] == "not_testable"
    assert "no grounded claim" in claim["text"].lower()
    assert claim["non_testable_reason"]
    assert claim["evidence_ids"]


def test_missing_method_reports_incomplete_without_inventing_procedure(tmp_path: Path) -> None:
    paper = tmp_path / "no-method.md"
    paper.write_text("# Descriptive Note\n\n## Background\n\nThis document only describes a historical context.\n", encoding="utf-8")
    envelope = _write_envelope(tmp_path, "missing-method", "extract_methods", {"paper_path": str(paper)})
    proc, out = _run_bridge(tmp_path, "extract_methods", envelope)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    evidence = json.loads((tmp_path / str(out["evidence_path"])).read_text(encoding="utf-8"))
    method = evidence["outputs"]["methods"][0]
    assert method["name"] == "No explicit method found"
    assert any("incomplete" in item.lower() for item in method["procedure"] + evidence["limitations"])


def test_generated_ideas_cite_source_evidence_and_explicit_gap_links(tmp_path: Path) -> None:
    for action, envelope in (
        ("ingest_paper", "envelope.ingest_paper.json"),
        ("extract_claims", "envelope.extract_claims.json"),
        ("extract_methods", "envelope.extract_methods.json"),
        ("generate_ideas", "envelope.generate_ideas.json"),
    ):
        proc, out = _run_bridge(tmp_path, action, FIXTURES / envelope)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    evidence = json.loads((tmp_path / "artifacts/scientific/smoke/idea_candidate.json").read_text(encoding="utf-8"))
    candidates = [item for item in evidence["outputs"]["ideas"] if item["duplicate_status"] == "new"]
    assert candidates
    for idea in candidates:
        assert idea["origin_evidence_ids"]
        gap_links = idea.get("gap_links") or idea.get("gap_ids") or idea.get("source_gap_ids")
        assert gap_links


def test_experiment_design_marks_review_evidence_absent_when_not_supplied(tmp_path: Path) -> None:
    proc, out = _run_bridge(tmp_path, "design_experiment", FIXTURES / "envelope.design_experiment.json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    evidence = json.loads((tmp_path / str(out["evidence_path"])).read_text(encoding="utf-8"))
    plan = evidence["outputs"]["experiment_plan"]
    assert plan["review_llm"]["status"] == "unavailable"
    assert any("not supplied" in item.lower() for item in evidence["limitations"])
    boundary = plan["source_context"]["final_execution_boundary"]
    assert boundary["review_llm_completed"] is False


def test_verify_claim_records_independent_review_disagreement_without_fabrication(tmp_path: Path) -> None:
    for action, fixture in (
        ("extract_claims", "envelope.extract_claims.json"),
        ("map_code_evidence", "envelope.map_code_evidence.json"),
        ("run_experiment", "envelope.run_experiment.fixture.json"),
    ):
        proc, out = _run_bridge(tmp_path, action, FIXTURES / fixture)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    review = tmp_path / "claim-disagreement-review.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-claim-disagreement",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "recommendation": "revise_required",
                        "evidence_ids": ["review:claim-disagreement"],
                        "review_llm": {"status": "completed"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    base = json.loads((FIXTURES / "envelope.verify_claim.supported.json").read_text(encoding="utf-8"))
    base["inputs"]["review_llm_evidence"] = str(review)
    envelope = tmp_path / "verify-disagreement.envelope.json"
    envelope.write_text(json.dumps(base), encoding="utf-8")
    proc, out = _run_bridge(tmp_path, "verify_claim", envelope)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    evidence = json.loads((tmp_path / str(out["evidence_path"])).read_text(encoding="utf-8"))
    verdict = evidence["outputs"]["verdicts"][0]
    assert verdict["verdict"] == "supported"
    assert verdict["review_llm"]["status"] == "completed"
    assert verdict["review_llm"]["recommendation"] == "revise_required"
    assert "review-claim-disagreement" in verdict["evidence_ids"]
    assert any("independent second opinion" in item for item in evidence["limitations"])


def test_plan_report_marks_invalid_review_evidence_inconclusive(tmp_path: Path) -> None:
    module_path = HARNESS / "plugins" / "autosci" / "tests" / "test_autosci_skill_shim.py"
    spec = importlib.util.spec_from_file_location("audit_autosci_skill_shim_tests", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.test_autosci_skill_shim_paper_plan_rejects_weak_review_llm_boundary(tmp_path)
