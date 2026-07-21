#!/bin/bash
# Solar Harness capability visibility prefixes.
#
# Human-facing pane visibility only. Prefixes go to stderr so stdout remains
# usable for JSON and shell pipelines unless callers explicitly merge streams.

solar_capability_color() {
  case "${1:-runtime}" in
    knowledge|qmd|mirage|obsidian) printf '\033[38;5;45m' ;;
    intent) printf '\033[38;5;208m' ;;
    atlas|repair) printf '\033[38;5;203m' ;;
    skills|skill) printf '\033[38;5;141m' ;;
    graph|dag|scheduler) printf '\033[38;5;82m' ;;
    autopilot|monitor) printf '\033[38;5;220m' ;;
    mineru|pdf) printf '\033[38;5;39m' ;;
    ruflo|runtime) printf '\033[38;5;117m' ;;
    model|routing) printf '\033[38;5;75m' ;;
    *) printf '\033[38;5;244m' ;;
  esac
}

solar_capability_prefix() {
  local module="${1:-runtime}"
  shift || true
  local detail="$*"
  [[ "${SOLAR_PREFIX_QUIET:-0}" == "1" ]] && return 0
  local color reset
  color="$(solar_capability_color "$module")"
  reset='\033[0m'
  if [[ -n "$detail" ]]; then
    printf '%b[harness-%s]%b %s\n' "$color" "$module" "$reset" "$detail" >&2
  else
    printf '%b[harness-%s]%b\n' "$color" "$module" "$reset" >&2
  fi
}

solar_capability_legend() {
  solar_capability_prefix "knowledge" "Mirage + QMD + Obsidian + Solar DB"
  solar_capability_prefix "intent" "intent engine / skill match"
  solar_capability_prefix "skills" "skill injection / readiness"
  solar_capability_prefix "graph" "DAG task_graph scheduler"
  solar_capability_prefix "atlas" "repair / failure recovery"
  solar_capability_prefix "autopilot" "deadlock and health monitor"
}
