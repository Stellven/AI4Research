"""The adapters that let this workflow use Solar's own research pipeline.

Part A had its own source format, claim model and report assembler. These
adapters replace all three with harness/lib/research, so the tests here are
about the seams -- which is where every defect in this workflow has been.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[4] / "harness"
for extra in (HARNESS / "plugins" / "autosci", HARNESS / "lib"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from operators.research_synthesis.synthesis_plan import build_plan, evidence_index  # noqa: E402
from operators.research_synthesis.validated_pack import write_validated_pack  # noqa: E402


def _validation(**overrides):
    source = {
        "source_id": "openalex-rag-01",
        "title": "Retrieval-Augmented Generation for Large Language Models",
        "content_summary": "Retrieval-augmented generation improves factuality by grounding output in retrieved passages.",
        "url": "https://doi.org/10.1000/rag",
        "canonical_id": "doi:10.1000/rag",
        "provider": "openalex",
    }
    source.update(overrides)
    return {"accepted": [source], "rejected": []}


def test_pack_carries_the_spans_claim_verification_needs(tmp_path) -> None:
    """Spans were reported as missing and needing to be built. They are not.

    write_source_pack emits span_start/span_end and content_hash per evidence
    row as a matter of course, which is what makes byte-level quote
    verification possible at all.
    """
    manifest = write_validated_pack(source_validation=_validation(), output_dir=tmp_path / "pack")

    assert manifest["usable"] is True
    rows = [
        json.loads(line)
        for line in (tmp_path / "pack" / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows, "pack wrote no evidence"
    assert {"span_start", "span_end", "content_hash"} <= set(rows[0])


def test_a_source_without_text_is_skipped_not_padded(tmp_path) -> None:
    """"Persist without inventing missing data" must survive the adapter."""
    validation = _validation(content_summary="", abstract="", metadata={})

    manifest = write_validated_pack(source_validation=validation, output_dir=tmp_path / "pack")

    assert manifest["accepted_input_count"] == 1
    assert not manifest.get("source_count")
    assert manifest["usable"] is False


def test_plan_resolves_source_ids_onto_pack_evidence_ids(tmp_path) -> None:
    """Two id spaces meet here, and conflating them breaks every claim.

    write_source_pack mints content-addressed `ev_<hash>` ids; claims cite the
    source id. Indexed naively, every claim looks like it cites evidence the
    pack does not contain.
    """
    write_validated_pack(source_validation=_validation(), output_dir=tmp_path / "pack")
    rows = [
        json.loads(line)
        for line in (tmp_path / "pack" / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    index = evidence_index(rows)
    assert "openalex-rag-01" in index, "source id must resolve"
    assert rows[0]["evidence_id"] in index, "evidence id must resolve too"

    plan = build_plan(
        claims=[{
            "claim_id": "claim-001",
            "text": "Retrieval-augmented generation improves factuality.",
            "evidence_ids": ["openalex-rag-01"],
            "evidence_quotes": [{
                # Shares vocabulary with the claim: the compiler refuses a
                # link whose quote and claim have no token in common, and the
                # plan builder now applies the same rule instead of emitting a
                # plan the compile would abort on.
                "source_id": "openalex-rag-01",
                "quote": "grounding output in retrieved passages improves factuality",
            }],
            "uncertainty": "medium",
        }],
        evidence_index=index,
    )

    assert plan["evidence_status"] == "sufficient"
    link = plan["sections"][0]["claims"][0]["evidence_links"][0]
    assert link["evidence_id"] == rows[0]["evidence_id"]
    assert link["relation"] == "supports"
    assert link["quote"] == "grounding output in retrieved passages improves factuality"


def test_a_claim_without_a_verified_quote_is_a_gap_not_a_link(tmp_path) -> None:
    """compile_grounded_report refuses a link with no quote, so say why here.

    Silently dropping the claim would leave a report that simply omits it;
    recording the gap keeps the omission visible.
    """
    write_validated_pack(source_validation=_validation(), output_dir=tmp_path / "pack")
    rows = [
        json.loads(line)
        for line in (tmp_path / "pack" / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    plan = build_plan(
        claims=[{
            "claim_id": "claim-001",
            "text": "Retrieval-augmented generation improves factuality.",
            "evidence_ids": ["openalex-rag-01"],
            "evidence_quotes": [],
            "uncertainty": "medium",
        }],
        evidence_index=evidence_index(rows),
    )

    assert plan["evidence_status"] == "insufficient"
    gap = next(gap for gap in plan["evidence_gaps"] if "no verified supporting quote" in gap["text"])
    assert "openalex-rag-01" in gap["text"]
    assert gap["evidence_ids"] == [rows[0]["evidence_id"]]
    assert gap["evidence_ids"][0].startswith("ev_")


def test_a_claim_citing_absent_evidence_is_reported(tmp_path) -> None:
    write_validated_pack(source_validation=_validation(), output_dir=tmp_path / "pack")
    rows = [
        json.loads(line)
        for line in (tmp_path / "pack" / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    plan = build_plan(
        claims=[{
            "claim_id": "claim-001",
            "text": "An unrelated assertion.",
            "evidence_ids": ["never-fetched-01"],
            "evidence_quotes": [{"source_id": "never-fetched-01", "quote": "x" * 60}],
            "uncertainty": "high",
        }],
        evidence_index=evidence_index(rows),
    )

    assert plan["evidence_status"] == "insufficient"
    assert any("absent from the source pack" in gap["text"] for gap in plan["evidence_gaps"])


def test_a_paraphrased_quote_is_dropped_at_the_operator(tmp_path) -> None:
    """The model is asked for a verbatim sentence. A paraphrase is not one.

    Dropping rather than repairing is the point: repairing would mean choosing
    the supporting evidence ourselves, which is a fabricated provenance that
    passes every downstream check.
    """
    from operators.research_synthesis.evidence_synthesis import _normalize_quotes

    source_text = {"s1": "Retrieval-augmented generation improves factuality by grounding output."}

    verbatim = _normalize_quotes(
        {"evidence_quotes": [{"source_id": "s1", "quote": "improves factuality by grounding output"}]},
        claim_id="claim-001", evidence_ids=["s1"], source_text_by_id=source_text,
    )
    assert verbatim == [{"source_id": "s1", "quote": "improves factuality by grounding output"}]

    paraphrase = _normalize_quotes(
        {"evidence_quotes": [{"source_id": "s1", "quote": "RAG makes models more factual"}]},
        claim_id="claim-001", evidence_ids=["s1"], source_text_by_id=source_text,
    )
    assert paraphrase == [], "a paraphrase is not a quote and must not be stored"

    uncited = _normalize_quotes(
        {"evidence_quotes": [{"source_id": "s2", "quote": "improves factuality by grounding output"}]},
        claim_id="claim-001", evidence_ids=["s1"], source_text_by_id=source_text,
    )
    assert uncited == [], "a quote attributed to an uncited source must not be stored"
