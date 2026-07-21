#!/usr/bin/env bash
# scripts/tech-hotspot-radar/lib/evidence-extractor.sh - Extract evidence atoms from repositories
set -euo pipefail

extract_evidence() {
    local db_path="$1"
    local repo_full_name="$2"
    local config_path="$3"
    local dry_run="$4"

    python3 - <<'EOF' "$db_path" "$repo_full_name" "$config_path" "$dry_run"
import sqlite3
import sys
import os
import json
import time
import urllib.request
import urllib.error
import hashlib
import datetime

db_path = sys.argv[1]
repo = sys.argv[2]
config_path = sys.argv[3]
dry_run = sys.argv[4].lower() == "true"

# Load config if exists
config = {}
if os.path.exists(config_path):
    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: could not load config {config_path}: {e}", file=sys.stderr)

# Resolve model and endpoint
cfg = (config.get("youtube") or {}).get("semantic_postprocess") or {}
base_url = str(cfg.get("base_url") or os.environ.get("THUNDEROMLX_BASE_URL") or "http://127.0.0.1:8002").rstrip("/")
endpoint = str(cfg.get("endpoint") or "/v1/chat/completions")
model = str(cfg.get("model") or "qwen3.6-35b-a3b")
api_key = os.environ.get("THUNDEROMLX_AUTH_TOKEN") or str(cfg.get("default_api_key") or "local-thunderomlx")

# Connect to DB
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get repo details
row = conn.execute(
    "SELECT description, topics, language, license, stars, forks, open_issues, "
    "pushed_at, latest_release_tag, latest_release_at, readme_text, html_url "
    "FROM github_repos WHERE full_name=?", (repo,)
).fetchone()

if not row:
    print(f"Error: repo {repo} not found in database", file=sys.stderr)
    sys.exit(1)

readme = row["readme_text"] or ""
description = row["description"] or ""
topics = row["topics"] or ""
lang = row["language"] or ""
license_id = row["license"] or ""
stars = row["stars"] or 0
forks = row["forks"] or 0
pushed = row["pushed_at"] or ""
release_tag = row["latest_release_tag"] or ""
html_url = row["html_url"] or f"https://github.com/{repo}"

created_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

# Heuristic fallback generator
def generate_fallbacks(err_msg=""):
    atoms = []
    # 1. readme_claim
    readme_snippet = (description + " " + readme)[:600].strip()
    if not readme_snippet:
        readme_snippet = "No description or readme available."
    atoms.append({
        "evidence_type": "readme_claim",
        "compressed_content": f"Readme claim for {repo}: {readme_snippet}",
        "entities": [repo.split("/")[0], repo.split("/")[1]],
        "tags": [lang or "unknown", "fallback"],
        "confidence": 0.5,
        "technical_depth": 0.4,
        "novelty_score": 0.3
    })
    # 2. growth_fact
    atoms.append({
        "evidence_type": "growth_fact",
        "compressed_content": f"Growth fact for {repo}: stars={stars}, forks={forks}, pushed={pushed}.",
        "entities": [repo.split("/")[1]],
        "tags": ["growth", "fallback"],
        "confidence": 0.8,
        "technical_depth": 0.3,
        "novelty_score": 0.4
    })
    return atoms

# Model Prompt
prompt = f"""You are a specialized technical analysis model.
Analyze the following GitHub repository details and extract key evidence atoms.
Your output MUST be a valid JSON array of objects. Do not wrap the JSON in markdown code blocks (e.g. do NOT use ```json). Do not output any explanation.

Each evidence atom object in the array MUST contain exactly these 7 fields:
1. "evidence_type": must be one of: "readme_claim", "release_feature", "issue_signal", "pr_signal", "social_mention", "youtube_mention", "growth_fact".
2. "compressed_content": a concise summary of the claim or feature (max 1200 characters).
3. "entities": a JSON list of key technologies, frameworks, companies or libraries mentioned in the content.
4. "tags": a JSON list of string tags for classification.
5. "confidence": a float between 0.0 and 1.0.
6. "technical_depth": a float between 0.0 and 1.0.
7. "novelty_score": a float between 0.0 and 1.0.

Repository Details:
Full Name: {repo}
Description: {description}
Topics: {topics}
Language: {lang}
License: {license_id}
Stars: {stars}
Forks: {forks}
Latest Release: {release_tag}
Pushed At: {pushed}
README content (first 3000 chars):
{readme[:3000]}
"""

# Call model
started = time.time()
success = 1
error_message = ""
atoms_list = []

payload = {
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.1,
    "max_tokens": 1500
}

input_tokens = len(prompt) // 4
output_tokens = 0

if dry_run:
    print(f"[DRY RUN] Would call Qwen3.6 for {repo} to extract evidence atoms.")
    atoms_list = generate_fallbacks("Dry run mode")
else:
    try:
        req = urllib.request.Request(
            f"{base_url}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "Authorization": f"Bearer {api_key}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        
        resp_json = json.loads(body)
        content_text = resp_json["choices"][0]["message"]["content"].strip()
        
        # Clean potential markdown wrapping
        if content_text.startswith("```"):
            lines = content_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content_text = "\n".join(lines).strip()
            
        atoms_list = json.loads(content_text)
        if not isinstance(atoms_list, list):
            raise ValueError("Response is not a JSON list")
            
        output_tokens = resp_json.get("usage", {}).get("completion_tokens", len(content_text) // 4)
        input_tokens = resp_json.get("usage", {}).get("prompt_tokens", len(prompt) // 4)
        
    except Exception as e:
        success = 0
        error_message = f"{type(e).__name__}: {str(e)}"
        print(f"Warning: model call failed, falling back to heuristics: {error_message}", file=sys.stderr)
        atoms_list = generate_fallbacks(error_message)

# Record token usage in model_call_ledger
latency_ms = int((time.time() - started) * 1000)
conn.execute("""
INSERT INTO model_call_ledger 
(repo_full_name, model, provider, call_purpose, input_type, input_token_count, output_token_count, latency_ms, cost_estimate_usd, evidence_atom_count, success, error_message, created_at)
VALUES (?, ?, 'thunderomlx', 'evidence_compression', 'raw_readme_bypass', ?, ?, ?, 0.0, ?, ?, ?, ?)
""", (repo, model, input_tokens, output_tokens, latency_ms, len(atoms_list), success, error_message, created_at))

# Write extracted evidence atoms to database
inserted_count = 0
for atom in atoms_list:
    # Ensure all required fields exist and validate types
    evidence_type = atom.get("evidence_type", "readme_claim")
    if evidence_type not in ('readme_claim','release_feature','issue_signal','pr_signal','social_mention','youtube_mention','growth_fact'):
        evidence_type = "readme_claim"
        
    comp_content = str(atom.get("compressed_content", ""))[:1200]
    entities = list(atom.get("entities", []))
    tags = list(atom.get("tags", []))
    conf = float(atom.get("confidence", 0.5))
    td = float(atom.get("technical_depth", 0.5))
    ns = float(atom.get("novelty_score", 0.5))
    
    # Calculate unique atom_id
    raw_src_id = release_tag if (evidence_type == "release_feature" and release_tag) else html_url
    raw_src_type = "github_release" if (evidence_type == "release_feature" and release_tag) else "github_readme"
    
    # Python equivalent of github_repo_atom_id
    raw_id_str = f"{repo}\0{evidence_type}\0{raw_src_id}"
    atom_id = "ghatom_" + hashlib.sha256(raw_id_str.encode("utf-8")).hexdigest()[:24]
    
    if not dry_run:
        conn.execute("""
        INSERT OR REPLACE INTO repo_evidence_atoms
        (atom_id, repo_full_name, evidence_type, compressed_content, entities_json, tags_json,
         confidence, technical_depth, novelty_score, raw_source_type, raw_source_id, model_used, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            atom_id, repo, evidence_type, comp_content, json.dumps(entities, ensure_ascii=False),
            json.dumps(tags, ensure_ascii=False), conf, td, ns, raw_src_type, raw_src_id, model, created_at
        ))
        inserted_count += 1
    else:
        print(f"[DRY RUN] Would write evidence atom {atom_id}: type={evidence_type}, confidence={conf}")

conn.commit()
conn.close()
print(f"Extracted {len(atoms_list)} evidence atoms (inserted/updated {inserted_count} rows)")
EOF
}

# If run directly as a CLI command
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    DB_PATH=""
    REPO=""
    CONFIG_PATH=""
    DRY_RUN="false"

    while [[ $# -gt 0 ]]; do
      case $1 in
        --db) DB_PATH="$2"; shift 2 ;;
        --repo) REPO="$2"; shift 2 ;;
        --config) CONFIG_PATH="$2"; shift 2 ;;
        --dry-run) DRY_RUN="true"; shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
      esac
    done

    if [[ -z "$DB_PATH" || -z "$REPO" ]]; then
        echo "Usage: evidence-extractor.sh --db <path> --repo <owner/name> [options]" >&2
        exit 1
    fi

    extract_evidence "$DB_PATH" "$REPO" "$CONFIG_PATH" "$DRY_RUN"
fi
