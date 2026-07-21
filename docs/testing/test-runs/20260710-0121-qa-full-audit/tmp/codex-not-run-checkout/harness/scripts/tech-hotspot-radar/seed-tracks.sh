#!/usr/bin/env bash
# seed-tracks.sh - Seed strategy tracks into tech-hotspot-radar SQLite database

set -euo pipefail

DB_PATH=""
YAML_PATH=""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

while [[ $# -gt 0 ]]; do
  case $1 in
    --db)
      DB_PATH="$2"
      shift 2
      ;;
    --yaml)
      YAML_PATH="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [ -z "$DB_PATH" ]; then
  CONFIG_PATH="$HOME/.solar/harness/config/tech-hotspot-radar.yaml"
  if [ ! -f "$CONFIG_PATH" ]; then
     CONFIG_PATH="$HOME/Solar/harness/config/tech-hotspot-radar.yaml"
  fi
  
  if [ -f "$CONFIG_PATH" ]; then
     DB_PATH=$(python3 -c "
import yaml
with open('$CONFIG_PATH') as f:
    cfg = yaml.safe_load(f) or {}
    print(cfg.get('output', {}).get('database', ''))
")
  fi

  if [ -z "$DB_PATH" ]; then
     DB_PATH="$HOME/.solar/harness/state/tech-hotspot-radar/tech-hotspot-radar.sqlite"
  fi
fi

if [ -z "$YAML_PATH" ]; then
  YAML_PATH="$SCRIPT_DIR/config/tracks.yaml"
fi

echo "[seed-tracks] seeding strategy tracks into DB: $DB_PATH"
echo "[seed-tracks] track config: $YAML_PATH"

python3 - <<EOF
import sqlite3
import yaml
import json

db_path = "$DB_PATH"
yaml_path = "$YAML_PATH"

with open(yaml_path) as f:
    data = yaml.safe_load(f) or {}

tracks = data.get("tracks", [])
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA foreign_keys=ON")

conn.execute("""
CREATE TABLE IF NOT EXISTS strategy_tracks (
    name                  TEXT PRIMARY KEY,
    keywords              TEXT NOT NULL,
    github_topics         TEXT NOT NULL,
    languages             TEXT NOT NULL,
    internal_capabilities TEXT NOT NULL,
    alert_threshold       REAL NOT NULL
)
""")

inserted = 0
for track in tracks:
    name = track.get("name")
    keywords = json.dumps(track.get("keywords", []))
    github_topics = json.dumps(track.get("github_topics", []))
    languages = json.dumps(track.get("languages", []))
    internal_capabilities = json.dumps(track.get("internal_capabilities", []))
    alert_threshold = float(track.get("alert_threshold", 1.0))
    
    conn.execute("""
    INSERT OR REPLACE INTO strategy_tracks 
    (name, keywords, github_topics, languages, internal_capabilities, alert_threshold)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (name, keywords, github_topics, languages, internal_capabilities, alert_threshold))
    inserted += 1

conn.commit()
conn.close()
print(f"[seed-tracks] successfully seeded {inserted} tracks.")
EOF
