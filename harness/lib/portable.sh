#!/usr/bin/env bash
# portable.sh — small shell portability helpers shared by harness scripts.

[[ -n "${SOLAR_PORTABLE_SH_LOADED:-}" ]] && return 0
SOLAR_PORTABLE_SH_LOADED=1

resolve_bash4() {
  local candidates=(
    /opt/homebrew/bin/bash
    /usr/local/bin/bash
    "$(command -v bash 2>/dev/null)"
  )
  local b major
  for b in "${candidates[@]}"; do
    [[ -z "$b" || ! -x "$b" ]] && continue
    major=$("$b" -c 'echo ${BASH_VERSINFO[0]}' 2>/dev/null || echo 0)
    if [[ "$major" =~ ^[0-9]+$ && "$major" -ge 4 ]]; then
      echo "$b"
      return 0
    fi
  done
  return 1
}

solar_file_mtime() {
  local path="${1:-}" mtime
  [[ -n "$path" && -e "$path" ]] || { echo 0; return 1; }

  mtime=$(stat -c %Y "$path" 2>/dev/null)
  if [[ "$mtime" =~ ^[0-9]+$ ]]; then
    echo "$mtime"
    return 0
  fi

  mtime=$(stat -f %m "$path" 2>/dev/null)
  if [[ "$mtime" =~ ^[0-9]+$ ]]; then
    echo "$mtime"
    return 0
  fi

  echo 0
  return 1
}

solar_file_mtime_human() {
  local path="${1:-}" stamp
  [[ -n "$path" && -e "$path" ]] || { echo "N/A"; return 1; }

  stamp=$(stat -c '%y' "$path" 2>/dev/null)
  if [[ -n "$stamp" ]]; then
    stamp="${stamp%%.*}"
    echo "$stamp"
    return 0
  fi

  stamp=$(stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S' "$path" 2>/dev/null)
  if [[ -n "$stamp" ]]; then
    echo "$stamp"
    return 0
  fi

  echo "N/A"
  return 1
}

solar_parse_epoch() {
  local format="${1:-}" value="${2:-}" epoch
  [[ -n "$value" ]] || { echo 0; return 1; }

  epoch=$(date -d "$value" +%s 2>/dev/null)
  if [[ "$epoch" =~ ^[0-9]+$ ]]; then
    echo "$epoch"
    return 0
  fi

  if [[ -n "$format" ]]; then
    epoch=$(date -j -f "$format" "$value" +%s 2>/dev/null)
    if [[ "$epoch" =~ ^[0-9]+$ ]]; then
      echo "$epoch"
      return 0
    fi
  fi

  echo 0
  return 1
}

solar_base64_one_line() {
  base64 | tr -d '\n'
}
