-- DeepResearch Storage Layer: Initial Schema
-- Sprint: s03-core-runtime | Node: N2
-- Spec: sprint-20260513-solar-deepresearch-product-line-s02-architecture.deepresearch.storage.md
-- Tables: 7 (research_runs, research_sources, evidence_items, claims, claim_evidence, report_sections, section_checks)

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- 1. research_runs: root entity for each deep research invocation
CREATE TABLE IF NOT EXISTS research_runs (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    topic           TEXT NOT NULL,
    depth_tier      TEXT NOT NULL DEFAULT 'standard',
    status          TEXT NOT NULL DEFAULT 'pending',
    config_json     TEXT NOT NULL DEFAULT '{}',
    result_summary  TEXT,
    total_sources   INTEGER NOT NULL DEFAULT 0,
    total_evidence  INTEGER NOT NULL DEFAULT 0,
    total_claims    INTEGER NOT NULL DEFAULT 0,
    char_budget     INTEGER NOT NULL DEFAULT 8000,
    char_used       INTEGER NOT NULL DEFAULT 0,
    started_at      TEXT,
    completed_at    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),

    CONSTRAINT chk_depth_tier CHECK (depth_tier IN ('quick','standard','deep')),
    CONSTRAINT chk_status     CHECK (status IN ('pending','running','completed','failed','cancelled')),
    CONSTRAINT chk_char_budget CHECK (char_budget > 0 AND char_used >= 0)
);

CREATE INDEX IF NOT EXISTS idx_research_runs_status  ON research_runs(status);
CREATE INDEX IF NOT EXISTS idx_research_runs_created ON research_runs(created_at);

-- 2. research_sources: discovered and ingested source material
CREATE TABLE IF NOT EXISTS research_sources (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    run_id          TEXT NOT NULL,
    url             TEXT,
    title           TEXT NOT NULL DEFAULT '',
    source_type     TEXT NOT NULL DEFAULT 'web',
    content_hash    TEXT NOT NULL,
    content_span    TEXT NOT NULL,
    relevance_score REAL NOT NULL DEFAULT 0.0,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),

    CONSTRAINT fk_source_run FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE,
    CONSTRAINT chk_relevance CHECK (relevance_score >= 0.0 AND relevance_score <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_research_sources_run ON research_sources(run_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_source_run_hash ON research_sources(run_id, content_hash);

-- 3. evidence_items: individual evidence fragments extracted from sources
CREATE TABLE IF NOT EXISTS evidence_items (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    run_id          TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    content         TEXT NOT NULL,
    evidence_type   TEXT NOT NULL DEFAULT 'factual',
    confidence      REAL NOT NULL DEFAULT 0.7,
    span_start      INTEGER NOT NULL DEFAULT 0,
    span_end        INTEGER NOT NULL DEFAULT 0,
    content_hash    TEXT NOT NULL,

    CONSTRAINT fk_evidence_run    FOREIGN KEY (run_id)    REFERENCES research_runs(id)    ON DELETE CASCADE,
    CONSTRAINT fk_evidence_source FOREIGN KEY (source_id) REFERENCES research_sources(id) ON DELETE CASCADE,
    CONSTRAINT chk_evidence_type  CHECK (evidence_type IN ('factual','statistical','quoted','derived')),
    CONSTRAINT chk_confidence     CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT chk_span_order     CHECK (span_end >= span_start)
);

CREATE INDEX IF NOT EXISTS idx_evidence_items_run    ON evidence_items(run_id);
CREATE INDEX IF NOT EXISTS idx_evidence_items_source ON evidence_items(source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_items_hash   ON evidence_items(content_hash);
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_run_hash ON evidence_items(run_id, content_hash);

-- 4. claims: atomic claims extracted or synthesized by the LLM
CREATE TABLE IF NOT EXISTS claims (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    run_id          TEXT NOT NULL,
    claim_text      TEXT NOT NULL,
    claim_type      TEXT NOT NULL DEFAULT 'assertion',
    stance          TEXT NOT NULL DEFAULT 'neutral',
    confidence      REAL NOT NULL DEFAULT 0.7,
    section_ref     TEXT,
    content_hash    TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),

    CONSTRAINT fk_claims_run  FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE,
    CONSTRAINT chk_claim_type CHECK (claim_type IN ('assertion','causal','comparative','predictive')),
    CONSTRAINT chk_stance     CHECK (stance IN ('supports','refutes','neutral')),
    CONSTRAINT chk_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_claims_run     ON claims(run_id);
CREATE INDEX IF NOT EXISTS idx_claims_type    ON claims(claim_type);
CREATE INDEX IF NOT EXISTS idx_claims_section ON claims(section_ref);
CREATE INDEX IF NOT EXISTS idx_claims_hash    ON claims(content_hash);
CREATE UNIQUE INDEX IF NOT EXISTS uq_claims_run_hash ON claims(run_id, content_hash);

-- 5. claim_evidence: many-to-many junction linking claims to evidence
CREATE TABLE IF NOT EXISTS claim_evidence (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    run_id          TEXT NOT NULL,
    claim_id        TEXT NOT NULL,
    evidence_id     TEXT NOT NULL,
    relation        TEXT NOT NULL DEFAULT 'supports',
    strength        REAL NOT NULL DEFAULT 0.7,

    CONSTRAINT fk_ce_run      FOREIGN KEY (run_id)      REFERENCES research_runs(id)      ON DELETE CASCADE,
    CONSTRAINT fk_ce_claim    FOREIGN KEY (claim_id)    REFERENCES claims(id)            ON DELETE CASCADE,
    CONSTRAINT fk_ce_evidence FOREIGN KEY (evidence_id) REFERENCES evidence_items(id)    ON DELETE CASCADE,
    CONSTRAINT chk_relation   CHECK (relation IN ('supports','refutes','qualifies')),
    CONSTRAINT chk_strength   CHECK (strength >= 0.0 AND strength <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_claim_evidence_run   ON claim_evidence(run_id);
CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim ON claim_evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_evidence_ev    ON claim_evidence(evidence_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_claim_evidence ON claim_evidence(claim_id, evidence_id, relation);

-- 6. report_sections: structured sections of the final research report
CREATE TABLE IF NOT EXISTS report_sections (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    run_id          TEXT NOT NULL,
    section_type    TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL DEFAULT '',
    char_count      INTEGER NOT NULL DEFAULT 0,
    section_order   INTEGER NOT NULL DEFAULT 0,
    parent_section  TEXT,
    metadata_json   TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),

    CONSTRAINT fk_sections_run    FOREIGN KEY (run_id)          REFERENCES research_runs(id) ON DELETE CASCADE,
    CONSTRAINT fk_sections_parent FOREIGN KEY (parent_section)  REFERENCES report_sections(id) ON DELETE SET NULL,
    CONSTRAINT chk_char_count     CHECK (char_count >= 0),
    CONSTRAINT chk_order          CHECK (section_order >= 0)
);

CREATE INDEX IF NOT EXISTS idx_report_sections_run   ON report_sections(run_id);
CREATE INDEX IF NOT EXISTS idx_report_sections_type  ON report_sections(section_type);
CREATE INDEX IF NOT EXISTS idx_report_sections_order ON report_sections(run_id, section_order);
CREATE UNIQUE INDEX IF NOT EXISTS uq_section_run_order ON report_sections(run_id, section_order);

-- 7. section_checks: factuality and quality checks per report section
CREATE TABLE IF NOT EXISTS section_checks (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    run_id          TEXT NOT NULL,
    section_id      TEXT NOT NULL,
    check_type      TEXT NOT NULL,
    score           REAL NOT NULL DEFAULT 0.0,
    details         TEXT NOT NULL DEFAULT '',
    passed          INTEGER NOT NULL DEFAULT 0,
    checked_at      TEXT NOT NULL DEFAULT (datetime('now')),

    CONSTRAINT fk_checks_run     FOREIGN KEY (run_id)     REFERENCES research_runs(id)     ON DELETE CASCADE,
    CONSTRAINT fk_checks_section FOREIGN KEY (section_id) REFERENCES report_sections(id) ON DELETE CASCADE,
    CONSTRAINT chk_check_type    CHECK (check_type IN ('factual_accuracy','source_coverage','coherence','completeness','bias_check')),
    CONSTRAINT chk_score         CHECK (score >= 0.0 AND score <= 1.0),
    CONSTRAINT chk_passed        CHECK (passed IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_section_checks_run     ON section_checks(run_id);
CREATE INDEX IF NOT EXISTS idx_section_checks_section ON section_checks(section_id);
CREATE INDEX IF NOT EXISTS idx_section_checks_type    ON section_checks(check_type);
CREATE UNIQUE INDEX IF NOT EXISTS uq_section_check    ON section_checks(section_id, check_type);
