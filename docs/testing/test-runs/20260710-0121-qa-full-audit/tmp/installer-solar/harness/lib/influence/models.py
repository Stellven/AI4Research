"""Canonical data models for the AI Influence Insight / Social Signal Plane.

These dataclasses are the single object model the convergence collapses the three
legacy lines (X backend digest, YouTube transcript digest, AI influence digest)
into. Field names mirror the frozen fixtures under tests/influence/fixtures/ and
the JSON Schemas under schemas/influence/.

No I/O and no network here — pure structures plus (de)serialization helpers so
they can be unit-tested in isolation and round-tripped against the schemas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Schema versions are the contract handshake with schemas/influence/*.schema.json
STATEMENT_SCHEMA_VERSION = "influence.statement.v1"
THESIS_SCHEMA_VERSION = "influence.thesis.v1"
EVIDENCE_PACKET_SCHEMA_VERSION = "influence.evidence_packet.v1"
INFLUENCER_PROFILE_SCHEMA_VERSION = "influence.influencer_profile.v1"

# The 7 local scores the EvidencePacket must always carry (ADR + S1-design §4.6).
LOCAL_SCORE_KEYS = (
    "novelty",
    "signal_strength",
    "source_credibility",
    "cross_source_resonance",
    "timeliness",
    "actionability",
    "contrarian_score",
)

# Buckets the ThesisMapper fills; empty lists are valid, coverage_gap records why.
MAPPED_EVIDENCE_BUCKETS = (
    "papers",
    "github_repos",
    "hf_assets",
    "conference_events",
    "company_releases",
    "financial_events",
    "major_news",
)


@dataclass
class Author:
    platform: str
    handle: str
    display_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"platform": self.platform, "handle": self.handle, "display_name": self.display_name}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Author":
        return cls(
            platform=d["platform"],
            handle=d["handle"],
            display_name=d.get("display_name", ""),
        )


@dataclass
class QualityFlags:
    is_quote: bool = False
    is_reply: bool = False
    is_joke_or_meme: bool = False
    is_marketing: bool = False
    transcript_quality: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_quote": self.is_quote,
            "is_reply": self.is_reply,
            "is_joke_or_meme": self.is_joke_or_meme,
            "is_marketing": self.is_marketing,
            "transcript_quality": self.transcript_quality,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "QualityFlags":
        return cls(
            is_quote=bool(d.get("is_quote", False)),
            is_reply=bool(d.get("is_reply", False)),
            is_joke_or_meme=bool(d.get("is_joke_or_meme", False)),
            is_marketing=bool(d.get("is_marketing", False)),
            transcript_quality=d.get("transcript_quality"),
        )


@dataclass
class Statement:
    statement_id: str
    source: str
    text: str
    author: Author
    timestamp: str = ""
    source_url: str = ""
    language: str = ""
    entities: list[str] = field(default_factory=list)
    entities_source: str = ""
    quality_flags: QualityFlags = field(default_factory=QualityFlags)
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = STATEMENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "statement_id": self.statement_id,
            "source": self.source,
            "source_url": self.source_url,
            "author": self.author.to_dict(),
            "timestamp": self.timestamp,
            "text": self.text,
            "language": self.language,
            "entities": list(self.entities),
            "quality_flags": self.quality_flags.to_dict(),
            "raw_metadata": dict(self.raw_metadata),
        }
        if self.entities_source:
            d["entities_source"] = self.entities_source
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Statement":
        return cls(
            statement_id=d["statement_id"],
            source=d["source"],
            text=d["text"],
            author=Author.from_dict(d.get("author", {"platform": "", "handle": ""})),
            timestamp=d.get("timestamp", ""),
            source_url=d.get("source_url", ""),
            language=d.get("language", ""),
            entities=list(d.get("entities", [])),
            entities_source=d.get("entities_source", ""),
            quality_flags=QualityFlags.from_dict(d.get("quality_flags", {})),
            raw_metadata=dict(d.get("raw_metadata", {})),
            schema_version=d.get("schema_version", STATEMENT_SCHEMA_VERSION),
        )


@dataclass
class Thesis:
    thesis_id: str
    claim: str
    derived_from_statements: list[str] = field(default_factory=list)
    viewpoint_cluster: str = ""
    confidence: float = 0.0
    extraction_method: str = ""
    extraction_source: str = ""
    schema_version: str = THESIS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "thesis_id": self.thesis_id,
            "derived_from_statements": list(self.derived_from_statements),
            "claim": self.claim,
            "viewpoint_cluster": self.viewpoint_cluster,
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
            "extraction_source": self.extraction_source,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Thesis":
        return cls(
            thesis_id=d["thesis_id"],
            claim=d["claim"],
            derived_from_statements=list(d.get("derived_from_statements", [])),
            viewpoint_cluster=d.get("viewpoint_cluster", ""),
            confidence=float(d.get("confidence", 0.0)),
            extraction_method=d.get("extraction_method", ""),
            extraction_source=d.get("extraction_source", ""),
            schema_version=d.get("schema_version", THESIS_SCHEMA_VERSION),
        )


def empty_mapped_evidence() -> dict[str, Any]:
    """A fully-shaped mapped_evidence block with all buckets + coverage_gap."""
    block: dict[str, Any] = {bucket: [] for bucket in MAPPED_EVIDENCE_BUCKETS}
    block["coverage_gap"] = []
    return block


@dataclass
class InfluenceEvidencePacket:
    packet_id: str
    thesis_id: str
    thesis_claim: str
    local_scores: dict[str, float] = field(default_factory=dict)
    mapped_evidence: dict[str, Any] = field(default_factory=empty_mapped_evidence)
    questions_for_high_model: list[str] = field(default_factory=list)
    source_statements: list[str] = field(default_factory=list)
    generated_at: str = ""
    schema_version: str = EVIDENCE_PACKET_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "thesis_id": self.thesis_id,
            "thesis_claim": self.thesis_claim,
            "local_scores": dict(self.local_scores),
            "mapped_evidence": dict(self.mapped_evidence),
            "questions_for_high_model": list(self.questions_for_high_model),
            "source_statements": list(self.source_statements),
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InfluenceEvidencePacket":
        return cls(
            packet_id=d["packet_id"],
            thesis_id=d["thesis_id"],
            thesis_claim=d["thesis_claim"],
            local_scores=dict(d.get("local_scores", {})),
            mapped_evidence=dict(d.get("mapped_evidence", empty_mapped_evidence())),
            questions_for_high_model=list(d.get("questions_for_high_model", [])),
            source_statements=list(d.get("source_statements", [])),
            generated_at=d.get("generated_at", ""),
            schema_version=d.get("schema_version", EVIDENCE_PACKET_SCHEMA_VERSION),
        )


@dataclass
class InfluencerProfile:
    influencer_id: str
    display_name: str
    tier: str = "T3"
    categories: list[str] = field(default_factory=list)
    platform_accounts: dict[str, str] = field(default_factory=dict)
    expertise_tags: list[str] = field(default_factory=list)
    bias_profile: dict[str, Any] = field(default_factory=dict)
    influence_weight: float = 0.5
    role_at_time: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = INFLUENCER_PROFILE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "influencer_id": self.influencer_id,
            "display_name": self.display_name,
            "tier": self.tier,
            "categories": list(self.categories),
            "platform_accounts": dict(self.platform_accounts),
            "expertise_tags": list(self.expertise_tags),
            "bias_profile": dict(self.bias_profile),
            "influence_weight": self.influence_weight,
            "role_at_time": list(self.role_at_time),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InfluencerProfile":
        return cls(
            influencer_id=d["influencer_id"],
            display_name=d["display_name"],
            tier=d.get("tier", "T3"),
            categories=list(d.get("categories", [])),
            platform_accounts=dict(d.get("platform_accounts", {})),
            expertise_tags=list(d.get("expertise_tags", [])),
            bias_profile=dict(d.get("bias_profile", {})),
            influence_weight=float(d.get("influence_weight", 0.5)),
            role_at_time=list(d.get("role_at_time", [])),
            schema_version=d.get("schema_version", INFLUENCER_PROFILE_SCHEMA_VERSION),
        )
