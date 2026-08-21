"""A published claim must be quoted verbatim AND actually supported.

Byte-level quote verification and support are different properties, and this
workflow was passing one while failing the other. In the 2026-08-19 green run,
Solar's own `claim_support_assessment` rated 2 of 5 published claims UNVERIFIED
(term coverage 0.12-0.43 against a 0.45 floor), and a third carried no verified
quote at all. `research_eval.json` nonetheless reports `unsupported_rate: 0.0`.

The fix is at the cause: `evidence_synthesis` refuses to publish a claim that
fails either condition and hands the reason back to the model, bounded to three
attempts. That refusal is what makes `unsupported_rate: 0.0` true by
construction rather than asserted -- so the gate recomputes it independently,
because a guarantee nobody re-derives is just a promise.

Solar's checker is rebound, not reimplemented, and its aggregation rule is
followed: assess against the FULL source text, and treat a claim as supported
when ANY cited source supports it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[2]
if str(HARNESS / "plugins" / "autosci") not in sys.path:
    sys.path.insert(0, str(HARNESS / "plugins" / "autosci"))
if str(HARNESS / "scripts") not in sys.path:
    sys.path.insert(0, str(HARNESS / "scripts"))

from operators.research_synthesis.evidence_synthesis import (  # noqa: E402
    assess_claim_grounding,
)
import validate_evidence_to_poc as gate  # noqa: E402

# Written so the claim shares well over 45% of its terms with the source.
SOURCE = (
    "The Retrieval-Augmented Generation Benchmark evaluates noise robustness, "
    "negative rejection, information integration and counterfactual robustness "
    "across a multi-lingual corpus of retrieval-augmented generation systems."
)
QUOTE = "evaluates noise robustness, negative rejection, information integration"
GROUNDED_CLAIM_TEXT = (
    "The Retrieval-Augmented Generation Benchmark evaluates noise robustness, "
    "negative rejection and information integration."
)
UNGROUNDED_CLAIM_TEXT = (
    "Longitudinal clinical deployment of surgical robotics improved patient "
    "recovery outcomes across hospital networks."
)


def _claim(claim_id: str, text: str, *, quotes: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "text": text,
        "evidence_ids": ["s1"],
        "evidence_quotes": quotes,
        "uncertainty": "low",
    }


TEXT_BY_ID = {"s1": SOURCE}


def test_a_quoted_and_supported_claim_is_kept() -> None:
    kept, rejected = assess_claim_grounding(
        [_claim("c1", GROUNDED_CLAIM_TEXT, quotes=[{"source_id": "s1", "quote": QUOTE}])],
        TEXT_BY_ID,
    )
    assert [c["claim_id"] for c in kept] == ["c1"]
    assert rejected == []
    assert kept[0]["support_assessment"]["supported_by"] == ["s1"]


def test_a_claim_with_no_verbatim_quote_is_refused() -> None:
    """The live defect: claim-003 was published carrying zero quotes.

    `compile_grounded_report` refuses such a claim downstream, so publishing it
    produced a report that could never be compiled.
    """
    kept, rejected = assess_claim_grounding(
        [_claim("c1", GROUNDED_CLAIM_TEXT, quotes=[])], TEXT_BY_ID
    )
    assert kept == []
    assert "no verbatim quote" in rejected[0]["reasons"][0]


def test_a_verbatim_quote_does_not_make_an_unsupported_claim_supported() -> None:
    """The property byte-level verification cannot see.

    The quote is genuinely present in the source; the claim built on it is about
    something else entirely.
    """
    kept, rejected = assess_claim_grounding(
        [_claim("c1", UNGROUNDED_CLAIM_TEXT, quotes=[{"source_id": "s1", "quote": QUOTE}])],
        TEXT_BY_ID,
    )
    assert kept == []
    assert any("no cited source supports" in reason for reason in rejected[0]["reasons"])
    # The reason has to name what failed, or a repair attempt is guesswork.
    assert "term_coverage" in rejected[0]["reasons"][-1]


def test_rejection_reasons_are_carried_for_feedback() -> None:
    kept, rejected = assess_claim_grounding(
        [
            _claim("good", GROUNDED_CLAIM_TEXT, quotes=[{"source_id": "s1", "quote": QUOTE}]),
            _claim("bad", UNGROUNDED_CLAIM_TEXT, quotes=[{"source_id": "s1", "quote": QUOTE}]),
        ],
        TEXT_BY_ID,
    )
    assert [c["claim_id"] for c in kept] == ["good"]
    assert [c["claim_id"] for c in rejected] == ["bad"]
    assert rejected[0]["text"] == UNGROUNDED_CLAIM_TEXT


# --- the gate recomputes rather than trusting the operator -------------------


def _workspace(tmp_path: Path, claims: list[dict[str, Any]]) -> Path:
    validation = tmp_path / gate.SOURCE_VALIDATION
    validation.parent.mkdir(parents=True, exist_ok=True)
    validation.write_text(json.dumps({
        "accepted": [{"source_id": "s1", "content_summary": SOURCE}],
        "rejected": [],
    }), encoding="utf-8")
    synthesis = tmp_path / gate.EVIDENCE_SYNTHESIS
    synthesis.parent.mkdir(parents=True, exist_ok=True)
    synthesis.write_text(json.dumps({"claims": claims}), encoding="utf-8")
    return tmp_path


def test_gate_passes_a_properly_grounded_claim(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, [
        _claim("c1", GROUNDED_CLAIM_TEXT, quotes=[{"source_id": "s1", "quote": QUOTE}])
    ])
    assert gate.check_claim_grounding(workspace) == []


def test_gate_does_not_trust_the_operators_own_support_verdict(tmp_path: Path) -> None:
    """The field the operator writes is the thing under test.

    A synthesis that recorded `support_assessment: supported` for a claim its
    evidence does not carry must still be caught, or the gate is checking the
    operator's opinion of itself.
    """
    lying = _claim("c1", UNGROUNDED_CLAIM_TEXT, quotes=[{"source_id": "s1", "quote": QUOTE}])
    lying["support_assessment"] = {"supported_by": ["s1"], "status": "supported"}
    workspace = _workspace(tmp_path, [lying])
    failures = gate.check_claim_grounding(workspace)
    assert any("no cited source supports" in item for item in failures)


def test_gate_catches_a_quote_that_is_not_in_its_source(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, [
        _claim("c1", GROUNDED_CLAIM_TEXT,
               quotes=[{"source_id": "s1", "quote": "a sentence that is not in the source"}])
    ])
    failures = gate.check_claim_grounding(workspace)
    assert any("verbatim" in item for item in failures)
