#!/bin/bash
# AgentRecall PreCompact Hook
#
# Fires RIGHT BEFORE conversation compaction.
# Blocks the AI and tells it to save session state via AgentRecall
# session_end + remember, so insights survive across compaction.
#
# Compaction destroys detailed context. This hook ensures the AI
# saves the most important insights before they're lost.

STATE_DIR="$HOME/.agent-recall/hook_state"
mkdir -p "$STATE_DIR"

# Read JSON input from stdin
INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id','unknown'))" 2>/dev/null)

echo "[$(date '+%H:%M:%S')] AgentRecall PRE-COMPACT for session $SESSION_ID" >> "$STATE_DIR/hook.log"

# Always block — compaction = save everything to AgentRecall
cat << 'HOOKJSON'
{
  "decision": "block",
  "reason": "COMPACTION IMMINENT — AgentRecall save required. 1) Call session_end with a concise summary of this session: what was discussed, key decisions, and trajectory. 2) Include 1-3 reusable insights (NOT 'fixed a bug' — instead 'API returns null when session expires, always null-check auth responses'). 3) Call remember for any important correction or lesson learned. Allow compaction after saving."
}
HOOKJSON
