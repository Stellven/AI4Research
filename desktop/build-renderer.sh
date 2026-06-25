#!/usr/bin/env bash
# Build the dashboard frontend (repo react-app) into this desktop app's renderer/.
# The bundle uses base=./ so it loads over file:// inside Electron, and api.ts reads
# the live API base from the ?api= query param the shell passes at load time.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Resolve the dashboard source repo-relative (works once the app lives at <repo>/desktop/);
# override with SOLAR_REACT_APP for out-of-tree builds. No personal paths.
REPO_ROOT="${SOLAR_REPO_ROOT:-$(cd "$APP_DIR/.." && pwd)}"
REACT_APP="${SOLAR_REACT_APP:-$REPO_ROOT/harness/status-server/react-app}"
OUT="$APP_DIR/renderer"

[ -d "$REACT_APP" ] || { echo "ERROR: react-app not found: $REACT_APP" >&2; exit 1; }

echo "[build-renderer] source : $REACT_APP"
echo "[build-renderer] output : $OUT"
cd "$REACT_APP"
[ -d node_modules ] || npm install

# base=./ -> relative asset URLs (file:// safe). emptyOutDir -> clean rebuild.
npx vite build --base=./ --outDir "$OUT" --emptyOutDir

[ -f "$OUT/index.html" ] || { echo "ERROR: build produced no index.html" >&2; exit 1; }
echo "[build-renderer] OK -> $(ls -1 "$OUT/assets" | wc -l) asset(s), index.html $(wc -c < "$OUT/index.html")b"
