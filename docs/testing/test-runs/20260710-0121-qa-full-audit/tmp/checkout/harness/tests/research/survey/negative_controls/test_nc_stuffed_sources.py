"""Negative control: same-domain low-authority source stuffing is visible."""

from __future__ import annotations

import json
from pathlib import Path

from research.survey.gates.source_quality_distribution import source_quality_gate
from research.survey.schemas import EvidencePack

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "nc_stuffed_sources.json"


def test_stuffed_sources_trigger_fail_or_stuffing_alert() -> None:
    data = json.loads(FIXTURE.read_text())
    pack = EvidencePack(
        pack_id="nc-stuffed",
        section_id=data["section_id"],
        evidence_ids=[],
        claim_ids=[],
        source_ids=data["source_ids"],
        source_types=data["source_types"],
        contradiction_slots=[],
        status="ready",
    )
    result = source_quality_gate(pack, source_urls=data["source_urls"])
    assert result.verdict == "fail" or len(result.stuffing_alerts) > 0
    assert result.primary_ratio == 0.0
    assert any("no_primary_sources" in reason for reason in result.verdict_reasons)
    assert result.stuffing_alerts[0].domain == "medium.com"

