#!/usr/bin/env bash
# lib/snapshot-writer.sh - Write repository snapshots to SQLite database
set -euo pipefail

write_snapshot() {
    local db_path="$1"
    local repo_full_name="$2"
    local stars_count="${3:-0}"
    local forks_count="${4:-0}"
    local open_issues_count="${5:-0}"
    local commit_count_7d="${6:-0}"
    local snapshot_at="${7:-}"
    local desc="${8:-}"
    local lang="${9:-}"
    local license="${10:-}"
    local created="${11:-}"
    local updated="${12:-}"
    local pushed="${13:-}"
    local archived="${14:-0}"

    if [[ -z "$snapshot_at" ]]; then
        snapshot_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    fi

    python3 - <<EOF
import sqlite3
import sys

db_path = """$db_path"""
repo = """$repo_full_name"""
stars = int("$stars_count")
forks = int("$forks_count")
issues = int("$open_issues_count")
commits = int("$commit_count_7d")
ts = """$snapshot_at"""

desc = """$desc"""
lang = """$lang"""
license = """$license"""
created = """$created"""
updated = """$updated"""
pushed = """$pushed"""
archived = int("$archived")

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA foreign_keys=ON")

# 1. Ensure tables exist
conn.execute("""
CREATE TABLE IF NOT EXISTS repo_snapshots (
    repo_full_name TEXT NOT NULL,
    snapshot_at    TEXT NOT NULL,
    stars_count    INTEGER NOT NULL DEFAULT 0,
    forks_count    INTEGER NOT NULL DEFAULT 0,
    open_issues_count INTEGER NOT NULL DEFAULT 0,
    commit_count_7d INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (repo_full_name, snapshot_at)
)
""")

# 2. Insert into repo_snapshots
conn.execute("""
INSERT OR IGNORE INTO repo_snapshots 
(repo_full_name, snapshot_at, stars_count, forks_count, open_issues_count, commit_count_7d)
VALUES (?, ?, ?, ?, ?, ?)
""", (repo, ts, stars, forks, issues, commits))

# 3. Insert into github_repos
owner, name = repo.split("/", 1)
conn.execute("""
INSERT INTO github_repos
(repo_id, full_name, owner, repo, html_url, description, topics, language,
 license, stars, forks, watchers, open_issues, default_branch, created_at,
 updated_at, pushed_at, readme_text, fetched_at, archived)
VALUES (0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'main', ?, ?, ?, '', ?, ?)
ON CONFLICT(full_name) DO UPDATE SET
 description=excluded.description,
 language=excluded.language,
 license=excluded.license,
 stars=excluded.stars,
 forks=excluded.forks,
 open_issues=excluded.open_issues,
 updated_at=excluded.updated_at,
 pushed_at=excluded.pushed_at,
 fetched_at=excluded.fetched_at,
 archived=excluded.archived
""", (
    repo, owner, name, f"https://github.com/{repo}", desc, "", lang,
    license, stars, forks, stars, issues, created, updated, pushed, ts, archived
))

# 4. Insert into github_star_snapshots
conn.execute("""
INSERT OR IGNORE INTO github_star_snapshots 
(full_name, snapshot_at, stars, forks, open_issues, watchers)
VALUES (?, ?, ?, ?, ?, ?)
""", (repo, ts, stars, forks, issues, stars))

# 5. Insert into repo_master
conn.execute("""
INSERT INTO repo_master
(full_name, description, language, license, archived, stars_count, forks_count, open_issues_count, created_at, updated_at, pushed_at, imported_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(full_name) DO UPDATE SET
 description=excluded.description,
 language=excluded.language,
 license=excluded.license,
 archived=excluded.archived,
 stars_count=excluded.stars_count,
 forks_count=excluded.forks_count,
 open_issues_count=excluded.open_issues_count,
 updated_at=excluded.updated_at,
 pushed_at=excluded.pushed_at
""", (
    repo, desc, lang, license, archived, stars, forks, issues, created, updated, pushed, ts
))

conn.commit()
conn.close()
EOF
}

# If run directly as a CLI command
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    DB_PATH=""
    REPO=""
    STARS=0
    FORKS=0
    ISSUES=0
    COMMITS=0
    TIMESTAMP=""
    DESC=""
    LANG=""
    LICENSE=""
    CREATED=""
    UPDATED=""
    PUSHED=""
    ARCHIVED=0

    while [[ $# -gt 0 ]]; do
      case $1 in
        --db) DB_PATH="$2"; shift 2 ;;
        --repo) REPO="$2"; shift 2 ;;
        --stars) STARS="$2"; shift 2 ;;
        --forks) FORKS="$2"; shift 2 ;;
        --issues) ISSUES="$2"; shift 2 ;;
        --commits) COMMITS="$2"; shift 2 ;;
        --timestamp) TIMESTAMP="$2"; shift 2 ;;
        --desc) DESC="$2"; shift 2 ;;
        --lang) LANG="$2"; shift 2 ;;
        --license) LICENSE="$2"; shift 2 ;;
        --created) CREATED="$2"; shift 2 ;;
        --updated) UPDATED="$2"; shift 2 ;;
        --pushed) PUSHED="$2"; shift 2 ;;
        --archived) ARCHIVED="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
      esac
    done

    if [[ -z "$DB_PATH" || -z "$REPO" ]]; then
        echo "Usage: snapshot-writer.sh --db <path> --repo <owner/name> [options]" >&2
        exit 1
    fi

    write_snapshot "$DB_PATH" "$REPO" "$STARS" "$FORKS" "$ISSUES" "$COMMITS" "$TIMESTAMP" "$DESC" "$LANG" "$LICENSE" "$CREATED" "$UPDATED" "$PUSHED" "$ARCHIVED"
fi
