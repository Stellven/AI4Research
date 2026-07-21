#!/usr/bin/env bash
# Bidirectionally sync compiled Knowledge content between this Mac and Mac mini.
#
# This is intentionally not the RAID/raw backup job. It syncs only the compiled
# vault layers and extracted markdown artifacts, and it never syncs Knowledge/_raw
# or machine-local indexes/databases.
set -euo pipefail

REMOTE="${REMOTE:-${SOLAR_MAC_MINI_REMOTE:-solar@example-host}}"
LOCAL_HOME="${LOCAL_HOME:-$HOME}"
LOCAL_VAULT="${LOCAL_VAULT:-$LOCAL_HOME/Knowledge}"
LOCAL_EXTRACTED="${LOCAL_EXTRACTED:-$LOCAL_HOME/.solar/extracted_knowledge}"
REMOTE_HOME="${REMOTE_HOME:-}"
DRY_RUN=0
CHECKSUM=1
LOCK_DIR="${LOCK_DIR:-$LOCAL_HOME/.solar/run/kb-bisync.lockdir}"

usage() {
  cat <<'EOF'
Usage:
  sync-knowledge-bidirectional-mac-mini.sh [--remote user@host] [--dry-run] [--no-checksum]

Env:
  REMOTE / SOLAR_MAC_MINI_REMOTE  default: solar@example-host
  LOCAL_VAULT                     default: ~/Knowledge
  LOCAL_EXTRACTED                 default: ~/.solar/extracted_knowledge
  REMOTE_HOME                     default: remote $HOME

Scope:
  Syncs compiled Knowledge layers and ~/.solar/extracted_knowledge markdown.
  Excludes Knowledge/_raw, nested PDF page dumps, sync conflict copies, .obsidian, .env, SQLite/QMD indexes, logs, and raw docs.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) REMOTE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-checksum) CHECKSUM=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

log() { printf '[kb-bisync] %s\n' "$*"; }
die() { printf '[kb-bisync] ERROR: %s\n' "$*" >&2; exit 1; }

require_dir() {
  [[ -d "$1" ]] || die "missing directory: $1"
}

ssh_remote() {
  ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$REMOTE" "$@"
}

require_dir "$LOCAL_VAULT"
require_dir "$LOCAL_EXTRACTED"
command -v rsync >/dev/null 2>&1 || die "rsync not found"

if ! mkdir -p "$(dirname "$LOCK_DIR")" || ! mkdir "$LOCK_DIR" 2>/dev/null; then
  if [[ -f "$LOCK_DIR/pid" ]]; then
    old_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
      log "another kb-bisync run is active pid=$old_pid; exiting"
      exit 0
    fi
  fi
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR" || die "cannot acquire lock: $LOCK_DIR"
fi
printf '%s\n' "$$" > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT

if [[ -z "$REMOTE_HOME" ]]; then
  REMOTE_HOME="$(ssh_remote 'printf "%s" "$HOME"')"
fi
[[ -n "$REMOTE_HOME" ]] || die "cannot resolve remote HOME"

REMOTE_VAULT="${REMOTE_VAULT:-$REMOTE_HOME/Knowledge}"
REMOTE_EXTRACTED="${REMOTE_EXTRACTED:-$REMOTE_HOME/.solar/extracted_knowledge}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_BACKUP="$LOCAL_HOME/.solar/backups/kb-bisync/$RUN_ID"
REMOTE_BACKUP="$REMOTE_HOME/.solar/backups/kb-bisync/$RUN_ID"

RSYNC_FLAGS=(-azhu --human-readable --itemize-changes --prune-empty-dirs)
VERIFY_FLAGS=(-azhu --dry-run --itemize-changes --prune-empty-dirs)
if [[ "$CHECKSUM" == "1" ]]; then
  RSYNC_FLAGS=(-azchu --human-readable --itemize-changes --prune-empty-dirs)
  VERIFY_FLAGS=(-azchu --dry-run --itemize-changes --prune-empty-dirs)
fi
if [[ "$DRY_RUN" == "1" ]]; then
  RSYNC_FLAGS+=(--dry-run)
fi

# Whitelist compiled vault layers. Top-level knowledge notes are included; raw
# source directories, Obsidian runtime state, secrets, indexes, and source docs
# are excluded.
VAULT_FILTER=(
  --exclude='/_raw/***'
  --exclude='/**/_raw/***'
  --exclude='/references/*/page-*.md'
  --exclude='/references/*/index.md'
  --exclude='*.conflict-*.md'
  --exclude='/.obsidian/***'
  --exclude='/.env'
  --exclude='/.manifest.json'
  --exclude='/.DS_Store'
  --exclude='/*.db'
  --exclude='/*.sqlite'
  --exclude='/*.sqlite3'
  --exclude='/*.pdf'
  --exclude='/*.doc'
  --exclude='/*.docx'
  --exclude='/*.ppt'
  --exclude='/*.pptx'
  --exclude='/*.zip'
  --exclude='/*.tar'
  --exclude='/*.tar.gz'
  --include='/analysis/***'
  --include='/concepts/***'
  --include='/entities/***'
  --include='/journal/***'
  --include='/projects/***'
  --include='/references/***'
  --include='/rules/***'
  --include='/skills/***'
  --include='/synthesis/***'
  --include='/*.md'
  --include='/*.base'
  --include='/*.canvas'
  --exclude='/*'
)

EXTRACTED_FILTER=(
  --include='*/'
  --include='*.md'
  --include='*.json'
  --exclude='.DS_Store'
  --exclude='*'
)

count_local_vault() {
  python3 - "$LOCAL_VAULT" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
dirs = {"analysis", "concepts", "entities", "journal", "projects", "references", "rules", "skills", "synthesis"}
count = size = 0
for p in root.rglob("*"):
    if not p.is_file():
        continue
    rel = p.relative_to(root)
    if rel.parts[0].startswith(".") or "_raw" in rel.parts:
        continue
    if rel.parts[0] in dirs or (len(rel.parts) == 1 and p.suffix in {".md", ".base", ".canvas"}):
        count += 1
        size += p.stat().st_size
print(f"{count} files {size} bytes")
PY
}

count_remote_vault() {
  ssh_remote "python3 - '$REMOTE_VAULT' <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
dirs = {'analysis', 'concepts', 'entities', 'journal', 'projects', 'references', 'rules', 'skills', 'synthesis'}
count = size = 0
for p in root.rglob('*'):
    if not p.is_file():
        continue
    rel = p.relative_to(root)
    if rel.parts[0].startswith('.') or '_raw' in rel.parts:
        continue
    if rel.parts[0] in dirs or (len(rel.parts) == 1 and p.suffix in {'.md', '.base', '.canvas'}):
        count += 1
        size += p.stat().st_size
print(f'{count} files {size} bytes')
PY"
}

change_count() {
  awk '/^[<>ch.*][^ ]/ {n++} END {print n+0}'
}

log "remote=$REMOTE remote_home=$REMOTE_HOME dry_run=$DRY_RUN checksum=$CHECKSUM"
log "local_vault_before=$(count_local_vault)"
log "remote_vault_before=$(count_remote_vault)"

if [[ "$DRY_RUN" == "0" ]]; then
  mkdir -p "$LOCAL_BACKUP/from-remote-vault" "$LOCAL_BACKUP/from-remote-extracted"
  ssh_remote "mkdir -p '$REMOTE_VAULT' '$REMOTE_EXTRACTED' '$REMOTE_BACKUP/from-local-vault' '$REMOTE_BACKUP/from-local-extracted'"
else
  ssh_remote "mkdir -p '$REMOTE_VAULT' '$REMOTE_EXTRACTED'"
fi

log "pull remote compiled vault -> local"
rsync "${RSYNC_FLAGS[@]}" --backup --backup-dir="$LOCAL_BACKUP/from-remote-vault" \
  "${VAULT_FILTER[@]}" "$REMOTE:$REMOTE_VAULT/" "$LOCAL_VAULT/"

log "push local compiled vault -> remote"
rsync "${RSYNC_FLAGS[@]}" --backup --backup-dir="$REMOTE_BACKUP/from-local-vault" \
  "${VAULT_FILTER[@]}" "$LOCAL_VAULT/" "$REMOTE:$REMOTE_VAULT/"

log "pull remote extracted_knowledge -> local"
rsync "${RSYNC_FLAGS[@]}" --backup --backup-dir="$LOCAL_BACKUP/from-remote-extracted" \
  "${EXTRACTED_FILTER[@]}" "$REMOTE:$REMOTE_EXTRACTED/" "$LOCAL_EXTRACTED/"

log "push local extracted_knowledge -> remote"
rsync "${RSYNC_FLAGS[@]}" --backup --backup-dir="$REMOTE_BACKUP/from-local-extracted" \
  "${EXTRACTED_FILTER[@]}" "$LOCAL_EXTRACTED/" "$REMOTE:$REMOTE_EXTRACTED/"

log "verify no pending vault transfers"
PULL_LEFT="$(rsync "${VERIFY_FLAGS[@]}" "${VAULT_FILTER[@]}" "$REMOTE:$REMOTE_VAULT/" "$LOCAL_VAULT/" | change_count)"
PUSH_LEFT="$(rsync "${VERIFY_FLAGS[@]}" "${VAULT_FILTER[@]}" "$LOCAL_VAULT/" "$REMOTE:$REMOTE_VAULT/" | change_count)"
EX_PULL_LEFT="$(rsync "${VERIFY_FLAGS[@]}" "${EXTRACTED_FILTER[@]}" "$REMOTE:$REMOTE_EXTRACTED/" "$LOCAL_EXTRACTED/" | change_count)"
EX_PUSH_LEFT="$(rsync "${VERIFY_FLAGS[@]}" "${EXTRACTED_FILTER[@]}" "$LOCAL_EXTRACTED/" "$REMOTE:$REMOTE_EXTRACTED/" | change_count)"

log "local_vault_after=$(count_local_vault)"
log "remote_vault_after=$(count_remote_vault)"

cat <<EOF
status=$([[ "$PULL_LEFT:$PUSH_LEFT:$EX_PULL_LEFT:$EX_PUSH_LEFT" == "0:0:0:0" ]] && echo ok || echo warn)
remote=$REMOTE
local_vault=$LOCAL_VAULT
remote_vault=$REMOTE_VAULT
local_extracted=$LOCAL_EXTRACTED
remote_extracted=$REMOTE_EXTRACTED
excluded=Knowledge/_raw,nested_pdf_page_dumps,sync_conflict_copies,.obsidian,.env,sqlite/qmd-db,raw-doc-extensions
pull_left=$PULL_LEFT
push_left=$PUSH_LEFT
extracted_pull_left=$EX_PULL_LEFT
extracted_push_left=$EX_PUSH_LEFT
local_backup=$LOCAL_BACKUP
remote_backup=$REMOTE_BACKUP
dry_run=$DRY_RUN
EOF
