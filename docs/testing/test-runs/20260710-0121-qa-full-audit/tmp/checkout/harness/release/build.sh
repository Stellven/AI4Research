#!/usr/bin/env bash
# ============================================================================
# Solar Product Platform — Release Builder
#
# Usage:
#   release/build.sh                       # build tarball from current tree
#   release/build.sh --version 1.2.0       # override version
#   release/build.sh --out /tmp/release    # custom output dir
#   release/build.sh --dry-run             # show what would be included
#
# Outputs:
#   release/artifacts/solar-harness-<version>.tar.gz
#   release/artifacts/solar-harness-<version>.sha256
#   release/artifacts/MANIFEST-<version>.json
# ============================================================================
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
VERSION_FILE="$HARNESS_DIR/VERSION"
ARTIFACTS_DIR="$HARNESS_DIR/release/artifacts"

red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*" >&2; }
info()  { printf '[build] %s\n' "$*" >&2; }

# ── parse args ─────────────────────────────────────────────────────────────
VERSION=""
OUT_DIR=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --out)     OUT_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) red "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  if [[ -f "$VERSION_FILE" ]]; then
    VERSION=$(tr -d '[:space:]' < "$VERSION_FILE")
  else
    red "No VERSION file at $VERSION_FILE and --version not set"; exit 1
  fi
fi

[[ -z "$OUT_DIR" ]] && OUT_DIR="$ARTIFACTS_DIR"

TARBALL_NAME="solar-harness-${VERSION}.tar.gz"
TARBALL_PATH="$OUT_DIR/$TARBALL_NAME"
CHECKSUM_PATH="$OUT_DIR/solar-harness-${VERSION}.sha256"
MANIFEST_PATH="$OUT_DIR/MANIFEST-${VERSION}.json"

TAR_EXCLUDES=(
  --exclude=".git"
  --exclude="__pycache__"
  --exclude="*.pyc"
  --exclude="venvs"
  --exclude="vendor"
  --exclude="release/artifacts"
  --exclude="run"
  --exclude="backups"
  --exclude="events"
  --exclude="logs"
  --exclude="sessions"
  --exclude="reports"
  --exclude="_extracted_knowledge_fallback"
  --exclude=".pytest_cache"
  --exclude="*.db"
  --exclude="*.sqlite"
  --exclude="*.sqlite3"
  --exclude="*.pid"
  --exclude="*.lock"
  --exclude="*.tmp"
)

# ── dry-run ────────────────────────────────────────────────────────────────
if [[ $DRY_RUN -eq 1 ]]; then
  info "DRY RUN — would create: $TARBALL_PATH"
  info "Exclusions: .git/ __pycache__/ venvs/ vendor/ *.pyc release/artifacts/ run/ backups/ events/ logs/ sessions/ reports/ _extracted_knowledge_fallback/ .pytest_cache/ *.db *.sqlite *.pid *.lock *.tmp"
  cd "$HARNESS_DIR"
  tar --list "${TAR_EXCLUDES[@]}" -czf /dev/null . 2>/dev/null | head -40
  info "Dry run complete."
  exit 0
fi

# ── build ──────────────────────────────────────────────────────────────────
mkdir -p "$OUT_DIR"
cd "$HARNESS_DIR"

info "Building solar-harness v${VERSION} …"

tar "${TAR_EXCLUDES[@]}" -czf "$TARBALL_PATH" .

info "Tarball: $TARBALL_PATH"

# ── checksum ───────────────────────────────────────────────────────────────
if command -v sha256sum &>/dev/null; then
  sha256sum "$TARBALL_PATH" > "$CHECKSUM_PATH"
elif command -v shasum &>/dev/null; then
  shasum -a 256 "$TARBALL_PATH" > "$CHECKSUM_PATH"
else
  red "No sha256sum or shasum found"; exit 1
fi

CHECKSUM=$(awk '{print $1}' "$CHECKSUM_PATH")
info "SHA256: $CHECKSUM"

# ── manifest ───────────────────────────────────────────────────────────────
FILE_COUNT=$(tar -tzf "$TARBALL_PATH" | wc -l | tr -d ' ')
TARBALL_BYTES=$(wc -c < "$TARBALL_PATH" | tr -d ' ')
BUILD_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

python3 - <<PYEOF
import json
manifest = {
    "version": "$VERSION",
    "build_at": "$BUILD_AT",
    "tarball": "$TARBALL_NAME",
    "sha256": "$CHECKSUM",
    "size_bytes": int("$TARBALL_BYTES"),
    "file_count": int("$FILE_COUNT"),
    "slices_included": ["S0","S1","S2","S3","S4","S5","S6","S7"],
    "adrs": ["ADR-001","ADR-002","ADR-003","ADR-004","ADR-005"],
    "changelog": "release/CHANGELOG.md",
    "upgrade_guide": "docs/upgrade-guide.md",
    "rollback_guide": "docs/rollback-guide.md",
}
with open("$MANIFEST_PATH", "w") as f:
    json.dump(manifest, f, indent=2)
print(json.dumps(manifest, indent=2))
PYEOF

green "Build complete: solar-harness v${VERSION}"
green "  tarball : $TARBALL_PATH"
green "  checksum: $CHECKSUM_PATH"
green "  manifest: $MANIFEST_PATH"
