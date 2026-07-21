"""GitHub Project Intelligence — shared schema, dataclass and row contracts.

Sprint: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s03-core-runtime
Node:   C1_schema_contract

Provides:
- Dataclass models for every L0–L5 storage row (S02 design.md, sections A1–A6)
- Stable row_contract() helpers: dataclass <-> sqlite row (dict)
- DDL constants and migration step list (additive only, never DROP/RENAME)
- Self-verification entry point (`python -m harness.lib.github_intelligence.schema`)

Design constraints honored:
- All timestamps are ISO-8601 UTC strings
- Migrations are additive (existing tech-hotspot-radar.sqlite columns untouched)
- No top-level import of optional dependencies; pure stdlib
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, ClassVar, Iterable

SCHEMA_VERSION = "github_intelligence.v1"


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string (seconds resolution)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_dump(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load(value: str | None) -> Any:
    if value is None or value == "":
        return None
    return json.loads(value)


# ---------------------------------------------------------------------------
# L1 Discovery
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryCandidate:
    """A repo seen by a discovery adapter."""

    full_name: str
    source_type: str  # topic | trending | tracked | social_mention | youtube_mention
    discovered_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    JSON_FIELDS: ClassVar[tuple[str, ...]] = ("metadata",)
    TABLE: ClassVar[str] = "repo_discovery_events"

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["metadata"] = _json_dump(self.metadata)
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "DiscoveryCandidate":
        return cls(
            full_name=row["full_name"],
            source_type=row["source_type"],
            discovered_at=row["discovered_at"],
            metadata=_json_load(row.get("metadata")) or {},
        )


# ---------------------------------------------------------------------------
# L2 Snapshots & Deltas
# ---------------------------------------------------------------------------


@dataclass
class RepoSnapshot:
    snapshot_id: str
    full_name: str
    snapshot_at: str
    stars: int | None = None
    forks: int | None = None
    watchers: int | None = None
    open_issues: int | None = None
    commit_count_7d: int | None = None
    active_contributors_30d: int | None = None
    latest_release_tag: str | None = None
    latest_release_at: str | None = None
    pushed_at: str | None = None
    stars_delta_1h: int | None = None
    stars_delta_6h: int | None = None
    stars_delta_24h: int | None = None
    stars_delta_7d: int | None = None
    stars_delta_30d: int | None = None
    forks_delta_24h: int | None = None
    issues_delta_24h: int | None = None
    prs_delta_24h: int | None = None
    star_acceleration: float | None = None
    history_status: str | None = None  # 'sufficient' | 'insufficient_history'

    TABLE: ClassVar[str] = "repo_snapshots"

    def to_row(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "RepoSnapshot":
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        return cls(**kwargs)

    @staticmethod
    def make_id(full_name: str, snapshot_at: str) -> str:
        return f"{full_name}#{snapshot_at}"


# ---------------------------------------------------------------------------
# L3 Evidence / Reasoning Packets
# ---------------------------------------------------------------------------


@dataclass
class EvidenceAtom:
    evidence_id: str
    full_name: str
    source: str
    evidence_type: str
    raw_ref: str | None = None
    one_sentence_summary: str | None = None
    compressed_content: str | None = None  # ≤500 chars
    entities: list[str] = field(default_factory=list)
    topic_tags: list[str] = field(default_factory=list)
    importance_score: float | None = None
    technical_depth_score: float | None = None
    novelty_score: float | None = None
    confidence: float | None = None
    created_at: str = field(default_factory=utc_now_iso)

    JSON_FIELDS: ClassVar[tuple[str, ...]] = ("entities", "topic_tags")
    TABLE: ClassVar[str] = "repo_evidence_atoms"

    MAX_COMPRESSED_CHARS: ClassVar[int] = 500

    def __post_init__(self) -> None:
        if (
            self.compressed_content is not None
            and len(self.compressed_content) > self.MAX_COMPRESSED_CHARS
        ):
            self.compressed_content = self.compressed_content[: self.MAX_COMPRESSED_CHARS]

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["entities"] = _json_dump(self.entities)
        row["topic_tags"] = _json_dump(self.topic_tags)
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "EvidenceAtom":
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        kwargs["entities"] = _json_load(row.get("entities")) or []
        kwargs["topic_tags"] = _json_load(row.get("topic_tags")) or []
        return cls(**kwargs)


@dataclass
class ReasoningPacket:
    packet_id: str
    full_name: str
    created_at: str = field(default_factory=utc_now_iso)
    metrics: dict[str, Any] = field(default_factory=dict)
    local_project_brief: str | None = None  # ≤1000 chars
    growth_evidence: list[str] = field(default_factory=list)
    readme_evidence: list[str] = field(default_factory=list)
    release_evidence: list[str] = field(default_factory=list)
    social_evidence: list[str] = field(default_factory=list)
    youtube_evidence: list[str] = field(default_factory=list)
    questions_for_reasoner: list[str] = field(default_factory=list)

    JSON_FIELDS: ClassVar[tuple[str, ...]] = (
        "metrics",
        "growth_evidence",
        "readme_evidence",
        "release_evidence",
        "social_evidence",
        "youtube_evidence",
        "questions_for_reasoner",
    )
    TABLE: ClassVar[str] = "project_reasoning_packets"
    MAX_BRIEF_CHARS: ClassVar[int] = 1000

    def __post_init__(self) -> None:
        if (
            self.local_project_brief is not None
            and len(self.local_project_brief) > self.MAX_BRIEF_CHARS
        ):
            self.local_project_brief = self.local_project_brief[: self.MAX_BRIEF_CHARS]

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        for jf in self.JSON_FIELDS:
            row[jf] = _json_dump(getattr(self, jf))
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ReasoningPacket":
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        for jf in cls.JSON_FIELDS:
            default: Any = {} if jf == "metrics" else []
            kwargs[jf] = _json_load(row.get(jf)) or default
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# L3/L4 Cards & Briefs
# ---------------------------------------------------------------------------


@dataclass
class AnalysisCard:
    analysis_id: str
    full_name: str
    analysis_date: str
    project_positioning: str | None = None
    what_it_does: str | None = None
    target_users: list[str] = field(default_factory=list)
    core_technical_idea: str | None = None
    why_it_is_hot: str | None = None
    potential_score: float | None = None
    heat_score: float | None = None
    technical_depth_score: float | None = None
    community_health_score: float | None = None
    strategic_relevance_score: float | None = None
    trend_implication: str | None = None
    product_planning_ideas: list[str] = field(default_factory=list)
    research_questions: list[str] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    watch_next: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    model_used: str | None = None
    verified: int = 0

    JSON_FIELDS: ClassVar[tuple[str, ...]] = (
        "target_users",
        "product_planning_ideas",
        "research_questions",
        "risks",
        "watch_next",
        "evidence_ids",
    )
    TABLE: ClassVar[str] = "repo_analysis_cards"
    MIN_EVIDENCE_REFS: ClassVar[int] = 3

    def validate_evidence_floor(self) -> None:
        """Enforce: A card cannot be created without ≥3 evidence_ids (S02 §A4)."""
        if len(self.evidence_ids) < self.MIN_EVIDENCE_REFS:
            raise ValueError(
                f"AnalysisCard requires ≥{self.MIN_EVIDENCE_REFS} evidence_ids, "
                f"got {len(self.evidence_ids)} for {self.full_name}"
            )

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        for jf in self.JSON_FIELDS:
            row[jf] = _json_dump(getattr(self, jf))
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "AnalysisCard":
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        for jf in cls.JSON_FIELDS:
            kwargs[jf] = _json_load(row.get(jf)) or []
        return cls(**kwargs)


@dataclass
class PlanningBrief:
    brief_id: str
    full_name: str
    analysis_id: str
    opportunity_summary: str | None = None
    user_pain_points: list[str] = field(default_factory=list)
    target_personas: list[str] = field(default_factory=list)
    proposed_product: str | None = None
    mvp_scope: str | None = None
    technical_architecture: str | None = None
    go_to_market: str | None = None
    risks: list[dict[str, Any]] = field(default_factory=list)
    validation_metrics: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    JSON_FIELDS: ClassVar[tuple[str, ...]] = (
        "user_pain_points",
        "target_personas",
        "risks",
        "validation_metrics",
        "next_steps",
    )
    TABLE: ClassVar[str] = "repo_planning_briefs"

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        for jf in self.JSON_FIELDS:
            row[jf] = _json_dump(getattr(self, jf))
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlanningBrief":
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        for jf in cls.JSON_FIELDS:
            kwargs[jf] = _json_load(row.get(jf)) or []
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# L4 Detection / Alerts
# ---------------------------------------------------------------------------


@dataclass
class Detection:
    detector_name: str
    full_name: str
    severity: str  # info | low | medium | high
    title: str
    evidence_ids: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    JSON_FIELDS: ClassVar[tuple[str, ...]] = ("evidence_ids", "details")
    TABLE: ClassVar[str] = "alerts"
    SEVERITIES: ClassVar[tuple[str, ...]] = ("info", "low", "medium", "high")

    def __post_init__(self) -> None:
        if self.severity not in self.SEVERITIES:
            raise ValueError(
                f"severity must be one of {self.SEVERITIES}, got {self.severity!r}"
            )

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["evidence_ids"] = _json_dump(self.evidence_ids)
        row["details"] = _json_dump(self.details)
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Detection":
        return cls(
            detector_name=row["detector_name"],
            full_name=row["full_name"],
            severity=row["severity"],
            title=row["title"],
            evidence_ids=_json_load(row.get("evidence_ids")) or [],
            details=_json_load(row.get("details")) or {},
            created_at=row.get("created_at") or utc_now_iso(),
        )


# ---------------------------------------------------------------------------
# L5 Reports
# ---------------------------------------------------------------------------


@dataclass
class DailyReport:
    report_date: str  # YYYY-MM-DD
    core_judgment: str | None = None
    sudden_hot: list[dict[str, Any]] = field(default_factory=list)
    early_potential: list[dict[str, Any]] = field(default_factory=list)
    tech_radar: list[dict[str, Any]] = field(default_factory=list)
    community_signals: list[dict[str, Any]] = field(default_factory=list)
    planning_suggestions: list[dict[str, Any]] = field(default_factory=list)
    watchlist: list[dict[str, Any]] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now_iso)
    model_used: str | None = None

    JSON_FIELDS: ClassVar[tuple[str, ...]] = (
        "sudden_hot",
        "early_potential",
        "tech_radar",
        "community_signals",
        "planning_suggestions",
        "watchlist",
    )
    TABLE: ClassVar[str] = "daily_reports"

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        for jf in self.JSON_FIELDS:
            row[jf] = _json_dump(getattr(self, jf))
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "DailyReport":
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        for jf in cls.JSON_FIELDS:
            kwargs[jf] = _json_load(row.get(jf)) or []
        return cls(**kwargs)


@dataclass
class WeeklyReport:
    week_start: str  # Monday YYYY-MM-DD
    one_sentence: str | None = None
    top5_trends: list[dict[str, Any]] = field(default_factory=list)
    top10_projects: list[dict[str, Any]] = field(default_factory=list)
    deep_analysis: list[dict[str, Any]] = field(default_factory=list)
    tech_route_abstraction: str | None = None
    planning_pool: list[dict[str, Any]] = field(default_factory=list)
    next_week_metrics: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now_iso)

    JSON_FIELDS: ClassVar[tuple[str, ...]] = (
        "top5_trends",
        "top10_projects",
        "deep_analysis",
        "planning_pool",
        "next_week_metrics",
    )
    TABLE: ClassVar[str] = "weekly_reports"

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        for jf in self.JSON_FIELDS:
            row[jf] = _json_dump(getattr(self, jf))
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "WeeklyReport":
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        for jf in cls.JSON_FIELDS:
            kwargs[jf] = _json_load(row.get(jf)) or []
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# DDL (additive migration)
# ---------------------------------------------------------------------------


DDL_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS repo_discovery_events (
        full_name      TEXT NOT NULL,
        source_type    TEXT NOT NULL,
        discovered_at  TEXT NOT NULL,
        metadata       TEXT,
        PRIMARY KEY (full_name, source_type, discovered_at)
    )""",
    """CREATE TABLE IF NOT EXISTS repo_snapshots (
        snapshot_id              TEXT PRIMARY KEY,
        full_name                TEXT NOT NULL,
        snapshot_at              TEXT NOT NULL,
        stars                    INTEGER,
        forks                    INTEGER,
        watchers                 INTEGER,
        open_issues              INTEGER,
        commit_count_7d          INTEGER,
        active_contributors_30d  INTEGER,
        latest_release_tag       TEXT,
        latest_release_at        TEXT,
        pushed_at                TEXT,
        stars_delta_1h           INTEGER,
        stars_delta_6h           INTEGER,
        stars_delta_24h          INTEGER,
        stars_delta_7d           INTEGER,
        stars_delta_30d          INTEGER,
        forks_delta_24h          INTEGER,
        issues_delta_24h         INTEGER,
        prs_delta_24h            INTEGER,
        star_acceleration        REAL,
        history_status           TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_repo_snapshots_full_name_at ON repo_snapshots(full_name, snapshot_at)",
    """CREATE TABLE IF NOT EXISTS repo_evidence_atoms (
        evidence_id            TEXT PRIMARY KEY,
        full_name              TEXT NOT NULL,
        source                 TEXT NOT NULL,
        evidence_type          TEXT NOT NULL,
        raw_ref                TEXT,
        one_sentence_summary   TEXT,
        compressed_content     TEXT,
        entities               TEXT,
        topic_tags             TEXT,
        importance_score       REAL,
        technical_depth_score  REAL,
        novelty_score          REAL,
        confidence             REAL,
        created_at             TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_evidence_full_name_type ON repo_evidence_atoms(full_name, evidence_type)",
    """CREATE TABLE IF NOT EXISTS project_reasoning_packets (
        packet_id               TEXT PRIMARY KEY,
        full_name               TEXT NOT NULL,
        created_at              TEXT NOT NULL,
        metrics                 TEXT,
        local_project_brief     TEXT,
        growth_evidence         TEXT,
        readme_evidence         TEXT,
        release_evidence        TEXT,
        social_evidence         TEXT,
        youtube_evidence        TEXT,
        questions_for_reasoner  TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS repo_analysis_cards (
        analysis_id                TEXT PRIMARY KEY,
        full_name                  TEXT NOT NULL,
        analysis_date              TEXT NOT NULL,
        project_positioning        TEXT,
        what_it_does               TEXT,
        target_users               TEXT,
        core_technical_idea        TEXT,
        why_it_is_hot              TEXT,
        potential_score            REAL,
        heat_score                 REAL,
        technical_depth_score      REAL,
        community_health_score     REAL,
        strategic_relevance_score  REAL,
        trend_implication          TEXT,
        product_planning_ideas     TEXT,
        research_questions         TEXT,
        risks                      TEXT,
        watch_next                 TEXT,
        evidence_ids               TEXT,
        model_used                 TEXT,
        verified                   INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS repo_planning_briefs (
        brief_id                TEXT PRIMARY KEY,
        full_name               TEXT NOT NULL,
        analysis_id             TEXT NOT NULL,
        opportunity_summary     TEXT,
        user_pain_points        TEXT,
        target_personas         TEXT,
        proposed_product        TEXT,
        mvp_scope               TEXT,
        technical_architecture  TEXT,
        go_to_market            TEXT,
        risks                   TEXT,
        validation_metrics      TEXT,
        next_steps              TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS alerts (
        alert_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        detector_name   TEXT NOT NULL,
        full_name       TEXT NOT NULL,
        severity        TEXT NOT NULL,
        title           TEXT NOT NULL,
        evidence_ids    TEXT,
        details         TEXT,
        created_at      TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS daily_reports (
        report_date           TEXT PRIMARY KEY,
        core_judgment         TEXT,
        sudden_hot            TEXT,
        early_potential       TEXT,
        tech_radar            TEXT,
        community_signals     TEXT,
        planning_suggestions  TEXT,
        watchlist             TEXT,
        generated_at          TEXT NOT NULL,
        model_used            TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS weekly_reports (
        week_start              TEXT PRIMARY KEY,
        one_sentence            TEXT,
        top5_trends             TEXT,
        top10_projects          TEXT,
        deep_analysis           TEXT,
        tech_route_abstraction  TEXT,
        planning_pool           TEXT,
        next_week_metrics       TEXT,
        generated_at            TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS github_intelligence_migrations (
        migration_id   TEXT PRIMARY KEY,
        applied_at     TEXT NOT NULL,
        schema_version TEXT NOT NULL
    )""",
)


def apply_schema(conn: sqlite3.Connection) -> None:
    """Apply additive DDL. Safe to call repeatedly (uses IF NOT EXISTS)."""
    cur = conn.cursor()
    for stmt in DDL_STATEMENTS:
        cur.execute(stmt)
    cur.execute(
        "INSERT OR IGNORE INTO github_intelligence_migrations(migration_id, applied_at, schema_version)"
        " VALUES (?, ?, ?)",
        (f"init_{SCHEMA_VERSION}", utc_now_iso(), SCHEMA_VERSION),
    )
    conn.commit()


def insert_row(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    col_list = ",".join(cols)
    conn.execute(
        f"INSERT OR REPLACE INTO {table}({col_list}) VALUES ({placeholders})",
        [row[c] for c in cols],
    )


def fetch_rows(
    conn: sqlite3.Connection, table: str, where: str | None = None, params: Iterable[Any] = ()
) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    cur.execute(sql, list(params))
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Self-test (acceptance: "schema API has unit coverage")
# ---------------------------------------------------------------------------


def _self_test() -> dict[str, Any]:
    """Exercise every model + DDL + row contract round-trip. Returns metrics."""
    import tempfile

    metrics: dict[str, Any] = {"tests_run": 0, "tests_passed": 0, "models": []}

    def _ok(name: str) -> None:
        metrics["tests_run"] += 1
        metrics["tests_passed"] += 1
        metrics["models"].append(name)

    # 1. Round-trip every dataclass
    samples: list[Any] = [
        DiscoveryCandidate(
            full_name="owner/repo",
            source_type="trending",
            discovered_at=utc_now_iso(),
            metadata={"rank": 3, "page": "daily"},
        ),
        RepoSnapshot(
            snapshot_id=RepoSnapshot.make_id("owner/repo", "2026-05-27T00:00:00Z"),
            full_name="owner/repo",
            snapshot_at="2026-05-27T00:00:00Z",
            stars=1234,
            forks=56,
            star_acceleration=2.5,
            history_status="sufficient",
        ),
        EvidenceAtom(
            evidence_id="ev-abc-readme-1",
            full_name="owner/repo",
            source="thunderomlx-qwen3.6",
            evidence_type="readme_claim",
            compressed_content="x" * 600,  # tests truncation
            entities=["foo", "bar"],
            topic_tags=["llm", "agent"],
            importance_score=75.0,
            confidence=0.9,
        ),
        ReasoningPacket(
            packet_id="rp-abc-1",
            full_name="owner/repo",
            metrics={"stars": 1234, "delta_24h": 50},
            local_project_brief="y" * 1200,  # tests truncation
            readme_evidence=["ev-abc-readme-1"],
            questions_for_reasoner=["Is this a wrapper?"],
        ),
        AnalysisCard(
            analysis_id="ac-abc-2026-05-27",
            full_name="owner/repo",
            analysis_date="2026-05-27",
            potential_score=82.5,
            heat_score=70.0,
            evidence_ids=["ev1", "ev2", "ev3"],  # exactly at floor
            risks=[{"type": "wrapper", "severity": "medium"}],
            model_used="qwen3.6-thunderomlx",
        ),
        PlanningBrief(
            brief_id="pb-abc-2026-05-27",
            full_name="owner/repo",
            analysis_id="ac-abc-2026-05-27",
            opportunity_summary="X opportunity",
            validation_metrics=["10k stars in 30d"],
        ),
        Detection(
            detector_name="sudden_hot",
            full_name="owner/repo",
            severity="high",
            title="star_acceleration > 8x",
            evidence_ids=["ev1"],
            details={"acceleration": 12.0},
        ),
        DailyReport(
            report_date="2026-05-27",
            core_judgment="3 sudden-hot repos today",
            sudden_hot=[{"repo": "owner/repo", "heat_score": 91.0}],
            model_used="qwen3.6-thunderomlx",
        ),
        WeeklyReport(
            week_start="2026-05-25",
            one_sentence="Agent frameworks dominate the week",
            top5_trends=[{"trend": "agent runtime"}],
        ),
    ]

    for obj in samples:
        cls = type(obj)
        row = obj.to_row()
        restored = cls.from_row(row)
        assert restored == obj, f"round-trip mismatch for {cls.__name__}: {restored} != {obj}"
        _ok(f"{cls.__name__}.row_contract_roundtrip")

    # 2. Truncation invariants
    long_atom = EvidenceAtom(
        evidence_id="ev-trim",
        full_name="o/r",
        source="x",
        evidence_type="readme_claim",
        compressed_content="a" * 1000,
    )
    assert len(long_atom.compressed_content or "") == EvidenceAtom.MAX_COMPRESSED_CHARS
    _ok("EvidenceAtom.truncation")

    long_packet = ReasoningPacket(
        packet_id="rp-trim", full_name="o/r", local_project_brief="b" * 5000
    )
    assert len(long_packet.local_project_brief or "") == ReasoningPacket.MAX_BRIEF_CHARS
    _ok("ReasoningPacket.truncation")

    # 3. Evidence floor for AnalysisCard
    thin_card = AnalysisCard(
        analysis_id="ac-thin",
        full_name="o/r",
        analysis_date="2026-05-27",
        evidence_ids=["only-one"],
    )
    try:
        thin_card.validate_evidence_floor()
        raise AssertionError("expected ValueError for thin evidence")
    except ValueError:
        _ok("AnalysisCard.evidence_floor_enforced")

    # 4. Detection severity guard
    try:
        Detection(
            detector_name="bad",
            full_name="o/r",
            severity="catastrophic",
            title="x",
        )
        raise AssertionError("expected ValueError for bad severity")
    except ValueError:
        _ok("Detection.severity_validated")

    # 5. DDL applies + insert + fetch round-trip via SQLite
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        db_path = tf.name
    try:
        conn = sqlite3.connect(db_path)
        apply_schema(conn)
        # idempotency
        apply_schema(conn)

        snap = RepoSnapshot(
            snapshot_id=RepoSnapshot.make_id("o/r", "2026-05-27T01:00:00Z"),
            full_name="o/r",
            snapshot_at="2026-05-27T01:00:00Z",
            stars=10,
        )
        insert_row(conn, snap.TABLE, snap.to_row())
        rows = fetch_rows(conn, snap.TABLE, "full_name=?", ("o/r",))
        assert len(rows) == 1
        restored = RepoSnapshot.from_row(rows[0])
        assert restored.stars == 10
        _ok("DDL.apply_and_roundtrip_sqlite")

        # migration log populated
        mig = fetch_rows(conn, "github_intelligence_migrations")
        assert any(r["schema_version"] == SCHEMA_VERSION for r in mig)
        _ok("DDL.migration_log_records_schema_version")

        conn.close()
    finally:
        import os as _os

        _os.unlink(db_path)

    return metrics


if __name__ == "__main__":
    import sys as _sys

    m = _self_test()
    print(json.dumps(m, indent=2))
    if m["tests_run"] != m["tests_passed"]:
        _sys.exit(1)
