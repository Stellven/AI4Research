#!/usr/bin/env bash
# Idempotently ensure the local daemon + dashboard server are running so
# smokes that talk to the core-policy API (smoke-core-policy.ts) have a live
# backend. Restored per P6 corpus PKG-004: the smoke shipped referencing this
# script while the file was absent, so the release verification bundle could
# never pass as shipped.
#
# Uses the canonical package entrypoints (package.json: "daemon",
# "dashboard"); safe to rerun — already-serving services are left untouched.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

BASE="http://127.0.0.1:3721"
SOCK="/tmp/solar.sock"
RUN_DIR="${TMPDIR:-/tmp}/solar-background-services"
mkdir -p "$RUN_DIR"

api_up() {
    curl -fsS --connect-timeout 1 --max-time 3 \
        "$BASE/api/orchestrator/core-policy" >/dev/null 2>&1
}

if api_up; then
    echo "core-policy API already serving on $BASE"
    exit 0
fi

command -v bun >/dev/null 2>&1 || {
    echo "bun is required to start the background services" >&2
    exit 1
}

if [ ! -S "$SOCK" ]; then
    setsid bun run core/daemon/server.ts \
        > "$RUN_DIR/daemon.out.log" 2> "$RUN_DIR/daemon.err.log" < /dev/null &
    echo $! > "$RUN_DIR/daemon.pid"
    echo "started daemon (pid $(cat "$RUN_DIR/daemon.pid"))"
fi

setsid bun run core/dashboard/server.ts \
    > "$RUN_DIR/dashboard.out.log" 2> "$RUN_DIR/dashboard.err.log" < /dev/null &
echo $! > "$RUN_DIR/dashboard.pid"
echo "started dashboard server (pid $(cat "$RUN_DIR/dashboard.pid"))"

for _ in $(seq 1 40); do
    if api_up; then
        echo "core-policy API ready on $BASE"
        exit 0
    fi
    sleep 0.5
done

echo "core-policy API did not become ready on $BASE; logs under $RUN_DIR" >&2
exit 1
