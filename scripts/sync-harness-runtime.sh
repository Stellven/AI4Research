#!/bin/bash
# Sync the repository-published Solar Harness into the local runtime directory.
#
# Contract:
#   Source of truth for distribution:  $SOLAR_DIR/harness  (normally ~/Solar/harness)
#   Runtime location on each machine:  $HOME/.solar/harness
#
# This script is safe to run repeatedly. It updates code and packaged artifacts
# without deleting local runtime state such as logs, run queues, state, venvs,
# vendor checkouts, or quarantine files.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOLAR_DIR="${SOLAR_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
SOLAR_HOME="${SOLAR_HOME:-$HOME/.solar}"
SRC_HARNESS="${SRC_HARNESS:-$SOLAR_DIR/harness}"
DEST_HARNESS="${DEST_HARNESS:-$SOLAR_HOME/harness}"
RUNTIME_RELEASE_VERSION="${SOLAR_RUNTIME_VERSION:-}"

if [ ! -d "$SRC_HARNESS" ]; then
    echo "missing harness source: $SRC_HARNESS" >&2
    exit 1
fi

mkdir -p "$DEST_HARNESS" "$SOLAR_HOME/bin"

rsync -a \
    --exclude '.DS_Store' \
    --exclude '*.log' \
    --exclude '*.pid' \
    --exclude '*.port' \
    --exclude '*.tmp' \
    --exclude '*~' \
    --exclude 'cache/***' \
    --exclude 'logs/***' \
    --exclude 'run/***' \
    --exclude 'state/***' \
    --exclude 'venvs/***' \
    --exclude 'vendor/***' \
    --exclude 'quarantine/***' \
    "$SRC_HARNESS/" "$DEST_HARNESS/"

if [ -z "$RUNTIME_RELEASE_VERSION" ] && [ -f "$SOLAR_DIR/VERSION" ]; then
    RUNTIME_RELEASE_VERSION="$(tr -d '[:space:]' < "$SOLAR_DIR/VERSION")"
fi
if [ -n "$RUNTIME_RELEASE_VERSION" ]; then
    printf '%s\n' "$RUNTIME_RELEASE_VERSION" > "$DEST_HARNESS/.desktop-runtime-version"
fi

chmod +x "$DEST_HARNESS/"*.sh 2>/dev/null || true
chmod +x "$DEST_HARNESS/lib/"*.sh 2>/dev/null || true
chmod +x "$DEST_HARNESS/tests/"*.sh 2>/dev/null || true
chmod +x "$DEST_HARNESS/tools/"*.sh 2>/dev/null || true
chmod +x "$DEST_HARNESS/tools/"*.py 2>/dev/null || true

if [ -f "$DEST_HARNESS/solar-harness.sh" ]; then
    ln -sf "$DEST_HARNESS/solar-harness.sh" "$SOLAR_HOME/bin/solar-harness"
fi

cat > "$DEST_HARNESS/.runtime-source" <<EOF
source=$SRC_HARNESS
destination=$DEST_HARNESS
synced_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
repo=$SOLAR_DIR
release_version=${RUNTIME_RELEASE_VERSION:-unknown}
EOF

echo "synced harness: $SRC_HARNESS -> $DEST_HARNESS"
if [ -L "$SOLAR_HOME/bin/solar-harness" ]; then
    echo "linked CLI: $SOLAR_HOME/bin/solar-harness"
fi
