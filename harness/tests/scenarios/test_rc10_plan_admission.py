"""Ordinary research attrition degrades the report; it does not end the run.

The live CRISPR run died at `report_draft` with
`evidence_quote_not_exact:in-silico-prediction-tool-performance:ev_88d6...`.
The quote WAS in the source. Publisher text strips italic markup and leaves
doubled spaces around the Latin phrases biomedical style italicises:

    "Benchmarking 13  in silico  prediction tools identified Cas-OFFinder"

`evidence_synthesis` verifies against whitespace-normalized text and stores the
normalized quote; `grounded_synthesis` checks byte-exactly against the raw pack.
Two components, two definitions of "verbatim". Fifteen stages of work lost over
one link out of ten.

Two fixes, tested here and deliberately kept separate:

* `canonical_text` removes the CAUSE, so the pack carries the same canonical
  form the synthesis verified against.
* `admit_plan` removes the BRITTLENESS, so the next instance of the class --
  PDF ligatures, smart quotes -- costs one claim rather than the whole run.

The floor matters as much as the tolerance. Dropping whatever fails until
something compiles produces a one-claim report with a PASS on it, which is
worse than failing because it reads as a result.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[2]
for extra in (HARNESS / "plugins" / "autosci", HARNESS / "lib"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from operators.research_synthesis.plan_admission import admit_plan  # noqa: E402
from operators.research_synthesis.validated_pack import canonical_text  # noqa: E402

# Verbatim from doi:10.1016/j.omtn.2026.102958 as Europe PMC returned it.
PUBLISHER_TEXT = (
    "Benchmarking 13  in silico  prediction tools identified Cas-OFFinder as the "
    "most sensitive, though precision remained low, and correlation with  in vitro  "
    "CIRCLE-seq data was modest."
)
# What the model quoted, and what evidence_synthesis stored after normalizing.
STORED_QUOTE = (
    "Benchmarking 13 in silico prediction tools identified Cas-OFFinder as the "
    "most sensitive, though precision remained low"
)
CLAIM = "Cas-OFFinder is the most sensitive in silico prediction tool but precision remained low."


def _rows(content: str) -> list[dict[str, Any]]:
    return [{"evidence_id": "ev_1", "source_id": "s1", "content": content}]


def _plan(*links: dict[str, Any], text: str = CLAIM) -> dict[str, Any]:
    return {
        "sections": [
            {
                "section_id": "sec-1",
                "title": "In silico prediction tool performance",
                "claims": [{"text": text, "uncertainty": "low", "evidence_links": list(links)}],
            }
        ]
    }


def _supports(quote: str = STORED_QUOTE) -> dict[str, Any]:
    return {"evidence_id": "ev_1", "relation": "supports", "quote": quote}


# --- the cause -------------------------------------------------------------


def test_canonical_text_makes_the_stored_quote_byte_exact() -> None:
    """The whole CRISPR defect, in one assertion pair."""
    assert STORED_QUOTE not in PUBLISHER_TEXT
    assert STORED_QUOTE in canonical_text(PUBLISHER_TEXT)


def test_canonical_text_changes_no_word_of_the_source() -> None:
    """Only whitespace may be touched, or the pack stops being the source."""
    assert canonical_text(PUBLISHER_TEXT).split() == PUBLISHER_TEXT.split()


def test_a_line_wrapped_abstract_is_canonicalised_too() -> None:
    """arXiv wraps mid-sentence and fails byte-exactness the same way."""
    wrapped = PUBLISHER_TEXT.replace(" ", "\n", 4)
    assert STORED_QUOTE in canonical_text(wrapped)


# --- the brittleness -------------------------------------------------------


def test_a_claim_grounded_in_canonical_text_is_admitted_whole() -> None:
    plan, report = admit_plan(plan=_plan(_supports()), evidence_rows=_rows(canonical_text(PUBLISHER_TEXT)))
    assert report["claims_out"] == 1
    assert report["dropped_links"] == []
    assert plan["sections"][0]["claims"][0]["evidence_links"] == [_supports()]


def test_an_inexact_quote_costs_its_claim_not_the_run() -> None:
    """What the compiler would have aborted on.

    `admit_plan` must not raise. The caller decides whether what survived is
    still a report.
    """
    plan, report = admit_plan(plan=_plan(_supports()), evidence_rows=_rows(PUBLISHER_TEXT))
    assert report["claims_out"] == 0
    assert report["dropped_links"][0]["reason"] == "quote_not_exact"
    assert plan["sections"] == []


def test_a_dropped_claim_is_named_in_the_record() -> None:
    """build_plan drops claim_id, so the text has to stand in as identity.

    An attrition record that cannot say WHAT it dropped is not a record.
    """
    _, report = admit_plan(plan=_plan(_supports()), evidence_rows=_rows(PUBLISHER_TEXT))
    dropped = report["dropped_claims"][0]
    assert dropped["claim_id"].startswith("Cas-OFFinder is the most sensitive")
    assert dropped["reason"] == "no_compilable_evidence_link"


def test_one_bad_link_does_not_take_a_claims_good_links_with_it() -> None:
    content = canonical_text(PUBLISHER_TEXT)
    plan, report = admit_plan(
        plan=_plan(
            _supports(),
            {"evidence_id": "ev_1", "relation": "supports", "quote": "not present in the source at all"},
        ),
        evidence_rows=_rows(content),
    )
    assert report["claims_out"] == 1
    assert report["links_in"] == 2 and report["links_out"] == 1


# --- contradiction is a finding, never attrition ---------------------------


def test_a_contradicting_source_is_carried_into_the_report() -> None:
    """The owner asked whether claims contradict. Disagreement must survive."""
    content = canonical_text(PUBLISHER_TEXT)
    contra = {
        "evidence_id": "ev_2",
        "relation": "contradicts",
        "quote": "precision remained low, and correlation with in vitro CIRCLE-seq data was modest",
    }
    rows = _rows(content) + [{"evidence_id": "ev_2", "source_id": "s2", "content": content}]
    plan, report = admit_plan(plan=_plan(_supports(), contra), evidence_rows=rows)
    relations = {link["relation"] for link in plan["sections"][0]["claims"][0]["evidence_links"]}
    assert relations == {"supports", "contradicts"}
    assert report["contradiction_links"] == 1


def test_a_claim_with_only_contradicting_evidence_is_dropped_and_said_so() -> None:
    """The compiler requires a `supports` link, so this cannot be published.

    It must still be visible: an unsupported claim that vanished silently is
    indistinguishable from one that was never made.
    """
    content = canonical_text(PUBLISHER_TEXT)
    contra = {"evidence_id": "ev_1", "relation": "contradicts", "quote": STORED_QUOTE}
    _, report = admit_plan(plan=_plan(contra), evidence_rows=_rows(content))
    dropped = report["dropped_claims"][0]
    assert dropped["reason"] == "no_surviving_support"
    assert dropped["surviving_relations"] == ["contradicts"]


# --- the floor -------------------------------------------------------------


def test_retention_is_reported_so_the_caller_can_refuse_a_thin_report() -> None:
    content = canonical_text(PUBLISHER_TEXT)
    good = {"text": CLAIM, "uncertainty": "low", "evidence_links": [_supports()]}
    bad = {
        "text": "An unrelated claim about delivery vectors.",
        "uncertainty": "low",
        "evidence_links": [{"evidence_id": "ev_1", "relation": "supports", "quote": "absent from this source entirely"}],
    }
    plan = {"sections": [{"section_id": "sec-1", "title": "T", "claims": [good, bad, dict(bad)]}]}
    _, report = admit_plan(plan=plan, evidence_rows=_rows(content))
    assert report["claims_in"] == 3 and report["claims_out"] == 1
    assert report.claim_retention == 1 / 3


def test_retention_of_a_plan_with_no_claims_is_not_a_division_by_zero() -> None:
    _, report = admit_plan(plan={"sections": []}, evidence_rows=_rows("x"))
    assert report.claim_retention == 1.0
    assert report["sections_out"] == 0
