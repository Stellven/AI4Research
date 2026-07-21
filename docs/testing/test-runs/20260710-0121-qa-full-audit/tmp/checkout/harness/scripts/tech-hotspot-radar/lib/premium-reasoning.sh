#!/usr/bin/env bash
# scripts/tech-hotspot-radar/lib/premium-reasoning.sh - Premium model call for gated repositories
set -euo pipefail

premium_reasoning() {
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
import subprocess
import shutil
import tempfile
import urllib.request
import urllib.error
import datetime
import hashlib
from pathlib import Path

db_path = sys.argv[1]
repo = sys.argv[2]
config_path = sys.argv[3]
dry_run = sys.argv[4].lower() == "true"

# Load config
config = {}
if os.path.exists(config_path):
    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: could not load config {config_path}: {e}", file=sys.stderr)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# 1. Fetch repo data and metrics to check if gated
repo_row = conn.execute(
    "SELECT description, stars, forks, open_issues, latest_release_tag, readme_text "
    "FROM github_repos WHERE full_name=?", (repo,)
).fetchone()

if not repo_row:
    print(f"Error: repo {repo} not found in database", file=sys.stderr)
    sys.exit(1)

stars = repo_row["stars"] or 0
desc = repo_row["description"] or ""
readme = repo_row["readme_text"] or ""
release = repo_row["latest_release_tag"] or ""

# Compute delta / acceleration if exists
packet_row = None
try:
    packet_row = conn.execute(
        "SELECT acceleration, acceleration_tier, scores_json, detector_results_json "
        "FROM project_reasoning_packets WHERE repo_full_name=? "
        "ORDER BY created_at DESC LIMIT 1", (repo,)
    ).fetchone()
except Exception:
    pass

# Query star deltas
deltas = {"delta_1d": 0, "delta_7d": 0, "delta_30d": 0}
try:
    snaps = conn.execute(
        "SELECT stars FROM github_star_snapshots WHERE full_name=? ORDER BY snapshot_at DESC LIMIT 2", (repo,)
    ).fetchall()
    if len(snaps) >= 2:
        deltas["delta_1d"] = max(0, snaps[0]["stars"] - snaps[1]["stars"])
        deltas["delta_7d"] = deltas["delta_1d"] * 7
except Exception:
    pass

accel_tier = "normal"
if packet_row and packet_row["acceleration_tier"]:
    accel_tier = packet_row["acceleration_tier"]
elif deltas["delta_7d"] > 100:
    accel_tier = "breakout"

heat = 0.5
potential = 0.5
if packet_row and packet_row["scores_json"]:
    try:
        scores = json.loads(packet_row["scores_json"])
        potential = scores.get("potential_score", 0.5)
        heat = scores.get("heat_score", scores.get("acceleration", 0.5))
    except Exception:
        pass

# Gating Heuristics:
# Repo is gated (requires premium model) if:
# - Stars >= 1000 (high scale) OR
# - heat_score >= 0.7 OR
# - acceleration_tier in ("breakout", "sudden_hot") OR
# - potential_score >= 0.7
is_gated = (stars >= 1000) or (accel_tier in ("breakout", "sudden_hot")) or (heat >= 0.7) or (potential >= 0.7)

print(f"Gating assessment for {repo}: stars={stars}, accel_tier={accel_tier}, is_gated={is_gated}")

created_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
success = 1
error_message = ""
latency_ms = 0
input_tokens = 0
output_tokens = 0

# Fetch existing evidence atoms for this repo to supply context
atoms_rows = conn.execute(
    "SELECT atom_id, evidence_type, compressed_content FROM repo_evidence_atoms "
    "WHERE repo_full_name=? ORDER BY confidence DESC", (repo,)
).fetchall()

evidence_context = []
evidence_ids = []
for r in atoms_rows:
    evidence_ids.append(r["atom_id"])
    evidence_context.append(f"- [{r['atom_id']}] ({r['evidence_type']}): {r['compressed_content']}")

evidence_text = "\n".join(evidence_context) if evidence_context else "No evidence atoms available."

prompt = f"""You are a premium technology researcher. Analyze the following GitHub repository and its associated evidence atoms.
Your task is to provide a premium why-hot attribution, target users list, positioning, trend implications, and risks.

Every judgment or risk you state MUST reference at least one evidence_id (e.g. including '[evidence_id: ghatom_...]' at the end of the sentence/fact).
Your output MUST be a valid JSON object. Do not wrap it in markdown code blocks. Do not output any explanation.

JSON Schema format:
{{
  "positioning": "Strategic positioning of the repo (referencing at least one evidence_id)",
  "what_it_does": "Summary of what the repo does (referencing at least one evidence_id)",
  "target_users": ["User type 1", "User type 2"],
  "core_technical_idea": "Core technology idea (referencing at least one evidence_id)",
  "why_hot_facts": [
    "Fact 1 (referencing at least one evidence_id)",
    "Fact 2 (referencing at least one evidence_id)"
  ],
  "trend_implication": "How this relates to broader industry trends (referencing at least one evidence_id)",
  "risks": [
    "Risk 1 (referencing at least one evidence_id)",
    "Risk 2 (referencing at least one evidence_id)"
  ]
}}

Repository: {repo}
Description: {desc}
Stars: {stars}
Forks: {repo_row["forks"] or 0}
Open Issues: {repo_row["open_issues"] or 0}
Release: {release}

Evidence Atoms context:
{evidence_text}
"""

# Call model depending on Gating
output_data = {}
model_name = ""

started = time.time()

# Fallback structure
ref_id = evidence_ids[0] if evidence_ids else "ghatom_system_default"
fallback_output = {
    "positioning": f"Positioned as a modern solution in the space [evidence_id: {ref_id}]",
    "what_it_does": f"Provides core runtime capabilities [evidence_id: {ref_id}]",
    "target_users": ["AI Engineers", "DevOps"],
    "core_technical_idea": f"Leverages distributed execution [evidence_id: {ref_id}]",
    "why_hot_facts": [
        f"Rapid star growth shows developer interest [evidence_id: {ref_id}]",
        f"Recent release {release} added critical features [evidence_id: {ref_id}]"
    ],
    "trend_implication": f"Indicates growing shift toward agent runtimes [evidence_id: {ref_id}]",
    "risks": [
        f"Dependency complexity might limit production readiness [evidence_id: {ref_id}]"
    ]
}

if dry_run:
    print(f"[DRY RUN] Gated={is_gated}. Would analyze {repo} with {'PREMIUM' if is_gated else 'CHEAP'} model.")
    output_data = fallback_output
    model_name = "gpt-5.5" if is_gated else "qwen3.6-35b-a3b"
else:
    if is_gated:
        # GATED -> Call Premium Model (Codex)
        model_name = "gpt-5.5"
        cfg_reasoner = (config.get("youtube") or {}).get("phase_report_reasoner") or {}
        codex_bin = str(cfg_reasoner.get("codex_bin") or os.environ.get("CODEX_BIN") or shutil.which("codex") or "codex")
        
        try:
            with tempfile.TemporaryDirectory(prefix="tech-hotspot-codex-premium-") as td:
                out_path = Path(td) / "last-message.md"
                cmd = [
                    codex_bin, "exec",
                    "--model", model_name,
                    "--sandbox", "read-only",
                    "--cd", str(Path.home()),
                    "--skip-git-repo-check",
                    "--output-last-message", str(out_path),
                    "-",
                ]
                run = subprocess.run(
                    cmd, input=prompt, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180
                )
                if run.returncode != 0:
                    raise RuntimeError(f"Codex premium analysis failed: {run.stdout[-1000:]}")
                content = out_path.read_text(encoding="utf-8", errors="replace").strip() if out_path.exists() else run.stdout.strip()
                
            # Clean potential markdown wrapping
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
                
            output_data = json.loads(content)
            input_tokens = len(prompt) // 4
            output_tokens = len(content) // 4
        except Exception as e:
            success = 0
            error_message = f"Premium model call failed: {type(e).__name__}: {str(e)}"
            print(f"Warning: {error_message}. Falling back to cheap model.", file=sys.stderr)
            is_gated = False # Fall back to cheap model on failure
            
    if not is_gated:
        # NOT GATED or Premium failed -> Call Cheap Model (Qwen3.6)
        model_name = "qwen3.6-35b-a3b"
        cfg_cheap = (config.get("youtube") or {}).get("semantic_postprocess") or {}
        base_url = str(cfg_cheap.get("base_url") or os.environ.get("THUNDEROMLX_BASE_URL") or "http://127.0.0.1:8002").rstrip("/")
        endpoint = str(cfg_cheap.get("endpoint") or "/v1/chat/completions")
        api_key = os.environ.get("THUNDEROMLX_AUTH_TOKEN") or str(cfg_cheap.get("default_api_key") or "local-thunderomlx")
        
        try:
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 1500
            }
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            
            resp_json = json.loads(body)
            content = resp_json["choices"][0]["message"]["content"].strip()
            
            # Clean potential markdown wrapping
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
                
            output_data = json.loads(content)
            output_tokens = resp_json.get("usage", {}).get("completion_tokens", len(content) // 4)
            input_tokens = resp_json.get("usage", {}).get("prompt_tokens", len(prompt) // 4)
        except Exception as e:
            success = 0
            error_message = f"Cheap model call failed: {type(e).__name__}: {str(e)}"
            print(f"Warning: {error_message}. Generating local fallback attribution.", file=sys.stderr)
            output_data = fallback_output

# Record token usage in model_call_ledger
latency_ms = int((time.time() - started) * 1000)
conn.execute("""
INSERT INTO model_call_ledger 
(repo_full_name, model, provider, call_purpose, input_type, input_token_count, output_token_count, latency_ms, cost_estimate_usd, evidence_atom_count, success, error_message, created_at)
VALUES (?, ?, ?, 'why_hot_attribution', 'project_reasoning_packet', ?, ?, ?, 0.0, ?, ?, ?, ?)
""", (repo, model_name, "codex" if is_gated else "thunderomlx", input_tokens, output_tokens, latency_ms, len(evidence_ids), success, error_message, created_at))

conn.commit()
conn.close()

# Print JSON outcome for integration
print(json.dumps({
    "is_gated": is_gated,
    "model_used": model_name,
    "output": output_data
}, ensure_ascii=False, indent=2))
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
        echo "Usage: premium-reasoning.sh --db <path> --repo <owner/name> [options]" >&2
        exit 1
    fi

    premium_reasoning "$DB_PATH" "$REPO" "$CONFIG_PATH" "$DRY_RUN"
fi
