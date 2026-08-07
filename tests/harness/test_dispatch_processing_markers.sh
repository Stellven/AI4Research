#!/usr/bin/env bash
set -euo pipefail
ROOT="${HARNESS_DIR:-${HOME}/.solar/harness}"
regex=$(grep -E "grep -qE 'Crafting\|Cogitating" "$ROOT/coordinator.sh" | sed -E "s/.*grep -qE '([^']+)'.*/\1/" | tail -1)
for marker in Ideating Musing Orbiting Reticulating Gusting 'What should Claude do' '按 dispatch' '✢'; do
  if ! printf '%s\n' "$marker" | grep -qE "$regex"; then
    echo "FAIL: missing processing marker $marker" >&2
    exit 1
  fi
done

grep -q 'tail -120' "$ROOT/coordinator.sh" || {
  echo "FAIL: dispatch verifier must use a wide capture window for wrapped paths" >&2
  exit 1
}
grep -q 'grep -qF "$sid"' "$ROOT/coordinator.sh" || {
  echo "FAIL: dispatch verifier must accept sid when dispatch basename wraps" >&2
  exit 1
}
grep -q 'grep -qF "dispatch.md"' "$ROOT/coordinator.sh" || {
  echo "FAIL: dispatch verifier must accept generic dispatch.md reference" >&2
  exit 1
}

echo "PASS: dispatch processing markers and wrapped-path fallbacks are covered"
