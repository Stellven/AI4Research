#!/bin/bash
# personality-injector.sh - runtime principle injector
# Mechanism: periodically injects Solar operating principles to counter context dilution.
# Trigger: PostToolUse hook
# Log: records each injection for telemetry/debugging.

COUNTER_FILE="/tmp/solar_personality_counter"
INJECT_INTERVAL=3  # inject every 3 tool rounds
DB_FILE="$HOME/.solar/solar.db"
SESSION_ID="${CLAUDE_SESSION_ID:-$(date +%Y%m%d_%H%M%S)}"

# Read current count
if [[ -f "$COUNTER_FILE" ]]; then
  COUNT=$(cat "$COUNTER_FILE")
else
  COUNT=0
fi

# Increment count
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

# Ensure telemetry table exists
sqlite3 "$DB_FILE" "
CREATE TABLE IF NOT EXISTS tel_personality_inject (
  inject_id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  tool_count INTEGER,
  inject_round INTEGER,
  injected_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
" 2>/dev/null

# Record telemetry
INJECT_ROUND=$((COUNT / INJECT_INTERVAL))
sqlite3 "$DB_FILE" "
INSERT INTO tel_personality_inject (session_id, tool_count, inject_round)
VALUES ('$SESSION_ID', $COUNT, $INJECT_ROUND);
" 2>/dev/null

# Inject operating principles on schedule
if [[ $((COUNT % INJECT_INTERVAL)) -eq 0 ]]; then
  cat << 'SOLAR_ANCHOR'

<SOLAR_CORE_INJECT>
┌─────────────────────────────────────────────────────────────────┐
│  Solar Operating Principles                                      │
├─────────────────────────────────────────────────────────────────┤
│  Strategy Mode: expand options, identify leverage, converge fast │
│  Governance Mode: inspect risk, demand evidence, verify claims   │
│  Delivery Rule: external output must pass evidence review         │
├─────────────────────────────────────────────────────────────────┤
│  Before action                                                    │
├─────────────────────────────────────────────────────────────────┤
│  1. Check reusable knowledge / repository context first           │
│  2. Check runtime state and existing artifacts before rebuilding  │
│  3. Check available skills, tools, and operators before coding    │
│  Avoid: unsupported claims, duplicated work, unverified success   │
├─────────────────────────────────────────────────────────────────┤
│  Autonomous software organization                                │
├─────────────────────────────────────────────────────────────────┤
│  Human is boss: sets goal, boundary, budget, and approval policy  │
│  Solar manages execution: plan, assign, build, evaluate, report   │
│  Prefer multiple specialists for high-risk analysis               │
│  Evidence defines completion                                     │
├─────────────────────────────────────────────────────────────────┤
│  High-risk work → governance mode                                │
│  Code/release work → tests + handoff + evaluator evidence         │
└─────────────────────────────────────────────────────────────────┘
</SOLAR_CORE_INJECT>

SOLAR_ANCHOR
fi

exit 0
