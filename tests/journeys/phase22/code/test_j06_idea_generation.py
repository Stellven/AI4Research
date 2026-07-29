from __future__ import annotations

from pathlib import Path

from evidence import JourneyRecorder
from journey_runner import action_evidence, load_json, run_autosci, write_demo_paper


def _tokens(text: str) -> set[str]:
    return {token for token in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(token) > 3}


def _semantically_distinct(ideas: list[dict]) -> bool:
    signatures = []
    for idea in ideas:
        text = f"{idea.get('title', '')} {idea.get('hypothesis', '')} {idea.get('approach', '')}"
        signatures.append(_tokens(text))
    for idx, left in enumerate(signatures):
        for right in signatures[idx + 1 :]:
            if not left or not right:
                continue
            overlap = len(left & right) / max(1, min(len(left), len(right)))
            if overlap < 0.75:
                return True
    return False


def _missing_card_fields(idea: dict) -> list[str]:
    required_groups = {
        "risk": ("risk", "risks", "limitations", "blocking_reasons"),
        "falsifiability": ("falsifiability", "falsifiable", "testability"),
        "validation": ("validation", "validation_plan", "evaluation", "review_plan"),
        "minimum_experiment": ("minimum_experiment", "min_experiment", "pilot", "experiment_plan"),
    }
    missing = []
    text_blob = " ".join(str(value).lower() for value in idea.values() if isinstance(value, str))
    for label, keys in required_groups.items():
        if not any(idea.get(key) for key in keys) and label not in text_blob:
            missing.append(label)
    return missing


def _has_verification_contract(idea: dict) -> bool:
    text_blob = " ".join(str(value).lower() for value in idea.values() if isinstance(value, str))
    has_test_signal = any(
        phrase in text_blob
        for phrase in (
            "measure",
            "measurable",
            "falsif",
            "success condition",
            "minimum experiment",
            "pilot",
            "threshold",
        )
    )
    return has_test_signal and not _missing_card_fields(idea)


def test_p22_j06_idea_generation(repo_root: Path, tmp_path: Path) -> None:
    rec = JourneyRecorder(repo_root, "P22-J06")
    sandbox = tmp_path / "p22-j06"
    paper = write_demo_paper(sandbox / "raw" / "phase22-paper.md")
    ingest, _ = run_autosci(rec, sandbox, "ingest", ["--paper", str(paper), "--run-id", "p22-j06-ingest"], timeout=90)
    summary, _ = run_autosci(
        rec,
        sandbox,
        "ideate",
        ["verifier-guided skill learning", "--paper", str(paper), "--from-wiki", "--max-ideas", "3", "--run-id", "p22-j06-ideate"],
        timeout=90,
    )
    ideas_ev = action_evidence(summary, "generate_ideas")
    evaluation_ev = action_evidence(summary, "evaluate_ideas")
    first_idea = "idea-001"
    ideas_payload = {}
    ideas = []
    if ideas_ev:
        ideas_payload = load_json(ideas_ev)
        ideas = ideas_payload.get("outputs", {}).get("ideas", [])
        if ideas and ideas[0].get("idea_id"):
            first_idea = str(ideas[0]["idea_id"])
        rec.add_artifact(ideas_ev, "generated_ideas")
    if evaluation_ev:
        rec.add_artifact(evaluation_ev, "local_idea_evaluation")
        evaluation_payload = load_json(evaluation_ev)
    else:
        evaluation_payload = {}
    novelty, _ = run_autosci(
        rec,
        sandbox,
        "novelty",
        [first_idea, "--from-wiki", "--run-id", "p22-j06-novelty-local"],
        timeout=90,
    )
    novelty_ev = action_evidence(novelty, "evaluate_ideas")
    novelty_payload = load_json(novelty_ev) if novelty_ev else {}
    if novelty_ev:
        rec.add_artifact(novelty_ev, "local_novelty_evaluation")
    evaluations = evaluation_payload.get("outputs", {}).get("evaluations", [])
    novelty_evaluations = novelty_payload.get("outputs", {}).get("evaluations", [])
    selected_idea_ids = [idea.get("idea_id") for idea in ideas if idea.get("selected_for_write")]
    rec.add_assertion("ingest_available", not ingest.get("_error"), ingest.get("_error"))
    rec.add_assertion("ideate_completed", not summary.get("_error"), summary.get("_error"))
    rec.add_assertion("generated_source_backed_ideas", ideas_ev is not None, summary.get("_error"))
    rec.add_assertion("at_least_two_ideas", len(ideas) >= 2, len(ideas))
    rec.add_assertion(
        "ideas_semantically_distinct",
        _semantically_distinct(ideas),
        [{"idea_id": idea.get("idea_id"), "title": idea.get("title")} for idea in ideas],
    )
    rec.add_assertion(
        "each_idea_has_hypothesis_and_source_evidence",
        bool(ideas)
        and all(
            bool(idea.get("hypothesis"))
            and (bool(idea.get("origin_evidence_ids")) or bool(idea.get("grounding_summary")))
            for idea in ideas
        ),
        [
            {
                "idea_id": idea.get("idea_id"),
                "has_hypothesis": bool(idea.get("hypothesis")),
                "has_source_evidence": bool(idea.get("origin_evidence_ids")) or bool(idea.get("grounding_summary")),
            }
            for idea in ideas
        ],
    )
    rec.add_assertion("local_novelty_or_evaluation_recorded", novelty_ev is not None or evaluation_ev is not None, novelty.get("_error"))
    rec.add_assertion(
        "evaluation_contains_novelty_and_feasibility",
        bool(evaluations)
        and all("novelty" in item and "feasibility" in item and item.get("recommendation") for item in evaluations),
        [
            {
                "idea_id": item.get("idea_id"),
                "novelty": item.get("novelty"),
                "feasibility": item.get("feasibility"),
                "recommendation": item.get("recommendation"),
            }
            for item in evaluations
        ],
    )
    rec.add_assertion(
        "selection_rationale_consistent_with_evaluation",
        bool(selected_idea_ids)
        and bool(evaluations)
        and any(item.get("idea_id") in selected_idea_ids for item in evaluations),
        {"selected_idea_ids": selected_idea_ids, "evaluated_idea_ids": [item.get("idea_id") for item in evaluations]},
    )
    rec.add_assertion(
        "at_least_one_verification_ready_card",
        any(_has_verification_contract(idea) for idea in ideas),
        [
            {
                "idea_id": idea.get("idea_id"),
                "missing_card_fields": _missing_card_fields(idea),
                "title": idea.get("title"),
            }
            for idea in ideas
        ],
    )
    rec.add_l2("Workflow", "Idea Identification", "offline local paper/wiki evidence produced candidate ideas", ideas_ev or rec.run_dir, "partial")
    rec.add_l2("Workflow", "Candidate Consolidation", "duplicate status and source grounding were recorded for generated candidates", ideas_ev or rec.run_dir, "partial")
    rec.add_l2("Workflow", "Idea Card Formation", "generated candidates include title, hypothesis, approach, and grounding, but verification-card fields are incomplete", ideas_ev or rec.run_dir, "partial")
    rec.add_l2("Workflow", "Opportunity Portfolio Prioritization", "local novelty/feasibility evaluation assigned recommendation and rank evidence", evaluation_ev or rec.run_dir, "partial")
    rec.add_l2("Workflow", "Research Question & Technical Claim Formation", "candidate hypotheses were generated from the ingested paper evidence", ideas_ev or rec.run_dir, "partial")
    rec.add_l2("Workflow", "Claim, Evidence, Data & Method Modeling", "candidate origin evidence IDs and method/paper evidence inputs were recorded", ideas_ev or rec.run_dir, "partial")
    rec.add_l2("Workflow", "Falsifiability Screening & Hypothesis Contracting", "test asserts verification-ready fields; current candidates lack complete falsifiability contracts", ideas_ev or rec.run_dir, False)
    rec.add_l2("Workflow", "Verification-Ready POC Design", "test asserts minimum-experiment fields; current candidates lack complete local POC design", ideas_ev or rec.run_dir, False)
    rec.add_l2("Foundation", "Capability Discovery, Scoring & Selection", "local evaluation scored novelty/feasibility and selected candidate ids", evaluation_ev or novelty_ev or rec.run_dir, "partial")
    limitations = [
        "Live literature discovery and provider-backed novelty were not run in this repair batch; offline local evidence only checks basic idea generation."
    ]
    if novelty_evaluations and not all(
        item.get("final_acceptance_boundary", {}).get("final_acceptance_ready") for item in novelty_evaluations
    ):
        limitations.append("Novelty final acceptance is incomplete because external novelty and Review LLM evidence are unavailable.")
    card_gaps = {str(idea.get("idea_id") or idx): _missing_card_fields(idea) for idx, idea in enumerate(ideas, start=1)}
    card_gaps = {idea_id: gaps for idea_id, gaps in card_gaps.items() if gaps}
    if card_gaps:
        limitations.append(f"Generated idea cards are incomplete for risk/falsifiability/validation/minimum-experiment fields: {card_gaps}.")
    status = "PASS_WITH_KNOWN_LIMITATIONS" if all(item["passed"] for item in rec.assertions) else "FAIL"
    rec.finalize(status, limitations=limitations)
