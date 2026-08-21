"""Part B must derive from the research report, not ignore it.

Before this, `_idea_evaluation` selected a hardcoded benchmark idea and never
opened the report at all. Part A produced a source-grounded, quote-verified
report and Part B then verified artifact digests, which is a provenance replay
with no connection to the research.

Now the accepted report travels through the handoff in the shape AutoSci reads,
and `execute_claim_extract` -- the registered `autosci-evidence-claim-extract`
operator -- pulls the claims. Rebound, not reimplemented: the claims, their
testability tags and their source anchors are AutoSci's.

The honest part is what happens next. The extracted claims are recorded, and the
testable ones are listed as rejected alternatives with the real reason: no
experiment executor is bound, so none of them is executed. Only the lineage
benchmark actually runs. That gap is written into the artifact rather than left
invisible.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[2]
REPO = HARNESS.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.plugins.autosci.operators.fixed_research_poc import (  # noqa: E402
    report_sections,
)

BODY = """# A Report

## Summary

Retrieval augmented generation improves factual grounding in language models.

## Evidence Method

This report uses only traceable claims.

## Findings

Benchmark evaluation shows that systems reduce hallucination by 30 percent.
"""


def test_structured_sections_are_preferred_over_parsing_markdown() -> None:
    """The writer's own division beats one inferred from formatting."""
    report: dict[str, Any] = {
        "body": BODY,
        "sections": [
            {"title": "Findings", "body": "Systems reduce hallucination by 30 percent."},
            {"title": "Limitations", "body": "Coverage is narrow."},
        ],
    }
    rows = report_sections(report)
    assert [row["title"] for row in rows] == ["Findings", "Limitations"]
    assert rows[0]["text"] == "Systems reduce hallucination by 30 percent."
    assert rows[0]["source_anchor"] == "report.md#findings"


def test_markdown_is_split_when_no_structured_sections_exist() -> None:
    rows = report_sections({"body": BODY})
    assert [row["title"] for row in rows] == ["Summary", "Evidence Method", "Findings"]
    assert "hallucination" in rows[2]["text"]


def test_every_section_carries_an_anchor_back_to_the_report() -> None:
    """A claim without a source anchor cannot be traced to what it came from."""
    for row in report_sections({"body": BODY}):
        assert row["source_anchor"].startswith("report.md#")
        assert row["source_anchor"] != "report.md#"


def test_empty_sections_are_dropped_not_emitted_blank() -> None:
    rows = report_sections({"body": "# T\n\n## Empty\n\n## Real\n\nSome content here.\n"})
    assert [row["title"] for row in rows] == ["Real"]


def test_a_report_with_no_body_yields_nothing_rather_than_a_stub() -> None:
    assert report_sections({}) == []
    assert report_sections({"body": ""}) == []
