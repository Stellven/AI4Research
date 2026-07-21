"""Cross-source resonance level computation (G0–G5).

Resonance levels per ADR §"三源共振等级":
  G0 — Code-only Spike
  G1 — Code + Social mention
  G2 — Code + Paper reference
  G3 — Code + Social + Paper (tri-source)
  G4 — Sustained Resonance (tri-source + >7d)
  G5 — Sustained Resonance + intervention outcome

The resonance level is stamped on Direction Brief and GitHubEvidencePacket.
"""
from __future__ import annotations

from typing import Any


RESONANCE_LEVELS = ("G0", "G1", "G2", "G3", "G4", "G5")


def compute_resonance_level(
    has_code_signal: bool = False,
    has_social_mention: bool = False,
    has_paper_ref: bool = False,
    sustained_days: int = 0,
    has_intervention: bool = False,
) -> str:
    """Compute resonance level from source presence flags."""
    if not has_code_signal:
        return "G0"
    sources = sum([has_code_signal, has_social_mention, has_paper_ref])
    if sources >= 3 and has_intervention:
        return "G5"
    if sources >= 3 and sustained_days > 7:
        return "G4"
    if sources >= 3:
        return "G3"
    if has_code_signal and has_paper_ref:
        return "G2"
    if has_code_signal and has_social_mention:
        return "G1"
    return "G0"


def stamp_packet_resonance(
    packet: dict[str, Any] | None = None,
    cross_source_refs: dict[str, Any] | None = None,
) -> str:
    """Compute and return resonance level for a packet given its cross-source refs."""
    refs = cross_source_refs or {}
    if packet:
        refs.update(_safe_json_load(packet.get("cross_source_refs_json", "{}")))

    has_social = bool(refs.get("social_mentions") or refs.get("influence_thesis_ids"))
    has_paper = bool(refs.get("paper_ids") or refs.get("hf_paper_refs"))
    sustained = refs.get("sustained_days", 0)
    has_intervention = bool(refs.get("intervention_outcome"))

    return compute_resonance_level(
        has_code_signal=True,
        has_social_mention=has_social,
        has_paper_ref=has_paper,
        sustained_days=sustained,
        has_intervention=has_intervention,
    )


def _safe_json_load(value: str) -> dict[str, Any]:
    import json
    try:
        return json.loads(value) if value else {}
    except (json.JSONDecodeError, TypeError):
        return {}
