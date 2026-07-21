"""Schema — 6 core entity dataclasses + DDL for HF Paper Insight Flow.

Per data_models.md §1: PaperSnapshot, PaperCanonical, PaperEnrichment,
PaperTaxonomy, PaperSignal, PaperEvidencePacket.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class WindowType(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class ResonanceLevel(str, Enum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:16]


def _title_hash(title: str) -> str:
    return hashlib.sha256(title.lower().strip().encode()).hexdigest()[:24]


# ── §1.1 PaperSnapshot ──────────────────────────────────────────────


@dataclass
class PaperSnapshot:
    snapshot_id: str = field(default_factory=lambda: _gen_id("snap-"))
    window_type: WindowType = WindowType.daily
    window_start: str = ""
    window_end: str = ""
    source: str = "huggingface_papers"
    paper_id: str = ""
    rank: int = 0
    upvotes: int = 0
    hf_url: str = ""
    observed_at: str = field(default_factory=_utc_now)
    first_seen_in_window: int = 1

    UNIQUE_CONSTRAINT = ("window_type", "window_start", "paper_id")


# ── §1.2 PaperCanonical ─────────────────────────────────────────────


@dataclass
class PaperCanonical:
    paper_id: str = field(default_factory=lambda: _gen_id("paper-"))
    title: str = ""
    title_hash: str = ""
    authors_json: str = "[]"
    orgs_json: str = "[]"
    published_at: Optional[str] = None
    hf_url: str = ""
    arxiv_abs_url: Optional[str] = None
    arxiv_pdf_url: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    arxiv_id: Optional[str] = None
    first_seen_at: str = field(default_factory=_utc_now)
    last_seen_at: str = field(default_factory=_utc_now)
    seen_windows_json: str = "[]"
    dedup_keys_json: str = "[]"
    updated_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.title_hash and self.title:
            self.title_hash = _title_hash(self.title)


# ── §1.3 PaperEnrichment ────────────────────────────────────────────


@dataclass
class PaperEnrichment:
    enrichment_id: str = field(default_factory=lambda: _gen_id("enr-"))
    paper_id: str = ""
    hf_metadata_json: str = "{}"
    arxiv_metadata_json: str = "{}"
    hf_assets_json: str = "{}"
    github_repo_json: str = "{}"
    semantic_scholar_json: str = "{}"
    provider_success_json: str = "{}"
    provider_failures_json: str = "{}"
    fetched_at: str = field(default_factory=_utc_now)
    ttl_expires_at: str = ""


# ── §1.4 PaperTaxonomy ──────────────────────────────────────────────


@dataclass
class PaperTaxonomy:
    taxonomy_id: str = field(default_factory=lambda: _gen_id("tax-"))
    paper_id: str = ""
    domain: str = ""
    method: str = ""
    task: str = ""
    asset: str = ""
    stack_layer: str = ""
    maturity: str = ""
    research_route: str = ""
    labels_json: str = "[]"
    confidence: float = 0.0
    classified_at: str = field(default_factory=_utc_now)


# ── §1.5 PaperSignal ────────────────────────────────────────────────


@dataclass
class PaperSignal:
    signal_id: str = field(default_factory=lambda: _gen_id("sig-"))
    paper_id: str = ""
    research_signal_score: float = 0.0
    insight_report_score: float = 0.0
    experiment_score: float = 0.0
    open_project_score: float = 0.0
    deep_research_seed_score: float = 0.0
    attention_signal: float = 0.0
    novelty_signal: float = 0.0
    reproducibility_signal: float = 0.0
    industry_coupling_signal: float = 0.0
    score_profile: str = "ai-influence"
    score_inputs_json: str = "{}"
    scored_at: str = field(default_factory=_utc_now)


# ── §1.6 PaperEvidencePacket v2 ─────────────────────────────────────


@dataclass
class PaperEvidencePacket:
    packet_id: str = field(default_factory=lambda: _gen_id("pkt-"))
    paper_id: str = ""
    packet_version: str = "v2"
    canonical_summary_json: str = "{}"
    enrichment_summary_json: str = "{}"
    taxonomy_summary_json: str = "{}"
    score_summary_json: str = "{}"
    provenance_json: str = "{}"
    packet_gate_json: str = "{}"
    built_at: str = field(default_factory=_utc_now)
    cache_expires_at: str = ""


# ── DDL ──────────────────────────────────────────────────────────────

ALL_DDL = """
CREATE TABLE IF NOT EXISTS paper_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  window_type TEXT NOT NULL CHECK (window_type IN ('daily', 'weekly', 'monthly')),
  window_start TEXT NOT NULL,
  window_end TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'huggingface_papers',
  paper_id TEXT NOT NULL,
  rank INTEGER NOT NULL,
  upvotes INTEGER NOT NULL DEFAULT 0,
  hf_url TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  first_seen_in_window INTEGER NOT NULL DEFAULT 1,
  UNIQUE(window_type, window_start, paper_id)
);
CREATE INDEX IF NOT EXISTS idx_paper_snapshots_paper_id ON paper_snapshots(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_snapshots_window ON paper_snapshots(window_type, window_start, window_end);

CREATE TABLE IF NOT EXISTS paper_canonical (
  paper_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  title_hash TEXT NOT NULL,
  authors_json TEXT NOT NULL,
  orgs_json TEXT NOT NULL DEFAULT '[]',
  published_at TEXT,
  hf_url TEXT NOT NULL,
  arxiv_abs_url TEXT,
  arxiv_pdf_url TEXT,
  semantic_scholar_id TEXT,
  arxiv_id TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  seen_windows_json TEXT NOT NULL DEFAULT '[]',
  dedup_keys_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_canonical_title_hash ON paper_canonical(title_hash);
CREATE INDEX IF NOT EXISTS idx_paper_canonical_arxiv_id ON paper_canonical(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_paper_canonical_semantic_id ON paper_canonical(semantic_scholar_id);

CREATE TABLE IF NOT EXISTS paper_enrichment (
  enrichment_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL,
  hf_metadata_json TEXT NOT NULL DEFAULT '{}',
  arxiv_metadata_json TEXT NOT NULL DEFAULT '{}',
  hf_assets_json TEXT NOT NULL DEFAULT '{}',
  github_repo_json TEXT NOT NULL DEFAULT '{}',
  semantic_scholar_json TEXT NOT NULL DEFAULT '{}',
  provider_success_json TEXT NOT NULL DEFAULT '{}',
  provider_failures_json TEXT NOT NULL DEFAULT '{}',
  fetched_at TEXT NOT NULL,
  ttl_expires_at TEXT NOT NULL,
  FOREIGN KEY(paper_id) REFERENCES paper_canonical(paper_id)
);
CREATE INDEX IF NOT EXISTS idx_paper_enrichment_paper_id ON paper_enrichment(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_enrichment_ttl ON paper_enrichment(ttl_expires_at);

CREATE TABLE IF NOT EXISTS paper_taxonomy (
  taxonomy_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL,
  domain TEXT NOT NULL,
  method TEXT NOT NULL,
  task TEXT NOT NULL,
  asset TEXT NOT NULL,
  stack_layer TEXT NOT NULL,
  maturity TEXT NOT NULL,
  research_route TEXT NOT NULL,
  labels_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL,
  classified_at TEXT NOT NULL,
  FOREIGN KEY(paper_id) REFERENCES paper_canonical(paper_id)
);
CREATE INDEX IF NOT EXISTS idx_paper_taxonomy_paper_id ON paper_taxonomy(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_taxonomy_domain_route ON paper_taxonomy(domain, research_route);

CREATE TABLE IF NOT EXISTS paper_signals (
  signal_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL,
  research_signal_score REAL NOT NULL,
  insight_report_score REAL NOT NULL,
  experiment_score REAL NOT NULL,
  open_project_score REAL NOT NULL,
  deep_research_seed_score REAL NOT NULL,
  attention_signal REAL NOT NULL,
  novelty_signal REAL NOT NULL,
  reproducibility_signal REAL NOT NULL,
  industry_coupling_signal REAL NOT NULL,
  score_profile TEXT NOT NULL,
  score_inputs_json TEXT NOT NULL,
  scored_at TEXT NOT NULL,
  FOREIGN KEY(paper_id) REFERENCES paper_canonical(paper_id)
);
CREATE INDEX IF NOT EXISTS idx_paper_signals_paper_id ON paper_signals(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_signals_profile ON paper_signals(score_profile);
CREATE INDEX IF NOT EXISTS idx_paper_signals_topline ON paper_signals(research_signal_score, deep_research_seed_score);

CREATE TABLE IF NOT EXISTS paper_evidence_packets (
  packet_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL,
  packet_version TEXT NOT NULL DEFAULT 'v2',
  canonical_summary_json TEXT NOT NULL,
  enrichment_summary_json TEXT NOT NULL,
  taxonomy_summary_json TEXT NOT NULL,
  score_summary_json TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  packet_gate_json TEXT NOT NULL,
  built_at TEXT NOT NULL,
  cache_expires_at TEXT NOT NULL,
  FOREIGN KEY(paper_id) REFERENCES paper_canonical(paper_id)
);
CREATE INDEX IF NOT EXISTS idx_paper_packets_paper_id ON paper_evidence_packets(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_packets_expiry ON paper_evidence_packets(cache_expires_at);

CREATE TABLE IF NOT EXISTS _schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

ENTITY_TABLE_MAP = {
    "PaperSnapshot": "paper_snapshots",
    "PaperCanonical": "paper_canonical",
    "PaperEnrichment": "paper_enrichment",
    "PaperTaxonomy": "paper_taxonomy",
    "PaperSignal": "paper_signals",
    "PaperEvidencePacket": "paper_evidence_packets",
}


def entity_to_row(entity: object) -> dict:
    """Convert dataclass entity to a dict suitable for DB insertion."""
    d = asdict(entity)
    for k, v in d.items():
        if isinstance(v, Enum):
            d[k] = v.value
    return d
