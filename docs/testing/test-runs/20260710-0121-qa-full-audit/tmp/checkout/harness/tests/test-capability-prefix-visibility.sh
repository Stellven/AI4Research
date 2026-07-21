#!/usr/bin/env bash
# Regression: human-facing Solar capability calls show visible harness prefixes.
set -euo pipefail

HARNESS="${HARNESS_DIR:-$HOME/.solar/harness}"
BIN="$HARNESS/solar-harness.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

bash -n "$BIN" "$HARNESS/pane-launcher.sh" "$HARNESS/lib/persona-config.sh" "$HARNESS/lib/capability-prefix.sh"

context_out="$(SOLAR_PREFIX_QUIET=0 "$BIN" context inject --query "太空数据中心" --format markdown --max-hits 1 --max-chars 200 2>&1 | sed -n '1,4p')"
grep -q '\[harness-knowledge\]' <<<"$context_out" || fail "context inject missing [harness-knowledge]"

intent_out="$(SOLAR_PREFIX_QUIET=0 "$BIN" intent match "太空数据中心" 2>&1 | sed -n '1,4p')"
grep -q '\[harness-intent\]' <<<"$intent_out" || fail "intent match missing [harness-intent]"

skills_out="$(SOLAR_PREFIX_QUIET=0 "$BIN" skills inventory 2>&1 | sed -n '1,4p')"
grep -q '\[harness-skills\]' <<<"$skills_out" || fail "skills inventory missing [harness-skills]"

policy_out="$(bash "$HARNESS/lib/persona-config.sh" --print-config pm >/dev/null; source "$HARNESS/lib/persona-config.sh"; inject_prefix_policy pm)"
grep -q '\[harness-knowledge\]' <<<"$policy_out" || fail "prefix policy missing knowledge rule"
grep -q 'Harness Modules Used' <<<"$policy_out" || fail "prefix policy missing final usage rule"

echo "PASS capability prefix visibility"
