-- Solar Experience Memory Index Schema
-- SQLite + FTS5

CREATE TABLE IF NOT EXISTS experience_entries (
    entry_id TEXT PRIMARY KEY,
    trigger_sig TEXT NOT NULL,
    state_sig TEXT,
    pattern_class TEXT NOT NULL,
    tags TEXT,          -- JSON array
    outcome TEXT NOT NULL,
    advisory TEXT,
    repair_recipe TEXT,
    source_sids TEXT,   -- JSON array
    hit_count INTEGER DEFAULT 0,
    last_seen TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trigger_sig ON experience_entries(trigger_sig);
CREATE INDEX IF NOT EXISTS idx_pattern_class ON experience_entries(pattern_class);
CREATE INDEX IF NOT EXISTS idx_outcome ON experience_entries(outcome);
CREATE INDEX IF NOT EXISTS idx_hit_count ON experience_entries(hit_count DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS experience_fts USING fts5(
    entry_id UNINDEXED,
    pattern_class,
    tags,
    advisory,
    repair_recipe,
    content='experience_entries',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS experience_entries_ai AFTER INSERT ON experience_entries BEGIN
    INSERT INTO experience_fts(rowid, entry_id, pattern_class, tags, advisory, repair_recipe)
    VALUES (new.rowid, new.entry_id, new.pattern_class, new.tags, new.advisory, new.repair_recipe);
END;

CREATE TRIGGER IF NOT EXISTS experience_entries_ad AFTER DELETE ON experience_entries BEGIN
    INSERT INTO experience_fts(experience_fts, rowid, entry_id, pattern_class, tags, advisory, repair_recipe)
    VALUES ('delete', old.rowid, old.entry_id, old.pattern_class, old.tags, old.advisory, old.repair_recipe);
END;

CREATE TRIGGER IF NOT EXISTS experience_entries_au AFTER UPDATE ON experience_entries BEGIN
    INSERT INTO experience_fts(experience_fts, rowid, entry_id, pattern_class, tags, advisory, repair_recipe)
    VALUES ('delete', old.rowid, old.entry_id, old.pattern_class, old.tags, old.advisory, old.repair_recipe);
    INSERT INTO experience_fts(rowid, entry_id, pattern_class, tags, advisory, repair_recipe)
    VALUES (new.rowid, new.entry_id, new.pattern_class, new.tags, new.advisory, new.repair_recipe);
END;

CREATE TABLE IF NOT EXISTS experience_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

INSERT OR IGNORE INTO experience_meta(key, value) VALUES ('schema_version', '1.0.0');
INSERT OR IGNORE INTO experience_meta(key, value) VALUES ('created_at', datetime('now'));
