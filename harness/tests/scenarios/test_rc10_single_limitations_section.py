"""A report gets one limitations section, not one per revision attempt.

`_normalize_report` appended "## Limitations" unconditionally, after the
heading-dedupe pass had already run. When the model wrote its own limitations
section the operator added a second one, and the reviewer raised a CRITICAL
finding for the duplicate. Because the append ran again on every revision
attempt, the operator recreated the duplicate each time, so the finding could
never be cleared and `report_revision` could not converge.

Duplicate headings are also not cosmetic here. `final_acceptance` looks for a
substantive limitations section and checks that every recorded limitation is
rendered; two competing sections make that check depend on which one is found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[2]
if str(HARNESS / "plugins" / "autosci") not in sys.path:
    sys.path.insert(0, str(HARNESS / "plugins" / "autosci"))

from operators.research_synthesis.report_draft import (  # noqa: E402
    _merge_limitations_section,
)

A = "Only five sources survived validation."
B = "Coverage is limited to English-language venues."


def _headings(body: str) -> list[str]:
    return re.findall(r"(?m)^#{2,6}\s*(.+?)\s*$", body)


def test_an_existing_section_is_extended_not_duplicated() -> None:
    body = f"# Title\n\n## Limitations\n\n- {A}\n"
    merged = _merge_limitations_section(body, [A, B], "Limitations")
    assert _headings(merged).count("Limitations") == 1
    assert A in merged and B in merged


def test_a_section_is_created_when_none_exists() -> None:
    body = "# Title\n\n## Summary\n\nText.\n"
    merged = _merge_limitations_section(body, [A], "Limitations")
    assert _headings(merged).count("Limitations") == 1
    assert A in merged


def test_repeated_merges_stay_idempotent() -> None:
    """The revision loop calls this on every attempt.

    Non-idempotence here is precisely what made the critical duplicate finding
    unclearable, so it is asserted directly rather than assumed.
    """
    body = "# Title\n\n## Summary\n\nText.\n"
    once = _merge_limitations_section(body, [A, B], "Limitations")
    twice = _merge_limitations_section(once, [A, B], "Limitations")
    thrice = _merge_limitations_section(twice, [A, B], "Limitations")
    assert once == twice == thrice
    assert _headings(thrice).count("Limitations") == 1


def test_entries_land_under_the_heading_not_at_the_end_of_the_document() -> None:
    body = f"# Title\n\n## Limitations\n\n- {A}\n\n## Sources\n\n- Example\n"
    merged = _merge_limitations_section(body, [A, B], "Limitations")
    limitations_at = merged.index("## Limitations")
    sources_at = merged.index("## Sources")
    assert limitations_at < merged.index(B) < sources_at


def test_nothing_is_added_when_everything_is_already_rendered() -> None:
    body = f"# Title\n\n## Limitations\n\n- {A}\n- {B}\n"
    assert _merge_limitations_section(body, [A, B], "Limitations") == body


def test_no_limitations_leaves_the_body_untouched() -> None:
    body = "# Title\n\n## Summary\n\nText.\n"
    assert _merge_limitations_section(body, [], "Limitations") == body
