-- Migration 001: Add browser backend columns to social_posts
-- Safe for legacy X API rows: all new columns have defaults or are nullable.
-- Requires: social_post_dedup_keys table MUST exist before this migration
--           (run ensure_dedup_keys_table first).

-- dedup keys table (idempotent)
CREATE TABLE IF NOT EXISTS social_post_dedup_keys (
    key           TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    post_pk       INTEGER REFERENCES social_posts(rowid)
);
CREATE INDEX IF NOT EXISTS idx_dk_post_pk ON social_post_dedup_keys(post_pk);

-- new columns on social_posts
-- Each ALTER is a separate statement so partial failure is recoverable.

ALTER TABLE social_posts ADD COLUMN dom_hash TEXT;

ALTER TABLE social_posts ADD COLUMN screenshot_path TEXT;

ALTER TABLE social_posts ADD COLUMN collection_backend TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE social_posts ADD COLUMN dedup_key TEXT REFERENCES social_post_dedup_keys(key);
