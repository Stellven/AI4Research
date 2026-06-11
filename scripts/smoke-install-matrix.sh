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

assert_config_rendered() {
    cfg="$home_dir/.solar/config.env"
    [ -f "$cfg" ] || { echo "config.env was not generated: $cfg" >&2; exit 1; }
    if grep -q '{{' "$cfg"; then
        echo "config.env has unresolved template vars:" >&2
        grep -n '{{' "$cfg" >&2
        exit 1
    fi
    grep -q "^SOLAR_HOME=$home_dir/.solar$" "$cfg" || {
        echo "config.env SOLAR_HOME not rendered to the sandbox path" >&2
        cat "$cfg" >&2
        exit 1
    }
    echo "config.env rendered: ok"
}

assert_settings_registered() {
    SETTINGS="$home_dir/.claude/settings.json" python3 - <<'PY'
import json
import os

path = os.environ["SETTINGS"]
if not os.path.isfile(path):
    raise SystemExit(f"settings.json was not created: {path}")
with open(path, encoding="utf-8") as f:
    data = json.load(f)
cmds = [
    h.get("command", "")
    for group in data.get("hooks", {}).get("UserPromptSubmit", [])
    for h in group.get("hooks", [])
]
if not any("/solar/hooks/intent-engine-hook.sh" in c for c in cmds):
    raise SystemExit(f"intent-engine-hook not registered in settings.json: {cmds!r}")
print("settings hook registration: ok")
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

assert_kernel_loadable() {
    # Proxy for the interactive kernel load: prove the generated kernel is
    # structurally loadable, so the manual `claude` check only has to confirm
    # Claude actually loads it (not discover it is broken).
    solar_md="$home_dir/.claude/solar/SOLAR.md"
    claude_md="$home_dir/.claude/CLAUDE.md"
    [ -s "$solar_md" ] || { echo "kernel: SOLAR.md missing or empty: $solar_md" >&2; exit 1; }
    if grep -q '{{' "$solar_md"; then
        echo "kernel: SOLAR.md has unresolved template vars:" >&2
        grep -n '{{' "$solar_md" >&2
        exit 1
    fi
    n_import="$(grep -cE '^@[^[:space:]]*solar/SOLAR\.md$' "$claude_md" 2>/dev/null || true)"
    if [ "$n_import" != "1" ]; then
        echo "kernel: expected exactly one managed import line in CLAUDE.md, found $n_import" >&2
        exit 1
    fi
    # No dangling @import inside SOLAR.md (Claude @imports start with @ + a path
    # char; the @Agent role mentions do not). Read from a file, not a pipe, so a
    # failure exits the script under set -e.
    grep -E '^[[:space:]]*@[~/.]' "$solar_md" > "$sandbox/kernel-imports.txt" 2>/dev/null || true
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        p="${line#*@}"; p="${p%%[[:space:]]*}"
        p="${p/#\~\//$home_dir/}"   # expand a leading ~/ to the sandbox home
        [ -e "$p" ] || { echo "kernel: SOLAR.md has a dangling @import: $line" >&2; exit 1; }
    done < "$sandbox/kernel-imports.txt"
    # No dangling agent refs: every base agent the kernel ships must be installed.
    while IFS= read -r a; do
        a="${a%%#*}"; a="$(printf '%s' "$a" | awk '{$1=$1; print}')"
        [ -n "$a" ] || continue
        [ -f "$home_dir/.claude/solar/agents/$a.md" ] \
            || { echo "kernel: base agent referenced but not installed: $a" >&2; exit 1; }
    done < "$repo_dir/kernel/base-agents.txt"
    echo "kernel loadable: ok (SOLAR.md non-empty, no {{, one import line, no dangling @/agent refs)"
}

assert_hooks_no_crash() {
    # (1) every event->hook binding in an installed component's hooks.json is
    # registered under that SAME event in settings.json; (2) each shipped hook
    # runs rc=0 on a benign JSON stdin (proves no-crash, NOT correctness). Runs
    # in its own isolated home (kernel hooks are profile-independent) and from a
    # non-repo cwd so session-end-save.sh skips its git checkpoint and hook side
    # effects never reach the main residue assertion.
    hc="$sandbox/hookcheck"
    mkdir -p "$hc"
    HOME="$hc" "$repo_dir/install.sh" --yes --components kernel,harness --fake-keys --skip-llm-cli >/dev/null
    REPO="$repo_dir" SETTINGS="$hc/.claude/settings.json" COMPONENTS="kernel,harness" python3 - <<'PY'
import json, os
repo = os.environ["REPO"]
comps = [c.strip() for c in os.environ["COMPONENTS"].split(",") if c.strip()]
expected = []
for c in comps:
    f = os.path.join(repo, "components.d", c, "hooks.json")
    if os.path.isfile(f):
        for evt, hooks in json.load(open(f)).items():
            for h in hooks:
                expected.append((evt, h))
settings = json.load(open(os.environ["SETTINGS"]))
actual = set()
for evt, groups in settings.get("hooks", {}).items():
    for g in groups:
        for hk in g.get("hooks", []):
            cmd = hk.get("command", "")
            if "/solar/hooks/" in cmd:
                actual.add((evt, cmd.split("/solar/hooks/")[-1].split()[0]))
missing = [f"{h} under {e}" for (e, h) in expected if (e, h) not in actual]
if missing:
    raise SystemExit("hooks not registered under the right event: " + ", ".join(missing))
print(f"hook registration: ok ({len(expected)} bindings match hooks.json)")
PY
    benign='{"hook_event_name":"PostToolUse","tool_name":"Read","tool_input":{"file_path":"/tmp/x"},"prompt":"hi","cwd":"'"$sandbox"'","transcript_path":"/tmp/none.jsonl"}'
    for h in "$hc/.claude/solar/hooks/"*.sh; do
        name="$(basename "$h")"
        [ "$name" = "hook-logger.sh" ] && continue
        rc=0
        ( cd "$sandbox" && printf '%s' "$benign" | HOME="$hc" SOLAR_HOME="$hc/.solar" bash "$h" >/dev/null 2>&1 ) || rc=$?
        if [ "$rc" != "0" ]; then
            echo "hook crashed (rc=$rc) on benign stdin: $name" >&2
            exit 1
        fi
    done
    echo "hook no-crash: ok (all shipped hooks rc=0 on benign stdin; no-crash, not correctness)"
}

assert_keep_data_contract() {
    # --keep-data must preserve ONLY db/ + config.env + .env and remove
    # everything else (code, venv, bin, node_modules, cache, receipt). Uses a
    # self-contained minimal install and pre-seeds node_modules/cache so the
    # core-runtime-residue removal is proven without a bun install here.
    kd="$sandbox/keepdata"
    mkdir -p "$kd"
    HOME="$kd" "$repo_dir/install.sh" --yes --components kernel,harness --fake-keys --skip-llm-cli >/dev/null
    sh="$kd/.solar"
    mkdir -p "$sh/node_modules/pkg" "$sh/cache/bun"
    HOME="$kd" "$sh/bin/solar" uninstall --yes --keep-data
    for keep in db config.env .env; do
        [ -e "$sh/$keep" ] || { echo "--keep-data dropped data it must preserve: $keep" >&2; exit 1; }
    done
    for gone in bin harness core codex-bridge mempalace venv node_modules cache install-receipt.json; do
        if [ -e "$sh/$gone" ]; then
            echo "--keep-data left an artifact it must remove: $gone" >&2
            ls -la "$sh" >&2
            exit 1
        fi
    done
    echo "--keep-data contract: ok (kept db+config; removed code/venv/bin/node_modules/cache/receipt)"
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
assert_config_rendered
assert_settings_registered
assert_kernel_loadable
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

# solar update — no-op round-trip. Completes the P3 exit criterion
# (doctor/update/uninstall round-trip green IN CI): update re-runs the installer
# from the receipt's source_dir + components and must leave a healthy install.
HOME="$home_dir" "$home_dir/.solar/bin/solar" update --fake-keys --skip-llm-cli --skip-py-deps >/dev/null
HOME="$home_dir" "$home_dir/.solar/bin/solar" doctor --json > "$doctor_json"
assert_doctor_ok
sentinel_count="$(grep -c '<!-- BEGIN OPENSOLAR -->' "$home_dir/.claude/CLAUDE.md")"
if [ "$sentinel_count" != "1" ]; then
    echo "expected one sentinel block after update, found $sentinel_count" >&2
    exit 1
fi
assert_no_bun_home_leak
echo "solar update round-trip: ok"

assert_hooks_no_crash
assert_keep_data_contract

HOME="$home_dir" "$home_dir/.solar/bin/solar" uninstall --yes
assert_residue_empty

echo "smoke profile passed: $profile"
