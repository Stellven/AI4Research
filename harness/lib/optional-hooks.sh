#!/usr/bin/env bash

# Resolve optional Claude hooks without turning an intentionally minimal public
# install into repeated "No such file" errors. Namespaced Solar hooks take
# precedence; the legacy ~/.claude/hooks location remains compatible.
solar_optional_claude_hook_path() {
  local hook_name="$1"
  local claude_root candidate
  [[ -n "$hook_name" && "$hook_name" == "${hook_name##*/}" ]] || return 1
  claude_root="${CLAUDE_DIR:-${HOME:-}/.claude}"
  [[ -n "$claude_root" ]] || return 1
  for candidate in \
    "$claude_root/solar/hooks/$hook_name" \
    "$claude_root/hooks/$hook_name"; do
    if [[ -x "$candidate" && -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}


solar_run_optional_claude_hook() {
  local hook_name="$1"
  local hook_path
  shift || true
  hook_path="$(solar_optional_claude_hook_path "$hook_name")" || return 0
  bash "$hook_path" "$@"
}
