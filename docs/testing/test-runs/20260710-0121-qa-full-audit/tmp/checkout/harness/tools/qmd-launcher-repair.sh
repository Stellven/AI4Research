#!/usr/bin/env bash
set -euo pipefail

APPLY=0
JSON=0
QMD_BIN="${QMD_BIN:-}"
HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
[[ -f "$HARNESS_DIR/lib/qmd-resolver.sh" ]] && . "$HARNESS_DIR/lib/qmd-resolver.sh"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      APPLY=1
      shift
      ;;
    --check)
      APPLY=0
      shift
      ;;
    --json)
      JSON=1
      shift
      ;;
    --qmd-bin)
      QMD_BIN="${2:-}"
      shift 2
      ;;
    *)
      echo "Usage: $0 [--check|--apply] [--json] [--qmd-bin PATH]" >&2
      exit 64
      ;;
  esac
done

if [[ -z "$QMD_BIN" ]]; then
  QMD_BIN="$(solar_qmd_bin_or_empty 2>/dev/null || true)"
fi
solar_export_qmd_runtime_path "$QMD_BIN"

json_escape() {
  local s="${1:-}"
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}
  printf '%s' "$s"
}

emit() {
  local status="$1"
  local action="$2"
  local message="$3"
  local rc="${4:-0}"
  if [[ "$JSON" == "1" ]]; then
    printf '{"status":"%s","action":"%s","qmd_bin":"%s","launcher":"%s","message":"%s"}\n' \
      "$(json_escape "$status")" \
      "$(json_escape "$action")" \
      "$(json_escape "${QMD_BIN:-}")" \
      "$(json_escape "${LAUNCHER:-}")" \
      "$(json_escape "$message")"
  else
    printf '%s: %s\n' "$status" "$message"
  fi
  exit "$rc"
}

resolve_launcher() {
  local source="$1"
  local dir target
  while [[ -L "$source" ]]; do
    dir="$(cd -P "$(dirname "$source")" && pwd)"
    target="$(readlink "$source")"
    [[ "$target" != /* ]] && target="$dir/$target"
    source="$target"
  done
  cd -P "$(dirname "$source")" >/dev/null
  printf '%s/%s\n' "$(pwd)" "$(basename "$source")"
}

if [[ -z "$QMD_BIN" || ! -e "$QMD_BIN" ]]; then
  LAUNCHER=""
  emit "warn" "skipped" "qmd not found; install qmd/mineru-document-explorer before checking launcher ABI" 0
fi

LAUNCHER="$(resolve_launcher "$QMD_BIN")"
ENTRY_DIR="$(cd -P "$(dirname "$QMD_BIN")" && pwd)"
LINKED_NODE="$ENTRY_DIR/node"

status_output=""
set +e
status_output="$("$QMD_BIN" status 2>&1)"
status_rc=$?
set -e

abi_error=0
if printf '%s\n' "$status_output" | grep -Eiq 'NODE_MODULE_VERSION|ERR_DLOPEN_FAILED|better-sqlite3'; then
  abi_error=1
fi

if [[ ! -f "$LAUNCHER" ]]; then
  if [[ "$status_rc" == "0" ]]; then
    emit "ok" "none" "qmd status ok; launcher file is not directly patchable" 0
  fi
  emit "error" "none" "qmd status failed and launcher file is missing or not patchable" 1
fi

if grep -q 'linked_node="${entry_dir}/node"' "$LAUNCHER"; then
  if [[ "$status_rc" == "0" ]]; then
    emit "ok" "none" "qmd launcher already prefers co-located node; qmd status ok" 0
  fi
  emit "error" "none" "qmd launcher already patched but qmd status still fails" 1
fi

patchable=0
if head -1 "$LAUNCHER" | grep -q 'bash' && grep -q '^find_node() {' "$LAUNCHER"; then
  patchable=1
fi

path_node="$(command -v node 2>/dev/null || true)"
needs_patch=0
if [[ -x "$LINKED_NODE" && "$patchable" == "1" ]]; then
  linked_major="$("$LINKED_NODE" --version 2>/dev/null | sed 's/^v//' | cut -d. -f1 || true)"
  if [[ "${linked_major:-0}" =~ ^[0-9]+$ && "$linked_major" -ge 22 ]]; then
    if [[ "$abi_error" == "1" || "$path_node" != "$LINKED_NODE" ]]; then
      needs_patch=1
    fi
  fi
fi

if [[ "$needs_patch" != "1" ]]; then
  if [[ "$status_rc" == "0" ]]; then
    emit "ok" "none" "qmd status ok; launcher does not require co-located node repair" 0
  fi
  if [[ "$abi_error" == "1" ]]; then
    emit "error" "none" "qmd has native-module ABI error, but this launcher is not safely patchable" 1
  fi
  emit "error" "none" "qmd status failed; not a recognized launcher ABI issue" 1
fi

if [[ "$APPLY" != "1" ]]; then
  emit "warn" "repair_available" "qmd launcher should prefer $LINKED_NODE; run: solar-harness wiki qmd-repair --apply" 2
fi

ts="$(date -u +%Y%m%dT%H%M%SZ)"
backup="${LAUNCHER}.backup.${ts}"
tmp="${LAUNCHER}.tmp.${ts}"
cp "$LAUNCHER" "$backup"

if ! awk '
  /^# Find node - prefer PATH, fallback to known locations$/ {
    print "# Find node. Prefer the node installed beside the qmd launcher symlink so native"
    print "# modules such as better-sqlite3 use the same ABI they were built against."
    next
  }
  /^find_node\(\) \{/ && inserted == 0 {
    print
    print "  local entry_dir linked_node"
    print "  entry_dir=\"$(cd -P \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\""
    print "  linked_node=\"${entry_dir}/node\""
    print "  if [[ -x \"$linked_node\" ]]; then"
    print "    local linked_ver"
    print "    linked_ver=$(\"$linked_node\" --version 2>/dev/null | sed '\''s/^v//'\'' || echo \"0\")"
    print "    local linked_major=\"${linked_ver%%.*}\""
    print "    if [[ \"$linked_major\" -ge 22 ]]; then"
    print "      echo \"$linked_node\""
    print "      return 0"
    print "    fi"
    print "  fi"
    print ""
    inserted=1
    next
  }
  { print }
  END { if (inserted != 1) exit 42 }
' "$LAUNCHER" > "$tmp"; then
  rm -f "$tmp"
  emit "error" "failed" "failed to patch launcher; backup kept at $backup" 1
fi

chmod --reference="$LAUNCHER" "$tmp" 2>/dev/null || chmod +x "$tmp"
mv "$tmp" "$LAUNCHER"

if "$QMD_BIN" status >/dev/null 2>&1; then
  emit "ok" "patched" "qmd launcher repaired; backup: $backup" 0
fi

cp "$backup" "$LAUNCHER"
emit "error" "rolled_back" "patched launcher failed qmd status; restored backup: $backup" 1
