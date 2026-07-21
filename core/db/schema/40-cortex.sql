-- Cortex/favorites/search compatibility schema.
--
-- Derived from statements touching cortex_sources, sys_favorites, and
-- fts_unified_search in hooks, rules, and the legacy kernel. This file only
-- creates the columns required by those statements so fresh installs do not
-- fail before a future canonical schema exists.

CREATE TABLE IF NOT EXISTS cortex_sources (
    citation_key TEXT PRIMARY KEY,
    title TEXT,
    finding TEXT,
    task_id TEXT,
    credibility REAL DEFAULT 0,
    expert_model TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cortex_sources_task_id ON cortex_sources(task_id);
CREATE INDEX IF NOT EXISTS idx_cortex_sources_credibility ON cortex_sources(credibility);

CREATE TABLE IF NOT EXISTS sys_favorites (
    title TEXT,
    question TEXT,
    answer TEXT,
    tags TEXT,
    importance INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sys_favorites_question ON sys_favorites(question);
CREATE INDEX IF NOT EXISTS idx_sys_favorites_importance ON sys_favorites(importance);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_unified_search USING fts5(
    doc_id UNINDEXED,
    title,
    doc_type UNINDEXED,
    content
);
