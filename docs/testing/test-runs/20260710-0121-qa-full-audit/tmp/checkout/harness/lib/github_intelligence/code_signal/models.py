"""Code Signal Plane — five unified object models.

Models (frozen per S1-design §2):
  RepoSnapshot       — point-in-time observation (append-only)
  RepoCanonical      — identity-resolved record (upsert by repo_key)
  RepoEnrichment     — compressed structure from README/releases/issues
  RepoSignal         — multi-objective scores + class + actionability
  GitHubEvidencePacket — compressed LLM input (sole legal high-model feed)
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, ClassVar


SCHEMA_VERSION = "code_signal.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_id(prefix: str) -> str:
    import uuid
    return prefix + uuid.uuid4().hex[:16]


def _json_dump(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load(value: str | None) -> Any:
    if value is None or value == "":
        return None
    return json.loads(value)


# ---------------------------------------------------------------------------
# RepoSnapshot
# ---------------------------------------------------------------------------


@dataclass
class RepoSnapshot:
    """L0/L1 — point-in-time repo observation. Append-only."""

    snapshot_id: str = field(default_factory=lambda: _gen_id("snap-"))
    repo_key: str = ""  # owner/repo
    observed_at: str = field(default_factory=utc_now_iso)
    source: str = ""  # trending | search | tracked | social_mention
    stars: int | None = None
    forks: int | None = None
    watchers: int | None = None
    open_issues: int | None = None
    language: str | None = None
    topics_json: str = "[]"
    description: str | None = None
    homepage: str | None = None
    license_key: str | None = None
    created_at: str | None = None
    pushed_at: str | None = None
    archived: bool = False
    stars_delta_24h: int | None = None
    stars_delta_7d: int | None = None
    commit_count_7d: int | None = None
    active_contributors_30d: int | None = None
    discovery_provenance_json: str = "{}"

    JSON_FIELDS: ClassVar[tuple[str, ...]] = (
        "topics_json",
        "discovery_provenance_json",
    )
    TABLE: ClassVar[str] = "cs_repo_snapshots"

    def to_row(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RepoSnapshot:
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# RepoCanonical
# ---------------------------------------------------------------------------


@dataclass
class RepoCanonical:
    """L1 — identity-resolved canonical record. Upsert by repo_key."""

    repo_key: str = ""  # PK: owner/repo
    canonical_name: str = ""
    owner: str = ""
    owner_type: str = ""  # User | Organization
    first_seen_at: str = field(default_factory=utc_now_iso)
    last_seen_at: str = field(default_factory=utc_now_iso)
    seen_count: int = 1
    seen_sources_json: str = "[]"
    dedup_keys_json: str = "[]"

    JSON_FIELDS: ClassVar[tuple[str, ...]] = (
        "seen_sources_json",
        "dedup_keys_json",
    )
    TABLE: ClassVar[str] = "cs_repo_canonicals"

    def to_row(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RepoCanonical:
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# RepoEnrichment
# ---------------------------------------------------------------------------


@dataclass
class RepoEnrichment:
    """L2 — compressed structure from README, releases, issues, PR, contributors."""

    enrichment_id: str = field(default_factory=lambda: _gen_id("enr-"))
    repo_key: str = ""
    observed_at: str = field(default_factory=utc_now_iso)
    readme_compressed: str | None = None
    readme_top_tags_json: str = "[]"
    latest_release_tag: str | None = None
    latest_release_notes_compressed: str | None = None
    latest_release_at: str | None = None
    recent_issues_sample_json: str = "[]"
    recent_prs_sample_json: str = "[]"
    contributors_summary_json: str = "{}"
    evidence_ids_json: str = "[]"

    JSON_FIELDS: ClassVar[tuple[str, ...]] = (
        "readme_top_tags_json",
        "recent_issues_sample_json",
        "recent_prs_sample_json",
        "contributors_summary_json",
        "evidence_ids_json",
    )
    TABLE: ClassVar[str] = "cs_repo_enrichments"

    def to_row(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RepoEnrichment:
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# RepoSignal
# ---------------------------------------------------------------------------


@dataclass
class RepoSignal:
    """L3 — multi-objective scores, signal class, actionability flags."""

    signal_id: str = field(default_factory=lambda: _gen_id("sig-"))
    repo_key: str = ""
    scored_at: str = field(default_factory=utc_now_iso)
    score_window: str = "daily"  # daily | weekly | monthly
    github_hotspot: float = 0.0
    technical_substance: float = 0.0
    community_health: float = 0.0
    intervention_opportunity: float = 0.0
    open_project_opportunity: float = 0.0
    strategic_fit: float = 0.0
    noise_risk: float = 0.0
    signal_class: str = ""  # rising | hot | sustained | cooling
    actionability_flags_json: str = "[]"
    evidence_ids_json: str = "[]"

    JSON_FIELDS: ClassVar[tuple[str, ...]] = (
        "actionability_flags_json",
        "evidence_ids_json",
    )
    TABLE: ClassVar[str] = "cs_repo_signals"

    def is_noise_filtered(self) -> bool:
        return self.noise_risk >= 0.6

    def to_row(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RepoSignal:
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# GitHubEvidencePacket
# ---------------------------------------------------------------------------


@dataclass
class GitHubEvidencePacket:
    """L4 — compressed high-LLM input. Sole legal high-model feed.

    Invariant: high model may only consume this type, never raw repo lists.
    """

    packet_id: str = field(default_factory=lambda: _gen_id("gep-"))
    packet_version: str = "v1"
    repo_key: str = ""
    built_at: str = field(default_factory=utc_now_iso)
    snapshot_summary_json: str = "{}"
    enrichment_summary_json: str = "{}"
    signal_summary_json: str = "{}"
    evidence_refs_json: str = "[]"
    cross_source_refs_json: str = "{}"
    local_scores_json: str = "{}"
    questions_for_high_model_json: str = "[]"
    resonance_level: str = "G0"  # G0..G5

    JSON_FIELDS: ClassVar[tuple[str, ...]] = (
        "snapshot_summary_json",
        "enrichment_summary_json",
        "signal_summary_json",
        "evidence_refs_json",
        "cross_source_refs_json",
        "local_scores_json",
        "questions_for_high_model_json",
    )
    TABLE: ClassVar[str] = "cs_github_evidence_packets"
    RESONANCE_LEVELS: ClassVar[tuple[str, ...]] = (
        "G0", "G1", "G2", "G3", "G4", "G5",
    )

    def validate_evidence_refs(self) -> None:
        refs = _json_load(self.evidence_refs_json) or []
        if not refs:
            raise ValueError(
                f"GitHubEvidencePacket requires ≥1 evidence_refs, "
                f"got none for {self.repo_key}"
            )

    def to_row(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> GitHubEvidencePacket:
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Output Asset shapes (7 types, per S1-design §6)
# ---------------------------------------------------------------------------


@dataclass
class OutputAsset:
    """Base for all 7 output asset types."""

    asset_id: str = field(default_factory=lambda: _gen_id("asset-"))
    asset_type: str = ""
    repo_key: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    evidence_refs_json: str = "[]"
    content_json: str = "{}"

    TABLE: ClassVar[str] = "cs_output_assets"

    def validate_evidence_refs(self) -> None:
        refs = _json_load(self.evidence_refs_json) or []
        if not refs:
            raise ValueError(
                f"OutputAsset ({self.asset_type}) requires ≥1 evidence_refs, "
                f"got none for {self.repo_key}"
            )

    def to_row(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> OutputAsset:
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        return cls(**kwargs)


ASSET_TYPES: tuple[str, ...] = (
    "github_hotspot_card",
    "direction_brief",
    "community_intervention_plan",
    "open_source_project_brief",
    "ai_influence_topic",
    "deep_research_seed_pack",
    "action_queue",
)


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------


DDL_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS cs_repo_snapshots (
        snapshot_id                TEXT PRIMARY KEY,
        repo_key                   TEXT NOT NULL,
        observed_at                TEXT NOT NULL,
        source                     TEXT NOT NULL DEFAULT '',
        stars                      INTEGER,
        forks                      INTEGER,
        watchers                   INTEGER,
        open_issues                INTEGER,
        language                   TEXT,
        topics_json                TEXT DEFAULT '[]',
        description                TEXT,
        homepage                   TEXT,
        license_key                TEXT,
        created_at                 TEXT,
        pushed_at                  TEXT,
        archived                   INTEGER DEFAULT 0,
        stars_delta_24h            INTEGER,
        stars_delta_7d             INTEGER,
        commit_count_7d            INTEGER,
        active_contributors_30d    INTEGER,
        discovery_provenance_json  TEXT DEFAULT '{}'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cs_snap_repo_at ON cs_repo_snapshots(repo_key, observed_at)",
    """CREATE TABLE IF NOT EXISTS cs_repo_canonicals (
        repo_key             TEXT PRIMARY KEY,
        canonical_name       TEXT DEFAULT '',
        owner                TEXT DEFAULT '',
        owner_type           TEXT DEFAULT '',
        first_seen_at        TEXT NOT NULL,
        last_seen_at         TEXT NOT NULL,
        seen_count           INTEGER DEFAULT 1,
        seen_sources_json    TEXT DEFAULT '[]',
        dedup_keys_json      TEXT DEFAULT '[]'
    )""",
    """CREATE TABLE IF NOT EXISTS cs_repo_enrichments (
        enrichment_id                  TEXT PRIMARY KEY,
        repo_key                       TEXT NOT NULL,
        observed_at                    TEXT NOT NULL,
        readme_compressed              TEXT,
        readme_top_tags_json           TEXT DEFAULT '[]',
        latest_release_tag             TEXT,
        latest_release_notes_compressed TEXT,
        latest_release_at              TEXT,
        recent_issues_sample_json      TEXT DEFAULT '[]',
        recent_prs_sample_json         TEXT DEFAULT '[]',
        contributors_summary_json      TEXT DEFAULT '{}',
        evidence_ids_json              TEXT DEFAULT '[]'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cs_enr_repo ON cs_repo_enrichments(repo_key, observed_at)",
    """CREATE TABLE IF NOT EXISTS cs_repo_signals (
        signal_id                  TEXT PRIMARY KEY,
        repo_key                   TEXT NOT NULL,
        scored_at                  TEXT NOT NULL,
        score_window               TEXT DEFAULT 'daily',
        github_hotspot             REAL DEFAULT 0.0,
        technical_substance        REAL DEFAULT 0.0,
        community_health           REAL DEFAULT 0.0,
        intervention_opportunity   REAL DEFAULT 0.0,
        open_project_opportunity   REAL DEFAULT 0.0,
        strategic_fit              REAL DEFAULT 0.0,
        noise_risk                 REAL DEFAULT 0.0,
        signal_class               TEXT DEFAULT '',
        actionability_flags_json   TEXT DEFAULT '[]',
        evidence_ids_json          TEXT DEFAULT '[]'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cs_sig_repo ON cs_repo_signals(repo_key, scored_at)",
    """CREATE TABLE IF NOT EXISTS cs_github_evidence_packets (
        packet_id                      TEXT PRIMARY KEY,
        packet_version                 TEXT DEFAULT 'v1',
        repo_key                       TEXT NOT NULL,
        built_at                       TEXT NOT NULL,
        snapshot_summary_json          TEXT DEFAULT '{}',
        enrichment_summary_json        TEXT DEFAULT '{}',
        signal_summary_json            TEXT DEFAULT '{}',
        evidence_refs_json             TEXT DEFAULT '[]',
        cross_source_refs_json         TEXT DEFAULT '{}',
        local_scores_json              TEXT DEFAULT '{}',
        questions_for_high_model_json  TEXT DEFAULT '[]',
        resonance_level                TEXT DEFAULT 'G0'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cs_pkt_repo ON cs_github_evidence_packets(repo_key, built_at)",
    """CREATE TABLE IF NOT EXISTS cs_output_assets (
        asset_id           TEXT PRIMARY KEY,
        asset_type         TEXT NOT NULL,
        repo_key           TEXT NOT NULL,
        generated_at       TEXT NOT NULL,
        evidence_refs_json TEXT DEFAULT '[]',
        content_json       TEXT DEFAULT '{}'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cs_asset_type ON cs_output_assets(asset_type, generated_at)",
)


def apply_schema(conn: sqlite3.Connection) -> None:
    for ddl in DDL_STATEMENTS:
        conn.execute(ddl)
    conn.commit()
