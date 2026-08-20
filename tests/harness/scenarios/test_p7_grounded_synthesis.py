"""P7 R3: compile verified source packs into a topic-general grounded report."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import research.grounded_synthesis as grounded_synthesis  # noqa: E402
import research.evaluator as research_evaluator  # noqa: E402
from research.evaluator import evaluate_final_closeout  # noqa: E402
from research.grounded_synthesis import GroundedSynthesisError, compile_grounded_report  # noqa: E402
from research.source_pack import write_source_pack  # noqa: E402
from research.sources.base import FetchResult  # noqa: E402


def _write_pack(root: Path, *, source_id: str, title: str, url: str, text: str) -> tuple[Path, str]:
    write_source_pack(
        root,
        [
            FetchResult(
                source_id=source_id,
                connector_id="codex_live_search",
                title=title,
                raw_text=text,
                source_url=url,
                metadata={"source_type": "official_doc"},
            )
        ],
    )
    evidence = json.loads((root / "evidence.jsonl").read_text(encoding="utf-8").strip())
    return root, evidence["id"]


def _fixture(tmp_path: Path) -> tuple[list[Path], dict]:
    pack_a, ev_a = _write_pack(
        tmp_path / "pack-a",
        source_id="github_copilot_docs",
        title="GitHub Copilot official feature documentation",
        url="https://docs.github.com/en/copilot/about-github-copilot",
        text=(
            "GitHub Copilot official documentation describes AI coding assistance, inline code completion, "
            "chat, and integrations with supported development environments. The documentation explains "
            "product capabilities and configuration, but it does not provide an independent benchmark proving "
            "that GitHub Copilot is universally better than every competing coding assistant."
        ),
    )
    pack_b, ev_b = _write_pack(
        tmp_path / "pack-b",
        source_id="cursor_docs",
        title="Cursor official feature documentation",
        url="https://docs.cursor.com/get-started/concepts",
        text=(
            "Cursor official documentation describes AI coding assistance, repository context, codebase chat, "
            "and editing workflows inside its development environment. The documentation explains product "
            "capabilities and context features, but it does not provide an independent benchmark proving that "
            "Cursor is universally better than every competing coding assistant."
        ),
    )
    plan = {
        "schema_version": "solar.grounded_synthesis_plan.v2",
        "title": "GitHub Copilot and Cursor: evidence-backed comparison",
        "evidence_status": "sufficient",
        "evidence_gaps": [
            {
                "text": "Independent head-to-head benchmark evidence is not present in the retrieved source packs.",
                "evidence_ids": [ev_a, ev_b],
            }
        ],
        "sections": [
            {
                "section_id": "capabilities",
                "title": "Documented capabilities",
                "claims": [
                    {
                        "text": "GitHub Copilot documentation describes AI coding assistance through inline code completion, chat, and integrations with supported development environments.",
                        "claim_type": "factual",
                        "evidence_links": [
                            {
                                "evidence_id": ev_a,
                                "relation": "supports",
                                "quote": "GitHub Copilot official documentation describes AI coding assistance, inline code completion, chat, and integrations with supported development environments.",
                            }
                        ],
                        "confidence": 0.98,
                    },
                    {
                        "text": "Cursor documentation describes AI coding assistance through repository context, codebase chat, and editing workflows inside its development environment.",
                        "claim_type": "factual",
                        "evidence_links": [
                            {
                                "evidence_id": ev_b,
                                "relation": "supports",
                                "quote": "Cursor official documentation describes AI coding assistance, repository context, codebase chat, and editing workflows inside its development environment.",
                            }
                        ],
                        "confidence": 0.98,
                    },
                ],
            },
            {
                "section_id": "limits",
                "title": "What the available evidence cannot establish",
                "claims": [
                    {
                        "text": "The official documentation for GitHub Copilot and Cursor explains product capabilities, but neither source is an independent benchmark of universal superiority.",
                        "claim_type": "comparative",
                        "evidence_links": [
                            {
                                "evidence_id": ev_a,
                                "relation": "supports",
                                "quote": "The documentation explains product capabilities and configuration, but it does not provide an independent benchmark proving that GitHub Copilot is universally better than every competing coding assistant.",
                            },
                            {
                                "evidence_id": ev_b,
                                "relation": "supports",
                                "quote": "The documentation explains product capabilities and context features, but it does not provide an independent benchmark proving that Cursor is universally better than every competing coding assistant.",
                            },
                        ],
                        "confidence": 0.93,
                    },
                    {
                        "text": "A defensible recommendation between these coding assistants therefore requires user-specific workflow criteria and independent benchmark evidence beyond the two official documentation pages.",
                        "claim_type": "hedging",
                        "evidence_links": [
                            {
                                "evidence_id": ev_a,
                                "relation": "supports",
                                "quote": "it does not provide an independent benchmark proving that GitHub Copilot is universally better than every competing coding assistant",
                            },
                            {
                                "evidence_id": ev_b,
                                "relation": "supports",
                                "quote": "it does not provide an independent benchmark proving that Cursor is universally better than every competing coding assistant",
                            },
                        ],
                        "confidence": 0.86,
                    },
                ],
            },
        ],
    }
    return [pack_a, pack_b], plan


def _rewrite_as_runtime_wire(pack: Path) -> None:
    sources = [json.loads(line) for line in (pack / "sources.jsonl").read_text().splitlines()]
    evidence = [json.loads(line) for line in (pack / "evidence.jsonl").read_text().splitlines()]
    runtime_sources = []
    for row in sources:
        runtime_sources.append(
            {
                "source_id": row["source_id"],
                "source_type": row["source_type"],
                "title": row["title"],
                "url": row["url"],
                "retrieved_at": row["retrieved_at"],
                "retrieval": {"method": row["provider"], "http_status": 200},
                "extract": {"path": row["extract_path"], "sha256": row["content_sha256"]},
            }
        )
    runtime_evidence = []
    for row in evidence:
        runtime_evidence.append(
            {
                "evidence_id": row["evidence_id"],
                "source_id": row["source_id"],
                "quote": row["content"],
                "location": {"char_start": row["span_start"], "char_end": row["span_end"]},
            }
        )
    (pack / "sources.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in runtime_sources), encoding="utf-8"
    )
    (pack / "evidence.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in runtime_evidence), encoding="utf-8"
    )


def test_runtime_wire_plan_and_source_packs_compile_through_canonical_checks(tmp_path):
    packs, canonical_plan = _fixture(tmp_path)
    for pack in packs:
        _rewrite_as_runtime_wire(pack)
    first = canonical_plan["sections"][0]["claims"][0]
    second = canonical_plan["sections"][0]["claims"][1]
    rich_plan = {
        "schema_version": "solar.grounded_synthesis_plan.v2",
        "research_question": "Compare two documented coding assistants.",
        "evidence_status": "insufficient",
        "evidence_gaps": [
            {
                "gap_id": "gap-independent-benchmark",
                "description": "Independent head-to-head benchmark evidence is not present.",
                "related_evidence_links": [first["evidence_links"][0]],
            }
        ],
        "publishable_claims": [
            {
                "claim_id": "claim-copilot",
                "claim": first["text"],
                "confidence": "medium",
                "evidence_links": first["evidence_links"],
                "rejection_criteria": ["Reject universal superiority without a benchmark."],
            },
            {
                "claim_id": "claim-cursor",
                "claim": second["text"],
                "confidence": "medium",
                "evidence_links": second["evidence_links"],
                "rejection_criteria": ["Reject universal superiority without a benchmark."],
            },
        ],
        "recommended_report_outline": [
            {
                "section_id": "documented-capabilities",
                "title": "Documented capabilities",
                "claim_ids": ["claim-copilot", "claim-cursor"],
            }
        ],
    }

    output = tmp_path / "runtime-wire-report"
    result = compile_grounded_report(
        source_packs=packs,
        synthesis_plan=rich_plan,
        output_dir=output,
        question="Compare two documented coding assistants.",
    )

    assert result["ok"] is True
    assert all(item["normalized"] is True for item in result["input_closeouts"])
    assert result["evidence_gap_count"] == 1
    assert (output / "final.md").stat().st_size > 0
    compiled_plan = json.loads((output / "synthesis_plan.json").read_text(encoding="utf-8"))
    assert compiled_plan["evidence_status"] == "insufficient"
    assert compiled_plan["bounded_partial_coverage"] is True


def test_chinese_request_localizes_compiler_owned_report_labels(tmp_path):
    packs, plan = _fixture(tmp_path)
    plan["title"] = "相关技术趋势深度分析"
    plan["language"] = "zh-CN"
    output = tmp_path / "chinese-report"

    compile_grounded_report(
        source_packs=packs,
        synthesis_plan=plan,
        output_dir=output,
        question="请生成相关技术趋势的中文深度分析报告。",
    )

    report = (output / "final.md").read_text(encoding="utf-8")
    assert "**研究问题：**" in report
    assert "## 证据边界" in report
    assert "## 来源" in report
    assert "LIMITED SUPPORT" not in report
    assert "Research question" not in report


def test_chinese_grounding_and_cross_script_context_are_supported():
    assert "计算" in grounded_synthesis._tokens("计算材料学与可编程结构")
    checks = research_evaluator._grounding_checks(
        "- 中文趋势判断 [cite:ev_english_context]",
        {"ev_english_context"},
        {"ev_english_context": "Independent English benchmark context."},
    )
    assert checks[0]["ok"] is True
    assert checks[0]["cross_script"] is True
    assert research_evaluator._source_type_is_plausible(
        "official_doc", "https://www.nasa.gov/mission/example", "Mission", ""
    )
    assert research_evaluator._source_type_is_plausible(
        "benchmark", "https://hai.stanford.edu/ai-index/report", "AI Index Report", ""
    )


def test_fixed_source_packs_compile_to_a_passing_topic_general_report(tmp_path):
    packs, plan = _fixture(tmp_path)
    plan_path = tmp_path / "synthesis-plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    output = tmp_path / "report"

    result = compile_grounded_report(
        source_packs=packs,
        synthesis_plan=plan_path,
        output_dir=output,
        question="Which coding assistant is better supported by the available evidence?",
    )

    assert result["ok"] is True
    assert result["retrieval_closeout"]["verdict"] == "pass"
    assert result["final_closeout"]["verdict"] == "pass"
    expected = {
        "sources.jsonl",
        "evidence.jsonl",
        "claims.jsonl",
        "claim_evidence.jsonl",
        "sections.jsonl",
        "section_checks.jsonl",
        "report_ast.json",
        "final.bibliography.json",
        "research_eval.json",
        "final.md",
        "run.finalized",
    }
    assert expected.issubset({path.name for path in output.iterdir()})

    final_text = (output / "final.md").read_text(encoding="utf-8")
    assert "GitHub Copilot" in final_text and "Cursor" in final_text
    assert "[cite:ev_" in final_text
    assert "latent-space reasoning" not in final_text.lower()
    assert "soft thought" not in final_text.lower()

    claims = [json.loads(line) for line in (output / "claims.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(claims) == 4
    assert all(row["schema_version"] == "v1" for row in claims)
    assert all(row["evidence_ids"] for row in claims)


def test_report_closeout_evaluation_is_pure_by_default(tmp_path):
    """A report judge must not also finalize or rewrite the evidence it reads."""
    packs, plan = _fixture(tmp_path)
    output = tmp_path / "report"
    compile_grounded_report(
        source_packs=packs,
        synthesis_plan=plan,
        output_dir=output,
        question="Which coding assistant is better supported by the available evidence?",
    )
    (output / "final_closeout.json").unlink(missing_ok=True)
    (output / "run.finalized").unlink(missing_ok=True)
    before = {
        path.relative_to(output): path.read_bytes()
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }

    result = evaluate_final_closeout(output, strict=True)

    after = {
        path.relative_to(output): path.read_bytes()
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    assert result["ok"] is True, result
    assert after == before


def test_dangling_evidence_id_fails_before_report_publication(tmp_path):
    packs, plan = _fixture(tmp_path)
    plan["sections"][0]["claims"][0]["evidence_links"][0]["evidence_id"] = "ev_missing"
    output = tmp_path / "report"

    with pytest.raises(GroundedSynthesisError, match="evidence_id_unknown"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=plan,
            output_dir=output,
            question="Compare the assistants.",
        )

    assert not output.exists()


def test_citation_with_no_token_support_fails_as_ungrounded(tmp_path):
    packs, plan = _fixture(tmp_path)
    plan["sections"][0]["claims"][0]["text"] = (
        "Marine biologists confirmed a newly discovered coral species near Antarctica."
    )
    output = tmp_path / "report"

    with pytest.raises(GroundedSynthesisError, match="claim_not_grounded"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=plan,
            output_dir=output,
            question="Compare the assistants.",
        )

    assert not output.exists()


def test_v1_token_overlap_plan_is_rejected_instead_of_claiming_strong_support(tmp_path):
    packs, _ = _fixture(tmp_path)
    legacy = {
        "schema_version": "solar.grounded_synthesis_plan.v1",
        "title": "Legacy weak plan",
        "sections": [
            {
                "section_id": "claim",
                "title": "Claim",
                "claims": [
                    {
                        "text": "GitHub Copilot is universally better than every competing coding assistant.",
                        "evidence_ids": [
                            json.loads((packs[0] / "evidence.jsonl").read_text(encoding="utf-8"))["id"]
                        ],
                    }
                ],
            }
        ],
    }

    with pytest.raises(GroundedSynthesisError, match="synthesis_plan_schema_invalid"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=legacy,
            output_dir=tmp_path / "legacy-report",
            question="Which assistant is better?",
        )


def test_exact_quote_and_relation_contract_preserves_mixed_evidence_and_gaps(tmp_path):
    support_text = (
        "A vendor benchmark reports that Assistant A completed 72 percent of the sampled coding tasks, "
        "compared with 61 percent for Assistant B under the vendor's test protocol."
    )
    contradiction_text = (
        "An independent replication reports no statistically significant completion-rate difference "
        "between Assistant A and Assistant B on its sampled maintenance tasks."
    )
    pack_a, ev_a = _write_pack(
        tmp_path / "support-pack",
        source_id="vendor_benchmark",
        title="Vendor benchmark",
        url="https://docs.vendor.example/benchmark",
        text=support_text,
    )
    pack_b, ev_b = _write_pack(
        tmp_path / "contradiction-pack",
        source_id="independent_replication",
        title="Independent replication",
        url="https://docs.research.example/replication",
        text=contradiction_text,
    )
    plan = {
        "schema_version": "solar.grounded_synthesis_plan.v2",
        "title": "Assistant benchmark comparison",
        "evidence_status": "sufficient",
        "evidence_gaps": [
            {
                "text": "Long-term production performance across diverse repositories remains unverified.",
                "evidence_ids": [],
            }
        ],
        "sections": [
            {
                "section_id": "performance",
                "title": "Mixed benchmark evidence",
                "claims": [
                    {
                        "text": "Assistant A appears faster in one vendor benchmark, but independent sampled evidence does not confirm a general completion-rate advantage.",
                        "claim_type": "comparative",
                        "confidence": 0.95,
                        "uncertainty": "The studies use different task samples and protocols.",
                        "evidence_links": [
                            {
                                "evidence_id": ev_a,
                                "relation": "supports",
                                "quote": support_text,
                            },
                            {
                                "evidence_id": ev_b,
                                "relation": "contradicts",
                                "quote": contradiction_text,
                            },
                        ],
                    },
                    {
                        "text": "The available studies use a vendor test protocol and sampled maintenance tasks, so their results do not establish universal superiority.",
                        "claim_type": "hedging",
                        "confidence": 0.75,
                        "evidence_links": [
                            {
                                "evidence_id": ev_a,
                                "relation": "supports",
                                "quote": "under the vendor's test protocol",
                            },
                            {
                                "evidence_id": ev_b,
                                "relation": "qualifies",
                                "quote": "on its sampled maintenance tasks",
                            },
                        ],
                    },
                ],
            }
        ],
    }
    output = tmp_path / "mixed-report"

    result = compile_grounded_report(
        source_packs=[pack_a, pack_b],
        synthesis_plan=plan,
        output_dir=output,
        question="Which assistant performs better?",
    )

    assert result["ok"] is True
    final_text = (output / "final.md").read_text(encoding="utf-8")
    assert "MIXED EVIDENCE" in final_text
    assert "UNVERIFIED" in final_text
    claims = [json.loads(line) for line in (output / "claims.jsonl").read_text(encoding="utf-8").splitlines()]
    assert claims[0]["support_rating"] == "weak"
    assert claims[0]["confidence"] <= 0.6
    assert claims[0]["contradiction_ids"] == [ev_b]
    links = [json.loads(line) for line in (output / "claim_evidence.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {row["relation"] for row in links} >= {"supports", "contradicts", "qualifies"}
    assert all(row["quote"] and row["quote_sha256"] for row in links)
    evaluation = json.loads((output / "research_eval.json").read_text(encoding="utf-8"))
    assert evaluation["contradiction_count"] == 1
    assert evaluation["evidence_gap_count"] == 1


def test_inexact_support_quote_fails_before_publication(tmp_path):
    packs, plan = _fixture(tmp_path)
    plan["sections"][0]["claims"][0]["evidence_links"][0]["quote"] = (
        "This exact sentence was never present in the fetched extract."
    )
    output = tmp_path / "report"

    with pytest.raises(GroundedSynthesisError, match="evidence_quote_not_exact"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=plan,
            output_dir=output,
            question="Compare the assistants.",
        )

    assert not output.exists()


def test_trivial_one_word_quote_is_not_accepted_as_claim_support(tmp_path):
    packs, plan = _fixture(tmp_path)
    plan["sections"][0]["claims"][0]["evidence_links"][0]["quote"] = "chat"

    with pytest.raises(GroundedSynthesisError, match="evidence_quote_too_short"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=plan,
            output_dir=tmp_path / "short-quote-report",
            question="Compare the assistants.",
        )


def test_whole_page_quote_is_not_accepted_as_a_focused_support_span(tmp_path):
    long_text = (
        "Official documentation reports Assistant A benchmark behavior and limitations. "
        + "Repeated benchmark context and implementation detail. " * 60
    )
    pack, evidence_id = _write_pack(
        tmp_path / "long-pack",
        source_id="long_official_page",
        title="Official benchmark documentation",
        url="https://docs.example.test/benchmark",
        text=long_text,
    )
    plan = {
        "schema_version": "solar.grounded_synthesis_plan.v2",
        "title": "Focused quote boundary",
        "evidence_status": "sufficient",
        "evidence_gaps": [],
        "sections": [
            {
                "section_id": "finding",
                "title": "Finding",
                "claims": [
                    {
                        "text": "Official documentation reports Assistant A benchmark behavior and limitations.",
                        "evidence_links": [
                            {
                                "evidence_id": evidence_id,
                                "relation": "supports",
                                "quote": long_text,
                            }
                        ],
                    }
                ],
            }
        ],
    }

    with pytest.raises(GroundedSynthesisError, match="evidence_quote_too_long"):
        compile_grounded_report(
            source_packs=[pack],
            synthesis_plan=plan,
            output_dir=tmp_path / "long-quote-report",
            question="What does the documentation establish?",
        )


def test_claim_with_only_contradicting_links_cannot_be_published_as_supported(tmp_path):
    packs, plan = _fixture(tmp_path)
    link = plan["sections"][0]["claims"][0]["evidence_links"][0]
    link["relation"] = "contradicts"
    output = tmp_path / "report"

    with pytest.raises(GroundedSynthesisError, match="claim_support_missing"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=plan,
            output_dir=output,
            question="Compare the assistants.",
        )

    assert not output.exists()


def test_declared_insufficient_evidence_fails_with_bounded_gap_and_no_report(tmp_path):
    packs, _ = _fixture(tmp_path)
    plan = {
        "schema_version": "solar.grounded_synthesis_plan.v2",
        "title": "Insufficient evidence",
        "evidence_status": "insufficient",
        "evidence_gaps": [
            {
                "text": "No independent benchmark was retrieved for the requested population.",
                "evidence_ids": [],
            }
        ],
        "sections": [],
    }
    output = tmp_path / "insufficient-report"

    with pytest.raises(GroundedSynthesisError, match="insufficient_evidence:No independent benchmark"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=plan,
            output_dir=output,
            question="Which assistant is universally best?",
        )

    assert not output.exists()


def test_malformed_insufficient_gap_is_a_controlled_failure(tmp_path):
    packs, _ = _fixture(tmp_path)
    plan = {
        "schema_version": "solar.grounded_synthesis_plan.v2",
        "title": "Insufficient evidence",
        "evidence_status": "insufficient",
        "evidence_gaps": ["not a structured gap"],
        "sections": [],
    }

    with pytest.raises(GroundedSynthesisError, match="evidence_gap_invalid:1"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=plan,
            output_dir=tmp_path / "malformed-gap-report",
            question="Which assistant is universally best?",
        )


def test_out_of_range_requested_confidence_is_rejected_not_silently_clamped(tmp_path):
    packs, plan = _fixture(tmp_path)
    plan["sections"][0]["claims"][0]["confidence"] = 1.5
    output = tmp_path / "report"

    with pytest.raises(GroundedSynthesisError, match="claim_schema_invalid.*confidence_out_of_range"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=plan,
            output_dir=output,
            question="Compare the assistants.",
        )

    assert not output.exists()


def test_corrupted_input_extract_fails_before_synthesis_or_publication(tmp_path):
    packs, plan = _fixture(tmp_path)
    extract = next((packs[0] / "extracts").iterdir())
    extract.write_text(extract.read_text(encoding="utf-8") + "\ncorrupted after hashing\n", encoding="utf-8")
    output = tmp_path / "report"

    with pytest.raises(GroundedSynthesisError, match="source_pack_invalid"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=plan,
            output_dir=output,
            question="Compare the assistants.",
        )

    assert not output.exists()


def test_invalid_claim_shape_is_a_controlled_grounding_failure(tmp_path):
    packs, plan = _fixture(tmp_path)
    plan["sections"][0]["claims"][0]["claim_type"] = "invented_type"
    output = tmp_path / "report"

    with pytest.raises(GroundedSynthesisError, match="claim_schema_invalid"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=plan,
            output_dir=output,
            question="Compare the assistants.",
        )

    assert not output.exists()


def test_final_closeout_failure_never_publishes_report(tmp_path, monkeypatch):
    packs, plan = _fixture(tmp_path)
    output = tmp_path / "report"
    monkeypatch.setattr(
        grounded_synthesis,
        "evaluate_final_closeout",
        lambda *_args, **_kwargs: {
            "ok": False,
            "verdict": "hard_fail",
            "issues": ["forced_final_closeout_failure"],
        },
    )

    with pytest.raises(GroundedSynthesisError, match="report_final_preflight_failed"):
        compile_grounded_report(
            source_packs=packs,
            synthesis_plan=plan,
            output_dir=output,
            question="Compare the assistants.",
        )

    assert not output.exists()


def test_compile_grounded_cli_runs_the_real_compiler(tmp_path):
    packs, plan = _fixture(tmp_path)
    plan_path = tmp_path / "synthesis-plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    output = tmp_path / "cli-report"

    proc = subprocess.run(
        [
            str(_HARNESS / "solar-harness.sh"),
            "research",
            "compile-grounded",
            "--source-pack",
            str(packs[0]),
            "--source-pack",
            str(packs[1]),
            "--synthesis-plan",
            str(plan_path),
            "--output-dir",
            str(output),
            "--question",
            "Which coding assistant is better supported by the available evidence?",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["final_closeout"]["verdict"] == "pass"
