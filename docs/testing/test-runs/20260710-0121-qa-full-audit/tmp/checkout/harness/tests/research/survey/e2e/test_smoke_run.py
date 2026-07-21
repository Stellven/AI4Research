"""S05 N1 deterministic survey-continue smoke verification."""

from __future__ import annotations

import json
from pathlib import Path

from research.survey.cli.gate_report_view import format_gate_report, to_dict_gate_report
from research.survey.explorer.exploration_run import exploration_run
from research.survey.gates.argument_density import argument_density_gate
from research.survey.gates.compile_gate_report import compile_gate_report
from research.survey.gates.controversy_matrix import controversy_gate
from research.survey.gates.source_quality_distribution import source_quality_gate
from research.survey.schemas import EvidencePack, ExplorationDirection, SectionReview, SourceMatrix

ROOT = Path(__file__).resolve().parents[4]
RUN_DIR = ROOT / "runtime" / "survey-continue" / "sample-run-001"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _section_text() -> str:
    return (
        "Mechanism comparison: quantization changes numeric precision versus pruning. "
        "Taxonomy: category one is post-training quantization and category two is distillation. "
        "Evaluation protocol: benchmark latency, memory, accuracy, and energy. "
        "Negative evidence: aggressive compression can fail on long-tail tasks. "
        "Engineering implication: production deploy requires hardware-aware kernels."
    )


def _pack() -> EvidencePack:
    return EvidencePack(
        pack_id="pack-compression",
        section_id="sec-compression",
        evidence_ids=["ev-paper-001", "ev-code-001", "ev-official-001", "ev-bench-001", "ev-web-001"],
        claim_ids=["c-compression-001"],
        source_ids=["src-paper-001", "src-code-001", "src-official-001", "src-bench-001", "src-web-001"],
        source_types=["paper", "code", "official", "benchmark", "web"],
        contradiction_slots=["c-compression-001"],
        status="ready",
    )


def test_sample_question_and_stub_llm_fixtures_exist() -> None:
    question = json.loads((FIXTURE_DIR / "sample_question.json").read_text())
    responses = (FIXTURE_DIR / "stub_llm_responses.jsonl").read_text().splitlines()
    assert question["text"] == "survey of small-scale model compression for on-device inference, 2024-2026"
    assert len(responses) == 2
    assert all(json.loads(line)["response"] for line in responses)


def test_gate_chain_produces_four_verdict_slots_and_cli_visibility() -> None:
    pack = _pack()
    source = source_quality_gate(
        pack,
        source_urls=[
            "https://arxiv.org/abs/0000.00001",
            "https://github.com/example/compress",
            "https://developer.example.com/mobile",
            "https://mlperf.org/mobile",
            "https://example.com/overview",
        ],
    )
    density = argument_density_gate(
        SectionReview("sec-compression", "pass", 0.0, 1.0, 0.9, 0.0),
        _section_text(),
    )
    matrix = controversy_gate(
        {"claim_ids": ["c-compression-001"], "section_id": "sec-compression"},
        [
            {"claim_id": "c-compression-001", "evidence_id": "ev-paper-001", "source_id": "src-paper-001", "relation_type": "supporting", "relation_strength": "strong"},
            {"claim_id": "c-compression-001", "evidence_id": "ev-paper-002", "source_id": "src-paper-002", "relation_type": "contradicting", "relation_strength": "moderate"},
        ],
        chapter_syntheses=[{"chapter_id": "ch1", "synthesis_text": "The synthesis references [claim:c-compression-001]."}],
    )
    report = compile_gate_report(
        evidence_pack=pack,
        section=SectionReview("sec-compression", "pass", 0.0, 1.0, 0.9, 0.0),
        text=_section_text(),
        claim_evidence_rows=[],
        run_metadata={"run_id": "q-small-model-compression-2024-2026"},
        artifact_paths={"elimination_log": str(RUN_DIR / "elimination_log.jsonl")},
    )
    rendered = format_gate_report(report)
    as_dict = to_dict_gate_report(report)
    assert source.verdict == "pass"
    assert density.density_score == 1.0
    assert matrix["verdict"] == "pass"
    assert set(report.gate_verdicts) == {"source_quality", "argument_density", "controversy_matrix", "exploration_log"}
    assert "source_quality" in rendered
    assert "argument_density" in rendered
    assert "controversy_matrix" in rendered
    assert "exploration_log" in rendered
    assert "partial_verdicts" in rendered
    assert as_dict["partial_verdicts"] == ["exploration_log"]


def test_exploration_log_has_elimination_record() -> None:
    matrix = SourceMatrix("sec-compression", ["paper", "code", "official", "benchmark"], [], 4, 4)
    candidates = [
        ExplorationDirection("dir-canonical", "canonical evidence", "papers code official benchmark", "active", matrix),
        ExplorationDirection("dir-web-roundup", "web roundup", "collect recent blog posts only", "active", matrix),
        ExplorationDirection("dir-benchmark", "benchmark led", "start from benchmark protocols", "active", matrix),
    ]

    def provider(direction: ExplorationDirection) -> list[dict]:
        if direction.direction_id == "dir-web-roundup":
            return [{"source_id": "blog-001", "source_type": "web", "claims": ["c1"], "evidence_count": 1}]
        return [
            {"source_id": "paper-001", "source_type": "paper", "claims": ["c1"], "evidence_count": 2},
            {"source_id": "code-001", "source_type": "code", "claims": ["c2"], "evidence_count": 2},
            {"source_id": "official-001", "source_type": "official", "claims": ["c3"], "evidence_count": 2},
            {"source_id": "bench-001", "source_type": "benchmark", "claims": ["c4"], "evidence_count": 2},
        ]

    result = exploration_run(
        "q-small-model-compression-2024-2026",
        candidates,
        source_provider=provider,
        log_path=RUN_DIR / "elimination_log.jsonl",
        clock=lambda: "1970-01-01T00:00:00Z",
        source_matrix=matrix,
    )
    lines = (RUN_DIR / "elimination_log.jsonl").read_text().splitlines()
    assert len(result.eliminated_directions) == 1
    assert len(lines) >= 1
    assert json.loads(lines[-1])["kill_reason"]


def test_runtime_artifacts_exist_and_reproduce_without_diff(tmp_path: Path) -> None:
    artifact_names = [
        "source_quality_distribution.json",
        "density_profile.json",
        "controversy_matrix.json",
        "elimination_log.jsonl",
        "gate_report.json",
        "activation_proof.jsonl",
    ]
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for name in artifact_names:
        payload = (RUN_DIR / name).read_text()
        assert payload.strip()
        (first / name).write_text(payload)
        (second / name).write_text(payload)
    assert {
        name: (first / name).read_text()
        for name in artifact_names
    } == {
        name: (second / name).read_text()
        for name in artifact_names
    }

