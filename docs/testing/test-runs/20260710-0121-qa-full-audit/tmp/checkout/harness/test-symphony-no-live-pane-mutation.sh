#!/usr/bin/env bash
# Test: verify no new .sh/.py files contain dangerous tmux commands targeting live sessions
set -eu

HARNESS_DIR="$HOME/.solar/harness"

echo "=== Test: No Live Pane Mutation ==="

# Files to scan
SCAN_FILES=(
  "$HARNESS_DIR/lib/symphony/runner.sh"
  "$HARNESS_DIR/lib/symphony/workspace-manager.sh"
  "$HARNESS_DIR/lib/symphony/scheduler.py"
  "$HARNESS_DIR/lib/symphony/issue-adapter.py"
  "$HARNESS_DIR/lib/symphony/workflow-loader.py"
)

# Dangerous patterns (tmux commands targeting solar-harness sessions)
DANGEROUS_PATTERNS=(
  "respawn-pane.*-k.*solar-harness"
  "kill-pane.*solar-harness"
  "kill-session.*solar-harness"
  "respawn-pane.*-k.*solar-harness-lab"
  "kill-pane.*solar-harness-lab"
  "kill-session.*solar-harness-lab"
  "send-keys.*solar-harness"
)

violations=0

for file in "${SCAN_FILES[@]}"; do
  [[ -f "$file" ]] || continue
  for pattern in "${DANGEROUS_PATTERNS[@]}"; do
    # grep for the pattern, excluding comment lines
    matches=$(grep -v '^\s*#' "$file" 2>/dev/null | grep -cE "$pattern" || true)
    if [[ "$matches" -gt 0 ]]; then
      echo "VIOLATION: $file matches '$pattern'"
      violations=$((violations + 1))
    fi
  done
done

if [[ $violations -eq 0 ]]; then
  echo "PASS: No live pane mutation commands found in symphony files"
  echo ""
  echo "=== No-live-pane-mutation test PASSED ==="
else
  echo "FAIL: $violations violations found"
  exit 1
fi
