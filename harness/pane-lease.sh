#!/usr/bin/env bash
# lib/pane-lease.sh — Pane Ownership Lease (S3, Coordinator Control Plane v2)
#
# Exports:
#   acquire_pane_lease <pane> <sid> <dispatch_id> [<ttl_sec>]  → exit 0=acquired / 1=busy
#   release_pane_lease <pane> <dispatch_id>                    → exit 0=released / 1=mismatch
#   check_pane_lease   <pane>                                  → JSON on stdout or empty
#   reap_expired_leases                                        → removes expired leases, logs count
#
# Rules:
#   - Lease file: run/pane-leases/<pane_safe>.json
#   - Atomic write via Python flock + tmp + rename
#   - release only succeeds when dispatch_id in file matches argument
#   - TTL default 600s; reaper called by coordinator main loop or doctor

HARNESS_DIR="${HARNESS_DIR:-${SOLAR_HARNESS_DIR:-$HOME/.solar/harness}}"
_PANE_LEASE_DIR="${HARNESS_DIR}/run/pane-leases"

_pane_safe()  { echo "${1//:/_}" | tr '.' '_'; }
_lease_file() { echo "${_PANE_LEASE_DIR}/$(_pane_safe "$1").json"; }

# ── acquire_pane_lease ────────────────────────────────────────────────────────
acquire_pane_lease() {
    local pane="${1:?acquire_pane_lease: pane required}"
    local sid="${2:?acquire_pane_lease: sid required}"
    local dispatch_id="${3:?acquire_pane_lease: dispatch_id required}"
    local ttl_sec="${4:-600}"
    local lf
    lf=$(_lease_file "$pane")

    python3 -c "
import json, datetime, fcntl, os, sys

pane        = sys.argv[1]
sid         = sys.argv[2]
dispatch_id = sys.argv[3]
ttl_sec     = int(sys.argv[4])
lf          = sys.argv[5]

os.makedirs(os.path.dirname(lf), exist_ok=True)
lock_path = lf + '.lock'
now = datetime.datetime.utcnow()
now_str = now.strftime('%Y-%m-%dT%H:%M:%SZ')

with open(lock_path, 'a') as lockf:
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX)

        # Check existing lease
        if os.path.exists(lf):
            try:
                existing = json.load(open(lf))
                expires_at = existing.get('expires_at', '')
                if expires_at and expires_at > now_str:
                    # Still valid lease held by another dispatch
                    print(json.dumps({'acquired': False,
                                      'reason': 'pane_leased',
                                      'held_by': existing.get('dispatch_id'),
                                      'held_sid': existing.get('sid') or existing.get('sprint_id'),
                                      'expires_at': expires_at}))
                    sys.exit(1)
            except Exception:
                pass  # Corrupt lease file: overwrite it

        expires_at = (now + datetime.timedelta(seconds=ttl_sec)).strftime('%Y-%m-%dT%H:%M:%SZ')
        lease = {
            'pane': pane, 'sid': sid, 'dispatch_id': dispatch_id,
            'acquired_at': now_str, 'expires_at': expires_at, 'ttl_sec': ttl_sec,
        }
        tmp = lf + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(lease, f)
        os.replace(tmp, lf)
        print(json.dumps({'acquired': True, 'dispatch_id': dispatch_id, 'expires_at': expires_at}))
    finally:
        fcntl.flock(lockf, fcntl.LOCK_UN)
" "$pane" "$sid" "$dispatch_id" "$ttl_sec" "$lf" 2>/dev/null
    return $?
}

# ── release_pane_lease ────────────────────────────────────────────────────────
release_pane_lease() {
    local pane="${1:?release_pane_lease: pane required}"
    local dispatch_id="${2:?release_pane_lease: dispatch_id required}"
    local release_reason="${3:-explicit_release}"
    local lf
    lf=$(_lease_file "$pane")

    [[ -f "$lf" ]] || return 0  # already gone

    python3 -c "
import json, fcntl, os, sys

pane           = sys.argv[1]
dispatch_id    = sys.argv[2]
release_reason = sys.argv[3]
lf             = sys.argv[4]

if not os.path.exists(lf):
    sys.exit(0)

lock_path = lf + '.lock'
with open(lock_path, 'a') as lockf:
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        existing = json.load(open(lf))
        held_by = existing.get('dispatch_id', '')
        if held_by != dispatch_id:
            print(json.dumps({'released': False, 'reason': 'dispatch_id_mismatch',
                               'held_by': held_by, 'requested': dispatch_id}))
            sys.exit(1)
        os.remove(lf)
        print(json.dumps({'released': True, 'release_reason': release_reason}))
    except FileNotFoundError:
        sys.exit(0)  # already released
    finally:
        fcntl.flock(lockf, fcntl.LOCK_UN)
" "$pane" "$dispatch_id" "$release_reason" "$lf" 2>/dev/null
    return $?
}

# ── check_pane_lease ──────────────────────────────────────────────────────────
check_pane_lease() {
    local pane="${1:?check_pane_lease: pane required}"
    local lf
    lf=$(_lease_file "$pane")
    [[ -f "$lf" ]] && cat "$lf" || echo ""
}

# ── reap_expired_leases ───────────────────────────────────────────────────────
reap_expired_leases() {
    [[ -d "$_PANE_LEASE_DIR" ]] || return 0
    python3 -c "
import json, datetime, fcntl, os, sys

lease_dir = sys.argv[1]
now_str   = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
reaped = 0

for fname in os.listdir(lease_dir):
    if not fname.endswith('.json') or fname.endswith('.lock.json'):
        continue
    path = os.path.join(lease_dir, fname)
    try:
        d = json.load(open(path))
        if d.get('expires_at', 'z') <= now_str:
            os.remove(path)
            reaped += 1
    except Exception:
        pass

for fname in os.listdir(lease_dir):
    if not fname.endswith('.json.lock'):
        continue
    lock_path = os.path.join(lease_dir, fname)
    lease_path = lock_path[:-5]
    if os.path.exists(lease_path):
        continue
    try:
        with open(lock_path, 'a') as lockf:
            try:
                fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            try:
                os.remove(lock_path)
                reaped += 1
            except FileNotFoundError:
                pass
            finally:
                try:
                    fcntl.flock(lockf, fcntl.LOCK_UN)
                except Exception:
                    pass
    except Exception:
        pass

print(reaped)
" "$_PANE_LEASE_DIR" 2>/dev/null || echo 0
}
