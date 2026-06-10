#!/usr/bin/env bash
set -e

profile="${1:-minimal}"
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/solar-install.XXXXXX")"
home_dir="$sandbox/home"
doctor_json="$sandbox/doctor.json"
daemon_log="$sandbox/daemon.log"
dashboard_log="$sandbox/dashboard.log"
daemon_pid=""
dashboard_pid=""

case "$profile" in
    minimal)
        components="kernel,harness"
        core_gate=false
        ;;
    full-non-rust)
        components="kernel,core-runtime,harness,skills-md,codex-bridge"
        core_gate=true
        ;;
    *)
        echo "unknown smoke profile: $profile" >&2
        exit 2
        ;;
esac

# Daemon and dashboard are started as their own process groups (set -m):
# `bun run <script>` spawns the real server as a child process, so killing
# only the job-leader pid leaks a listener that can then serve a stale
# response to the next run's HTTP gate.
kill_group() {
    [ -n "$1" ] || return 0
    kill -- -"$1" >/dev/null 2>&1 || kill "$1" >/dev/null 2>&1 || true
    wait "$1" >/dev/null 2>&1 || true
}

cleanup() {
    kill_group "$dashboard_pid"
    dashboard_pid=""
    kill_group "$daemon_pid"
    daemon_pid=""
    rm -f /tmp/solar.sock
}
trap cleanup EXIT INT TERM

wait_for_file_socket() {
    path="$1"
    tries=0
    while [ "$tries" -lt 60 ]; do
        [ -S "$path" ] && return 0
        sleep 0.5
        tries=$((tries + 1))
    done
    return 1
}

wait_for_http() {
    url="$1"
    tries=0
    while [ "$tries" -lt 60 ]; do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.5
        tries=$((tries + 1))
    done
    return 1
}

assert_doctor_ok() {
    python3 - "$doctor_json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
if data.get("verdict") != "ok":
    raise SystemExit(f"doctor verdict is not ok: {data!r}")
PY
}

assert_db_schema() {
    SOLAR_DB="$home_dir/.solar/db/solar.db" python3 - <<'PY'
import os
import sqlite3

conn = sqlite3.connect(os.environ["SOLAR_DB"])
names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
for need in ("cortex_sources", "sys_favorites", "fts_unified_search"):
    if need not in names:
        raise SystemExit(f"installed db missing table: {need}")
conn.execute(
    "INSERT INTO fts_unified_search(doc_id,title,doc_type,content) "
    "VALUES('smoke','t','probe','smoke probe content')"
)
rows = list(
    conn.execute(
        "SELECT doc_id FROM fts_unified_search "
        "WHERE fts_unified_search MATCH 'probe'"
    )
)
if not rows:
    raise SystemExit("fts5 MATCH probe returned nothing")
conn.rollback()
print("db schema assertions passed")
PY
}

assert_no_bun_home_leak() {
    if [ -e "$home_dir/.bun" ]; then
        echo "bun wrote into the sandbox home outside SOLAR_HOME: $home_dir/.bun" >&2
        exit 1
    fi
}

assert_residue_empty() {
    residue="$sandbox/residue.txt"
    find "$home_dir" -mindepth 1 -print | sort > "$residue"
    if [ -s "$residue" ]; then
        echo "install residue remains:" >&2
        cat "$residue" >&2
        exit 1
    fi
}

mkdir -p "$home_dir"

echo "profile=$profile"
echo "sandbox=$sandbox"
echo "components=$components"

HOME="$home_dir" "$repo_dir/install.sh" \
    --yes \
    --components "$components" \
    --fake-keys \
    --skip-llm-cli

HOME="$home_dir" "$home_dir/.solar/bin/solar" doctor --json > "$doctor_json"
assert_doctor_ok
assert_db_schema
assert_no_bun_home_leak

HOME="$home_dir" "$repo_dir/install.sh" \
    --yes \
    --components "$components" \
    --fake-keys \
    --skip-llm-cli

sentinel_count="$(grep -c '<!-- BEGIN OPENSOLAR -->' "$home_dir/.claude/CLAUDE.md")"
if [ "$sentinel_count" != "1" ]; then
    echo "expected one sentinel block, found $sentinel_count" >&2
    exit 1
fi

if [ "$core_gate" = "true" ]; then
    # Preconditions: the gate must observe THIS run's servers, not a stale
    # listener leaked by an earlier run.
    if [ -e /tmp/solar.sock ]; then
        echo "stale /tmp/solar.sock present; kill the old daemon first" >&2
        exit 1
    fi
    if curl -fsS "http://127.0.0.1:3721/" >/dev/null 2>&1; then
        echo "port 3721 already serving; kill the stale dashboard first" >&2
        exit 1
    fi

    set -m
    HOME="$home_dir" SOLAR_HOME="$home_dir/.solar" "$home_dir/.solar/bin/solar-daemon" >"$daemon_log" 2>&1 &
    daemon_pid="$!"
    set +m

    if ! wait_for_file_socket /tmp/solar.sock; then
        echo "daemon did not create socket" >&2
        cat "$daemon_log" >&2 || true
        exit 1
    fi
    if ! kill -0 "$daemon_pid" >/dev/null 2>&1; then
        echo "daemon process exited early" >&2
        cat "$daemon_log" >&2 || true
        exit 1
    fi
    echo "daemon socket gate: ok"

    # Start the dashboard only after the daemon is up: both open the same
    # SQLite DB and the first opener's WAL conversion needs an exclusive
    # lock, so a concurrent cold start hits SQLITE_BUSY.
    set -m
    (cd "$home_dir/.solar" && HOME="$home_dir" exec bun run dashboard:web >"$dashboard_log" 2>&1) &
    dashboard_pid="$!"
    set +m

    if ! wait_for_http "http://127.0.0.1:3721/"; then
        echo "dashboard route did not return 200" >&2
        cat "$dashboard_log" >&2 || true
        exit 1
    fi
    if ! kill -0 "$dashboard_pid" >/dev/null 2>&1; then
        echo "dashboard process exited early" >&2
        cat "$dashboard_log" >&2 || true
        exit 1
    fi
    echo "dashboard http gate: ok"
    if [ -e "$home_dir/.solar/solar.db" ]; then
        echo "legacy DB path was created: $home_dir/.solar/solar.db" >&2
        exit 1
    fi
fi

cleanup

HOME="$home_dir" "$home_dir/.solar/bin/solar" uninstall --yes
assert_residue_empty

echo "smoke profile passed: $profile"
