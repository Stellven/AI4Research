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

cleanup() {
    if [ -n "$dashboard_pid" ]; then
        kill "$dashboard_pid" >/dev/null 2>&1 || true
        wait "$dashboard_pid" >/dev/null 2>&1 || true
    fi
    if [ -n "$daemon_pid" ]; then
        kill "$daemon_pid" >/dev/null 2>&1 || true
        wait "$daemon_pid" >/dev/null 2>&1 || true
    fi
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
    HOME="$home_dir" SOLAR_HOME="$home_dir/.solar" "$home_dir/.solar/bin/solar-daemon" >"$daemon_log" 2>&1 &
    daemon_pid="$!"
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

    (cd "$home_dir/.solar" && HOME="$home_dir" bun run dashboard:web >"$dashboard_log" 2>&1) &
    dashboard_pid="$!"
    if ! wait_for_http "http://127.0.0.1:3721/"; then
        echo "dashboard route did not return 200" >&2
        cat "$dashboard_log" >&2 || true
        exit 1
    fi
    if [ -e "$home_dir/.solar/solar.db" ]; then
        echo "legacy DB path was created: $home_dir/.solar/solar.db" >&2
        exit 1
    fi
fi

cleanup
daemon_pid=""
dashboard_pid=""

HOME="$home_dir" "$home_dir/.solar/bin/solar" uninstall --yes
assert_residue_empty

echo "smoke profile passed: $profile"
