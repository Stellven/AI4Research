"""AI Influence Insight / Social Signal Plane — unified convergence package.

Collapses three legacy lines (X-backend digest, YouTube transcript digest, AI
influence digest) into one canonical pipeline:

    Statement -> (normalize) -> Thesis -> mapped_evidence -> EvidencePacket -> 8 assets

with quality gates applied at each stage. High models only ever consume the
``InfluenceEvidencePacket`` (contract invariant), never raw posts.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from . import (
    evidence_packet_compiler,
    gates,
    insight_compiler,
    models,
    seed_registry,
    statement_collector,
    statement_normalizer,
    store,
    thesis_extractor,
    thesis_mapper,
)
from .models import (
    Author,
    InfluenceEvidencePacket,
    InfluencerProfile,
    QualityFlags,
    Statement,
    Thesis,
)

__all__ = [
    "Author",
    "QualityFlags",
    "Statement",
    "Thesis",
    "InfluenceEvidencePacket",
    "InfluencerProfile",
    "run_pipeline",
    "models",
    "gates",
    "store",
    "seed_registry",
    "statement_collector",
    "statement_normalizer",
    "thesis_extractor",
    "thesis_mapper",
    "evidence_packet_compiler",
    "insight_compiler",
]


def run_pipeline(
    statements: Iterable[Statement],
    thresholds: Optional[dict[str, Any]] = None,
    connectors: Optional[dict[str, thesis_mapper.Connector]] = None,
    claim_refiner: Optional[thesis_extractor.ClaimRefiner] = None,
    generated_at: str = "",
) -> dict[str, Any]:
    """Run the full Statement -> assets chain with gates applied.

    Returns a structured result with the gated statements, theses, packets, the 8
    output assets per packet, and the gate results — so a caller (or a test) can
    inspect exactly what passed each stage. This is the real integration path the
    thin ``scripts/influence/run_*.py`` CLIs call into.
    """
    # L1: normalize + Statement/Transcript gates
    normalized = statement_normalizer.normalize_batch(statements)
    accepted_statements: list[Statement] = []
    gate_log: list[dict[str, Any]] = []
    for stmt in normalized:
        sg = gates.statement_gate(stmt, thresholds)
        tg = gates.transcript_gate(stmt, thresholds)
        gate_log.append({"statement_id": stmt.statement_id, "statement_gate": sg.to_dict(),
                         "transcript_gate": tg.to_dict()})
        if sg.passed and tg.passed:
            accepted_statements.append(stmt)

    # L2: theses + Thesis gate
    theses = thesis_extractor.extract_theses(accepted_statements, claim_refiner=claim_refiner)
    by_id = {s.statement_id: s for s in accepted_statements}

    packets: list[InfluenceEvidencePacket] = []
    assets_by_packet: dict[str, dict[str, Any]] = {}
    for thesis in theses:
        thg = gates.thesis_gate(thesis, thresholds)
        gate_log.append({"thesis_id": thesis.thesis_id, "thesis_gate": thg.to_dict()})
        if not thg.passed:
            continue
        members = [by_id[sid] for sid in thesis.derived_from_statements if sid in by_id]
        # L3: map evidence
        mapped = thesis_mapper.map_thesis(thesis, connectors)
        # L4: compile packet + Evidence/Compliance gates
        packet = evidence_packet_compiler.compile_packet(thesis, members, mapped, generated_at)
        pdict = packet.to_dict()
        eg = gates.evidence_mapping_gate(pdict, thresholds)
        cg = gates.compliance_gate(pdict)
        gate_log.append({"packet_id": packet.packet_id, "evidence_mapping_gate": eg.to_dict(),
                         "compliance_gate": cg.to_dict()})
        if not (eg.passed and cg.passed):
            continue
        packets.append(packet)
        # L5: render assets
        assets_by_packet[packet.packet_id] = insight_compiler.build_assets(packet)

    return {
        "statements": [s.to_dict() for s in accepted_statements],
        "theses": [t.to_dict() for t in theses],
        "packets": [p.to_dict() for p in packets],
        "assets": assets_by_packet,
        "gate_log": gate_log,
    }
