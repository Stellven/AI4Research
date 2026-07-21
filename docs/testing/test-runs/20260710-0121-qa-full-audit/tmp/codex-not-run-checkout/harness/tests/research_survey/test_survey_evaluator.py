from __future__ import annotations

import json
import os
import sys

_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research.survey.evaluator import evaluate_survey
from research.survey.evidence_pack import build_evidence_packs
from research.survey.planner import create_survey_plan, write_survey_plan
from research.survey.section_compiler import compile_section, compile_survey


def _append_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _strong_sources():
    return [
        {"id": "src_0", "source_type": "paper", "title": "Latent Reasoning Paper", "url": "https://arxiv.org/abs/2412.06769"},
        {"id": "src_1", "source_type": "paper", "title": "Continuous Thought Paper", "url": "https://openreview.net/forum?id=latent-reasoning"},
        {"id": "src_2", "source_type": "paper", "title": "Reasoning Survey Proceedings", "url": "https://doi.org/10.1145/latent-reasoning"},
        {"id": "src_3", "source_type": "paper", "title": "Neural Computation Journal Article", "url": "https://ieeexplore.ieee.org/document/123456"},
        {"id": "src_4", "source_type": "official_doc", "title": "Official Developer Docs", "url": "https://docs.example.edu/latent-reasoning"},
        {"id": "src_5", "source_type": "code", "title": "Latent Reasoning Repository", "url": "https://github.com/example/latent-reasoning"},
        {"id": "src_6", "source_type": "benchmark", "title": "Latent Reasoning Benchmark", "url": "https://paperswithcode.com/task/latent-reasoning"},
        {"id": "src_7", "source_type": "benchmark", "title": "Hugging Face Evaluation Dataset", "url": "https://huggingface.co/datasets/example/latent-reasoning"},
    ]


def test_strict_eval_fails_five_section_brief(tmp_path):
    ast = {
        "title": "brief",
        "chapters": [{"chapter_id": "ch1", "title": "Brief"}],
        "sections": [{"section_id": f"ch1/sec{i}", "chapter_id": "ch1", "title": f"S{i}"} for i in range(5)],
    }
    (tmp_path / "survey_report_ast.json").write_text(json.dumps(ast), encoding="utf-8")
    (tmp_path / "survey_evidence_packs.json").write_text(json.dumps({"blocked": 0}), encoding="utf-8")
    result = evaluate_survey(tmp_path, strict=True)
    assert result["ok"] is False
    assert "chapter_count_low:1<8" in result["scorecard"]["issues"]
    assert "section_count_low:5<30" in result["scorecard"]["issues"]


def test_strict_eval_passes_controlled_strong_fixture(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(40)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(40)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(40)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    for section in plan["report_ast"]["sections"][:3]:
        compile_section(tmp_path, section["section_id"])
    compile_survey(tmp_path)
    result = evaluate_survey(tmp_path, strict=True)
    assert result["ok"] is True
    assert result["scorecard"]["chapter_count"] >= 8
    assert result["scorecard"]["section_count"] >= 30
    assert result["coverage"]["source_type_count"] == 4
    assert result["coverage"]["claim_support_coverage"] == 1.0
    assert result["taxonomy"]["taxonomy_depth_score"] >= 0.75
    assert result["contradiction_matrix"]["contradiction_coverage"] >= 0.80
    assert result["section_factual_audit"]["section_factual_accuracy"] == 1.0
    assert result["section_factual_audit"]["section_grounding_accuracy"] == 1.0
    assert result["section_scorecard"]["ok"] is True
    assert result["section_scorecard"]["needs_rewrite_count"] == 0
    assert result["chief_editor_review"]["ok"] is True
    assert result["depth_profile"]["ok"] is True
    assert (tmp_path / "survey_chief_editor.json").exists()
    assert (tmp_path / "survey_depth_profile.json").exists()


def test_strict_eval_fails_when_claims_have_no_evidence_links(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(40)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(40)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", [])
    build_evidence_packs(tmp_path, plan["report_ast"])
    for section in plan["report_ast"]["sections"][:3]:
        compile_section(tmp_path, section["section_id"])
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True)
    assert result["ok"] is False
    assert "claim_support_coverage_low:0.0000<0.8000" in result["scorecard"]["issues"]


def test_strict_eval_fails_when_source_types_are_too_narrow(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = [{"id": "src_0", "source_type": "paper", "title": "paper", "url": "https://arxiv.org/abs/0000.00000"}]
    evidence = [{"id": f"ev_{i}", "source_id": "src_0", "content": "latent reasoning architecture evaluation deployment"} for i in range(40)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(40)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(40)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True)
    assert result["ok"] is False
    assert "source_type_count_low:1<4" in result["scorecard"]["issues"]


def test_strict_eval_fails_when_taxonomy_is_shallow(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    for chapter in plan["report_ast"]["chapters"]:
        chapter["title"] = "General Notes"
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(40)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(40)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(40)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    for section in plan["report_ast"]["sections"][:3]:
        compile_section(tmp_path, section["section_id"])
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True)
    assert result["ok"] is False
    assert any(item.startswith("taxonomy_depth_score_low:") for item in result["scorecard"]["issues"])


def test_strict_eval_fails_when_contradiction_slots_are_missing(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(40)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(40)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(40)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    packs = build_evidence_packs(tmp_path, plan["report_ast"])
    for pack in packs["packs"]:
        pack["contradiction_slots"] = []
        section_pack = tmp_path / "sections" / pack["section_id"] / "evidence_pack.json"
        section_pack.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "survey_evidence_packs.json").write_text(json.dumps(packs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for section in plan["report_ast"]["sections"][:3]:
        compile_section(tmp_path, section["section_id"])
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True)
    assert result["ok"] is False
    assert "contradiction_coverage_low:0.0000<0.8000" in result["scorecard"]["issues"]


def test_strict_eval_fails_when_section_references_out_of_pack_claim(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(40)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(40)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(40)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    for section in plan["report_ast"]["sections"][:3]:
        compile_section(tmp_path, section["section_id"])
    bad_final = tmp_path / "sections" / plan["report_ast"]["sections"][0]["section_id"] / "final.md"
    bad_final.write_text(
        bad_final.read_text(encoding="utf-8") + "\n\nInvalid unsupported claim [claim:cl_not_in_pack] [evidence:ev_not_in_pack]\n",
        encoding="utf-8",
    )
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True)
    assert result["ok"] is False
    assert "section_factual_accuracy_low:0.6667<0.9500" in result["scorecard"]["issues"]
    failed = result["section_factual_audit"]["failed_sections"]
    assert failed[0]["unknown_claim_ids"] == ["cl_not_in_pack"]
    assert failed[0]["unknown_evidence_ids"] == ["ev_not_in_pack"]
    top = result["section_scorecard"]["top_issues"][0]
    assert top["section_id"] == plan["report_ast"]["sections"][0]["section_id"]
    assert top["p0_count"] >= 2
    assert top["rewrite_recommended"] is True


def test_strict_eval_fails_when_section_has_no_claim_or_evidence_tags(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(40)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(40)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(40)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    for section in plan["report_ast"]["sections"][:3]:
        compile_section(tmp_path, section["section_id"])
    bad_final = tmp_path / "sections" / plan["report_ast"]["sections"][0]["section_id"] / "final.md"
    bad_final.write_text("A polished section with no factual tags.\n", encoding="utf-8")
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True)
    assert result["ok"] is False
    failed = result["section_factual_audit"]["failed_sections"]
    assert failed[0]["missing_claim_tags"] is True
    assert failed[0]["missing_evidence_tags"] is True


def test_strict_eval_fails_when_evidence_tag_context_is_not_grounded(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(40)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(40)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(40)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    for section in plan["report_ast"]["sections"][:3]:
        compile_section(tmp_path, section["section_id"])
    section_id = plan["report_ast"]["sections"][0]["section_id"]
    pack = json.loads((tmp_path / "sections" / section_id / "evidence_pack.json").read_text(encoding="utf-8"))
    allowed_claim = pack["claim_ids"][0]
    allowed_evidence = pack["evidence_ids"][0]
    bad_final = tmp_path / "sections" / section_id / "final.md"
    bad_final.write_text(
        f"# Bad Section\n\n## Claim\n\nBanana ocean unrelated sentence [claim:{allowed_claim}] [evidence:{allowed_evidence}]\n",
        encoding="utf-8",
    )
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True)
    assert result["ok"] is False
    assert "section_grounding_accuracy_low:0.6667<0.9500" in result["scorecard"]["issues"]
    failed = result["section_factual_audit"]["failed_sections"]
    assert failed[0]["grounding_failures"][0]["reason"] == "citation_context_not_grounded"
    assert result["section_scorecard"]["top_issues"][0]["issues"][0]["severity"] == "P0"


def test_section_scorecard_ranks_rewrite_candidates(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(40)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(40)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(40)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    for section in plan["report_ast"]["sections"][:3]:
        compile_section(tmp_path, section["section_id"])
    first = plan["report_ast"]["sections"][0]["section_id"]
    second = plan["report_ast"]["sections"][1]["section_id"]
    (tmp_path / "sections" / first / "final.md").write_text("No tags here.\n", encoding="utf-8")
    review = tmp_path / "sections" / second / "review.json"
    data = json.loads(review.read_text(encoding="utf-8"))
    data["issues"] = ["section_structure_shallow:3<6"]
    review.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True)
    top = result["section_scorecard"]["top_issues"]
    assert top[0]["section_id"] == first
    assert top[0]["p0_count"] == 2
    assert top[0]["risk_score"] > top[1]["risk_score"]


def test_complete_professor_gate_rejects_tiny_tagged_sections(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(80)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(80)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(80)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    for section in plan["report_ast"]["sections"]:
        section_id = section["section_id"]
        pack = json.loads((tmp_path / "sections" / section_id / "evidence_pack.json").read_text(encoding="utf-8"))
        claim_id = pack["claim_ids"][0]
        evidence_id = pack["evidence_ids"][0]
        final = tmp_path / "sections" / section_id / "final.md"
        final.write_text(
            f"# Tiny\n\n## Claim\n\nlatent reasoning architecture evaluation deployment [claim:{claim_id}] [evidence:{evidence_id}]\n",
            encoding="utf-8",
        )
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True, require_complete=True)
    assert result["ok"] is False
    assert result["final_quality"]["ok"] is False
    assert any(item.startswith("final_char_count_low:") for item in result["scorecard"]["issues"])
    assert any(item.startswith("avg_section_chars_low:") for item in result["scorecard"]["issues"])


def test_strict_eval_fails_low_authority_web_heavy_sources(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = [
        {"id": f"src_{i}", "source_type": "web", "title": f"SEO blog {i}", "url": f"https://blog.example.com/latent-{i}"}
        for i in range(12)
    ]
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(80)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(80)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(80)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True)
    assert result["ok"] is False
    assert result["source_coverage"]["ok"] is False
    assert any(item.startswith("survey_missing_required_source_types:") for item in result["scorecard"]["issues"])
    assert any(item.startswith("low_value_source_ratio_high:") for item in result["scorecard"]["issues"])


def test_chief_editor_gate_flags_duplicate_complete_sections(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [{"id": f"ev_{i}", "source_id": sources[i % len(sources)]["id"], "content": "latent reasoning architecture evaluation deployment"} for i in range(80)]
    claims = [{"id": f"cl_{i}", "claim_text": "latent reasoning architecture requires evaluation evidence"} for i in range(80)]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(80)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    duplicate_body = "# Duplicate\n\n## Claim\n\nlatent reasoning architecture evaluation deployment [claim:{claim_id}] [evidence:{evidence_id}]\n"
    for section in plan["report_ast"]["sections"]:
        section_id = section["section_id"]
        pack = json.loads((tmp_path / "sections" / section_id / "evidence_pack.json").read_text(encoding="utf-8"))
        final = tmp_path / "sections" / section_id / "final.md"
        final.write_text(duplicate_body.format(claim_id=pack["claim_ids"][0], evidence_id=pack["evidence_ids"][0]), encoding="utf-8")
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True, require_complete=True)
    assert result["ok"] is False
    assert result["chief_editor_review"]["ok"] is False
    assert any(item.startswith("chief_editor_section_duplicate_rate_high:") for item in result["scorecard"]["issues"])


def test_final_quality_flags_repeated_long_sentences_across_complete_report(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [
        {
            "id": f"ev_{i}",
            "source_id": sources[i % len(sources)]["id"],
            "content": "latent reasoning architecture evaluation deployment hidden state planning explicit verbalization benchmark coverage implementation constraints",
        }
        for i in range(96)
    ]
    claims = [
        {
            "id": f"cl_{i}",
            "claim_text": f"latent reasoning architecture claim {i} requires evaluation evidence and implementation constraints",
        }
        for i in range(96)
    ]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(96)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    repeated = (
        "Latent reasoning architecture evaluation deployment requires a balanced analysis of hidden state planning, "
        "explicit verbalization, benchmark coverage, and implementation constraints."
    )
    for section in plan["report_ast"]["sections"]:
        section_id = section["section_id"]
        pack = json.loads((tmp_path / "sections" / section_id / "evidence_pack.json").read_text(encoding="utf-8"))
        claim_ids = pack["claim_ids"][:3]
        evidence_ids = pack["evidence_ids"][:4]
        final = tmp_path / "sections" / section_id / "final.md"
        final.write_text(
            f"# {section['title']}\n\n"
            "## Research Question\n\n"
            f"{section['research_question']}\n\n"
            "## Position\n\n"
            f"{repeated} [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}]\n\n"
            "## Claim Map\n\n"
            f"1. Section-specific claim for {section_id} [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}]\n"
            f"2. Section-specific implementation constraint {section_id} [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}]\n"
            f"3. Section-specific evaluation boundary {section_id} [claim:{claim_ids[2]}] [evidence:{evidence_ids[2]}]\n\n"
            "## Evidence Map\n\n"
            f"- Evidence for architecture evaluation deployment {section_id} [evidence:{evidence_ids[0]}]\n"
            f"- Evidence for hidden state planning {section_id} [evidence:{evidence_ids[1]}]\n"
            f"- Evidence for benchmark coverage {section_id} [evidence:{evidence_ids[2]}]\n"
            f"- Evidence for implementation constraints {section_id} [evidence:{evidence_ids[3]}]\n\n"
            "## Source Map\n\n"
            "The section uses paper, official, code, and benchmark sources.\n\n"
            "## Architecture Synthesis\n\n"
            f"{repeated} This unique section {section_id} ties the repeated frame to a local architectural decision. "
            "The analysis expands the design axis, runtime implications, and evaluation constraints with grounded evidence.\n\n"
            "## Comparative Positioning\n\n"
            f"Compared with token-only chain-of-thought, section {section_id} separates latent search, explicit narration, and benchmark-facing outputs.\n\n"
            "## Evaluation And Risk Boundary\n\n"
            f"Evaluation for {section_id} must separate benchmark gains, hidden-state opacity, and reproducibility constraints. [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}]\n\n"
            "## Limitations And Failure Modes\n\n"
            f"Failure modes for {section_id} include hidden-state drift, unverifiable reasoning traces, and benchmark overfitting. [claim:{claim_ids[2]}] [evidence:{evidence_ids[2]}]\n\n"
            "## Contradiction Slots\n\n"
            f"Contradiction slot for {section_id}: latent compression can improve compute efficiency while reducing interpretability. [evidence:{evidence_ids[3]}]\n\n"
            "## Open Problems\n\n"
            f"Open problems for {section_id} include controllable latent planning, robust evaluation, and reproducible implementation contracts.\n",
            encoding="utf-8",
        )
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True, require_complete=True)
    assert result["ok"] is False
    assert result["final_quality"]["ok"] is False
    assert result["final_quality"]["max_duplicate_long_sentence_count"] >= 8
    assert any(item.startswith("final_duplicate_sentence_count_high:") for item in result["scorecard"]["issues"])


def test_depth_profile_rejects_long_but_shallow_complete_survey(tmp_path):
    plan = create_survey_plan("latent reasoning", target_chars=50000)
    write_survey_plan(plan, tmp_path)
    sources = _strong_sources()
    evidence = [
        {
            "id": f"ev_{i}",
            "source_id": sources[i % len(sources)]["id"],
            "content": "latent reasoning architecture evaluation deployment evidence supports source-specific claims",
        }
        for i in range(96)
    ]
    claims = [
        {
            "id": f"cl_{i}",
            "claim_text": "latent reasoning architecture evaluation deployment requires evidence",
        }
        for i in range(96)
    ]
    links = [{"claim_id": f"cl_{i}", "evidence_id": f"ev_{i}"} for i in range(96)]
    _append_jsonl(tmp_path / "sources.jsonl", sources)
    _append_jsonl(tmp_path / "evidence.jsonl", evidence)
    _append_jsonl(tmp_path / "claims.jsonl", claims)
    _append_jsonl(tmp_path / "claim_evidence.jsonl", links)
    build_evidence_packs(tmp_path, plan["report_ast"])
    for section in plan["report_ast"]["sections"]:
        section_id = section["section_id"]
        pack = json.loads((tmp_path / "sections" / section_id / "evidence_pack.json").read_text(encoding="utf-8"))
        claim_ids = pack["claim_ids"][:3]
        evidence_ids = pack["evidence_ids"][:4]
        def shallow_sentence(label: str, idx: int) -> str:
            return (
                f"latent reasoning architecture evaluation deployment evidence section {section_id} "
                f"uses source-specific wording for {label} detail {idx} while still remaining shallow."
            )

        def shallow_block(label: str, count: int) -> str:
            return " ".join(shallow_sentence(label, idx) for idx in range(1, count + 1))

        final = tmp_path / "sections" / section_id / "final.md"
        final.write_text(
            f"# {section['title']}\n\n"
            "## Research Question\n\n"
            f"{section['research_question']}\n\n"
            "## Position\n\n"
            f"{shallow_block('position', 4)} [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}]\n\n"
            "## Claim Map\n\n"
            f"1. {shallow_sentence('claim', 1)} [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}]\n"
            f"2. {shallow_sentence('claim', 2)} [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}]\n"
            f"3. {shallow_sentence('claim', 3)} [claim:{claim_ids[2]}] [evidence:{evidence_ids[2]}]\n\n"
            "## Evidence Map\n\n"
            f"- {shallow_sentence('evidence', 1)} [evidence:{evidence_ids[0]}]\n"
            f"- {shallow_sentence('evidence', 2)} [evidence:{evidence_ids[1]}]\n"
            f"- {shallow_sentence('evidence', 3)} [evidence:{evidence_ids[2]}]\n"
            f"- {shallow_sentence('evidence', 4)} [evidence:{evidence_ids[3]}]\n\n"
            "## Source Map\n\n"
            f"Source families for {section_id} are listed as paper, official, code, and benchmark evidence without additional synthesis claims.\n\n"
            "## Architecture Synthesis\n\n"
            f"{shallow_block('architecture', 3)} [claim:{claim_ids[0]}] [evidence:{evidence_ids[0]}]\n\n"
            "## Comparative Positioning\n\n"
            f"{shallow_block('comparison', 3)} [claim:{claim_ids[1]}] [evidence:{evidence_ids[1]}]\n\n"
            "## Evaluation And Risk Boundary\n\n"
            f"{shallow_block('evaluation', 3)} [claim:{claim_ids[2]}] [evidence:{evidence_ids[2]}]\n\n"
            "## Limitations And Failure Modes\n\n"
            f"{shallow_block('limitations', 3)} [claim:{claim_ids[2]}] [evidence:{evidence_ids[2]}]\n\n"
            "## Contradiction Slots\n\n"
            f"{shallow_block('contradiction', 2)} [evidence:{evidence_ids[3]}]\n\n"
            "## Open Problems\n\n"
            f"{shallow_block('open-problems', 2)}\n",
            encoding="utf-8",
        )
    compile_survey(tmp_path)

    result = evaluate_survey(tmp_path, strict=True, require_complete=True)
    assert result["ok"] is False
    assert result["depth_profile"]["ok"] is False
    assert result["final_quality"]["ok"] is True
    assert any(item.startswith("depth_academic_marker_variety_low:") for item in result["scorecard"]["issues"])
    assert any(item.startswith("depth_terminology_variant_count_low:") for item in result["scorecard"]["issues"])
