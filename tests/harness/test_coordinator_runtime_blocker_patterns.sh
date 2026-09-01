#!/usr/bin/env bash
set -euo pipefail

ROOT="${HARNESS_DIR:-$HOME/.solar/harness}"
COORD="$ROOT/coordinator.sh"

grep -q 'How is Claude doing this session' "$COORD"
grep -Eq '1:\[\[:space:\]\]\*Bad.*2:\[\[:space:\]\]\*Fine.*3:\[\[:space:\]\]\*Good.*0:\[\[:space:\]\]\*Dismiss' "$COORD"
grep -q 'pane_has_runtime_blocker_snapshot' "$COORD"
grep -q 'pane_has_runtime_blocker_snapshot "$snapshot"' "$COORD"

sample='
● How is Claude doing this session?
  (optional)
  1: Bad    2: Fine    3: Good   0: Dismiss
  ${HOME}/.solar/harness/sprints/example.dispatch.md
  ⏵⏵ bypass permissions on
'

if ! printf '%s\n' "$sample" | grep -qiE "How is Claude doing this session|1:[[:space:]]*Bad[[:space:]]+2:[[:space:]]*Fine[[:space:]]+3:[[:space:]]*Good[[:space:]]+0:[[:space:]]*Dismiss"; then
  echo "survey prompt blocker regex did not match sample" >&2
  exit 1
fi

quota_sample='
❯ solar
  ⎿  You'\''ve hit your limit · resets 1am (America/Toronto)
───────────────────────────────────────
❯
  ⏵⏵ bypass permissions on
'

if ! printf '%s\n' "$quota_sample" | grep -qiE "You've hit your limit|hit your limit|rate[- ]limit|usage limit|/upgrade to increase your usage limit|resets .*\\(America/Toronto\\)"; then
  echo "quota blocker regex did not match sample" >&2
  exit 1
fi

code_host_sample='
⚠ Code Mode is unavailable because failed to spawn code-mode host /home/james/.local/bin/codex-code-mode-host:
host executable was not found.
'

if ! printf '%s\n' "$code_host_sample" | grep -qiE "Code Mode is unavailable|code-mode host is disabled|failed to spawn code-mode host|codex-code-mode-host.*(not found|No such file|Permission denied)"; then
  echo "code-mode host blocker regex did not match sample" >&2
  exit 1
fi

permission_sample='/home/james/.local/bin/codex-code-mode-host: Permission denied'
if ! printf '%s\n' "$permission_sample" | grep -qiE "Code Mode is unavailable|code-mode host is disabled|failed to spawn code-mode host|codex-code-mode-host.*(not found|No such file|Permission denied)"; then
  echo "code-mode host permission blocker regex did not match sample" >&2
  exit 1
fi

echo "ok coordinator runtime blocker patterns"
