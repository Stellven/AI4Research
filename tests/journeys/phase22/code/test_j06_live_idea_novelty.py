from __future__ import annotations

import os
from pathlib import Path

import pytest

from evidence import JourneyRecorder
from journey_runner import action_evidence, load_json, run_autosci, write_demo_paper


def test_p22_j06_live_idea_generation_and_novelty(repo_root: Path, tmp_path: Path) -> None:
    if os.environ.get("P22_J06_LIVE_NOVELTY") != "1":
        pytest.skip("Set P22_J06_LIVE_NOVELTY=1 to run the public live-provider journey.")

    rec = JourneyRecorder(repo_root, "P22-J06")
    sandbox = tmp_path / "p22-j06-live"
    paper = write_demo_paper(sandbox / "raw" / "phase22-paper.md")
    ingest, _ = run_autosci(
        rec,
        sandbox,
        "ingest",
        ["--paper", str(paper), "--run-id", "p22-j06-live-ingest"],
        timeout=90,
    )
    ideate, _ = run_autosci(
        rec,
        sandbox,
        "ideate",
        [
            "verifier-guided skill learning",
            "--paper",
            str(paper),
            "--from-wiki",
            "--max-ideas",
            "1",
            "--run-id",
            "p22-j06-live-ideate",
        ],
        timeout=90,
    )
    ideas_path = action_evidence(ideate, "generate_ideas")
    ideas_payload = load_json(ideas_path) if ideas_path else {}
    ideas = ideas_payload.get("outputs", {}).get("ideas", [])
    selected = [idea for idea in ideas if idea.get("selected_for_write") is True]
    deferred = [idea for idea in ideas if idea.get("selected_for_write") is False]
    target = str((selected[0] if selected else ideas[0] if ideas else {}).get("title") or "verifier-guided skill learning")

    novelty, _ = run_autosci(
        rec,
        sandbox,
        "novelty",
        [target, "--from-wiki", "--online", "--run-id", "p22-j06-live-novelty"],
        timeout=120,
        allow_live=True,
    )
    novelty_path = action_evidence(novelty, "evaluate_ideas")
    novelty_payload = load_json(novelty_path) if novelty_path else {}
    evaluations = novelty_payload.get("outputs", {}).get("evaluations", [])
    evaluation = evaluations[0] if evaluations else {}
    external = evaluation.get("external_novelty", {})
    provenance = external.get("provenance", {})
    proof_artifact = next(
        (
            item
            for item in novelty_payload.get("artifacts", [])
            if item.get("type") == "provider_source_runtime_proof_manifest_json"
        ),
        {},
    )
    proof_path = sandbox / "harness" / str(proof_artifact.get("path") or "missing-runtime-proof")
    completed_providers = [
        item for item in external.get("provider_statuses", []) if item.get("status") == "completed"
    ]

    if ideas_path:
        rec.add_artifact(ideas_path, "generated_ranked_ideas")
    if novelty_path:
        rec.add_artifact(novelty_path, "live_provider_novelty")
    if proof_path.is_file():
        rec.add_artifact(proof_path, "live_provider_runtime_proof")
    rec.add_assertion("ingest_completed", not ingest.get("_error"), ingest.get("_error"))
    rec.add_assertion("ideate_completed", not ideate.get("_error"), ideate.get("_error"))
    rec.add_assertion("at_least_two_candidates_generated", len(ideas) >= 2, len(ideas))
    rec.add_assertion(
        "multiple_generation_paths",
        len({str(idea.get("generation_path") or "") for idea in ideas}) >= 2,
        [idea.get("generation_path") for idea in ideas],
    )
    rec.add_assertion(
        "all_candidates_are_source_backed",
        bool(ideas) and all(idea.get("origin_evidence_ids") for idea in ideas),
        [idea.get("origin_evidence_ids") for idea in ideas],
    )
    rec.add_assertion(
        "bounded_selection_and_rank_recorded",
        len(selected) == 1 and selected[0].get("selection_rank") == 1,
        {"selected": [idea.get("idea_id") for idea in selected], "ranks": [idea.get("selection_rank") for idea in ideas]},
    )
    rec.add_assertion(
        "deferred_candidate_has_reason",
        bool(deferred) and all(idea.get("selection_reason") for idea in deferred),
        [{"idea_id": idea.get("idea_id"), "reason": idea.get("selection_reason")} for idea in deferred],
    )
    rec.add_assertion("live_novelty_completed", not novelty.get("_error") and external.get("status") == "completed", external)
    rec.add_assertion("live_source_count_positive", int(external.get("source_count") or 0) >= 1, external.get("source_count"))
    rec.add_assertion("provider_provenance_passed", provenance.get("status") == "passed", provenance)
    rec.add_assertion(
        "provider_runtime_proof_persisted",
        proof_path.is_file(),
        {"type": proof_artifact.get("type"), "path": str(proof_path)},
    )
    rec.add_assertion(
        "raw_provider_payload_archived",
        bool(completed_providers)
        and all(item.get("raw_payload_archive_status") == "completed" for item in completed_providers),
        completed_providers,
    )
    rec.add_assertion(
        "external_prior_work_used_in_novelty",
        any(str(item.get("source_id") or "").startswith("external:") for item in evaluation.get("closest_prior_work", [])),
        evaluation.get("closest_prior_work", []),
    )
    rec.add_l2(
        "Workflow",
        "Idea Generation",
        "source-backed candidates were generated through multiple paths, bounded, ranked, and checked against live literature",
        novelty_path or rec.run_dir,
        True,
    )
    rec.finalize(
        "PASS_WITH_KNOWN_LIMITATIONS" if all(item["passed"] for item in rec.assertions) else "FAIL",
        limitations=[
            "Live provider novelty is screening evidence, not final human acceptance or an independent Review LLM decision."
        ],
    )
