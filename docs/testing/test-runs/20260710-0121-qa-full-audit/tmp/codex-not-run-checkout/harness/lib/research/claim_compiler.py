"""Claim Compiler v2 — atomic claim + evidence alignment + contradiction search.

Provides the contract interface for the next-generation claim pipeline.
The compiler aligns claims with supporting/contradicting evidence atoms
and supports high-impact claim paths that trigger counter-evidence lookup.

This module defines the contract (interfaces and data models) so that
downstream nodes can implement concrete strategies without modifying
the CLI or the core claim-mining loop.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Protocol


# ---------------------------------------------------------------------------
# Alignment status
# ---------------------------------------------------------------------------

class AlignmentStatus(Enum):
    """Result of aligning a claim with its evidence."""
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    MIXED = "mixed"
    UNVERIFIED = "unverified"


# ---------------------------------------------------------------------------
# ClaimEvidenceAlignment — atomic claim + evidence pair
# ---------------------------------------------------------------------------

@dataclass
class ClaimEvidenceAlignment:
    """One claim aligned against its supporting and contradicting evidence."""

    claim_id: str
    claim_text: str
    section_path: str
    supporting_evidence_ids: list[str] = field(default_factory=list)
    contradicting_evidence_ids: list[str] = field(default_factory=list)
    neutral_evidence_ids: list[str] = field(default_factory=list)
    alignment_status: AlignmentStatus = AlignmentStatus.UNVERIFIED
    confidence: float = 0.0
    is_high_impact: bool = False
    counter_evidence_requested: bool = False
    counter_evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# CounterEvidenceRequest — request for contradiction search
# ---------------------------------------------------------------------------

@dataclass
class CounterEvidenceRequest:
    """Request to search for counter-evidence against a high-impact claim."""

    claim_id: str
    claim_text: str
    section_path: str
    search_queries: list[str] = field(default_factory=list)
    max_results_per_query: int = 5
    priority: str = "normal"  # "normal" | "high" | "critical"
    reason: str = ""


# ---------------------------------------------------------------------------
# Protocol: ClaimCompilerStrategy
# ---------------------------------------------------------------------------

class ClaimCompilerStrategy(Protocol):
    """Protocol for claim compiler implementations.

    Implementations can vary by depth tier, evidence source availability,
    or model routing strategy.
    """

    def compile(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        *,
        enable_contradiction_search: bool = False,
        high_impact_threshold: float = 0.7,
    ) -> list[ClaimEvidenceAlignment]:
        """Compile claims with evidence alignment.

        Args:
            conn: Active SQLite connection.
            run_id: Research run ID.
            enable_contradiction_search: Whether to search for counter-evidence.
            high_impact_threshold: Confidence threshold above which claims are
                marked high-impact and eligible for counter-evidence lookup.

        Returns:
            List of ClaimEvidenceAlignment objects.
        """
        ...

    def request_counter_evidence(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        alignment: ClaimEvidenceAlignment,
    ) -> CounterEvidenceRequest:
        """Build a counter-evidence search request for a high-impact claim.

        The request contains search queries designed to find contradicting
        evidence. The caller is responsible for executing the search and
        updating the alignment with results.
        """
        ...


# ---------------------------------------------------------------------------
# Protocol: CounterEvidenceSearcher
# ---------------------------------------------------------------------------

class CounterEvidenceSearcher(Protocol):
    """Protocol for executing counter-evidence searches."""

    def search(
        self,
        request: CounterEvidenceRequest,
    ) -> list[dict[str, Any]]:
        """Execute counter-evidence search and return raw evidence dicts."""
        ...


# ---------------------------------------------------------------------------
# Default implementation: NaiveClaimCompiler
# ---------------------------------------------------------------------------

class NaiveClaimCompiler:
    """Minimal claim compiler that reads claims and links from the DB.

    This is the default strategy for the v2 contract. It reads existing
    claims and claim_evidence_links, groups them into alignments, and
    identifies high-impact claims eligible for counter-evidence lookup.
    """

    def compile(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        *,
        enable_contradiction_search: bool = False,
        high_impact_threshold: float = 0.7,
    ) -> list[ClaimEvidenceAlignment]:
        claims = conn.execute(
            "SELECT id, claim_text, section_ref, confidence, stance FROM claims WHERE run_id = ?",
            (run_id,),
        ).fetchall()

        alignments: list[ClaimEvidenceAlignment] = []
        for claim in claims:
            claim_id = claim["id"]
            links = conn.execute(
                "SELECT evidence_id, relation, strength FROM claim_evidence WHERE claim_id = ?",
                (claim_id,),
            ).fetchall()

            supporting: list[str] = []
            contradicting: list[str] = []
            neutral: list[str] = []

            for link in links:
                rel = link["relation"]
                eid = link["evidence_id"]
                if rel == "supports":
                    supporting.append(eid)
                elif rel == "refutes":
                    contradicting.append(eid)
                else:
                    neutral.append(eid)

            confidence = claim["confidence"] or 0.0
            is_high_impact = confidence >= high_impact_threshold

            if contradicting and not supporting:
                status = AlignmentStatus.CONTRADICTED
            elif supporting and not contradicting:
                status = AlignmentStatus.SUPPORTED
            elif supporting and contradicting:
                status = AlignmentStatus.MIXED
            else:
                status = AlignmentStatus.UNVERIFIED

            alignments.append(ClaimEvidenceAlignment(
                claim_id=claim_id,
                claim_text=claim["claim_text"],
                section_path=claim["section_ref"] or "",
                supporting_evidence_ids=supporting,
                contradicting_evidence_ids=contradicting,
                neutral_evidence_ids=neutral,
                alignment_status=status,
                confidence=confidence,
                is_high_impact=is_high_impact,
                counter_evidence_requested=enable_contradiction_search and is_high_impact,
            ))

        return alignments

    def request_counter_evidence(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        alignment: ClaimEvidenceAlignment,
    ) -> CounterEvidenceRequest:
        """Generate counter-evidence queries from a high-impact claim."""
        claim_text = alignment.claim_text
        # Build negation-style queries
        queries = [
            f"evidence against {claim_text[:100]}",
            f"criticism limitation {claim_text[:80]}",
            f"contradicting findings {claim_text[:80]}",
        ]
        return CounterEvidenceRequest(
            claim_id=alignment.claim_id,
            claim_text=claim_text,
            section_path=alignment.section_path,
            search_queries=queries,
            max_results_per_query=5,
            priority="high" if alignment.confidence >= 0.9 else "normal",
            reason=f"high_impact_claim(confidence={alignment.confidence:.2f})",
        )
