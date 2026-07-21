#!/usr/bin/env bash
# ============================================================================
# Solar Product Platform — Restore from snapshot
#
# Wraps product_snapshot restore with safety guards.
# Always defaults to --dry-run first.
#
# Usage:
#   restore.sh --latest                   # dry-run restore from latest snapshot
#   restore.sh --latest --apply            # actually restore (requires confirm)
#   restore.sh --id SNAP_ID --dry-run      # dry-run specific snapshot
#   restore.sh --list                      # list available snapshots
# ============================================================================
set -euo pipefail

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
info()   { printf '[restore] %s\n' "$*" >&2; }

SOLAR_HOME="${SOLAR_HOME:-$HOME/.solar}"
HARNESS_DIR="${HARNESS_DIR:-$SOLAR_HOME/harness}"

SNAP_ID=""
LATEST=false
DRY_RUN=true
APPLY=false
LIST=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --latest)  LATEST=true;   shift ;;
    --id)      SNAP_ID="$2";  shift 2 ;;
    --dry-run) DRY_RUN=true;  shift ;;
    --apply)   APPLY=true;    DRY_RUN=false; shift ;;
    --list)    LIST=true;     shift ;;
    --help|-h)
      echo "Solar Product Platform — Restore from snapshot"
      echo ""
      echo "Usage:"
      echo "  restore.sh --latest                     dry-run from latest"
      echo "  restore.sh --latest --apply              actual restore"
      echo "  restore.sh --id SNAP_ID --dry-run       dry-run specific"
      echo "  restore.sh --list                        list snapshots"
      echo ""
      echo "WARNING: --apply overwrites files. Always verify with --dry-run first."
      exit 0 ;;
    *) red "Unknown option: $1"; exit 2 ;;
  esac
done

# ── list snapshots ─────────────────────────────────────────────────────────
if [[ "$LIST" == "true" ]]; then
  info "Available snapshots:"
  if [[ -d "$HARNESS_DIR/backups/product-snapshots" ]]; then
    ls -1 "$HARNESS_DIR/backups/product-snapshots" 2>/dev/null || echo "  (none)"
  else
    echo "  (no snapshots directory)"
  fi
  exit 0
fi

# ── validate input ─────────────────────────────────────────────────────────
if [[ "$LATEST" == "false" ]] && [[ -z "$SNAP_ID" ]]; then
  red "Must specify --latest or --id SNAP_ID. Use --list to see available snapshots."
  exit 1
fi

# ── find snapshot ──────────────────────────────────────────────────────────
SNAPSHOT_DIR=""
if [[ "$LATEST" == "true" ]]; then
  SNAPSHOT_DIR=$(ls -1dt "$HARNESS_DIR/backups/product-snapshots"/*/ 2>/dev/null | head -1 || echo "")
  if [[ -z "$SNAPSHOT_DIR" ]]; then
    red "No snapshots found in $HARNESS_DIR/backups/product-snapshots/"
    exit 1
  fi
else
  SNAPSHOT_DIR="$HARNESS_DIR/backups/product-snapshots/$SNAP_ID"
  if [[ ! -d "$SNAPSHOT_DIR" ]]; then
    red "Snapshot not found: $SNAP_ID"
    exit 1
  fi
fi

info "Snapshot: $SNAPSHOT_DIR"

# ── dry-run restore ───────────────────────────────────────────────────────
if [[ "$DRY_RUN" == "true" ]]; then
  info "DRY-RUN mode — no files will be modified"

  MANIFEST_FILE="$SNAPSHOT_DIR/manifest.json"
  if [[ -f "$MANIFEST_FILE" ]]; then
    echo ""
    echo "Files that would be restored:"
    echo "──────────────────────────────────────"
    python3 -c "
import json, sys, os
with open('$MANIFEST_FILE') as f:
    m = json.load(f)
files = m.get('files', [])
print(f'  Total files: {len(files)}')
print()
for f in files[:20]:
    print(f'  {f.get(\"path\",\"?\")}  ({f.get(\"size\",0)} bytes, {f.get(\"mode\",\"0644\")})')
if len(files) > 20:
    print(f'  ... and {len(files)-20} more files')
print()
secrets_exc = m.get('secrets_excluded', [])
if secrets_exc:
    print(f'Secrets excluded (paths only, no values):')
    for s in secrets_exc:
        print(f'  [excluded] {s}')
" 2>/dev/null
    echo "──────────────────────────────────────"
    echo ""
    info "To apply this restore: restore.sh --id $(basename "$SNAPSHOT_DIR") --apply"
  else
    yellow "No manifest.json found — cannot show restore plan"
  fi

  exit 0
fi

# ── apply restore ──────────────────────────────────────────────────────────
if [[ "$APPLY" == "true" ]]; then
  red "========================================================"
  red "  WARNING: This will overwrite files in $HARNESS_DIR"
  red "  Snapshot: $(basename "$SNAPSHOT_DIR")"
  red "========================================================"

  # Confirm non-interactive or prompt
  if [[ -t 0 ]]; then
    read -r -p "Type 'yes' to confirm restore: " confirm
    if [[ "$confirm" != "yes" ]]; then
      red "Restore aborted."
      exit 1
    fi
  fi

  # Use product_snapshot to restore
  if [[ -f "$HARNESS_DIR/lib/product_snapshot.py" ]]; then
    info "Running product_snapshot restore..."
    python3 "$HARNESS_DIR/lib/product_snapshot.py" restore \
      --id "$(basename "$SNAPSHOT_DIR")" \
      --target-dir "$HARNESS_DIR" \
      2>/dev/null && {
      green "Restore complete."
    } || {
      red "Restore FAILED. Check logs and try again."
      exit 1
    }
  else
    # Manual restore from tarball
    local tarball="$SNAPSHOT_DIR/$(python3 -c "import json; m=json.load(open('$MANIFEST_FILE')); print(m.get('tarball',''))" 2>/dev/null || echo "")"
    if [[ -z "$tarball" ]] || [[ ! -f "$SNAPSHOT_DIR/$tarball" ]]; then
      # Try to find tarball
      tarball=$(ls "$SNAPSHOT_DIR"/*.tar.* 2>/dev/null | head -1 || echo "")
    fi

    if [[ -n "$tarball" ]] && [[ -f "$tarball" ]]; then
      info "Extracting $tarball to $HARNESS_DIR..."
      tar xf "$tarball" -C "$HARNESS_DIR" --strip-components=0 2>/dev/null && {
        green "Restore complete (manual extraction)."
      } || {
        red "Restore FAILED during extraction."
        exit 1
      }
    else
      red "No tarball found in snapshot."
      exit 1
    fi
  fi

  info "Run 'installer/doctor.sh --json' to verify restore."
fi
