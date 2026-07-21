#!/usr/bin/env bash
# lib/ack-watcher.sh — Ack Contract Watcher (S3, Coordinator Control Plane v2)
#
# Exports:
#   ack_watcher_bg <sid> <dispatch_id> [<timeout_sec>]  → launch background watcher (disown)
#   write_ack_file <sid> <dispatch_id> <role> <status> <exit_code> <message>
#                                                       → write sprints/<sid>.ack-<did>.json
#   read_ack_file  <sid> <dispatch_id>                  → JSON on stdout or empty
#
# Rules:
#   - Ack file: sprints/<sid>.ack-<dispatch_id>.json
#   - Schema: {dispatch_id, sid, role, status, exit_code, message, artifacts[], wrote_at}
#   - status enum: success | failed | in_progress | noop
#   - Watcher polls every 2s; on found → dispatch_ledger_append acked_by_ack
#   - On timeout → dispatch_ledger_append ack_timeout

_ACK_WATCHER_INTERVAL=2

# ── write_ack_file ────────────────────────────────────────────────────────────
write_ack_file() {
    local sid="${1:?write_ack_file: sid required}"
    local dispatch_id="${2:?write_ack_file: dispatch_id required}"
    local role="${3:-unknown}"
    local status="${4:-success}"
    local exit_code="${5:-0}"
    local message="${6:-}"
    local ack_file="${SPRINTS_DIR:-${HARNESS_DIR:-$HOME/.solar/harness}/sprints}/${sid}.ack-${dispatch_id}.json"

    python3 -c "
import json, datetime, os, sys
sid=sys.argv[1]; did=sys.argv[2]; role=sys.argv[3]
status=sys.argv[4]; ec=int(sys.argv[5]); msg=sys.argv[6]
path=sys.argv[7]
os.makedirs(os.path.dirname(path), exist_ok=True)
now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
ack = {'dispatch_id':did,'sid':sid,'role':role,'status':status,
       'exit_code':ec,'message':msg,'artifacts':[],'wrote_at':now}
with open(path,'w') as f: json.dump(ack, f, indent=2)
" "$sid" "$dispatch_id" "$role" "$status" "$exit_code" "$message" "$ack_file" 2>/dev/null
}

# ── read_ack_file ─────────────────────────────────────────────────────────────
read_ack_file() {
    local sid="${1:?read_ack_file: sid required}"
    local dispatch_id="${2:?read_ack_file: dispatch_id required}"
    local ack_file="${SPRINTS_DIR:-${HARNESS_DIR:-$HOME/.solar/harness}/sprints}/${sid}.ack-${dispatch_id}.json"
    [[ -f "$ack_file" ]] && cat "$ack_file" || echo ""
}

# ── ack_watcher_bg ────────────────────────────────────────────────────────────
# Launches a background process that watches for the ack file.
# Disowns the child so it survives even if the parent shell exits.
ack_watcher_bg() {
    local sid="${1:?ack_watcher_bg: sid required}"
    local dispatch_id="${2:?ack_watcher_bg: dispatch_id required}"
    local timeout_sec="${3:-300}"
    local harness_dir="${HARNESS_DIR:-$HOME/.solar/harness}"
    local sprints_dir="${SPRINTS_DIR:-${harness_dir}/sprints}"
    local ledger_file="${DISPATCH_LEDGER_FILE:-${harness_dir}/run/dispatch-ledger.jsonl}"

    # Launch watcher as a detached subprocess
    (
        ack_file="${sprints_dir}/${sid}.ack-${dispatch_id}.json"
        elapsed=0
        interval=${_ACK_WATCHER_INTERVAL}

        while (( elapsed < timeout_sec )); do
            if [[ -f "$ack_file" ]]; then
                # Read ack content and write ledger
                ack_status=$(python3 -c "
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    print(d.get('status','unknown'))
except: print('unknown')
" "$ack_file" 2>/dev/null || echo "unknown")
                python3 -c "
import json,datetime,fcntl,os,sys
lf=sys.argv[1]; sid=sys.argv[2]; did=sys.argv[3]
ack_file=sys.argv[4]; ack_status=sys.argv[5]
now=datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
record=json.dumps({'ts':now,'kind':'acked_by_ack_file','dispatch_id':did,
    'sid':sid,'ack_status':ack_status,'ack_file':ack_file})
os.makedirs(os.path.dirname(lf),exist_ok=True)
with open(lf,'a') as f:
    try:
        fcntl.flock(f,fcntl.LOCK_EX)
        f.write(record+'\n')
    finally:
        fcntl.flock(f,fcntl.LOCK_UN)
" "$ledger_file" "$sid" "$dispatch_id" "$ack_file" "$ack_status" 2>/dev/null
                exit 0
            fi
            sleep "$interval"
            elapsed=$(( elapsed + interval ))
        done

        # Timeout
        python3 -c "
import json,datetime,fcntl,os,sys
lf=sys.argv[1]; sid=sys.argv[2]; did=sys.argv[3]; timeout=sys.argv[4]
now=datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
record=json.dumps({'ts':now,'kind':'ack_timeout','dispatch_id':did,
    'sid':sid,'timeout_sec':int(timeout)})
os.makedirs(os.path.dirname(lf),exist_ok=True)
with open(lf,'a') as f:
    try:
        fcntl.flock(f,fcntl.LOCK_EX)
        f.write(record+'\n')
    finally:
        fcntl.flock(f,fcntl.LOCK_UN)
" "$ledger_file" "$sid" "$dispatch_id" "$timeout_sec" 2>/dev/null
    ) &
    disown "$!" 2>/dev/null || true
}
