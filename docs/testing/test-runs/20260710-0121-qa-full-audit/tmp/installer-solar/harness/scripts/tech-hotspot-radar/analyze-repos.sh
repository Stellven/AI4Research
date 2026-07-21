#!/usr/bin/env bash
# scripts/tech-hotspot-radar/analyze-repos.sh - Main command driver for repo analysis pipeline
set -euo pipefail

DB_PATH=""
CONFIG_PATH=""
EVIDENCE_ONLY="false"
DRY_RUN="false"
REPO_FILTER=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --db) DB_PATH="$2"; shift 2 ;;
    --config) CONFIG_PATH="$2"; shift 2 ;;
    --repo) REPO_FILTER="$2"; shift 2 ;;
    --evidence-only) EVIDENCE_ONLY="true"; shift ;;
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

if [[ ! -f "$DB_PATH" ]]; then
    echo "Warning: database file $DB_PATH does not exist. Initializing a clean database..." >&2
    # If the database does not exist, run schema creation using sqlite3
    # Look for schema.sql in parent scripts/tech-hotspot-radar/
    SCHEMA_FILE="$(dirname "${BASH_SOURCE[0]}")/schema.sql"
    if [[ -f "$SCHEMA_FILE" ]]; then
        sqlite3 "$DB_PATH" < "$SCHEMA_FILE"
    fi
fi

# Get script directory in bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# We use python to query the list of repos and loop over them
python3 - <<EOF "$DB_PATH" "$CONFIG_PATH" "$EVIDENCE_ONLY" "$DRY_RUN" "$SCRIPT_DIR" "$REPO_FILTER"
import sqlite3
import sys
import os
import subprocess
from pathlib import Path

db_path = sys.argv[1]
config_path = sys.argv[2]
evidence_only = sys.argv[3].lower() == "true"
dry_run = sys.argv[4].lower() == "true"
script_dir = sys.argv[5]
repo_filter = sys.argv[6]

# Define helpers
lib_dir = Path(script_dir) / "lib"
extractor_script = lib_dir / "evidence-extractor.sh"
dossier_script = lib_dir / "project-dossier.sh"

if not extractor_script.exists():
    print(f"Error: {extractor_script} not found", file=sys.stderr)
    sys.exit(1)
if not dossier_script.exists():
    print(f"Error: {dossier_script} not found", file=sys.stderr)
    sys.exit(1)

# Connect to database
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Query all tracked repos in the database
# Check if github_repos table exists
try:
    rows = conn.execute("SELECT full_name FROM github_repos").fetchall()
except sqlite3.OperationalError:
    # If table github_repos doesn't exist, create it (schema initialization check)
    print("Warning: github_repos table does not exist. Running schema.sql creation...", file=sys.stderr)
    SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"
    if SCHEMA_FILE.exists():
        with open(SCHEMA_FILE) as sf:
            conn.executescript(sf.read())
        conn.commit()
    rows = []

repos = [r["full_name"] for r in rows]
if repo_filter:
    repos = [repo_filter] if repo_filter in repos else []
conn.close()

if not repos:
    print("No repositories found in database github_repos table. Pipeline execution skipped.")
    sys.exit(0)

print(f"Starting analysis pipeline for {len(repos)} repositories (evidence_only={evidence_only}, dry_run={dry_run})")

success_count = 0
for repo in repos:
    print(f"\n==================================================")
    print(f"Analyzing repository: {repo}")
    print(f"==================================================")
    
    # 1. Run evidence atom extraction
    print(f"-> Extracting evidence atoms...")
    cmd_ext = [
        "bash", str(extractor_script),
        "--db", db_path,
        "--repo", repo,
        "--config", config_path
    ]
    if dry_run:
        cmd_ext.append("--dry-run")
        
    res_ext = subprocess.run(cmd_ext, capture_output=True, text=True)
    if res_ext.returncode != 0:
        print(f"Error extracting evidence atoms for {repo}: {res_ext.stderr}", file=sys.stderr)
        continue
    print(res_ext.stdout.strip())
    
    if not evidence_only:
        # 2. Run dossier compilation
        print(f"-> Compiling project intelligence dossier...")
        cmd_dos = [
            "bash", str(dossier_script),
            "--db", db_path,
            "--repo", repo,
            "--config", config_path
        ]
        if dry_run:
            cmd_dos.append("--dry-run")
            
        res_dos = subprocess.run(cmd_dos, capture_output=True, text=True)
        if res_dos.returncode != 0:
            print(f"Error building dossier for {repo}: {res_dos.stderr}", file=sys.stderr)
            continue
        print(res_dos.stdout.strip())
        
    success_count += 1

print(f"\nPipeline finished. Successfully analyzed {success_count}/{len(repos)} repositories.")
EOF
