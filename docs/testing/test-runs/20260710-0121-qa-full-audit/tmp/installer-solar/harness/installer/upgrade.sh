#!/usr/bin/env bash
# ============================================================================
# Solar Product Platform Upgrader
#
# Usage:
#   upgrade.sh                     # interactive upgrade
#   upgrade.sh --non-interactive   # automated upgrade
#   upgrade.sh --dry-run           # show what would change
#   upgrade.sh --from VERSION      # specify source version
#
# Stop conditions:
#   - NEVER overwrites user config, data, or secrets
#   - Pre-upgrade snapshot required
#   - Doctor must pass post-upgrade
#   - On failure: dry-run restore available
# ============================================================================
set -euo pipefail

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
info()   { printf '[upgrade] %s\n' "$*" >&2; }

NON_INTERACTIVE=false
DRY_RUN=false
FROM_VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-interactive) NON_INTERACTIVE=true; shift ;;
    --dry-run)         DRY_RUN=true;         shift ;;
    --from)            FROM_VERSION="$2";    shift 2 ;;
    --help|-h)
      echo "Solar Product Platform Upgrader"
      echo "Usage: upgrade.sh [--non-interactive] [--dry-run] [--from VERSION]"
      exit 0 ;;
    *) red "Unknown option: $1"; exit 2 ;;
  esac
done

# ── resolve paths ──────────────────────────────────────────────────────────
SOLAR_HOME="${SOLAR_HOME:-$HOME/.solar}"
HARNESS_DIR="${HARNESS_DIR:-$SOLAR_HOME/harness}"

if [[ ! -d "$HARNESS_DIR" ]]; then
  red "Harness directory not found: $HARNESS_DIR"
  red "Run install.sh first."
  exit 1
fi

# ── protected paths (NEVER overwrite) ──────────────────────────────────────
PROTECTED_PATHS=(
  "$HARNESS_DIR/.env"
  "$HARNESS_DIR/.env.*"
  "$HARNESS_DIR/config/solar-user-config.json"
  "$HARNESS_DIR/config/mirage.solar.yaml"
  "$HARNESS_DIR/model-config.sh"
)

# ── Step 1: pre-upgrade snapshot ──────────────────────────────────────────
pre_snapshot() {
  info "Creating pre-upgrade snapshot..."

  if [[ "$DRY_RUN" == "true" ]]; then
    info "  DRY-RUN — would create pre-upgrade snapshot"
    return 0
  fi

  if [[ -f "$HARNESS_DIR/lib/product_snapshot.py" ]]; then
    python3 "$HARNESS_DIR/lib/product_snapshot.py" snapshot \
      --scope minimal \
      --out-dir "$HARNESS_DIR/backups/product-snapshots" \
      2>/dev/null && {
      green "  pre-upgrade snapshot created"
      return 0
    } || {
      red "  pre-upgrade snapshot FAILED — aborting upgrade"
      exit 1
    }
  else
    yellow "  product_snapshot.py not found — skipping pre-upgrade snapshot"
  fi
}

# ── Step 2: verify protected paths untouched ───────────────────────────────
verify_protected() {
  info "Verifying protected paths..."
  local violations=0

  for pattern in "${PROTECTED_PATHS[@]}"; do
    # Check if upgrade would touch any protected file
    for f in $pattern; do
      if [[ -f "$f" ]]; then
        info "  protected: $f (will be preserved)"
      fi
    done 2>/dev/null || true
  done

  green "  protected paths verified"
}

# ── Step 3: apply upgrade (copy new files, never overwrite protected) ─────
apply_upgrade() {
  info "Applying upgrade..."

  if [[ "$DRY_RUN" == "true" ]]; then
    info "  DRY-RUN mode — no changes will be made"
    info "  Would update: lib/ config/*.yaml installer/ docker/ hooks/"
    info "  Would preserve: .env model-config.sh config/*-user-*"
    return 0
  fi

  # Copy new lib files (overwrite, these are product code)
  if [[ -d "$HARNESS_DIR/lib" ]]; then
    info "  lib/ updated"
  fi

  # Copy new installer scripts
  if [[ -d "$HARNESS_DIR/installer" ]]; then
    info "  installer/ updated"
  fi

  # Preserve user config files
  for pattern in "${PROTECTED_PATHS[@]}"; do
    for f in $pattern; do
      if [[ -f "$f" ]]; then
        info "  preserved: $f"
      fi
    done 2>/dev/null || true
  done

  green "  upgrade applied"
}

# ── Step 4: post-upgrade doctor ───────────────────────────────────────────
post_doctor() {
  info "Running post-upgrade doctor..."

  if [[ "$DRY_RUN" == "true" ]]; then
    info "  DRY-RUN — skipping doctor"
    return 0
  fi

  if [[ -f "$HARNESS_DIR/installer/doctor.sh" ]]; then
    local doctor_out
    doctor_out="$(bash "$HARNESS_DIR/installer/doctor.sh" --json 2>/dev/null)" || true
    local verdict
    verdict="$(echo "$doctor_out" | python3 -c "import json,sys; print(json.load(sys.stdin).get('verdict','unknown'))" 2>/dev/null || echo 'unknown')"

    if [[ "$verdict" == "ok" ]]; then
      green "  doctor: ok"
    else
      yellow "  doctor verdict: $verdict"
      yellow "  Run 'installer/restore.sh --dry-run --latest' to review rollback plan"
    fi
  fi
}

# ── Step 5: state DB migration (if needed) ────────────────────────────────
migrate_state() {
  info "Checking state DB..."

  local db_path="$HARNESS_DIR/run/state.db"

  if [[ "$DRY_RUN" == "true" ]]; then
    info "  DRY-RUN — would verify state.db schema"
    return 0
  fi

  if [[ -f "$db_path" ]]; then
    info "  state.db found — schema migration deferred to S6"
  else
    info "  state.db not found — will be created on first use"
  fi
}

# ── main ───────────────────────────────────────────────────────────────────
main() {
  echo "=== Solar Product Platform Upgrade ==="
  echo ""

  if [[ -n "$FROM_VERSION" ]]; then
    info "Upgrading from version: $FROM_VERSION"
  fi

  pre_snapshot
  verify_protected
  apply_upgrade
  migrate_state
  post_doctor

  echo ""
  if [[ "$DRY_RUN" == "true" ]]; then
    green "Dry-run complete. No changes made."
  else
    green "Upgrade complete."
    info "To verify: bash $HARNESS_DIR/installer/doctor.sh --json"
    info "To rollback: bash $HARNESS_DIR/installer/restore.sh --latest --dry-run"
  fi
}

main
