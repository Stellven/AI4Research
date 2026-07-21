#!/usr/bin/env bash
# scripts/tech-hotspot-radar/fetch-github-ultimate.sh
set -euo pipefail

DB_PATH=""
CONFIG_PATH=""
TIER=0
TRACK=""
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case $1 in
    --db) DB_PATH="$2"; shift 2 ;;
    --config) CONFIG_PATH="$2"; shift 2 ;;
    --tier) TIER="$2"; shift 2 ;;
    --track) TRACK="$2"; shift 2 ;;
    --dry-run) DRY_RUN="true"; shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$CONFIG_PATH" ]]; then
    CONFIG_PATH="$HOME/.solar/harness/config/tech-hotspot-radar.yaml"
    if [[ ! -f "$CONFIG_PATH" ]]; then
        CONFIG_PATH="$HOME/Solar/harness/config/tech-hotspot-radar.yaml"
    fi
fi

if [[ -z "$DB_PATH" ]]; then
    if [[ -f "$CONFIG_PATH" ]]; then
        DB_PATH=$(python3 -c "
import yaml
with open('$CONFIG_PATH') as f:
    cfg = yaml.safe_load(f) or {}
    print(cfg.get('output', {}).get('database', ''))
")
    fi
    if [[ -z "$DB_PATH" ]]; then
        DB_PATH="$HOME/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite"
    fi
fi

# Ensure database directory exists
mkdir -p "$(dirname "$DB_PATH")"

# Execute collection using python3
python3 - <<'EOF' "$DB_PATH" "$CONFIG_PATH" "$TIER" "$TRACK" "$DRY_RUN"
import os
import sys
import json
import time
import sqlite3
import urllib.request
import urllib.error
import re
import datetime

db_path = sys.argv[1]
config_path = sys.argv[2]
tier = int(sys.argv[3])
track = sys.argv[4]
dry_run = sys.argv[5].lower() == "true"

import yaml
with open(config_path) as f:
    config = yaml.safe_load(f) or {}

fetch_config = config.get("fetch") or {}
token_env = config.get("github", {}).get("github_token_env", "GITHUB_TOKEN")
token = os.environ.get(token_env, "")
user_agent = fetch_config.get("user_agent", "Solar-Tech-Hotspot-Radar/1.0")
timeout = int(fetch_config.get("timeout_seconds", 20))

budget_file = f"{db_path}.budget.json"
if not os.path.exists(budget_file):
    with open(budget_file, "w") as f:
        json.dump({
            "tier_0": {"limit": 2000, "remaining": 2000, "reset_at": 0},
            "tier_1": {"limit": 1000, "remaining": 1000, "reset_at": 0},
            "tier_2": {"limit": 500, "remaining": 500, "reset_at": 0}
        }, f, indent=2)

def check_budget(t):
    try:
        with open(budget_file, "r") as f:
            data = json.load(f)
    except Exception:
        return True
    key = f"tier_{t}"
    if key not in data:
        return True
    info = data[key]
    now = int(time.time())
    if now >= info["reset_at"]:
        info["remaining"] = info["limit"]
        info["reset_at"] = now + 3600
        with open(budget_file, "w") as f:
            json.dump(data, f, indent=2)
    return info["remaining"] > 0

def consume_budget(t):
    try:
        with open(budget_file, "r") as f:
            data = json.load(f)
    except Exception:
        return
    key = f"tier_{t}"
    if key in data:
        data[key]["remaining"] = max(0, data[key]["remaining"] - 1)
        with open(budget_file, "w") as f:
            json.dump(data, f, indent=2)

def gh_api(path, t):
    if not check_budget(t):
        print(f"[fetch-github-ultimate] Quota exhausted for Tier {t}. Skipping {path}", file=sys.stderr)
        return None

    url = f"https://api.github.com{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": user_agent
    }
    if token:
        headers["Authorization"] = f"token {token}"

    retries = 0
    max_retries = 3
    while retries < max_retries:
        req = urllib.request.Request(url, headers=headers)
        try:
            consume_budget(t)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8', errors='replace'))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                body = e.read().decode('utf-8', errors='replace')
                if "abuse" in body.lower() or "rate limit" in body.lower() or "secondary" in body.lower():
                    print(f"[api-budget] Secondary rate limit triggered on {path}. Backing off 60s...", file=sys.stderr)
                    time.sleep(60)
                    retries += 1
                    continue
                else:
                    print(f"[fetch-github-ultimate] HTTP 403 Forbidden: {body}", file=sys.stderr)
                    break
            elif e.code == 404:
                print(f"[fetch-github-ultimate] HTTP 404 Not Found for {path}", file=sys.stderr)
                break
            else:
                print(f"[fetch-github-ultimate] HTTP {e.code} on {path}", file=sys.stderr)
                break
        except Exception as e:
            print(f"[fetch-github-ultimate] Error requesting {path}: {e}", file=sys.stderr)
            break
    return None

def write_snap(repo_data, commit_count_7d):
    full_name = repo_data.get("full_name")
    if not full_name:
        return
    owner, name = full_name.split("/", 1)
    stars = int(repo_data.get("stargazers_count") or 0)
    forks = int(repo_data.get("forks_count") or 0)
    issues = int(repo_data.get("open_issues_count") or 0)
    desc = repo_data.get("description") or ""
    lang = repo_data.get("language") or ""
    license = (repo_data.get("license") or {}).get("spdx_id") or ""
    created = repo_data.get("created_at")
    updated = repo_data.get("updated_at")
    pushed = repo_data.get("pushed_at")
    archived = 1 if repo_data.get("archived") else 0
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    if dry_run:
        print(f"[DRY RUN] Would write snapshot for {full_name}: stars={stars}, forks={forks}, issues={issues}, commits_7d={commit_count_7d}")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
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

        conn.execute("""
        INSERT OR IGNORE INTO repo_snapshots 
        (repo_full_name, snapshot_at, stars_count, forks_count, open_issues_count, commit_count_7d)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (full_name, ts, stars, forks, issues, commit_count_7d))

        conn.execute("""
        INSERT INTO github_repos
        (repo_id, full_name, owner, repo, html_url, description, topics, language,
         license, stars, forks, watchers, open_issues, default_branch, created_at,
         updated_at, pushed_at, readme_text, fetched_at, archived)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
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
            int(repo_data.get("id") or 0), full_name, owner, name, repo_data.get("html_url") or "", desc,
            ",".join(repo_data.get("topics") or []), lang, license, stars, forks, stars, issues,
            repo_data.get("default_branch") or "main", created, updated, pushed, ts, archived
        ))

        conn.execute("""
        INSERT OR IGNORE INTO github_star_snapshots 
        (full_name, snapshot_at, stars, forks, open_issues, watchers)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (full_name, ts, stars, forks, issues, stars))

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
            full_name, desc, lang, license, archived, stars, forks, issues, created, updated, pushed, ts
        ))

        conn.commit()
    except Exception as e:
        print(f"[fetch-github-ultimate] DB Write Error for {full_name}: {e}", file=sys.stderr)
    finally:
        conn.close()

if tier == 0:
    repos = config.get("github", {}).get("tracked_repos", [])
    print(f"[fetch-github-ultimate] Starting Tier 0 collection for {len(repos)} tracked repos")
    for r in repos:
        if dry_run:
            write_snap({"full_name": r, "stargazers_count": 0, "forks_count": 0, "open_issues_count": 0}, 0)
        else:
            repo_data = gh_api(f"/repos/{r}", 0)
            if not repo_data:
                continue
            since_time = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
            commits_data = gh_api(f"/repos/{r}/commits?since={since_time}", 0)
            commit_count_7d = len(commits_data) if isinstance(commits_data, list) else 0
            write_snap(repo_data, commit_count_7d)

elif tier == 1:
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT name, github_topics FROM strategy_tracks")
    tracks_data = cur.fetchall()
    conn.close()

    matched_topics = set()
    for name, topics_json in tracks_data:
        name_norm = "".join(c for c in name.lower() if c.isalnum())
        req_norm = "".join(c for c in track.lower() if c.isalnum()) if track else ""
        if not req_norm or req_norm in name_norm:
            try:
                topics = json.loads(topics_json)
                for t in topics:
                    matched_topics.add(t)
            except Exception:
                pass

    print(f"[fetch-github-ultimate] Starting Tier 1 collection for topics: {list(matched_topics)}")
    for topic in matched_topics:
        if dry_run:
            print(f"[DRY RUN] Would search topic {topic}")
            continue
        search_res = gh_api(f"/search/repositories?q=topic:{topic}", 1)
        if not search_res:
            continue
        items = search_res.get("items", [])
        for item in items[:10]:
            since_time = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
            commits_data = gh_api(f"/repos/{item['full_name']}/commits?since={since_time}", 1)
            commit_count_7d = len(commits_data) if isinstance(commits_data, list) else 0
            write_snap(item, commit_count_7d)

elif tier == 2:
    print("[fetch-github-ultimate] Starting Tier 2 collection from GitHub Trending page")
    valid_repos = []
    if not dry_run:
        trending_url = "https://github.com/trending"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        req = urllib.request.Request(trending_url, headers=headers)
        html = ""
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                html = resp.read().decode('utf-8', errors='replace')
        except Exception as e:
            print(f"[fetch-github-ultimate] Scrape error: {e}. Falling back to popular defaults.", file=sys.stderr)
            
        repos = re.findall(r'class="lh-condensed"[^>]*>\s*<a\s+href="/([^/"]+/[^/"]+)"', html)
        if not repos:
            repos = re.findall(r'href="/([^/"]+/[^/"]+)"[^>]*data-hydro-click', html)
        
        for r in repos:
            r_clean = r.split('?')[0].strip()
            if '/' in r_clean and r_clean.count('/') == 1 and r_clean not in valid_repos:
                if not any(x in r_clean.lower() for x in ["/features", "/explore", "/trending", "/about", "/site", "/contact"]):
                    valid_repos.append(r_clean)

    if not valid_repos:
        valid_repos = [
            "modelcontextprotocol/servers",
            "modelcontextprotocol/clients",
            "openai/openai-python"
        ]

    print(f"[fetch-github-ultimate] Trending repos found: {valid_repos[:15]}")
    for r in valid_repos[:10]:
        if dry_run:
            write_snap({"full_name": r, "stargazers_count": 0, "forks_count": 0, "open_issues_count": 0}, 0)
        else:
            repo_data = gh_api(f"/repos/{r}", 2)
            if not repo_data:
                continue
            since_time = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
            commits_data = gh_api(f"/repos/{r}/commits?since={since_time}", 2)
            commit_count_7d = len(commits_data) if isinstance(commits_data, list) else 0
            write_snap(repo_data, commit_count_7d)

print("[fetch-github-ultimate] Collection complete.")
EOF
