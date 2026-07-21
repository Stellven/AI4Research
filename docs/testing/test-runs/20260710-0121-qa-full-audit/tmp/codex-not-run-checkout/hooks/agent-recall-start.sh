#!/bin/bash
# AgentRecall SessionStart Hook — v2
#
# On every new session, injects an instruction for the AI to call
# AgentRecall session_start via MCP. This handles both cold start
# (first time, no data) and warm start (subsequent sessions).
#
# If AgentRecall MCP is not available, silently skips.

INPUT=$(cat)

# Inject instruction — AI will call session_start if MCP tools are available
# This creates the data directory on first run and loads awareness on subsequent runs
cat << 'INSTRUCTION'
[AgentRecall] Auto-start: Call session_start({ project: "auto" }) to load compounding awareness, insights, and watch_for warnings from past sessions. If the tool is not available (MCP not connected), skip silently — do not mention this to the user.
INSTRUCTION

exit 0
