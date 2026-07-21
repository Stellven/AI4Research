#!/bin/bash
# Solar Skill Improver Auto-Runner
# SessionEnd hook: evaluates and improves low-scoring auto-generated skills
#
# Triggered when a session ends. Runs in background so it doesn't
# block session cleanup. Only processes skills in skills/auto/ directory.

set -u

# Consume stdin to prevent pipe issues
cat > /dev/null 2>&1 || true

BUN="$(which bun 2>/dev/null || true)"
if [[ -z "$BUN" ]]; then
    exit 0
fi

IMPROVER="$HOME/.claude/core/solar-farm/skill-improver.ts"
if [[ ! -f "$IMPROVER" ]]; then
    exit 0
fi

# Run silently in background, do not block session end
# Only evaluates auto-generated skills (skills/auto/)
# Skills scoring < 0.3 trigger improvement
"$BUN" run "$IMPROVER" auto-improve 2>/dev/null &

exit 0
