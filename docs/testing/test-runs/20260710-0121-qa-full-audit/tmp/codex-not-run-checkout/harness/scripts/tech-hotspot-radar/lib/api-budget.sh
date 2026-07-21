#!/usr/bin/env bash
# lib/api-budget.sh - API Budget Management and Rate Limiting
set -euo pipefail

# Path to the budget JSON file
get_budget_file() {
    local db_path="$1"
    echo "${db_path}.budget.json"
}

# Initialize budget file if missing
budget_init() {
    local db_path="$1"
    local budget_file
    budget_file=$(get_budget_file "$db_path")

    if [[ ! -f "$budget_file" ]]; then
        # Default allocation: Tier 0: 2000, Tier 1: 1000, Tier 2: 500
        cat > "$budget_file" <<EOF
{
  "tier_0": {
    "limit": 2000,
    "remaining": 2000,
    "reset_at": 0
  },
  "tier_1": {
    "limit": 1000,
    "remaining": 1000,
    "reset_at": 0
  },
  "tier_2": {
    "limit": 500,
    "remaining": 500,
    "reset_at": 0
  }
}
EOF
    fi
}

# Check if a tier has remaining quota, reset if past reset_at
budget_check() {
    local db_path="$1"
    local tier="$2"
    local budget_file
    budget_file=$(get_budget_file "$db_path")

    budget_init "$db_path"

    python3 - <<EOF
import json
import time
import sys

with open("$budget_file", "r") as f:
    data = json.load(f)

key = f"tier_{tier}"
if key not in data:
    # Unknown tier, default allowed
    sys.exit(0)

info = data[key]
now = int(time.time())

# If past reset time, reset quota
if now >= info["reset_at"]:
    info["remaining"] = info["limit"]
    info["reset_at"] = now + 3600
    with open("$budget_file", "w") as f:
        json.dump(data, f, indent=2)

if info["remaining"] <= 0:
    print(f"[api-budget] Tier {tier} budget exhausted. Remaining: 0", file=sys.stderr)
    sys.exit(1)

sys.exit(0)
EOF
}

# Consume 1 request from budget
budget_consume() {
    local db_path="$1"
    local tier="$2"
    local budget_file
    budget_file=$(get_budget_file "$db_path")

    budget_init "$db_path"

    python3 - <<EOF
import json

with open("$budget_file", "r") as f:
    data = json.load(f)

key = f"tier_{tier}"
if key in data:
    data[key]["remaining"] = max(0, data[key]["remaining"] - 1)
    with open("$budget_file", "w") as f:
        json.dump(data, f, indent=2)
EOF
}

# Handle secondary rate limits / backoff
# Usage: handle_rate_limit <status_code> <response_body_file>
handle_rate_limit() {
    local status_code="$1"
    local response_file="$2"

    if [[ "$status_code" -eq 403 ]]; then
        local is_abuse=0
        if [[ -f "$response_file" ]]; then
            if grep -iq "abuse" "$response_file" || grep -iq "rate limit" "$response_file" || grep -iq "secondary" "$response_file"; then
                is_abuse=1
            fi
        fi

        if [[ "$is_abuse" -eq 1 ]]; then
            echo "[api-budget] Secondary rate limit or abuse detection triggered (403). Backing off for 60 seconds..." >&2
            sleep 60
            return 0
        fi
    fi
    return 1
}
