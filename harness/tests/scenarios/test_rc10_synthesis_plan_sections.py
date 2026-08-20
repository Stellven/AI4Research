"""The synthesis plan groups claims into the sections the synthesis labelled.

`build_plan` used to put every claim into one hardcoded "Findings" section, so
`compile_grounded_report` had exactly one section to render and the report came
out as a flat list no matter how much structure the synthesis actually had.

Grouping happens after validation, never before, because a claim can still be
dropped for citing absent evidence or carrying no verified quote. Grouping first
would leave a section heading with nothing under it -- a report that looks like
it covers a theme it has no surviving evidence for.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[2]
REPO = HARNESS.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.plugins.autosci.operators.research_synthesis.synthesis_plan import (  # noqa: E402
    build_plan,
)

INDEX = {"s1": ["ev_1"], "s2": ["ev_2"], "s3": ["ev_3"]}


def _claim(claim_id: str, source: str, **extra: Any) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "text": f"Claim {claim_id} about retrieval quality.",
        "uncertainty": "low",
        "evidence_ids": [source],
        "evidence_quotes": [{"source_id": source, "quote": f"quote for {claim_id}"}],
        **extra,
    }


def _titles(plan: dict[str, Any]) -> list[str]:
    return [section["title"] for section in plan["sections"]]


def test_unlabelled_claims_still_produce_one_section() -> None:
    """The fallback matters: a synthesis that emits no theme must still compile."""
    plan = build_plan(
        claims=[_claim("c1", "s1"), _claim("c2", "s2")],
        evidence_index=INDEX,
    )
    assert _titles(plan) == ["Findings"]
    assert len(plan["sections"][0]["claims"]) == 2
    assert plan["evidence_status"] == "sufficient"


def test_themed_claims_group_in_first_appearance_order() -> None:
    plan = build_plan(
        claims=[
            _claim("c1", "s1", theme="Motivation"),
            _claim("c2", "s2", theme="Benchmarks"),
            _claim("c3", "s3", theme="Motivation"),
        ],
        evidence_index=INDEX,
    )
    # Order follows the synthesis, not an alphabetical re-sort nobody asked for.
    assert _titles(plan) == ["Motivation", "Benchmarks"]
    assert [len(section["claims"]) for section in plan["sections"]] == [2, 1]


def test_section_ids_are_slugged_and_unique() -> None:
    """The compiler enforces ^[A-Za-z0-9_.-]+$ and refuses duplicates.

    An unslugged theme would not degrade the report, it would abort the whole
    compile, so this is checked here rather than discovered there.
    """
    import re

    plan = build_plan(
        claims=[
            _claim("c1", "s1", theme="Evaluation & Benchmarks"),
            _claim("c2", "s2", theme="Evaluation / Benchmarks"),
        ],
        evidence_index=INDEX,
    )
    ids = [section["section_id"] for section in plan["sections"]]
    assert len(ids) == len(set(ids)), ids
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in ids), ids


def test_a_theme_whose_only_claim_is_dropped_leaves_no_empty_section() -> None:
    """Grouping after validation, asserted directly.

    The dropped claim cites evidence the pack does not contain. If grouping ran
    first, "Orphans" would appear as a heading with nothing beneath it.
    """
    plan = build_plan(
        claims=[
            _claim("c1", "s1", theme="Kept"),
            _claim("c2", "missing-source", theme="Orphans"),
        ],
        evidence_index=INDEX,
    )
    assert _titles(plan) == ["Kept"]
    assert any("absent from the source pack" in gap["text"] for gap in plan["evidence_gaps"])


def test_alternate_label_keys_are_accepted() -> None:
    plan = build_plan(
        claims=[_claim("c1", "s1", section="Retrieval"), _claim("c2", "s2", topic="Generation")],
        evidence_index=INDEX,
    )
    assert _titles(plan) == ["Retrieval", "Generation"]


def test_contradicted_by_becomes_a_labelled_contradicts_link() -> None:
    """Disagreement travels as a first-class relation, not a lost annotation."""
    claim = _claim(
        "c1",
        "s1",
        contradicted_by=[
            {"source_id": "s2", "quote": "Retrieval quality does not improve under this claim's conditions."},
            # Absent from the pack: dropped, never allowed to abort the compile.
            {"source_id": "missing-source", "quote": "Retrieval quality is disputed by this absent source."},
            # Too short for the compiler's quote bounds: dropped for the same reason.
            {"source_id": "s3", "quote": "No."},
        ],
    )
    plan = build_plan(claims=[claim], evidence_index=INDEX)
    links = plan["sections"][0]["claims"][0]["evidence_links"]
    relations = {(link["evidence_id"], link["relation"]) for link in links}
    assert ("ev_1", "supports") in relations
    assert ("ev_2", "contradicts") in relations
    assert not any(link["evidence_id"] == "ev_3" for link in links)
    assert len(links) == 2


def test_missing_citation_gap_names_ids_in_text_only() -> None:
    """A gap about an absent id must not itself cite the absent id.

    The compiler resolves every gap evidence_id against the pack and raises
    evidence_id_unknown for one it does not contain -- which is exactly what a
    missing-citation gap reports, so carrying the id in the ids field aborts
    the whole compile.
    """
    claim = _claim("c1", "s1")
    claim["evidence_ids"] = ["s1", "absent-source"]
    plan = build_plan(claims=[claim], evidence_index=INDEX)
    gap = next(item for item in plan["evidence_gaps"] if "absent" in item["text"])
    assert gap["evidence_ids"] == []
    assert "absent-source" in gap["text"]
