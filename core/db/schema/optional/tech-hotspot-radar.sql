-- Schema extensions for Tech Hotspot Radar - Node P0-N1

CREATE TABLE IF NOT EXISTS strategy_tracks (
    name                  TEXT PRIMARY KEY,
    keywords              TEXT NOT NULL, -- JSON array of strings
    github_topics         TEXT NOT NULL, -- JSON array of strings
    languages             TEXT NOT NULL, -- JSON array of strings
    internal_capabilities TEXT NOT NULL, -- JSON array of strings
    alert_threshold       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS repo_master (
    full_name             TEXT PRIMARY KEY,
    description           TEXT NOT NULL DEFAULT '',
    language              TEXT,
    license               TEXT,
    archived              INTEGER NOT NULL DEFAULT 0,
    stars_count           INTEGER NOT NULL DEFAULT 0,
    forks_count           INTEGER NOT NULL DEFAULT 0,
    open_issues_count     INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT,
    updated_at            TEXT,
    pushed_at             TEXT,
    imported_at           TEXT NOT NULL
);
