#!/usr/bin/env bash
# lib/dispatch-ledger.sh — Dispatch Ledger (S2, Coordinator Control Plane v2)
#
# Exports:
#   new_dispatch_id                                          → stdout "d-<UTCcompact>-<6hex>"
#   dispatch_ledger_append <kind> <sid> <pane> <did> <json> → atomic flock append
#   dispatch_ledger_query [--sid X|--pane Y|--did Z|--tail N] → filtered lines
#
# Rules:
#   - Atomic appends via Python fcntl.flock (macOS + Linux compatible)
#   - dispatch_id format: d-<YYYYMMDDTHHMMSSz>-<6hex>; unique per call
#   - All reads are pure; no state mutation

HARNESS_DIR="${HARNESS_DIR:-${SOLAR_HARNESS_DIR:-$HOME/.solar/harness}}"
DISPATCH_LEDGER_FILE="$HARNESS_DIR/run/dispatch-ledger.jsonl"

# ── new_dispatch_id ───────────────────────────────────────────────────────────
new_dispatch_id() {
    python3 -c "
import datetime, secrets
ts = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
hex6 = secrets.token_hex(3)
print(f'd-{ts}-{hex6}')
" 2>/dev/null
}

# ── dispatch_ledger_append ────────────────────────────────────────────────────
# Usage: dispatch_ledger_append <kind> <sid> <pane> <dispatch_id> <extra_json>
# kind: attempted | acked | nacked | ack_timeout | quarantined
dispatch_ledger_append() {
    local kind="${1:?dispatch_ledger_append: kind required}"
    local sid="${2:?dispatch_ledger_append: sid required}"
    local pane="${3:-unknown}"
    local dispatch_id="${4:-$(new_dispatch_id)}"
    local extra_json="${5:-{}}"
    local ledger_file="$DISPATCH_LEDGER_FILE"

    python3 -c "
import json, datetime, fcntl, os, sys

ledger_file = sys.argv[1]
kind        = sys.argv[2]
sid         = sys.argv[3]
pane        = sys.argv[4]
dispatch_id = sys.argv[5]
try:
    extra = json.loads(sys.argv[6])
except Exception:
    extra = {'_raw': sys.argv[6]}

now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
record = {'ts': now, 'kind': kind, 'dispatch_id': dispatch_id, 'sid': sid, 'pane': pane}
record.update(extra)
line = json.dumps(record, ensure_ascii=False) + '\n'

os.makedirs(os.path.dirname(ledger_file), exist_ok=True)
with open(ledger_file, 'a') as f:
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(line)
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
" "$ledger_file" "$kind" "$sid" "$pane" "$dispatch_id" "$extra_json" 2>/dev/null || true
}

# ── dispatch_ledger_query ─────────────────────────────────────────────────────
# Usage: dispatch_ledger_query [--sid X] [--pane Y] [--did Z] [--tail N]
dispatch_ledger_query() {
    local filter_sid="" filter_pane="" filter_did="" tail_n=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --sid)  filter_sid="$2";  shift 2 ;;
            --pane) filter_pane="$2"; shift 2 ;;
            --did)  filter_did="$2";  shift 2 ;;
            --tail) tail_n="$2";      shift 2 ;;
            *) shift ;;
        esac
    done
    [[ -f "$DISPATCH_LEDGER_FILE" ]] || return 0
    python3 -c "
import json, sys
path, fs, fp, fd, tn = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
results = []
with open(path) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except Exception: continue
        if fs and d.get('sid')         != fs: continue
        if fp and d.get('pane')        != fp: continue
        if fd and d.get('dispatch_id') != fd: continue
        results.append(line)
if tn > 0: results = results[-tn:]
for r in results: print(r)
" "$DISPATCH_LEDGER_FILE" "$filter_sid" "$filter_pane" "$filter_did" "$tail_n" 2>/dev/null
}
