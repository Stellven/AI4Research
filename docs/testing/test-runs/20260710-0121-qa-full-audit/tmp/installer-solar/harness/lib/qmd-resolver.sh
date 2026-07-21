#!/usr/bin/env bash
# Shared qmd binary resolver for interactive shells, launchd, and stripped PATH.

solar_resolve_qmd_bin() {
  local candidates=()
  local qmd_env="${QMD_BIN:-}"
  local qmd_path=""

  if [[ -n "$qmd_env" ]]; then
    candidates+=("$qmd_env")
  fi

  qmd_path="$(command -v qmd 2>/dev/null || true)"
  if [[ -n "$qmd_path" ]]; then
    candidates+=("$qmd_path")
  fi

  candidates+=(
    "$HOME/.npm-global/bin/qmd"
    "$HOME/n/bin/qmd"
    "/opt/homebrew/bin/qmd"
    "/usr/local/bin/qmd"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    printf '%s\n' "$candidate"
    return 0
  done
  return 1
}

solar_qmd_bin_or_empty() {
  solar_resolve_qmd_bin 2>/dev/null || true
}

solar_export_qmd_runtime_path() {
  local qmd_bin="${1:-}"
  local qmd_dir=""
  if [[ -n "$qmd_bin" ]]; then
    qmd_dir="$(cd -P "$(dirname "$qmd_bin")" 2>/dev/null && pwd || true)"
  fi
  local additions=(
    "$qmd_dir"
    "$HOME/n/bin"
    "$HOME/.npm-global/bin"
    "/opt/homebrew/bin"
    "/usr/local/bin"
  )
  local item idx
  for ((idx=${#additions[@]}-1; idx>=0; idx--)); do
    item="${additions[$idx]}"
    [[ -n "$item" && -d "$item" ]] || continue
    case ":$PATH:" in
      *":$item:"*) ;;
      *) PATH="$item:$PATH" ;;
    esac
  done
  export PATH
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:---print}" in
    --print)
      solar_resolve_qmd_bin
      ;;
    --check)
      solar_resolve_qmd_bin >/dev/null
      ;;
    *)
      echo "Usage: $0 [--print|--check]" >&2
      exit 64
      ;;
  esac
fi
