"""A rejected source must record where it came from, not just why it failed.

`_rejection` kept five fields and dropped `provenance` and
`acquisition_channel`, while the accepted path kept both. With a five-source
pack that was invisible. The first live-retrieval run rejected 36 of 66
candidates across arxiv, openalex and europe_pmc, and the artifact could not
answer which provider supplied the rejected ones -- the first question anyone
tuning retrieval asks.

The decision was always correct; only its provenance was missing. These tests
pin the record shape and, deliberately, also pin that recording more does not
change what gets rejected.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[2]
if str(HARNESS / "plugins" / "autosci") not in sys.path:
    sys.path.insert(0, str(HARNESS / "plugins" / "autosci"))

from operators.research_synthesis.source_validation import _rejection  # noqa: E402


def _candidate(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source_id": "arxiv-2401-00001",
        "title": "Off-target detection in CRISPR-Cas9 editing",
        "url": "https://arxiv.org/abs/2401.00001",
        "acquisition_channel": "live_search",
        "provenance": {
            "provider": "arxiv",
            "query": "CRISPR-Cas9 off-target detection",
            "retrieved_at": "2026-08-20T10:00:00Z",
        },
    }
    base.update(extra)
    return base


def test_a_rejected_source_records_its_provider_and_channel() -> None:
    record = _rejection(_candidate(), ["off_topic"], 0)
    assert record["acquisition_channel"] == "live_search"
    assert record["provenance"]["provider"] == "arxiv"
    assert record["provenance"]["query"] == "CRISPR-Cas9 off-target detection"
    assert record["provenance"]["retrieved_at"] == "2026-08-20T10:00:00Z"


def test_the_reason_and_identity_are_still_recorded() -> None:
    """Adding provenance must not have displaced what was already there."""
    record = _rejection(_candidate(), ["off_topic", "no_abstract"], 4)
    assert record["source_id"] == "arxiv-2401-00001"
    assert record["title"].startswith("Off-target detection")
    assert record["url"].endswith("2401.00001")
    assert record["reasons"] == ["off_topic", "no_abstract"]
    assert record["candidate_sha256"]


def test_a_pack_source_records_its_channel_too() -> None:
    """The live run rejected all five pack sources against an off-topic query.

    Those rejections are correct and are exactly the ones worth being able to
    attribute, so the pack channel has to survive too.
    """
    record = _rejection(
        _candidate(acquisition_channel="source_pack", provenance={"provider": "openalex"}),
        ["off_topic"],
        1,
    )
    assert record["acquisition_channel"] == "source_pack"
    assert record["provenance"]["provider"] == "openalex"


def test_provider_at_the_top_level_is_used_when_provenance_omits_it() -> None:
    record = _rejection(
        _candidate(provider="europe_pmc", provenance={}), ["duplicate"], 2
    )
    assert record["provenance"]["provider"] == "europe_pmc"


def test_a_candidate_with_no_origin_yields_empty_strings_not_none() -> None:
    """Absent must read as absent.

    `None` in an artifact field is indistinguishable from "not carried", which
    is the bug this file exists for. Empty strings say the value was looked for.
    """
    record = _rejection(
        {"source_id": "x", "title": "t", "url": "u"}, ["off_topic"], 3
    )
    assert record["acquisition_channel"] == ""
    assert record["provenance"] == {"provider": "", "query": "", "retrieved_at": ""}
    assert record["acquisition_channel"] is not None


def test_the_id_falls_back_to_a_positional_name() -> None:
    record = _rejection({"title": "t"}, ["off_topic"], 6)
    assert record["source_id"] == "candidate-007"
